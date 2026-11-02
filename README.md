# Protein length and Gene Ontology annotation counts

인간 Reviewed 단백질의 아미노산 서열 길이와 고유 GO 주석 개수의 관계에 관한 탐색적 연구입니다.

- Source: UniProtKB, `organism_id:9606 AND reviewed:true`
- Release: `2026_03`; collection date: 2026-10-30
- Analysis unit: Primary Accession; 20,431 proteins
- Primary Spearman rho: 0.27045797; 95% paired bootstrap CI: [0.25697508, 0.28397212]
- Bootstrap: 2,000 replicates per result; seed: 20261030

GO counts describe recorded annotation terms, not the number of biological functions. The association is exploratory and does not establish causation.

## Project contents

- [Full documentation and execution commands](protein-go-research/README.md)
- [Analysis report](protein-go-research/results/analysis_report.md)
- [Analysis dataset](protein-go-research/data/processed/full_20261030/protein_go_dataset.csv)
- [Statistical results](protein-go-research/results/statistics/)
- [PNG and PDF figures](protein-go-research/results/figures/)
- [Collection and analysis scripts](protein-go-research/scripts/)
- [Original API responses and provenance](protein-go-research/data/raw/)

## Reproduce the analysis

From `protein-go-research/`, with Python 3.12:

```sh
python -m pip install -r requirements-analysis.txt
python scripts/04_analyze_statistics.py
python scripts/04_analyze_statistics.py --output-dir results/reproducibility_run --no-figures
python -m unittest discover -s tests -v
```

The original API responses, processed dataset, checksums, quality reports and independent rerun results are included. Some large JSON response bodies retain gzip compression; the supplied reader detects gzip magic bytes before parsing. See the project documentation for details.

Local Python installations, virtual environments and caches are excluded. `.gitattributes` disables newline conversion to preserve the exact bytes used by the recorded SHA-256 checksums.

## 과제 10 제출 — 총 업로드 8MB 제한

- [8MB 미만 제출용 ZIP](protein-go-research-submission-8mb.zip): 논문 PDF, 분석 CSV, 코드, 결과·그림과 실행 안내를 포함합니다.
- [제출용 README](protein-go-research-submission-8mb/README.md): 공개 원자료 링크, 다운로드·체크섬 검증 및 오프라인 재현 절차.
- [고정 커밋의 전체 원자료](https://github.com/arnixs115/protein-go-research/tree/7d7cc33078aa8b684534f03ef339b46789f01a14/protein-go-research/data/raw): 큰 응답 파일 83개는 ZIP에서 제외하고 이 공개 주소에서 복원합니다.

`protein-go-research-submission-8mb/scripts/07_restore_raw_data.py`는 고정 커밋의 응답을 인증 없이 내려받고 파일별 SHA256을 확인합니다. 원자료 다운로드는 UniProt API 재수집이 아닙니다. 기존 전체 원자료와 검증된 분석 결과는 변경하지 않았습니다. 과제 업로드 대상은 작은 ZIP 1개이며, 기존 약 182MB ZIP은 사용하지 않습니다.
