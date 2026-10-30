"""Offline deterministic JSON-derived dataset, gated by raw-data validation."""
import argparse
import csv
import json
from pathlib import Path

from uniprot_dataset import COLUMNS, digest, inspect_collection, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    source = args.run_dir.resolve()
    output = args.output_dir or Path(__file__).resolve().parents[1] / 'data/processed' / source.name
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'complete':
        save(output / 'quality_report.json', {'passed': False, 'error': 'Source manifest is not complete'})
        save(output / 'dataset_metadata.json', {'status': 'validation_failed', 'source_run': source.name})
        raise ValueError('Source manifest is not complete; no dataset produced')
    # Re-read and re-hash all pages; never rely only on a previous passed flag.
    try:
        items, report = inspect_collection(source, manifest)
    except Exception as exc:
        save(output / 'quality_report.json', {'passed': False, 'error': f'{type(exc).__name__}: {exc}'})
        save(output / 'dataset_metadata.json', {'status': 'validation_failed', 'source_run': source.name})
        raise
    report['source_manifest_sha256'] = digest(source / 'manifest.json')
    report['snapshot'] = manifest['snapshot']
    report['csv_columns'] = COLUMNS
    report['protein_name_definition'] = 'JSON recommendedName.fullName.value; submissionNames fallback if present'
    report['multi_value_separator'] = '; (sorted unique values); missing identifiers are empty strings'
    save(output / 'quality_report.json', report)
    if not report['passed']:
        save(output / 'dataset_metadata.json', {'status': 'validation_failed', 'source_run': source.name})
        raise ValueError('Quality validation failed; no dataset produced')
    path = output / 'protein_go_dataset.csv'
    tmp = path.with_suffix('.csv.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(items[a] for a in sorted(items))
    tmp.replace(path)
    save(output / 'dataset_metadata.json', {'status': 'complete', 'source_run': source.name, 'snapshot': manifest['snapshot'],
                                           'row_count': len(items), 'csv_columns': COLUMNS,
                                           'csv_sha256': digest(path), 'quality_report_sha256': digest(output / 'quality_report.json'),
                                           'source_manifest_sha256': digest(source / 'manifest.json'),
                                           'code_sha256': {p.name: digest(p) for p in (Path(__file__), Path(__file__).with_name('uniprot_dataset.py'))}})
    print(json.dumps({k: v for k, v in report.items() if k not in ('issues', 'raw_checksums', 'shared_gene_ids', 'go_duplicate_ids')}, ensure_ascii=False, indent=2))
    print(f'DATASET={path}\nSHA256={digest(path)}')


if __name__ == '__main__':
    main()
