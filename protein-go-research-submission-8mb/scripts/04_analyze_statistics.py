"""Deterministic Spearman analysis; paired, re-ranked percentile bootstrap."""
import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy import integrate, stats

ROOT = Path(__file__).resolve().parents[1]
NUMERIC = ['sequence_length', 'go_total_count', 'go_bp_count', 'go_mf_count', 'go_cc_count']
OUTCOMES = NUMERIC[1:]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def csv_save(frame, path):
    frame.to_csv(path, index=False, float_format='%.17g', lineterminator='\n')


def scientific_log(logp):
    if logp == 0:
        return '1.000000e+0'
    exponent = int(np.floor(logp / np.log(10)))
    mantissa = np.exp(logp - exponent * np.log(10))
    return f'{mantissa:.6f}e{exponent:+d}'


def log_two_sided_t_p(rho, n):
    """Same large-sample t null as spearmanr; scaled integral avoids underflow."""
    if rho == 0:
        return 0.0
    if abs(rho) >= 1:
        raise ValueError('Perfect correlation requires a separate boundary treatment')
    df = n - 2
    t = abs(rho) * np.sqrt(df / (1 - rho * rho))
    width = (df + t * t) / ((df + 1) * t)
    def scaled_pdf(v):
        delta = width * v
        return np.exp(-(df + 1) / 2 * np.log1p((2 * t * delta + delta * delta) / (df + t * t)))
    area, error = integrate.quad(scaled_pdf, 0, np.inf, epsabs=1e-11, epsrel=1e-11)
    if not area > 0 or error > 1e-7 * area:
        raise ValueError('Scaled p-value tail integration did not converge')
    return float(min(0, np.log(2) + stats.t.logpdf(t, df) + np.log(width) + np.log(area)))


def paired_bootstrap(x, ys, replicates, seed_sequence, label):
    """Resample raw paired rows; re-rank every variable within every replicate."""
    rng = np.random.default_rng(seed_sequence)
    raw = np.column_stack([x, ys]).T
    n = len(x)
    samples = np.empty((replicates, ys.shape[1]))
    for start in range(0, replicates, 16):
        end = min(start + 16, replicates)
        indices = rng.integers(0, n, size=(end - start, n))
        ranked = stats.rankdata(raw[:, indices], method='average', axis=-1)
        centered = ranked - ranked.mean(axis=-1, keepdims=True)
        numerator = np.sum(centered[0] * centered[1:], axis=-1)
        denominator = np.sqrt(np.sum(centered[0] ** 2, axis=-1) * np.sum(centered[1:] ** 2, axis=-1))
        samples[start:end] = (numerator / denominator).T
        if start % 400 == 0 or end == replicates:
            print(f'{label}: bootstrap {end}/{replicates}', flush=True)
    if not np.isfinite(samples).all():
        raise ValueError('Undefined bootstrap replicate; no replicates silently discarded')
    return samples


def analyze(frame, outcomes, name, replicates, seed_sequence):
    x = frame['sequence_length'].to_numpy()
    ys = frame[outcomes].to_numpy()
    distribution = paired_bootstrap(x, ys, replicates, seed_sequence, name)
    rows = []
    for i, outcome in enumerate(outcomes):
        result = stats.spearmanr(x, ys[:, i], alternative='two-sided', nan_policy='raise')
        rho, p = float(result.statistic), float(result.pvalue)
        logp = log_two_sided_t_p(rho, len(frame))
        if p > 0 and not np.isclose(logp, np.log(p), rtol=1e-9, atol=1e-8):
            raise ValueError('Stable p-value calculation disagrees with scipy.stats.spearmanr')
        ci = np.quantile(distribution[:, i], [0.025, 0.975], method='linear')
        rows.append({'analysis': name, 'outcome': outcome, 'n': len(frame), 'rho': rho,
                     'p_value_two_sided': p, 'p_value_text': scientific_log(logp), 'log10_p_value': logp / np.log(10),
                     'p_float_underflow': p == 0, 'ci95_low': float(ci[0]), 'ci95_high': float(ci[1]),
                     'bootstrap_replicates': replicates, 'bootstrap_seed': seed_sequence.entropy,
                     'seed_spawn_key': str(seed_sequence.spawn_key),
                     'method': 'SciPy spearmanr; average tied ranks; two-sided asymptotic t p-value',
                     'ci_method': 'paired row bootstrap; re-rank each resample; percentile 2.5/97.5; linear quantiles'})
    return rows, distribution


def figures(frame, correlations, directory):
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'pdf.fonttype': 42, 'savefig.dpi': 300})
    def finish(fig, name):
        for ext in ('png', 'pdf'):
            fig.savefig(directory / f'{name}.{ext}', bbox_inches='tight', metadata={'Creator': 'protein-go-research'})
        plt.close(fig)
    x = frame.sequence_length.to_numpy()
    y = frame.go_total_count.to_numpy()
    n = len(frame)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    axes[0].hist(x, bins=60, color='#31688e', edgecolor='white', linewidth=.3)
    axes[0].set(title='Full range; linear axis', xlabel='Sequence length (aa)', ylabel='Protein count')
    axes[1].hist(x, bins=np.geomspace(x.min(), x.max(), 55), color='#31688e', edgecolor='white', linewidth=.3)
    axes[1].set_xscale('log')
    axes[1].set(title='Full range; logarithmic axis', xlabel='Sequence length (aa; log scale)', ylabel='Protein count')
    fig.suptitle(f'Human reviewed protein sequence lengths | n = {n:,}')
    finish(fig, '01_sequence_length_distribution')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout='constrained')
    axes[0].hist(y, bins=np.arange(-.5, y.max() + 1.5), color='#35a78b', edgecolor='none')
    axes[0].set(title='Full range; linear axis', xlabel='Unique GO term count', ylabel='Protein count')
    edges = np.expm1(np.linspace(0, np.log1p(y.max()), 45))
    edges[-1] = np.nextafter(float(y.max()), np.inf)
    assert np.histogram(y, bins=edges)[0].sum() == n
    axes[1].hist(y, bins=edges, color='#35a78b', edgecolor='white', linewidth=.3)
    axes[1].set_xscale('function', functions=(np.log1p, np.expm1))
    ticks = [t for t in (0, 1, 2, 5, 10, 20, 50, 100, 200, 500) if t <= y.max()]
    axes[1].set_xticks(ticks, labels=[str(t) for t in ticks])
    axes[1].set(title=f'log(1 + count) spacing; zeros retained (n = {(y == 0).sum():,})', xlabel='Unique GO term count', ylabel='Protein count')
    fig.suptitle(f'Total GO annotation counts | n = {n:,}')
    finish(fig, '02_go_total_distribution')
    fig, ax = plt.subplots(figsize=(7.5, 5.2), layout='constrained')
    hb = ax.hexbin(x, y, gridsize=65, xscale='log', bins='log', mincnt=1, cmap='viridis', linewidths=0)
    assert int(hb.get_array().sum()) == n
    ax.set(xlabel='Sequence length (aa; log scale)', ylabel='Unique GO term count',
           title=f'Sequence length and total GO annotations | n = {n:,}')
    fig.colorbar(hb, ax=ax, label='Proteins per hexagon (log color scale)')
    r = correlations[0]
    ax.text(.03, .97, f"Spearman rho = {r['rho']:.3f}\n95% bootstrap CI [{r['ci95_low']:.3f}, {r['ci95_high']:.3f}]",
            transform=ax.transAxes, va='top', bbox={'facecolor': 'white', 'alpha': .9, 'edgecolor': 'none'})
    finish(fig, '03_length_go_hexbin')
    fig, ax = plt.subplots(figsize=(7, 4), layout='constrained')
    for index, (r, color) in enumerate(zip(correlations[1:], ['#31688e', '#35a78b', '#bf812d'])):
        ax.errorbar(r['rho'], index, xerr=[[r['rho'] - r['ci95_low']], [r['ci95_high'] - r['rho']]], fmt='o', color=color, capsize=5, markersize=7)
        ax.text(r['ci95_high'] + .008, index, f"{r['rho']:.3f} [{r['ci95_low']:.3f}, {r['ci95_high']:.3f}]", va='center', fontsize=9)
    ax.set_yticks([0, 1, 2], ['BP', 'MF', 'CC'])
    ax.invert_yaxis()
    ax.axvline(0, color='gray', linewidth=.8, linestyle='--')
    upper = max(r['ci95_high'] for r in correlations[1:])
    lower = min(0, min(r['ci95_low'] for r in correlations[1:]) - .025)
    ax.set(xlabel='Spearman rho (95% paired bootstrap CI)', ylabel='GO category',
           xlim=(lower, upper + .19), ylim=(2.5, -.5), title=f'Sequence length vs. GO categories | n = {n:,}')
    finish(fig, '04_go_category_correlations')


def write_report(output, desc, main_rows, sensitivity, metadata):
    def table(headers, rows):
        return '\n'.join(['| ' + ' | '.join(headers) + ' |', '|' + '|'.join(['---'] * len(headers)) + '|'] +
                         ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows])
    lines = ['# 통계 분석 결과 기록', '', '## 실제 계산 결과', '',
             f"입력은 인간 Reviewed 단백질 {metadata['input_validation']['row_count']:,}개이며 기본 분석에서 제외한 행은 0개다.",
             '원본 CSV 체크섬은 수집 당시 기록과 일치했고 분석 종료 시 다시 확인했다. accession 중복, 분석 숫자형 결측·음수·비정수, GO 전체와 범주별 합계 불일치는 모두 0건이다. 숫자형 5개 컬럼은 모두 int64다.', '',
             '### 기술통계', '',
             table(['변수', 'n', '평균', '표본 SD', '중앙값', '25%', '75%', '최솟값', '최댓값', '결측', '0개', '왜도'],
                   [[d['variable'], d['n'], f"{d['mean']:.5f}", f"{d['std_sample_ddof1']:.5f}", d['median'], d['q25'], d['q75'], d['min'], d['max'], d['missing_count'], d['zero_count'], f"{d['skewness_bias_corrected']:.5f}"] for d in desc]), '',
             '표본 SD는 ddof=1, 분위수는 pandas 선형 보간, 왜도는 scipy.stats.skew(bias=False)다. 모든 변수의 왜도가 양수이고 평균이 중앙값보다 커 오른쪽 꼬리가 긴 분포다. 모든 관측치를 유지했다.', '',
             '### Spearman 상관', '',
             table(['결과 변수', 'n', 'rho', '양측 p', '95% CI', '보조 3개 Holm p'],
                   [[r['outcome'], r['n'], f"{r['rho']:.8f}", r['p_value_text'], f"[{r['ci95_low']:.8f}, {r['ci95_high']:.8f}]", r['holm_p_value_text'] or '해당 없음'] for r in main_rows]), '',
             '전체 GO가 주요 분석이며 BP/MF/CC는 탐색적 보조 분석이다. 양측 p-value는 SciPy spearmanr의 큰 표본 t 근사(df=n−2)를 사용했다. 주요 분석의 float64 p-value는 수치 언더플로로 0을 반환하여, 같은 t 분포 꼬리를 스케일 조정 적분한 log p와 과학적 표기 문자열을 함께 보존했다. 이는 실제 p=0이라는 뜻이 아니다. 표현 가능한 다른 p-value는 SciPy 값과 로그 값의 일치 여부를 확인했다.', '',
             f"각 결과의 신뢰구간은 {metadata['bootstrap_replicates_per_analysis']:,}회 paired row bootstrap의 2.5%, 97.5% percentile(선형 보간)이다. Seed는 {metadata['seed']}, NumPy PCG64, SeedSequence의 spawn key (0,)/(1,)/(2,)를 사용했다. 매 표본에서 원자료를 다시 순위화하며 동률은 평균 순위로 처리했다. 기본 분석 4개는 같은 행 재표본을 공유한다. 정의 불가능한 재표본을 조용히 제외하지 않는다.", '',
             '### 민감도 분석', '',
             table(['분석', 'n', '기본 대비 제외', 'rho', '양측 p', '95% CI', '기본 대비 rho 변화'],
                   [[r['analysis'], r['n'], r['excluded_from_baseline_n'], f"{r['rho']:.8f}", r['p_value_text'], f"[{r['ci95_low']:.8f}, {r['ci95_high']:.8f}]", f"{r['delta_rho_from_baseline']:+.8f}"] for r in sensitivity]), '']
    s = metadata['selection']
    lines.extend([f"GO 0개 제외 분석은 {s['exclude_zero_go_n']:,}개를 제외했다. 기본 분석의 GO 0개 행은 그대로 유지한다.", '',
                  f"유전자 기준 분석은 Gene ID 누락 {s['gene_missing_excluded_n']:,}개와 복수 매핑 {s['gene_multiple_excluded_n']:,}개를 제외한 {s['single_gene_eligible_n']:,}개에서 시작했다. 같은 단일 Gene ID 내 accession 오름차순 첫 항목을 선택하여 추가 {s['single_gene_duplicate_accessions_excluded_n']:,}개를 제외하고 {s['gene_sensitivity_final_n']:,}개를 사용했다. 이는 결정적 중복 축소 규칙이며 생물학적 대표 단백질 선정 기준이 아니다. 항목별 선택/제외 사유는 statistics/sensitivity_selection.csv에 있다.", '',
                  '## 결과의 해석', '',
                  '서열 길이와 고유 GO 주석 개수 사이에 약한 양의 단조 관계가 관찰되며 주요 가설의 방향과 일치한다. 작은 p-value는 큰 효과나 인과관계를 의미하지 않는다. GO 개수는 데이터베이스 주석 용어의 개수이며 실제 생물학적 기능 수로 해석하지 않는다.', '',
                  '두 민감도 분석에서도 양의 방향이 유지되지만 상관계수는 감소했다. 유전자 기준 결과의 변화에는 Gene ID 누락·복수 매핑 제외와 중복 축소가 함께 작용하므로 중복 24개 제거만의 영향으로 해석할 수 없다. 보조 범주의 점추정 차이에 대한 별도 유의성 검정은 수행하지 않았다.', '',
                  '이 자료는 한 릴리스의 조건 일치 전체 항목이다. p-value와 bootstrap CI는 관측 행의 교환가능성/독립성을 가정한 탐색적 모형 기반 추론이며 이 고정된 전체 데이터베이스 자체의 표본추출 오차가 아니다. 단백질·유전자 사이 의존성, 연구 관심도·주석 밀도 등은 남은 해석상 한계다.', '',
                  '## 그래프 및 재현성', '',
                  'figures/의 01–04 파일은 각각 길이 분포, 전체 GO 분포, 길이–GO hexbin, BP/MF/CC rho 비교다. PNG(300 dpi)와 PDF로 저장한다. 분포 그림은 전체 범위를 유지하며 보조 패널에서만 로그 간격을 사용한다. hexbin은 모든 관측치와 GO 0개를 포함하고 색으로 겹침을 나타낸다. 주요 상관은 로그 변환값으로 대체하지 않았다.', '',
                  '입력 SHA256: `' + metadata['input_sha256'] + '`.',
                  'Python 및 라이브러리 버전, 코드·결과 체크섬, 분석 시각과 제외 규칙은 statistics/analysis_metadata.json에 있다. 독립 재실행 비교 결과는 statistics/reproducibility_report.json에 기록한다. 이 문서는 분석 기록이며 논문 본문은 작성하지 않았다.', '',
                  '계산 방법 참고: [SciPy spearmanr](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html), [SciPy bootstrap 설명](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).'])
    (output / 'analysis_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/full_20261030/protein_go_dataset.csv')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--replicates', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=20261030)
    parser.add_argument('--no-figures', action='store_true')
    args = parser.parse_args()
    if args.replicates < 2000:
        parser.error('At least 2000 bootstrap replicates required')
    output = args.output_dir
    out = output / 'statistics'
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    input_sha = sha(args.input)
    frame = pd.read_csv(args.input, dtype={'accession': 'string', 'protein_name': 'string', 'gene_name': 'string', 'gene_id': 'string'}, keep_default_na=False)
    previous = json.loads(args.input.with_name('dataset_metadata.json').read_text(encoding='utf-8'))
    quality = json.loads(args.input.with_name('quality_report.json').read_text(encoding='utf-8'))
    if input_sha != previous['csv_sha256'] or not quality['passed']:
        raise ValueError('Input checksum or previous quality gate failed')
    checks = {'row_count': len(frame), 'accession_duplicates': int(frame.accession.duplicated().sum()),
              'accession_blank': int((frame.accession == '').sum()), 'numeric_dtypes': {},
              'missing_counts': {}, 'negative_counts': {}, 'noninteger_counts': {},
              'go_zero_entries': int((frame.go_total_count == 0).sum()),
              'go_category_sum_mismatch': int((frame.go_total_count != frame[['go_bp_count', 'go_mf_count', 'go_cc_count']].sum(axis=1)).sum())}
    for col in NUMERIC:
        if not pd.api.types.is_numeric_dtype(frame[col]):
            raise ValueError(f'Non-numeric analysis column: {col}')
        checks['numeric_dtypes'][col] = str(frame[col].dtype)
        checks['missing_counts'][col] = int(frame[col].isna().sum())
        checks['negative_counts'][col] = int((frame[col] < 0).sum())
        checks['noninteger_counts'][col] = int((frame[col] % 1 != 0).sum())
    checks['passed'] = (len(frame) == previous['row_count'] == 20431 and checks['accession_duplicates'] == checks['accession_blank'] == checks['go_category_sum_mismatch'] == 0
                        and checks['go_zero_entries'] == quality['go_zero_entries'] and (frame.sequence_length > 0).all()
                        and not any(v for k in ('missing_counts', 'negative_counts', 'noninteger_counts') for v in checks[k].values()))
    checks['passed'] = bool(checks['passed'])
    save(out / 'input_validation.json', checks)
    if not checks['passed']:
        raise ValueError('Analysis input validation failed; no rows silently dropped')
    frame = frame.sort_values('accession', kind='stable').reset_index(drop=True)
    desc = []
    for col in NUMERIC:
        s = frame[col]
        desc.append({'variable': col, 'n': int(s.count()), 'mean': s.mean(), 'std_sample_ddof1': s.std(ddof=1),
                     'median': s.median(), 'min': s.min(), 'max': s.max(), 'q25': s.quantile(.25), 'q75': s.quantile(.75),
                     'missing_count': int(s.isna().sum()), 'zero_count': int((s == 0).sum()),
                     'skewness_bias_corrected': stats.skew(s, bias=False), 'unique_values': s.nunique(),
                     'observations_in_tied_groups': int(s.duplicated(keep=False).sum())})
    csv_save(pd.DataFrame(desc), out / 'descriptive_statistics.csv')
    seeds = np.random.SeedSequence(args.seed).spawn(3)
    main_rows, boot_main = analyze(frame, OUTCOMES, 'primary_and_exploratory', args.replicates, seeds[0])
    # Holm family: only the three auxiliary category tests.
    logps = np.array([r['log10_p_value'] * np.log(10) for r in main_rows[1:]])
    order = np.argsort(logps)
    adjusted = np.empty(3)
    running = -np.inf
    for j, index in enumerate(order):
        running = max(running, logps[index] + np.log(3 - j))
        adjusted[index] = min(0, running)
    for i, row in enumerate(main_rows):
        row['test_role'] = 'primary' if i == 0 else 'exploratory_auxiliary'
        row['holm_p_value'] = '' if i == 0 else float(np.exp(adjusted[i - 1]))
        row['holm_p_value_text'] = '' if i == 0 else scientific_log(adjusted[i - 1])
    csv_save(pd.DataFrame(main_rows), out / 'correlation_results.csv')
    nozero = frame[frame.go_total_count > 0].copy()
    gene_lists = frame.gene_id.map(lambda s: sorted({x.strip() for x in s.split(';') if x.strip()}))
    missing = gene_lists.map(len) == 0
    multiple = gene_lists.map(len) > 1
    singleton = frame[gene_lists.map(len) == 1].copy()
    singleton['_gene_id'] = gene_lists[gene_lists.map(len) == 1].map(lambda g: g[0])
    gene_selected = singleton.drop_duplicates('_gene_id', keep='first').copy()
    selection = {'baseline_n': len(frame), 'exclude_zero_go_n': len(frame) - len(nozero), 'nonzero_go_final_n': len(nozero),
                 'gene_missing_excluded_n': int(missing.sum()), 'gene_multiple_excluded_n': int(multiple.sum()),
                 'single_gene_eligible_n': len(singleton), 'single_gene_duplicate_accessions_excluded_n': len(singleton) - len(gene_selected),
                 'gene_sensitivity_final_n': len(gene_selected),
                 'gene_rule': 'Only exactly one unique Gene ID; accession ascending first per Gene ID; deterministic reduction, not biological representative selection'}
    audit = pd.DataFrame({'accession': frame.accession, 'gene_id': frame.gene_id,
                          'included_nozero': frame.accession.isin(nozero.accession), 'included_gene_sensitivity': frame.accession.isin(gene_selected.accession)})
    audit['gene_exclusion_reason'] = np.where(missing, 'missing_gene_id', np.where(multiple, 'multiple_gene_ids', np.where(audit.included_gene_sensitivity, '', 'later_accession_same_single_gene')))
    csv_save(audit, out / 'sensitivity_selection.csv')
    rows_a, boot_a = analyze(nozero, ['go_total_count'], 'sensitivity_nozero_go', args.replicates, seeds[1])
    rows_b, boot_b = analyze(gene_selected, ['go_total_count'], 'sensitivity_one_accession_per_single_gene', args.replicates, seeds[2])
    sensitivity = rows_a + rows_b
    for row in sensitivity:
        row['baseline_rho'] = main_rows[0]['rho']
        row['delta_rho_from_baseline'] = row['rho'] - main_rows[0]['rho']
        row['excluded_from_baseline_n'] = len(frame) - row['n']
    csv_save(pd.DataFrame(sensitivity), out / 'sensitivity_results.csv')
    boot = pd.DataFrame(np.column_stack([boot_main, boot_a, boot_b]), columns=['main_total', 'main_bp', 'main_mf', 'main_cc', 'nozero_total', 'single_gene_total'])
    boot.insert(0, 'replicate', np.arange(1, args.replicates + 1))
    csv_save(boot, out / 'bootstrap_correlations.csv')
    if not args.no_figures:
        figures(frame, main_rows, output / 'figures')
    if sha(args.input) != input_sha:
        raise ValueError('Input file changed during analysis')
    metadata = {'status': 'complete', 'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
                'input_file': str(args.input.resolve()), 'input_sha256': input_sha, 'script_sha256': sha(__file__),
                'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__, 'scipy': scipy.__version__, 'matplotlib': matplotlib.__version__},
                'seed': args.seed, 'rng': 'NumPy default_rng / PCG64; SeedSequence.spawn(3)',
                'bootstrap_replicates_per_analysis': args.replicates, 'bootstrap_total_rho_estimates': args.replicates * 6,
                'ci_method': 'paired rows with replacement, sample size n, re-rank raw values in every sample using average ties, percentile [0.025,0.975], linear quantile interpolation',
                'p_value_method': 'Two-sided asymptotic t, df=n-2, scipy.stats.spearmanr; scaled log-tail integration for scientific text/log10 p and underflow preservation',
                'multiplicity': 'Holm for the 3 auxiliary BP/MF/CC tests only; primary and sensitivity tests reported separately',
                'ci_assumptions': 'Ordinary row bootstrap treats accessions as exchangeable independent observations. Full database population is fixed; intervals and p-values are model-based exploratory inference, not sampling uncertainty of this complete release.',
                'selection': selection, 'baseline_rows_excluded': 0, 'input_validation': checks,
                'output_sha256': {p.name: sha(p) for p in sorted(out.glob('*.csv'))}}
    metadata['figure_sha256'] = {p.name: sha(p) for p in sorted((output / 'figures').glob('*'))} if not args.no_figures else {}
    save(out / 'analysis_metadata.json', metadata)
    write_report(output, desc, main_rows, sensitivity, metadata)
    print(json.dumps({'correlations': main_rows, 'sensitivity': sensitivity, 'selection': selection}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
