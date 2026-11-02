# 인간 Reviewed 단백질: UniProt 수집 및 전처리

현재 작업은 통계 분석·시각화까지 확장되었다. 소량 검증과 전체 수집·전처리 절은 당시 작업 기록이며, 최신 분석 실행법은 문서 끝의 **통계 분석 및 시각화**를 따른다.

연구: **인간 단백질의 아미노산 서열 길이와 Gene Ontology 기능 주석 개수의 관계에 관한 탐색적 분석**

이번 단계는 API 구조 확인에 한정한다. 전체 수집, 통계 분석, 그래프, 웹 앱 구현은 포함하지 않는다.
GO 주석 수는 실제 기능 수가 아니라 데이터베이스에 기록된 고유 GO ID 수다.

## 실행

Python 3.10 이상과 `requests`가 필요하다. 일반 Python 환경에서는 프로젝트 폴더에서:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\01_check_uniprot.py
```

이 작업 환경에는 `python` 명령이 없어 uv로 Python 3.12.14를 작업 폴더의 `../.python/`에 설치했다.
실제 설치·실행 명령(작업 폴더 `paper` 기준):

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.python'
$env:UV_PYTHON_BIN_DIR = Join-Path (Get-Location) '.python-bin'
uv python install 3.12
uv venv protein-go-research/.venv --python .python-bin/python3.12.exe
uv pip install --python protein-go-research/.venv/Scripts/python.exe requests==2.32.5
Set-Location protein-go-research
.\.venv\Scripts\python.exe scripts\01_check_uniprot.py > data\raw\execution.log 2>&1
```

`requirements-lock.txt`는 실제 실행 환경의 하위 의존성까지 기록한다. uv로 만든 이 가상환경에는 pip가 없으므로 추가 설치는 `uv pip`를 사용한다.

## 요청 범위와 보존 방식

- 첫 검색 조건: `organism_id:9606 AND reviewed:true`, `size=10`, `includeIsoform=false`, JSON.
- 두 번째 검색은 위 조건에 첫 응답의 accession 10개만 OR 조건으로 추가하고 TSV를 요청한다.
- `Link`의 다음 페이지를 따라가지 않고 stream 엔드포인트도 사용하지 않는다.
- 표본 선정은 API 기본 순서이며 무작위 표본이 아니다. 정렬 요청에서 예비 HTTP 500 오류가 발생하여 최종 스크립트에는 정렬을 지정하지 않았다.
- 요청 URL, 상태, 전체 응답 헤더, UTC 요청/응답 시각, SHA256을 `metadata.json`에 기록한다.
- 실행마다 새 날짜/UUID 폴더를 만들어 기존 원본을 덮어쓰지 않는다. HTTP 오류 본문도 수신했다면 저장한다.
- 연결/읽기 타임아웃은 각각 10초/60초다. 오류는 종료 코드 1, 검증 불일치는 2로 반환한다.
- TSV 셀은 문자열이며 `Length`만 검증 시 정수로 해석한다. ID는 문자열로 유지한다.
- 빈 GO는 빈 집합으로 세어 0을 유지한다. 빈 Gene ID 등은 임의 생성하거나 다른 DB에서 보충하지 않는다.

## 공식 정의의 확인

공식 [UniProtKB OpenAPI](https://rest.uniprot.org/uniprotkb/api/docs)의 `/uniprotkb/search` 매개변수와 `SearchResult`, `UniProtKBEntry`, `UniProtKBCrossReference`, `Property`, `Evidence` 스키마를 확인했다.
OpenAPI가 직접 연결하는 [공식 반환 필드 설정](https://rest.uniprot.org/configure/uniprotkb/result-fields)에서 아래 필드 이름을 확인했고, 스크립트도 실행마다 이 정의를 대조한다.
공식 웹 도움말은 브라우징 도구에서 JavaScript 안내 화면만 반환하여 실제 정의 확인에는 위 기계 판독용 공식 문서를 사용했다.

| API 필드 | 실제 TSV 컬럼 |
|---|---|
| accession | Entry |
| protein_name | Protein names |
| gene_primary | Gene Names (primary) |
| xref_geneid | GeneID |
| length | Length |
| go_p | Gene Ontology (biological process) |
| go_f | Gene Ontology (molecular function) |
| go_c | Gene Ontology (cellular component) |
| go_id | Gene Ontology IDs |
| organism_id | Organism (ID) |
| reviewed | Reviewed |

JSON의 최상위 `results`는 배열이다. 각 항목의 `primaryAccession`은 문자열, `sequence.length`는 정수다.
`proteinDescription`은 단백질 이름 객체, `genes[].geneName.value`는 대표 유전자 이름이다.
`uniProtKBCrossReferences[]`에서 `database == "GeneID"`인 객체의 `id`가 NCBI Gene ID이며, 복수일 수 있으므로 목록으로 보존한다.
스키마가 일반적인 key/value 구조를 정의하는 GO 속성 이름은 실제 응답으로 추가 확인했다.

실제 GO 교차 참조 예:

```json
{
  "database": "GO",
  "id": "GO:0005576",
  "properties": [
    {"key": "GoTerm", "value": "C:extracellular region"},
    {"key": "GoEvidenceType", "value": "IDA:UniProtKB"}
  ],
  "evidences": [
    {"evidenceCode": "ECO:0000314", "source": "PubMed", "id": "25738459"}
  ]
}
```

`GoTerm`의 `P:`는 BP, `F:`는 MF, `C:`는 CC다.
TSV `go_id`는 `GO:0001649; GO:0003677; ...` 형식이고, 범주별 셀은 `DNA binding [GO:0003677]; ...` 형식이다.
ID 형식은 `GO:` + 숫자 7자리다. 구분자는 세미콜론이며 GO 집합은 문자열 전체가 아닌 ID로 비교한다.

요청한 TSV GO 필드에는 evidence가 포함되지 않았다. 공식 반환 필드 정의에도 전용 GO evidence 필드는 확인되지 않았다.
JSON의 `GoEvidenceType`에 GO evidence 약어와 제공기관이 있고, 일부 GO 객체의 `evidences[]`에는 ECO 코드·문헌 출처가 있다.
실제 관찰 약어는 IDA, IPI, IBA, IEA, ISS, IMP, TAS, NAS, EXP다. **모든 GO 항목에 ECO 배열이 제공되는 것은 아니다.**
JSON 전체를 보존하므로 evidence를 추후 활용할 수 있다. GAF 전체 다운로드나 별도 evidence 수집은 하지 않았다.

## 실제 실행 결과

성공 실행 폴더: `data/raw/20261030T072135Z_8fce6346/`.
수집일은 2026-10-30, 시작 시각은 07:21:35 UTC (16:21:35 KST)다.
공식 정의 2건 및 JSON·TSV 요청 모두 HTTP 200. 기본 검색 전체 건수는 **20,431**, JSON·TSV는 각각 **10개**다.
TSV의 전체 건수 헤더는 accession으로 제한한 두 번째 조건의 건수이므로 원래 모집단 건수와 구분해야 한다.
릴리스 **2026_03**, 릴리스 날짜 **02-September-2026**이며 두 데이터 응답의 릴리스가 일치했다.
전체 결과는 `validation.json`, 실제 URL·헤더·시각은 `metadata.json`, 출력은 `data/raw/execution.log`에서 확인한다.

| Accession | 대표 유전자 | Gene ID | 길이 aa | 고유 GO 전체 | BP | MF | CC |
|---|---|---|---:|---:|---:|---:|---:|
| A0A0C5B5G6 | MT-RNR1 | 미제공 | 16 | 14 | 9 | 2 | 3 |
| A0A1B0GTW7 | CIROP | 100128908 | 788 | 7 | 3 | 2 | 2 |
| A0JNW5 | BLTP3B | 23074 | 1464 | 7 | 2 | 3 | 2 |
| A0JP26 | POTEB3 | 102724631 | 581 | 0 | 0 | 0 | 0 |
| A0PK11 | CLRN2 | 645104 | 232 | 5 | 3 | 0 | 2 |
| A1A4S6 | ARHGAP10 | 79658 | 786 | 9 | 4 | 1 | 4 |
| A1A519 | FAM170A | 340069 | 330 | 10 | 8 | 1 | 1 |
| A1L190 | SYCE3 | 644186 | 88 | 10 | 5 | 0 | 5 |
| A1L3X0 | ELOVL7 | 79993 | 281 | 10 | 7 | 1 | 2 |
| A1X283 | SH3PXD2B | 285590 | 911 | 28 | 19 | 7 | 2 |

단백질 이름은 `sample.tsv` 및 `validation.json`의 `protein_names_tsv`에 있다.
Primary Accession 중복, 단백질별 GO ID 중복, 잘못된 GO ID 형식은 이 표본에서 발견되지 않았다.
9개 항목에서 Gene ID를 확인했고 표본 내 공유 Gene ID는 없었다. 이 결과는 전체 데이터의 중복 부재를 뜻하지 않는다.
길이·GO 전체 및 범주별 집합·Gene ID의 TSV/JSON 일치 검증이 통과했다.
GO evidence 속성은 표본의 모든 GO 교차 참조에서 확인되었다.

저장된 응답으로 최종 코드의 컬럼 정의 검증을 다시 실행했다. GO 0개 유지, 길이 불일치 탐지, 메모리 내 GO 중복 추가 시 고유 개수 유지, 저장 원본 SHA256 대조를 모두 확인했다. 이 검증용 변형은 원본 파일에 기록하지 않았다.

## 저장 파일

- `scripts/01_check_uniprot.py`: 요청·보존·구조 검증 코드.
- `requirements.txt`, `requirements-lock.txt`: 직접 의존성과 실제 환경 기록.
- `data/raw/20261030T072135Z_8fce6346/`: `sample.json`, `sample.tsv`, `metadata.json`, `validation.json`, `result-fields.json`, `uniprotkb-openapi.json`.
- `data/raw/20261030T072119Z_e06b66f2/metadata.json`: 최초 제한 환경의 네트워크 연결 실패 기록. 성공 결과와 분리했다.
- `data/raw/execution.log`: 성공 실행의 전체 출력.
- `data/raw/documentation/`: 사전 확인한 공식 문서 2개와 출처 메모.
- `data/raw/structure-probe.json`: 사전 PowerShell 구조 확인의 같은 10개 항목 JSON. 정식 검증 원본은 성공 실행 폴더의 `sample.json`이다.
- `../.gitignore`: 로컬 Python·가상환경·캐시를 제외한다. 데이터는 제외하지 않는다.

기존에는 `.git`만 있었고 기존 파일은 수정·삭제하지 않았다. Git commit/push는 하지 않았다.

## 전체 수집 전에 처리할 사항

1. 지금 확인한 20,431건은 이 릴리스/조회 시점 값이다. 전체 수집 시 검색 건수·릴리스 일관성을 다시 확인해야 한다.
2. 페이지네이션, 일시적 429/5xx 재시도, 중단 후 재개와 전체 accession 유일성 검증은 다음 단계에서 구현한다. 이번 코드는 의도적으로 10개에서 멈춘다.
3. Gene ID 누락·복수 매핑·동일 유전자 공유를 전체 데이터에서 점검하되 기본 분석에서 항목을 제거하지 않는다.
4. GO는 accession별 고유 ID 집합으로 세며, 근거 레코드 수를 GO 수로 세지 않는다. GO 없음은 0으로 유지하고 범주 미해석/형식 오류와 구분한다.
5. Evidence 활용 시 `GoEvidenceType`과 선택적인 ECO/출처 배열을 함께 보존한다. 완전한 주석 이벤트별 근거 이력이 필요한지는 후속 단계에서 검토한다.
6. isoform은 추가 행으로 확장하지 않는다. 이 표본의 대표 서열 길이와 항목 단위 GO를 사용했다. 이 10개로 가설이나 상관을 판단하지 않는다.

## 전체 수집 및 전처리

추가 의존성 없이 동일한 `requests==2.32.5`와 Python 표준 라이브러리만 사용한다.
`scripts/01_check_uniprot.py`와 과거 검증 원본은 변경하지 않았다.
연구 조건과 가설은 동일하다. Spearman 분석과 그래프 생성은 아직 수행하지 않는다.

### 실행 명령

프로젝트 폴더 `protein-go-research`에서 실행한다.

```powershell
# 새 수집: 날짜와 UUID가 포함된 새 원본 폴더 생성
.\.venv\Scripts\python.exe scripts\02_collect_uniprot.py

# 이번 실제 수집 및 같은 수집의 재개
.\.venv\Scripts\python.exe scripts\02_collect_uniprot.py --run-dir data\raw\full_20261030

# 완료된 원본의 오프라인 전처리
.\.venv\Scripts\python.exe scripts\03_prepare_dataset.py --run-dir data\raw\full_20261030

# 같은 원본으로 독립된 출력 생성: CSV SHA256 비교 가능
.\.venv\Scripts\python.exe scripts\03_prepare_dataset.py --run-dir data\raw\full_20261030 --output-dir data\processed\reproducibility_check

# 네트워크 없는 회귀 시험
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

새로운 시점에 새 모집단을 수집할 때는 `--run-dir` 없이 실행한다. 기존 실행 디렉터리를 지정하면 동일한 설정과 스냅샷의 재개로 해석한다.
이 환경에서는 네트워크가 제한되어 최초 실행은 연결 실패했으며, 네트워크 접근 권한을 받은 실행에서 실제 수집했다. 실패 기록도 보존한다.

### 수집 파일 및 완료 조건

- `data/raw/full_20261030/json/`, `tsv/`: 두 형식의 독립적인 전체 페이지. 한 페이지당 최대 500개, `includeIsoform=false`.
- `manifest.json`: 상태(`incomplete`/`failed`/`complete`), 검색 조건, 릴리스·전체 건수, 각 페이지의 URL·다음 URL·시각·응답 헤더·SHA256·건수, 수집 세션 이력.
- `request_log.jsonl`: 시도별 URL·시각·HTTP 상태·헤더·오류·백오프 기록.
- `checkpoints/`: 시작/재개 및 종료 시점의 현재 API 스냅샷 확인 응답. 분석 페이지에 합산하지 않는다.
- `errors/`: HTTP 오류 응답 본문. 완료된 데이터 페이지와 분리한다.
- `collection_validation.json`: 두 전체 형식의 교차 검증과 데이터 품질 결과.
- `raw_inventory.json`: 검증된 페이지뿐 아니라 체크포인트·오류·미채택 응답까지 포함한 원본 파일 SHA256 목록.
- `collection_execution.log`: 실제 실행 출력. API 500 오류 및 복구 이력도 포함한다.

요청은 최대 4회(첫 시도 + 재시도 3회)다. 연결 오류·타임아웃·429·5xx만 재시도하며, 기본 1/2/4초 백오프와 `Retry-After`를 적용하되 대기 상한은 60초다. 연결/읽기 타임아웃은 10/60초다.
재개 시 현재 API 스냅샷을 먼저 대조하고, 기존 페이지의 SHA256·요청 URL·스냅샷·구조·개수를 다시 확인한 후 재사용한다. 체크섬이 다른 파일은 조용히 덮어쓰지 않고 실패한다.
각 페이지와 시작·종료 스냅샷에서 릴리스·릴리스 날짜·전체 건수가 일치해야 한다. 현재 값과 과거 기준(`2026_03`, 20,431)의 비교 결과도 별도 기록한다.
다음 페이지가 없을 때까지 수집하고 양쪽 건수·accession 유일성·집합·핵심 필드를 검증한 후에만 `complete`로 표시한다. 중간 실패는 완료로 취급하지 않는다.

일부 대용량 응답은 `requests`의 HTTP 압축 해제 후에도 gzip 본문이었다. 파일 확장자와 별개로 **받은 본문 바이트를 그대로 저장**하며, 읽을 때 gzip magic bytes를 확인해 메모리에서만 해제한다. 원본을 직접 UTF-8로 읽기 전에 `uniprot_dataset.decode_body(path.read_bytes())`를 사용한다. 첫 압축 처리 실패 때 저장한 미채택 응답도 삭제하지 않고 원본 목록에 포함한다.

### 전처리 정의와 검증

원본 JSON만으로 CSV를 생성하고 TSV는 교차 검증에 사용한다. 페이지 순서와 무관하게 accession으로 정렬하고 UTF-8/LF로 기록한다.

| CSV 컬럼 | 정의 |
|---|---|
| accession | JSON Primary Accession |
| protein_name | JSON 권장 전체 이름. 미제공 시 실제 제출 이름이 있을 때만 사용 |
| gene_name | JSON 대표 유전자 이름의 정렬된 고유 목록, `;` 구분 |
| gene_id | JSON GeneID의 정렬된 고유 목록, `;` 구분. 미제공은 빈 문자열 |
| sequence_length | JSON `sequence.length` |
| go_total_count | 단백질별 고유 GO ID 수 |
| go_bp_count | `GoTerm`이 P인 고유 GO ID 수 |
| go_mf_count | `GoTerm`이 F인 고유 GO ID 수 |
| go_cc_count | `GoTerm`이 C인 고유 GO ID 수 |

복수 Gene ID를 하나로 선택하거나 대체하지 않는다. GO가 없는 항목과 Gene ID가 없는 항목도 유지한다. GO 상위 용어는 추가하지 않는다.
BP·MF·CC 합집합이 전체 GO 집합과 같은지, 범주 사이 겹침이 있는지 검사한다. 잘못된 GO ID와 불명확한 범주는 accession 및 원래 값과 함께 보고하고 품질 검증을 실패시킨다. 문제를 숨기기 위해 행을 제거하지 않는다.

핵심 교차 검증은 accession 집합·서열 길이·대표 유전자 이름 집합·Gene ID 집합·전체/범주별 GO 집합·종/Reviewed 상태다.
단백질 이름은 JSON의 권장 이름을 TSV의 첫 이름과 비교한다. TSV는 대체 이름·EC 번호·절단산물 설명도 포함하므로 전체 표시 문자열을 CSV 이름으로 복제하지 않는다.
전체 응답에서 복수 대표 유전자 이름이 `DEFB4A; DEFB4B`처럼 세미콜론으로 구분되는 것을 확인하여 해당 구분자로 파싱한다. JSON의 모든 대표 이름과 집합으로 대조한다.
서열 문자열 길이와 `sequence.length`도 대조한다.

전처리는 원본 체크섬·페이지 체인·헤더의 스냅샷을 다시 검증한다. 원본 manifest가 완료 상태가 아니거나 품질 검증이 실패하면 정상 CSV를 새로 생성하지 않는다. 기존 출력이 있는 실패 재실행에서는 메타데이터의 `validation_failed`를 확인해야 한다.
`quality_report.json`에는 누락·복수 Gene ID, 공유 Gene ID별 accession 목록, GO 0개, 형식/범주/집합/교차 검증 오류와 원본 체크섬이 있다. 공유 accession 수는 두 개 이상 accession에 연결된 Gene ID 중 하나 이상을 가지는 accession의 합집합 크기다.
`dataset_metadata.json`에는 CSV·품질 보고서·원본 manifest·전처리 코드의 SHA256을 기록한다. 실행 시각처럼 매번 달라지는 값은 분석 CSV와 결정적 품질 보고서에 넣지 않는다.

회귀 시험은 기존 실제 표본과 모의 네트워크를 사용하며, HTTP 재시도 제한, 비재시도 오류, 페이지 재사용, 릴리스/전체 건수 변경, 체크섬 훼손, 핵심 필드 불일치, GO 오류·중복·0개 유지 등을 검증한다. 실제 모집단 검증 결과와 모의 시험 결과는 구분한다.

### 전체 수집 실제 결과 — 2026-10-30

전체 실행 시작은 07:34:56 UTC (16:34:56 KST), 검증 후 완료는 07:47:22 UTC (16:47:22 KST)다. 시작 시각에는 최초 네트워크 제한 실패도 포함되며 세션별 시각은 manifest에 있다.
릴리스는 `2026_03` (릴리스 날짜 2026-09-02), API 전체 건수는 20,431이다. 이전 소량 검증과 동일하다.
JSON 41페이지와 TSV 41페이지를 수집했다. 최종 재개 실행에서 82개 페이지를 SHA256으로 검증하여 모두 재사용하고 현재 API 시작/종료 스냅샷과 최종 교차 검증을 통과했다.

| 검증 항목 | 실제 결과 |
|---|---:|
| API 전체 건수 | 20,431 |
| JSON 고유 accession | 20,431 |
| TSV 고유 accession | 20,431 |
| 분석 CSV 행 수 | 20,431 |
| JSON/TSV accession 중복 | 각각 0 |
| accession 집합 차이 | 0 |
| 길이 누락·비정상 값 및 서열 문자열 길이 불일치 | 0 |
| GO 주석 0개 항목 | 1,056 |
| Gene ID 누락 항목 | 1,277 |
| 고유 Gene ID 복수 매핑 항목 | 99 |
| 둘 이상 accession이 공유하는 Gene ID | 52 |
| 위 공유 Gene ID 중 하나 이상을 가지는 고유 accession | 90 |
| 잘못된 GO ID 형식 | 0 |
| GO 범주 분류·합집합 불일치·범주 간 겹침 | 각각 0 |
| 같은 단백질의 중복 GO ID | 0 |
| JSON/TSV 핵심 필드 불일치 | 0 |
| GO evidence type 미제공 참조 | 0 |
| 상세 ECO 배열 미제공 GO 참조 | 114,057 |

최초 전체 검증은 당시 실행 중이던 파서에서 TSV 복수 유전자 구분자 68건 및 `[Cleaved into: ...]`/`[Includes: ...]` 표시 접미사 80건을 불일치로 보고했다. `collection_validation_before_parser_fix.json`에 실패 결과를 보존했다. 실제 반환 형식에 맞게 파싱을 수정하고 원본을 변경하지 않은 채 재검증하여 최종 불일치 0건을 확인했다. 비교 대상은 JSON 권장 이름과 TSV 첫 이름이며 접미사의 대체 이름/절단산물 목록은 비교 대상이 아니다.

최종 분석용 파일은 `data/processed/full_20261030/protein_go_dataset.csv`이며 정확한 컬럼은 아래 9개다.

```text
accession,protein_name,gene_name,gene_id,sequence_length,go_total_count,go_bp_count,go_mf_count,go_cc_count
```

CSV SHA256: `a1b62f7bcb6524f53fb93cef4efc48744e96ed7a3bc33c71318473f0913bf567`.
같은 원본으로 독립 출력 디렉터리에 전처리를 다시 실행하여 CSV, `quality_report.json`, `dataset_metadata.json`의 SHA256이 각각 동일함을 확인했다. 결과는 `data/processed/full_20261030/reproducibility_report.json`에 보존했다.
CSV를 다시 읽어 행 수·accession 유일성·GO 0개·Gene ID 누락/복수·GO 범주별 합계를 대조했고, 원본 목록의 93개 파일 체크섬과 기존 소량 검증 응답 체크섬도 확인했다. 회귀 시험 9개가 실제 통과했다(`tests/test_results.log`).
`quality_report.json`과 `dataset_metadata.json`도 같은 출력 디렉터리에 있다. 누락·복수·공유 Gene ID의 accession별 목록을 품질 보고서에 기록했다.
GO 0개와 Gene ID 누락·복수·공유 항목은 모두 유지했다. 이 값은 자료의 주석/매핑 현황이며 검증 오류로 취급하지 않았다.
Evidence type은 확보했지만 상세 ECO/문헌 배열은 일부만 제공된다. 원본 JSON이 제공한 범위만 보존했고 빈 근거를 생성하거나 보충하지 않았다.
현재 검증 기준에서 해결되지 않은 구조적 오류는 없으며, 주석 밀도와 유전자 공유에 따른 해석상 한계는 후속 분석에서 고려해야 한다.

추가/변경 파일: `scripts/02_collect_uniprot.py`, `scripts/03_prepare_dataset.py`, `scripts/uniprot_dataset.py`, `tests/test_pipeline.py`, `tests/test_results.log`, 이 README, `data/raw/full_20261030/`의 수집 원본·기록, `data/processed/`의 데이터셋·보고서. `requirements.txt`, `requirements-lock.txt`, `.gitignore`, 소량 검증 스크립트와 당시 원본은 변경하지 않았다.

## 통계 분석 및 시각화

분석 입력: `data/processed/full_20261030/protein_go_dataset.csv` (20,431행).
기존 원본·전처리 CSV·품질 보고서와 기존 스크립트는 변경하지 않았다. 논문 본문 및 Git commit/push는 진행하지 않았다.

프로젝트 폴더에서 실행한다.

```powershell
# 일반 Python 가상환경
.\.venv\Scripts\python.exe -m pip install -r requirements-analysis.txt
# 이 환경처럼 uv 가상환경을 쓸 때는 위 설치 대신:
uv pip install --python .venv/Scripts/python.exe -r requirements-analysis.txt

.\.venv\Scripts\python.exe scripts\04_analyze_statistics.py
.\.venv\Scripts\python.exe scripts\04_analyze_statistics.py --output-dir results/reproducibility_run --no-figures
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_statistics.py -v

# 두 실행의 CSV 체크섬 확인 (각 파일 쌍이 같아야 함)
Get-FileHash results/statistics/*.csv -Algorithm SHA256
Get-FileHash results/reproducibility_run/statistics/*.csv -Algorithm SHA256
```

직접 의존성은 `requirements-analysis.txt`, 실제 하위 의존성을 포함한 실행 환경은 `requirements-analysis-lock.txt`에 고정했다. 분석은 Python 3.12.14, NumPy 2.5.4, pandas 3.1.0, SciPy 1.18.1, Matplotlib 3.11.2를 사용했다. 기존 수집용 의존성 파일은 보존했다.

기본 옵션은 `--replicates 2000 --seed 20261030`이다. 각 결과에 2,000회, 전체 6개 결과에 총 12,000개 bootstrap rho를 계산한다. 원래 paired row를 복원추출하고 매번 평균 동률 순위를 다시 계산한다. CI는 percentile 2.5/97.5%, 선형 분위수 보간이다. 전체 표본 상관과 양측 p-value는 SciPy spearmanr를 사용한다. 주 분석 p-value의 float64 언더플로에 대비해 같은 t 근사의 로그 꼬리 적분으로 계산한 p-value 문자열과 log10 p도 저장한다. 보조 BP/MF/CC 3개에는 Holm 보정을 추가한다.

실제 결과: 전체 GO rho=0.27045797, 95% CI [0.25697508, 0.28397212], 양측 p≈2.210109×10^-339.
GO 0개 제외(n=19,375) rho=0.23311080; 유전자 기준(n=19,031) rho=0.20132929.
후자는 Gene ID 누락 1,277개, 복수 매핑 99개, 단일 Gene ID 내 후순위 accession 24개를 제외했다. 이 기준은 생물학적 대표 단백질 선정이 아니라 결정적 중복 축소 규칙이다.

생성 파일:

- `scripts/04_analyze_statistics.py`, `tests/test_statistics.py`: 분석 및 계산 검증 코드.
- `results/statistics/descriptive_statistics.csv`: 요청한 기술통계, 왜도, 동률 현황.
- `results/statistics/correlation_results.csv`: 전체 GO와 탐색적 BP/MF/CC 상관, 양측 p, CI, Holm p.
- `results/statistics/sensitivity_results.csv`, `sensitivity_selection.csv`: 민감도 결과 및 accession별 포함·제외 사유.
- `results/statistics/bootstrap_correlations.csv`: 2,000행의 재표본 상관계수.
- `results/statistics/input_validation.json`, `analysis_metadata.json`: 입력 검증, 버전·seed·방법·체크섬.
- `results/statistics/reproducibility_report.json`: 독립 재실행의 통계 결과 비교.
- `results/figures/01_sequence_length_distribution.{png,pdf}`.
- `results/figures/02_go_total_distribution.{png,pdf}`.
- `results/figures/03_length_go_hexbin.{png,pdf}`.
- `results/figures/04_go_category_correlations.{png,pdf}`.
- `results/analysis_report.md`: 실제 계산 결과와 해석을 구분한 분석 기록.
- `results/reproducibility_run/`: 같은 입력·seed로 독립 재실행한 결과.
- `analysis_execution.log`, `analysis_reproducibility_execution.log`, `statistics_tests.log`: 실행 및 시험 로그.

PNG는 300 dpi, PDF는 벡터 출력을 기본으로 한다. 그림은 전체 관측치와 GO 0개를 유지하며 축에 단위와 로그 간격 사용 여부를 표시했다. 주 상관은 로그 변환값으로 대체하지 않았다.
이 데이터는 한 릴리스의 전체 항목이므로 p-value·CI는 행 독립성/교환가능성을 가정한 탐색적 모형 기반 추론이다. 자세한 기술통계, 보정 p-value, 민감도 해석과 한계는 `results/analysis_report.md`를 참고한다.

실제 재현성 검증에서 두 독립 실행의 통계 CSV 5개(기술통계, 상관, 민감도 결과, 선택 이력, bootstrap 분포)와 분석 보고서가 각각 바이트 단위로 일치했다. 저장한 2,000회 bootstrap 값으로 모든 CI를 재계산하여 일치 여부를 확인했고, 원본 CSV 체크섬도 유지됐다. 통계 계산 회귀 시험 2개가 통과했다. PNG 4개는 시각적으로 확인했으며 PDF 4개도 생성·파일 형식을 확인했다. 실행 시각과 그림 생성 여부를 제외한 분석 메타데이터도 동일했다.
