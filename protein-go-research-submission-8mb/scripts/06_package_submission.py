"""Create one submission ZIP and verify extraction, hashes and required files."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'protein-go-research-submission-8mb.zip')
    parser.add_argument('--extract-dir', type=Path, default=ROOT.parent / 'protein-go-research-submission-8mb-extracted-check')
    args = parser.parse_args()
    archive = args.output.resolve()
    extraction = args.extract_dir.resolve()
    if archive.exists() or extraction.exists():
        raise ValueError('ZIP or extraction path already exists; choose new output paths')
    if archive.is_relative_to(ROOT) or extraction.is_relative_to(ROOT):
        raise ValueError('ZIP and extraction paths must be outside the source submission folder')
    report_path = archive.with_name(archive.stem + '-zip-validation.json')
    checksum_path = archive.with_suffix('.zip.sha256')
    if report_path.exists() or checksum_path.exists():
        raise ValueError('Archive report/checksum path already exists')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run([sys.executable, str(ROOT / 'scripts/05_verify_submission.py'), '--verify-checksums'], check=True, env=env)
    reproduction = json.loads((ROOT / 'verification_run/reproducibility_report.json').read_text(encoding='utf-8'))
    paper_review = json.loads((ROOT / 'verification_run/paper_validation.json').read_text(encoding='utf-8'))
    if not reproduction['passed'] or not paper_review['passed']:
        raise ValueError('Reproducibility/PDF gate failed')
    external = json.loads((ROOT / 'data/raw/external_raw_files.json').read_text(encoding='utf-8'))
    public = json.loads((ROOT / 'verification_run/public_raw_verification.json').read_text(encoding='utf-8'))
    if not public['passed'] or public['authentication_used'] or public['files_verified'] != external['file_count'] or public['commit'] != external['commit']:
        raise ValueError('Anonymous public raw-data restoration has not been verified')
    paper = ROOT / paper_review['file']
    if sha(paper) != paper_review['sha256'] or not paper.read_bytes().startswith(b'%PDF-'):
        raise ValueError('Reviewed paper PDF changed or is invalid')
    files = []
    for line in (ROOT / 'checksums.sha256').read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        p = (ROOT / relative).resolve()
        if not p.is_relative_to(ROOT) or sha(p) != expected:
            raise ValueError('Invalid manifest member: ' + relative)
        files.append(p)
    files.append(ROOT / 'checksums.sha256')
    expected_entries = {ROOT.name + '/' + p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    required = ['paper/' + paper.name, 'README.md', 'requirements.txt', 'AI_and_My_Decisions.md',
                'data/raw/full_20261030/manifest.json', 'data/processed/full_20261030/protein_go_dataset.csv',
                'scripts/03_prepare_dataset.py', 'scripts/04_analyze_statistics.py']
    if any(ROOT.name + '/' + r not in expected_entries for r in required):
        raise ValueError('Missing required submission component')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for p in files:
            z.write(p, ROOT.name + '/' + p.relative_to(ROOT).as_posix())
    if archive.stat().st_size >= 8_000_000:
        raise ValueError('Upload ZIP must be strictly smaller than 8,000,000 bytes')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC test failed')
        names = z.namelist()
        if set(names) != set(expected_entries) or len(names) != len(expected_entries):
            raise ValueError('ZIP inventory mismatch')
        extraction.mkdir(parents=True, exist_ok=False)
        for name in names:
            if not (extraction / name).resolve().is_relative_to(extraction):
                raise ValueError('Unsafe ZIP path')
        z.extractall(extraction)
    for name, expected in expected_entries.items():
        if sha(extraction / name) != expected:
            raise ValueError('Extracted file differs: ' + name)
    extracted_root = extraction / ROOT.name
    checked = subprocess.run([sys.executable, str(extracted_root / 'scripts/05_verify_submission.py'), '--verify-checksums'],
                             check=True, capture_output=True, text=True, env=env)
    cache = extracted_root / 'verification_run/runtime_cache'
    (cache / 'tmp').mkdir(parents=True, exist_ok=True)
    test_env = {**env, 'MPLCONFIGDIR': str(cache / 'matplotlib'), 'TEMP': str(cache / 'tmp'), 'TMP': str(cache / 'tmp')}
    tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                           cwd=extracted_root, capture_output=True, text=True, env=test_env)
    if tests.returncode != 0 or 'Ran 11 tests' not in tests.stderr or not tests.stderr.rstrip().endswith('OK'):
        raise ValueError('Tests failed in extracted lightweight package: ' + tests.stderr[-2000:])
    if any((extracted_root / x['local_path']).exists() for x in external['files']):
        raise ValueError('Large external raw files accidentally included in ZIP')
    report = {'passed': True, 'verified_at_utc': datetime.now(timezone.utc).isoformat(),
              'zip_file': archive.name, 'zip_bytes': archive.stat().st_size, 'zip_sha256': sha(archive),
              'archive_file_count': len(files), 'zip_crc_passed': True, 'exact_file_inventory_passed': True,
              'upload_limit_bytes': 8_000_000, 'under_upload_limit': True,
              'raw_files_excluded_from_zip': external['file_count'], 'raw_bytes_external': external['total_bytes'],
              'public_raw_repository': external['repository'], 'public_raw_commit': external['commit'],
              'anonymous_raw_download_verified': True,
              'extracted_offline_tests_passed': True, 'extracted_offline_test_count': 11,
              'all_extracted_file_sha256_match': True, 'extracted_checksum_verifier_stdout': checked.stdout.strip(),
              'paper_file': paper_review['file'], 'paper_sha256': sha(paper), 'paper_pages': paper_review['pages'],
              'required_components_present': required, 'environment_and_runtime_caches_excluded': True,
              'reproducibility_report_passed': True, 'extracted_folder': str(extracted_root),
              'submission_system_uploaded': False, 'notes': ['Archive packaging verified; no submission-system upload or Git commit/push performed.']}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    checksum_path.write_text(report['zip_sha256'] + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
