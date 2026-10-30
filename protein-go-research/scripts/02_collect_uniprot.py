"""Collect both formats with bounded retries and hash-verified page resume."""
import argparse
import hashlib
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from uniprot_dataset import FIELDS, QUERY, decode_body, digest, inspect_collection, save, tsv_rows

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://rest.uniprot.org/uniprotkb/search'


def now():
    return datetime.now(timezone.utc).isoformat()


def snapshot(headers):
    h = requests.structures.CaseInsensitiveDict(headers)
    release, date, total = h.get('X-UniProt-Release'), h.get('X-UniProt-Release-Date'), h.get('X-Total-Results')
    if not release or not date or total is None or not total.isdigit():
        raise ValueError('Missing release/release-date/total headers; cannot verify snapshot')
    return {'release': release, 'release_date': date, 'total_results': int(total)}


def retry_delay(header, attempt):
    delay = min(30, 2 ** attempt)
    if header:
        try:
            delay = max(delay, float(header))
        except ValueError:
            try:
                delay = max(delay, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError):
                pass
    return min(60, max(0, delay))


def first_url(fmt, size):
    params = {'query': QUERY, 'format': fmt, 'size': size, 'includeIsoform': 'false'}
    if fmt == 'tsv':
        params['fields'] = ','.join(FIELDS)
    return requests.Request('GET', ENDPOINT, params=params).prepare().url


def check_url(url, fmt, size):
    u = urlparse(url)
    q = parse_qs(u.query)
    expected = parse_qs(urlparse(first_url(fmt, size)).query)
    if u.scheme != 'https' or u.netloc != 'rest.uniprot.org' or u.path != '/uniprotkb/search':
        raise ValueError('Unexpected pagination origin/path')
    if any(q.get(k) != v for k, v in expected.items()) or set(q) - set(expected) - {'cursor'}:
        raise ValueError('Pagination changed query/format/fields/page size/isoform settings')


class Client:
    def __init__(self, directory):
        self.directory = directory
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'protein-go-research/0.2', 'Accept-Encoding': 'gzip'})

    def get(self, url):
        for attempt in range(4):
            event = {'requested_at_utc': now(), 'url': url, 'attempt': attempt + 1}
            response = None
            try:
                response = self.session.get(url, timeout=(10, 60))
                event.update({'received_at_utc': now(), 'http_status': response.status_code,
                              'headers': dict(response.headers), 'response_body_sha256': hashlib.sha256(response.content).hexdigest()})
                if response.status_code != 200:
                    name = f'errors/{uuid.uuid4().hex}.body'
                    (self.directory / name).write_bytes(response.content)
                    event.update({'body_file': name, 'sha256': digest(self.directory / name)})
                if response.status_code == 200:
                    return response
                response.raise_for_status()
                raise ValueError(f'Unexpected HTTP status: {response.status_code}')
            except requests.RequestException as exc:
                event['error'] = str(exc)
                retryable = response is None or response.status_code == 429 or 500 <= response.status_code <= 599
                if not retryable or attempt == 3:
                    raise
                delay = retry_delay(response.headers.get('Retry-After') if response is not None else None, attempt)
                event['backoff_seconds'] = delay
                print(f'Retry {attempt + 1}/3 after {delay}s: {exc}', flush=True)
                time.sleep(delay)
            finally:
                with (self.directory / 'request_log.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        raise RuntimeError('Retries exhausted')


def page_data(content, fmt, size):
    if fmt == 'json':
        obj = json.loads(content)
        rows = obj['results']
        ids = [r['primaryAccession'] for r in rows]
    else:
        rows = tsv_rows(content)
        ids = [r['accession'] for r in rows]
    if not 0 < len(ids) <= size or len(ids) != len(set(ids)):
        raise ValueError('Empty/oversized page or duplicate accession inside page')
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, help='Existing run to resume; otherwise create a new run')
    parser.add_argument('--page-size', type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 500:
        parser.error('page-size must be 1..500')
    directory = args.run_dir.resolve() if args.run_dir else ROOT / 'data/raw' / ('full_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=True)
    for sub in ('json', 'tsv', 'checkpoints', 'errors'):
        (directory / sub).mkdir(exist_ok=True)
    path = directory / 'manifest.json'
    if path.exists():
        manifest = json.loads(path.read_text(encoding='utf-8'))
        if manifest['query'] != QUERY or manifest['page_size'] != args.page_size or manifest['tsv_fields'] != FIELDS:
            raise ValueError('Resume configuration mismatch')
    else:
        manifest = {'schema_version': 1, 'query': QUERY, 'page_size': args.page_size, 'tsv_fields': FIELDS,
                    'include_isoform': False, 'started_at_utc': now(), 'status': 'incomplete',
                    'reference_snapshot': {'release': '2026_03', 'total_results': 20431},
                    'pages': {'json': [], 'tsv': []}, 'sessions': []}
    session = {'started_at_utc': now(), 'python_version': sys.version, 'requests_version': requests.__version__,
               'code_sha256': {p.name: digest(p) for p in (Path(__file__), Path(__file__).with_name('uniprot_dataset.py'))}}
    manifest['sessions'].append(session)
    client = Client(directory)

    def checkpoint(stage):
        response = client.get(first_url('json', 1))
        name = 'checkpoints/' + uuid.uuid4().hex + '.json'
        (directory / name).write_bytes(response.content)
        current = snapshot(response.headers)
        manifest.setdefault('checkpoints', []).append({'stage': stage, 'url': response.url, 'file': name,
                                                       'sha256': digest(directory / name), 'snapshot': current, 'at_utc': now(),
                                                       'headers': dict(response.headers)})
        if 'snapshot' in manifest and manifest['snapshot'] != current:
            raise ValueError(f'Snapshot changed: expected {manifest["snapshot"]}, got {current}')
        manifest['snapshot'] = current
        manifest['reference_comparison'] = {k: current[k] == v for k, v in manifest['reference_snapshot'].items()}
        save(path, manifest)

    try:
        manifest['status'] = 'incomplete'
        checkpoint('start_or_resume')
        for fmt in ('json', 'tsv'):
            url = first_url(fmt, args.page_size)
            seen, urls = set(), set()
            index = 0
            while url:
                check_url(url, fmt, args.page_size)
                if url in urls:
                    raise ValueError('Pagination cycle')
                urls.add(url)
                pages = manifest['pages'][fmt]
                if index < len(pages):
                    page = pages[index]
                    if page['url'] != url or digest(directory / page['file']) != page['sha256'] or page['snapshot'] != manifest['snapshot']:
                        raise ValueError('Cached page URL/checksum/snapshot mismatch; refusing reuse')
                    content = decode_body((directory / page['file']).read_bytes())
                    ids = page_data(content, fmt, args.page_size)
                    if len(ids) != page['count']:
                        raise ValueError('Cached page count mismatch')
                    reused = True
                else:
                    response = client.get(url)
                    current = snapshot(response.headers)
                    name = f'{fmt}/page_{index + 1:05d}_{uuid.uuid4().hex[:8]}.{fmt}'
                    (directory / name).write_bytes(response.content)
                    # Keep even a rejected raw response; it is never a validated page.
                    if current != manifest['snapshot']:
                        raise ValueError(f'Snapshot changed during collection: {current}; raw={name}')
                    ids = page_data(decode_body(response.content), fmt, args.page_size)
                    page = {'url': url, 'file': name, 'sha256': digest(directory / name), 'count': len(ids),
                            'body_encoding': 'gzip' if response.content.startswith(b'\x1f\x8b') else 'utf-8',
                            'snapshot': current, 'received_at_utc': now(), 'headers': dict(response.headers),
                            'next_url': response.links.get('next', {}).get('url')}
                    pages.append(page)
                    save(path, manifest)
                    reused = False
                if seen.intersection(ids):
                    raise ValueError('Duplicate primary accession across pages')
                seen.update(ids)
                url = page['next_url']
                index += 1
                print(f'{fmt} page={index} entries={len(seen)}/{manifest["snapshot"]["total_results"]} reused={reused}', flush=True)
            if index != len(pages) or len(seen) != manifest['snapshot']['total_results']:
                raise ValueError(f'{fmt}: truncated collection or stale cached pages')
        checkpoint('end')
        _, report = inspect_collection(directory, manifest)
        save(directory / 'collection_validation.json', report)
        if not report['passed']:
            raise ValueError(f'Cross-validation failed: {report["issue_counts"]}; see collection_validation.json')
        manifest['status'] = 'complete'
        manifest['finished_at_utc'] = now()
        manifest['validation_sha256'] = digest(directory / 'collection_validation.json')
        print(f'COMPLETE: {directory}; entries={report["json_unique_accessions"]}', flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        manifest['status'] = 'failed'
        session['error'] = f'{type(exc).__name__}: {exc}'
        print(session['error'], file=sys.stderr, flush=True)
        return 1
    finally:
        session['finished_at_utc'] = now()
        inventory = []
        for sub in ('json', 'tsv', 'checkpoints', 'errors'):
            for raw in sorted((directory / sub).iterdir()):
                if raw.is_file():
                    inventory.append({'file': raw.relative_to(directory).as_posix(), 'sha256': digest(raw), 'bytes': raw.stat().st_size})
        save(directory / 'raw_inventory.json', inventory)
        manifest['raw_inventory_sha256'] = digest(directory / 'raw_inventory.json')
        save(path, manifest)
        client.session.close()
        print(f'RUN_DIR={directory}', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
