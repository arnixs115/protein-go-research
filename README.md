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
