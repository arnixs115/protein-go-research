# 과제 10 — 8MB 제한용 제출 패키지

논문 PDF·분석용 데이터·코드·실행 절차·통계 결과·그림을 포함합니다. 대용량 원자료는 아래 **공개 GitHub 저장소**에서 내려받습니다. 제출 시스템에는 `protein-go-research-submission-8mb.zip` **1개만** 올립니다. 실제 업로드·접수는 아직 수행하지 않았습니다.

## 공개 원자료 주소

- 저장소: https://github.com/arnixs115/protein-go-research
- 고정 원자료 버전: `7d7cc33078aa8b684534f03ef339b46789f01a14`
- 원자료 폴더: https://github.com/arnixs115/protein-go-research/tree/7d7cc33078aa8b684534f03ef339b46789f01a14/protein-go-research/data/raw
- 이 ZIP에서 제외한 JSON·TSV 응답: **83개, 177,808,088바이트**. 파일별 주소·크기·SHA256은 `data/raw/external_raw_files.json`에 있습니다.

고정 커밋 URL을 사용하므로 이후 저장소에 추가 커밋이 생겨도 같은 원자료를 복원합니다. 저장소를 공개로 전환한 뒤 인증 없이 83개 파일을 실제 다운로드하고 모두 SHA256을 대조했습니다. 로그인·토큰이 필요하지 않습니다. 원자료는 이미 수집된 응답이며 **UniProt API를 다시 호출하지 않습니다.** 일부 `.json` 본문은 gzip 형식이므로 기존 파서를 사용합니다.

## 연구와 데이터

연구 제목은 ‘인간 단백질의 아미노산 서열 길이와 Gene Ontology 기능 주석 개수의 관계에 관한 탐색적 분석’입니다. UniProtKB의 `organism_id:9606 AND reviewed:true`, 릴리스 `2026_03`, 수집일 2026-10-30의 Primary Accession 20,431개를 사용했습니다. GO 0개와 Gene ID 누락은 기본 분석에서 유지했습니다. GO 수는 기록된 고유 용어 수이며 실제 기능 수가 아닙니다.

분석 입력 `data/processed/full_20261030/protein_go_dataset.csv`의 SHA256:
`a1b62f7bcb6524f53fb93cef4efc48744e96ed7a3bc33c71318473f0913bf567`

## 포함 파일

- `paper/human_protein_length_go_paper.pdf`: 사용자가 추가한 16페이지 논문. 파일을 수정하지 않았습니다.
- `data/processed/`: 분석 CSV, 품질·데이터 메타데이터·기존 재현성 결과.
- `data/raw/`: 소량 검증 표본, 공식 문서, 수집 메타데이터·로그·원본 체크섬. 큰 응답 83개만 외부 저장소로 분리했습니다.
- `scripts/01`–`04`, `uniprot_dataset.py`: 기존 수집·전처리·통계 코드 그대로.
- `scripts/05_verify_submission.py`: 제출 파일 체크섬과 복원 후 재현성 결과 대조.
- `scripts/06_package_submission.py`: 원자료를 ZIP에서 제외하고 8,000,000바이트 미만인지 강제 검사, 압축 해제 검증.
- `scripts/07_restore_raw_data.py`: 공개 고정 커밋에서 원자료 복원·SHA256 확인.
- `results/statistics/`, `results/figures/`, `results/analysis_report.md`: 기존 통계·그림·분석 기록.
- `tests/`: 실제 테스트 11개와 기록.
- `verification_run/`: 새 재현성 기록, PDF 점검, 익명 원자료 다운로드 검증과 로그.
- `requirements.txt`: 실제 실행 환경 패키지 19개 고정.
- `AI_and_My_Decisions.md`: 확인된 AI 활용과 연구자 지시 3줄.
- `checksums.sha256`: ZIP 내 파일의 SHA256. 외부 원자료는 별도 JSON 목록으로 검증합니다.
- `provenance/`: 과거 상태 기록과 원본→제출 위치 매핑. 그 안의 PDF 누락·대용량 ZIP 설명은 역사적 기록이며 현재 안내는 이 README입니다.

## 실행 환경과 설치

Python 3.12.14, requests 2.32.5, NumPy 2.5.4, pandas 3.1.0, SciPy 1.18.1, Matplotlib 3.11.2로 검증했습니다. 압축을 푼 패키지 폴더에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MPLCONFIGDIR = Join-Path (Get-Location) 'verification_run/runtime_cache/matplotlib'
```

이번에는 기존 동일 버전 가상환경을 사용했으며 새 가상환경 설치·다른 운영체제 실행은 검증하지 않았습니다.

## 먼저 ZIP 내 파일과 오프라인 분석 확인

원자료 다운로드 없이도 포함된 분석 CSV로 통계 분석·그림 생성 및 테스트를 실행할 수 있습니다. 기본 결과를 덮어쓰지 않도록 출력 경로를 지정합니다.

```powershell
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --verify-checksums
.\.venv\Scripts\python.exe scripts/04_analyze_statistics.py --output-dir verification_run/analysis_from_included_csv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

기본 설정은 seed 20261030, 결과별 paired bootstrap 2,000회, 평균 동률 순위와 percentile 95% CI입니다. 기본 상관 4개와 민감도 분석 2개를 수행합니다. 보조 BP/MF/CC p-value에는 Holm 보정을 기록합니다.

## 공개 원자료 복원 후 전처리부터 반복

```powershell
.\.venv\Scripts\python.exe scripts/07_restore_raw_data.py
.\.venv\Scripts\python.exe scripts/07_restore_raw_data.py --verify-only
.\.venv\Scripts\python.exe scripts/03_prepare_dataset.py --run-dir data/raw/full_20261030 --output-dir verification_run/processed/full_20261030
.\.venv\Scripts\python.exe scripts/04_analyze_statistics.py --input verification_run/processed/full_20261030/protein_go_dataset.csv --output-dir verification_run/results
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --compare-rerun
```

첫 명령만 인터넷에서 공개 저장소를 읽습니다. 이후 전처리·분석은 오프라인입니다. 이미 복원된 파일은 체크섬을 대조해 재사용하고, 내용이 다르면 임의로 덮어쓰지 않고 실패합니다. `01_check_uniprot.py`, `02_collect_uniprot.py`는 새 API 수집용이므로 이 재현 절차에서는 실행하지 않습니다.

## 실제 결과·검증 범위

전체 GO rho 0.27045797(n=20,431), GO 0개 제외 rho 0.23311080(n=19,375), 단일 Gene ID당 1개 rho 0.20132929(n=19,031)입니다. 유전자 기준은 누락 1,277개·복수 매핑 99개·같은 단일 Gene ID 후순위 accession 24개를 제외한 결정적 축소 규칙입니다. 인과관계나 생물학적 대표 단백질 선정을 의미하지 않습니다.

보존 원자료에서 생성한 전처리 3개 파일과 통계 CSV 5개가 기존 결과와 정확히 일치했고, PNG/PDF 각 4개 생성 및 테스트 11개 통과를 확인했습니다. 이번에는 공개 URL에서 83개 원자료를 인증 없이 복원해 기록된 SHA256과 대조했습니다. 검증 기록은 `verification_run/`에 있습니다.

원자료를 복원해도 ZIP 파일 검증은 계속 사용할 수 있습니다. `05`의 ZIP 목록 및 `06` 포장 과정은 외부 응답 파일·환경·캐시를 제외하고, 원자료 무결성은 `07 --verify-only`와 수집 당시 `raw_inventory.json`으로 확인합니다. 실행 로그·시각 등이 변경되면 예상한 변경임을 먼저 확인하고 체크섬 목록을 다시 만듭니다.

```powershell
.\.venv\Scripts\python.exe scripts/05_verify_submission.py --write-manifest --verify-checksums
.\.venv\Scripts\python.exe scripts/06_package_submission.py
```

`06`은 8,000,000바이트 이상 ZIP을 실패 처리하고 기존 ZIP을 덮어쓰지 않습니다. ZIP 생성·압축 해제 결과와 ZIP SHA256은 ZIP 옆 검증 파일에 기록합니다. 해당 검증 파일들은 확인용이며 과제 업로드에는 ZIP 1개만 필요합니다. 문헌 DOI 전수 확인, 연구자의 별도 최종 교정 여부, 제출 시스템 업로드는 수행했다고 주장하지 않습니다.
