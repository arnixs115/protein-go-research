"""Restore exact omitted raw files from a public, commit-pinned GitHub URL."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true', help='Verify restored files without any network calls')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'data/raw/external_raw_files.json').read_text(encoding='utf-8'))
    repo, commit = manifest['repository'], manifest['commit']
    if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Public repository and full commit SHA must be configured')
    session = requests.Session()
    session.trust_env = False  # No saved credentials: downloads must be anonymously accessible.
    restored = reused = 0
    try:
        for i, item in enumerate(manifest['files'], 1):
            target = (ROOT / item['local_path']).resolve()
            if not target.is_relative_to(ROOT) or '..' in Path(item['repository_path']).parts:
                raise ValueError('Invalid raw-data manifest path')
            if target.exists():
                if target.stat().st_size != item['bytes'] or sha(target) != item['sha256']:
                    raise ValueError('Existing raw file differs; refusing overwrite: ' + item['local_path'])
                reused += 1
                continue
            if args.verify_only:
                raise FileNotFoundError('Restore missing raw file first: ' + item['local_path'])
            url = f"https://raw.githubusercontent.com/{repo}/{commit}/{item['repository_path']}"
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + '.download')
            for attempt in range(4):
                try:
                    with session.get(url, stream=True, timeout=(10, 60)) as response:
                        response.raise_for_status()
                        h = hashlib.sha256(); size = 0
                        with part.open('wb') as output:
                            for block in response.iter_content(1024 * 1024):
                                size += len(block)
                                if size > item['bytes']:
                                    raise ValueError('Raw response larger than recorded size')
                                output.write(block); h.update(block)
                    if size != item['bytes'] or h.hexdigest() != item['sha256']:
                        raise ValueError('Downloaded raw checksum/size mismatch: ' + item['local_path'])
                    part.replace(target)
                    restored += 1
                    print(f"Restored {i}/{manifest['file_count']}: {item['local_path']}", flush=True)
                    break
                except requests.RequestException as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if attempt == 3 or (status is not None and status != 429 and status < 500):
                        raise
                    time.sleep(min(4, 2 ** attempt))
        report = {'passed': True, 'repository': repo, 'commit': commit,
                          'files_verified': restored + reused, 'downloaded': restored, 'reused': reused,
                          'authentication_used': False, 'uniprot_api_called': False}
        if restored:
            (ROOT / 'verification_run/public_raw_verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        session.close()


if __name__ == '__main__':
    main()
