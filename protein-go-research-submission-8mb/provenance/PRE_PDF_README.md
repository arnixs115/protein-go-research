# 과제 10 제출용 자료 — 논문 PDF 추가 필요

**현재 최종 제출 완료 상태가 아닙니다. `paper/`에 연구자가 검토한 최종 논문 PDF를 추가해야 합니다. ZIP은 아직 생성하지 않았습니다.**

연구 제목: 인간 단백질의 아미노산 서열 길이와 Gene Ontology 기능 주석 개수의 관계에 관한 탐색적 분석.
연구 목적은 인간 Reviewed 단백질의 서열 길이와 데이터베이스에 기록된 고유 GO ID 개수의 단조 관계를 탐색하는 것입니다. GO 개수는 실제 생물학적 기능의 개수로 해석하지 않습니다.

## 데이터와 실행 환경

- 출처: UniProtKB REST API, 조건 `organism_id:9606 AND reviewed:true`.
- 릴리스 `2026_03`, 릴리스 날짜 2026-09-02, 수집일 2026-10-30.
- 분석 단위: Primary Accession 20,431개. isoform을 별도 행으로 확장하지 않았습니다.
- GO 0개와 Gene ID 미제공 행을 기본 분석에 유지했습니다.
- 실제 검증 환경: Windows, Python 3.12.14, NumPy 2.5.4, pandas 3.1.0, SciPy 1.18.1, Matplotlib 3.11.2, requests 2.32.5.
- `requirements.txt`는 원 프로젝트의 실제 분석 환경 잠금 파일을 복사한 것으로 하위 의존성을 포함한 19개 패키지를 고정합니다.
- 분석 입력 SHA256: `a1b62f7bcb6524f53fb93cef4efc48744e96ed7a3bc33c71318473f0913bf567`.

## 포함 자료

| 경로 | 내용 |
|---|---|
| `paper/` | 최종 논문 PDF를 추가할 위치와 누락 안내. 개별 그래프 PDF는 논문이 아닙니다. |
| `data/raw/` | 소량 검증·공식 문서, 전체 JSON/TSV 각 41페이지, 수집 manifest·요청 로그·원본 SHA256 목록·실패/체크포인트 응답 |
| `data/processed/full_20261030/` | 기존 분석 CSV 20,431행, 품질·데이터 메타데이터·재현성 보고서 |
| `data/processed/reproducibility_check/` | 원 프로젝트에서 수행한 이전 전처리 반복 결과 |
| `scripts/01_check_uniprot.py` | API 소량 검증. API를 호출하므로 오프라인 재현 시 실행하지 않습니다. |
| `scripts/02_collect_uniprot.py` | 전체 수집 및 재개. API를 호출하므로 오프라인 재현 시 실행하지 않습니다. |
| `scripts/03_prepare_dataset.py` | 보존한 JSON을 기준으로 전처리하고 TSV와 교차 검증 |
| `scripts/04_analyze_statistics.py` | 기술통계·Spearman·bootstrap·민감도·PNG/PDF 그림 생성 |
| `scripts/uniprot_dataset.py` | 공통 파싱·체크섬·품질 검증 모듈 |
| `scripts/05_verify_submission.py` | 제출용 보존 파일·새 재실행 결과 비교 및 휴대 가능한 체크섬 검증. 이번 정리 단계에 추가한 보조 코드 |
| `results/statistics/`, `results/figures/`, `results/analysis_report.md` | 기존 검증된 통계 결과·그림·분석 기록. 논문 본문이 아닙니다. |
| `results/reproducibility_run/` | 원 프로젝트에서 수행한 이전 통계 반복 결과 |
| `tests/` | 원 코드의 테스트 11개와 이전 실행 기록. 네트워크는 모의 응답으로 대체합니다. |
| `verification_run/` | 이번 제출용 폴더에서 새로 생성한 전처리·분석·그림·로그·대조 보고서 |
| `provenance/` | 원 README, 원 수집용 requirements, 원본→제출 폴더 매핑과 체크섬 목록 |
| `AI_and_My_Decisions.md` | 확인된 지시에 한정한 AI 활용과 연구자 결정 기록 |
| `checksums.sha256` | 포함 파일의 상대경로별 SHA256 목록. 자기 자신, 환경·캐시 파일은 제외 |

원 프로젝트의 161개 파일은 바이트를 유지해 복사했습니다. 원 README는 `provenance/PROJECT_README.md`, 원 최소 수집 의존성은 `provenance/requirements-collection.txt`에 보존했습니다. 기존 스크립트 5개는 수정하지 않았습니다. 이 제출 폴더의 상대 경로 구조는 기존 코드와 테스트의 경로 규칙을 그대로 만족합니다.

## 설치

먼저 Python 3.12를 준비하고 제출 폴더로 이동합니다. Python이 `python` 명령에 등록된 환경에서는 다음과 같이 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python이 PATH에 없으면 첫 명령의 `python` 대신 Python 3.12 실행 파일의 절대 경로를 사용합니다. 설치에는 패키지 저장소 접근 또는 준비된 wheel이 필요하지만, 아래 전처리·분석·테스트에는 UniProt API 접근이 필요하지 않습니다. 이번에는 원 프로젝트에 이미 설치된 동일 버전 가상환경을 사용했습니다. 새 가상환경 설치·다른 운영체제에서의 실행·최종 ZIP 압축 해제 후 검증은 아직 수행하지 않았습니다.

## API 재호출 없는 전처리·분석 재현

아래 모든 명령은 **이 README가 있는 제출 폴더**에서 실행합니다. 기존 `data/processed/`, `results/`를 덮어쓰지 않도록 별도 출력 폴더를 지정합니다.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MPLCONFIGDIR = Join-Path (Get-Location) 'verification_run/runtime_cache/matplotlib'
New-Item -ItemType Directory -Force verification_run/logs | Out-Null

.\.venv\Scripts\python.exe scripts/03_prepare_dataset.py --run-dir data/raw/full_20261030 --output-dir verification_run/processed/full_20261030 > verification_run/logs/prepare.log 2>&1

.\.venv\Scripts\python.exe scripts/04_analyze_statistics.py --input verification_run/processed/full_20261030/protein_go_dataset.csv --output-dir verification_run/results > verification_run/logs/analysis.log 2>&1

.\.venv\Scripts\python.exe -m unittest discover -s tests -v > verification_run/logs/tests.log 2>&1

.\.venv\Scripts\python.exe scripts/05_verify_submission.py --compare-rerun
```

이번 실제 실행에서는 위의 `.venv/Scripts/python.exe` 대신 원 프로젝트의 `../protein-go-research/.venv/Scripts/python.exe`를 사용했습니다. 원본 입력과 기준 결과를 수정하지 않았습니다.
`05_verify_submission.py`는 기존 전처리 결과 3개와 통계 CSV 5개를 SHA256으로 비교하고, 분석 메타데이터의 방법·seed·버전·표본 선택 등 안정적 필드와 그림 생성·11개 테스트 성공을 확인합니다. 실패하면 비정상 종료하며 원본을 덮어쓰지 않습니다.

기존 CLI에는 유효한 `--run-dir`, `--output-dir`, `--input`, `--replicates`, `--seed`, `--no-figures` 옵션이 있습니다. 기본 통계 설정은 seed 20261030, 각 결과당 bootstrap 2,000회입니다. paired row 복원추출 뒤 매번 동률을 평균 순위로 다시 계산하고 percentile 95% CI를 구합니다. p-value는 양측이며 보조 범주 3개에는 Holm 보정을 기록합니다. Gene ID 누락·복수 매핑은 유전자 민감도 분석에서만 제외하고, 명확한 단일 Gene ID 내 accession 오름차순 첫 항목을 선택합니다.

## 결과 파일과 해석

- `descriptive_statistics.csv`: n, 평균, 표본 SD, 중앙값, 사분위수, 최소·최대, 결측·0개, 왜도와 동률 현황.
- `correlation_results.csv`: 전체 GO와 BP/MF/CC의 rho·양측 p·95% CI·계산 방법·Holm 보정.
- `sensitivity_results.csv`: GO 0개 제외 및 단일 Gene ID당 1개 선택 결과.
- `sensitivity_selection.csv`: accession별 포함/제외 이유.
- `bootstrap_correlations.csv`: 결과별 2,000회 재표본 rho.
- `analysis_metadata.json`: 입력·코드·결과 체크섬, 버전, 시각, seed, CI와 p 계산 방법.
- `figures/`의 01–04 PNG/PDF: 길이 분포, 전체 GO 분포, 길이–GO hexbin, BP/MF/CC 상관 비교.

기존 주요 결과는 전체 GO rho 0.27045797, GO 0개 제외 rho 0.23311080, 유전자 기준 rho 0.20132929입니다. 통계적으로 작은 p-value는 큰 효과 또는 인과관계를 의미하지 않습니다. Gene ID 기준 결과는 누락·복수 매핑 제외와 중복 축소의 결합 영향입니다. 한 릴리스의 전체 항목에 대한 CI·p-value는 모형 기반 탐색적 추론으로 해석합니다.

기존 메타데이터에 있는 절대 경로·실행 시각은 당시 실행 기록입니다. 새 실행에서는 입력 경로와 시각, PDF 생성 메타데이터가 달라질 수 있어 PDF 바이트 동일성을 요구하지 않습니다. 현재 비교는 통계 CSV의 정확한 동일성과 새 그림 생성 여부를 구분합니다.

## 체크섬 검증

Python만으로 다음을 실행할 수 있습니다. 추가 패키지나 API 접근은 필요하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --verify-checksums
```

파일 내용 외에 누락·추가 파일도 검사합니다. SHA256 목록은 `checksums.sha256`이며 자기 자신과 `.venv`, `__pycache__`, `runtime_cache`는 대상에서 제외합니다. `data/raw/full_20261030/raw_inventory.json`은 원본 응답 93개의 수집 당시 체크섬을 보존합니다. 일부 큰 `.json` 파일은 HTTP 디코딩 뒤에도 gzip 본문이므로 파일명만 보고 텍스트로 읽지 말고 기존 `decode_body`를 사용합니다.

전처리·분석을 재실행하면 새 시각 등이 기록되어 제출 폴더의 기존 체크섬 목록과 달라질 수 있습니다. 재실행 검증 또는 최종 PDF 추가 후에는 다음 순서로 갱신하고 확인합니다. **파일이 예상대로 변경된 것을 먼저 확인한 뒤** 목록을 재생성해야 합니다.

```powershell
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --compare-rerun
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --write-manifest
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --verify-checksums
```

## 현재 상태와 최종 ZIP 전 남은 작업

이번 검증의 실제 결과는 `verification_run/reproducibility_report.json`, 실행 출력은 `verification_run/logs/`에 기록합니다. 과거 `results/statistics/reproducibility_report.json`과 구분합니다. 초기 테스트의 임시 디렉터리 접근 실패 로그도 별도로 보존하며 성공 로그와 혼동하지 않습니다.

1. `paper/`에 연구자가 검토한 최종 논문 PDF를 추가하고 제목·수치·그림·참고문헌과 PDF 열림 상태를 확인합니다. 빈 PDF나 임시 논문은 만들지 않았습니다.
2. 예상한 파일만 포함되는지 점검하고 재현성 대조 및 체크섬 목록을 갱신·검증합니다.
3. `.venv`, `__pycache__`, `verification_run/runtime_cache`를 제외하고 이 제출 폴더를 ZIP 1개로 압축합니다. 원본·기준 결과를 임의로 삭제하지 않습니다.
4. 별도 위치에 ZIP을 풀어 체크섬을 검증하고 논문 PDF·원자료·실행 안내가 모두 열리는지 확인합니다. 이 절차가 끝나기 전에는 최종 제출 완료로 표시하지 않습니다.

논문 PDF 누락을 숨기기 위해 그래프 PDF를 논문으로 지정하지 않았습니다. 이번 정리 작업에서 Git commit/push는 하지 않습니다.
