"""Verify preserved source, offline rerun outputs, and portable SHA256 manifest."""
import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def resolve_member(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f'Path escapes submission: {relative}')
    return path


def members():
    external_path = ROOT / 'data/raw/external_raw_files.json'
    external = {x['local_path'] for x in load(external_path)['files']} if external_path.exists() else set()
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and p.name != 'checksums.sha256'
                  and p.relative_to(ROOT).as_posix() not in external
                  and not any(x in p.parts for x in ('.venv', '__pycache__', 'runtime_cache')))


def compare_rerun(source_project=None):
    failures = []
    source_inventory = load(ROOT / 'provenance/source_inventory.json')
    for item in source_inventory:
        if digest(resolve_member(item['submission'])) != item['sha256']:
            failures.append('Preserved source changed: ' + item['submission'])
        if source_project is not None and digest(source_project / item['source']) != item['sha256']:
            failures.append('Original project changed: ' + item['source'])
    raw = ROOT / 'data/raw/full_20261030'
    manifest = load(raw / 'manifest.json')
    raw_inventory = load(raw / 'raw_inventory.json')
    for item in raw_inventory:
        if digest(raw / item['file']) != item['sha256']:
            failures.append('Raw checksum mismatch: ' + item['file'])
    if digest(raw / 'raw_inventory.json') != manifest['raw_inventory_sha256']:
        failures.append('Raw inventory checksum mismatch')
    sample = ROOT / 'data/raw/20261030T072135Z_8fce6346'
    for item in load(sample / 'metadata.json')['requests']:
        if digest(sample / item['raw_file']) != item['sha256']:
            failures.append('Sample raw checksum mismatch')
    with (ROOT / 'data/processed/full_20261030/protein_go_dataset.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 20431 or len({row['accession'] for row in rows}) != 20431:
        failures.append('Dataset count or accession uniqueness failed')
    input_sha = digest(ROOT / 'data/processed/full_20261030/protein_go_dataset.csv')
    if input_sha != load(ROOT / 'data/processed/full_20261030/dataset_metadata.json')['csv_sha256']:
        failures.append('Input dataset checksum mismatch')
    pairs = []
    for name in ('protein_go_dataset.csv', 'quality_report.json', 'dataset_metadata.json'):
        pairs.append(('data/processed/full_20261030/' + name, 'verification_run/processed/full_20261030/' + name))
    for name in ('descriptive_statistics.csv', 'correlation_results.csv', 'sensitivity_results.csv', 'sensitivity_selection.csv', 'bootstrap_correlations.csv'):
        pairs.append(('results/statistics/' + name, 'verification_run/results/statistics/' + name))
    comparisons = []
    for left, right in pairs:
        a, b = digest(ROOT / left), digest(ROOT / right)
        comparisons.append({'reference': left, 'rerun': right, 'reference_sha256': a, 'rerun_sha256': b, 'identical': a == b})
        if a != b:
            failures.append('Rerun differs: ' + left)
    rerun = load(ROOT / 'verification_run/results/statistics/analysis_metadata.json')
    reference = load(ROOT / 'results/statistics/analysis_metadata.json')
    stable_keys = ('seed', 'bootstrap_replicates_per_analysis', 'ci_method', 'p_value_method', 'selection', 'versions', 'input_sha256', 'output_sha256', 'script_sha256')
    for key in stable_keys:
        if rerun[key] != reference[key]:
            failures.append('Analysis metadata differs: ' + key)
    if not rerun['input_validation']['passed']:
        failures.append('Rerun input validation failed')
    figures = []
    for name in ('01_sequence_length_distribution', '02_go_total_distribution', '03_length_go_hexbin', '04_go_category_correlations'):
        png = ROOT / 'verification_run/results/figures' / (name + '.png')
        pdf = png.with_suffix('.pdf')
        header = png.read_bytes()[:24]
        valid_png = header.startswith(b'\x89PNG\r\n\x1a\n') and len(header) == 24
        dimensions = struct.unpack('>II', header[16:24]) if valid_png else (0, 0)
        valid_pdf = pdf.read_bytes().startswith(b'%PDF-')
        valid = valid_png and min(dimensions) > 0 and valid_pdf
        figures.append({'name': name, 'png_pixels': dimensions, 'png_sha256': digest(png), 'pdf_sha256': digest(pdf), 'valid': valid})
        if not valid:
            failures.append('Figure not generated correctly: ' + name)
    test_log = (ROOT / 'verification_run/logs/tests.log').read_text(encoding='utf-8')
    tests_passed = 'Ran 11 tests' in test_log and test_log.rstrip().endswith('OK')
    if not tests_passed:
        failures.append('Expected 11 successful tests not found in tests.log')
    with (ROOT / 'verification_run/results/statistics/correlation_results.csv').open(encoding='utf-8', newline='') as stream:
        correlations = list(csv.DictReader(stream))
    with (ROOT / 'verification_run/results/statistics/sensitivity_results.csv').open(encoding='utf-8', newline='') as stream:
        sensitivity = list(csv.DictReader(stream))
    paper_present = bool(list((ROOT / 'paper').glob('*.pdf')))
    report = {'passed': not failures, 'failures': failures, 'input_rows': len(rows), 'input_sha256': input_sha,
              'preserved_source_files_verified': len(source_inventory), 'original_project_checked': source_project is not None,
              'raw_inventory_files_verified': len(raw_inventory), 'json_pages': len(manifest['pages']['json']), 'tsv_pages': len(manifest['pages']['tsv']),
              'snapshot': manifest['snapshot'], 'artifact_comparisons': comparisons, 'analysis_metadata_stable_fields_identical': not any('metadata' in f for f in failures),
              'figures': figures, 'tests_passed': tests_passed, 'tests_count': 11, 'correlations': correlations, 'sensitivity': sensitivity,
              'api_recalled': False, 'paper_pdf_present': paper_present, 'final_submission_complete': False,
              'notes': [('Paper PDF is present; PDF review and archive verification are recorded separately.' if paper_present else 'Paper PDF must be added before final ZIP creation.'), 'This report verifies reproducibility, not upload to a submission system.', 'New PDF figure metadata may include new creation times; statistical CSVs are compared byte-for-byte.']}
    target = ROOT / 'verification_run/reproducibility_report.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'failures': failures, 'source_files': len(source_inventory), 'raw_files': len(raw_inventory), 'comparisons': len(comparisons), 'tests_count': 11, 'report': str(target)}, ensure_ascii=False, indent=2))
    return not failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-rerun', action='store_true')
    parser.add_argument('--source-project', type=Path, help='Optional read-only original-project comparison')
    parser.add_argument('--write-manifest', action='store_true')
    parser.add_argument('--verify-checksums', action='store_true')
    args = parser.parse_args()
    if not any((args.compare_rerun, args.write_manifest, args.verify_checksums)):
        parser.error('Select at least one verification action')
    if args.compare_rerun and not compare_rerun(args.source_project):
        return 1
    path = ROOT / 'checksums.sha256'
    if args.write_manifest:
        files = members()
        path.write_text(''.join(digest(p) + '  ' + p.relative_to(ROOT).as_posix() + '\n' for p in files), encoding='utf-8', newline='\n')
        print(f'Wrote SHA256 manifest: {len(files)} files')
    if args.verify_checksums:
        recorded = []
        for line in path.read_text(encoding='utf-8').splitlines():
            expected, relative = line.split('  ', 1)
            if digest(resolve_member(relative)) != expected:
                raise ValueError('Checksum mismatch: ' + relative)
            recorded.append(relative)
        current = {p.relative_to(ROOT).as_posix() for p in members()}
        if set(recorded) != current or len(recorded) != len(current):
            raise ValueError('Unlisted, missing, or duplicate files in checksum manifest')
        print(f'PASS: SHA256 and file inventory verified for {len(recorded)} files')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
