"""Shared, offline validation. No GO ancestors or identifier imputation."""
import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

QUERY = 'organism_id:9606 AND reviewed:true'
FIELDS = ['accession', 'protein_name', 'gene_primary', 'xref_geneid', 'length',
          'go_p', 'go_f', 'go_c', 'go_id', 'organism_id', 'reviewed']
COLUMNS = ['accession', 'protein_name', 'gene_name', 'gene_id', 'sequence_length',
           'go_total_count', 'go_bp_count', 'go_mf_count', 'go_cc_count']
LABELS = ['Entry', 'Protein names', 'Gene Names (primary)', 'GeneID', 'Length',
          'Gene Ontology (biological process)', 'Gene Ontology (molecular function)',
          'Gene Ontology (cellular component)', 'Gene Ontology IDs', 'Organism (ID)', 'Reviewed']


def decode_body(content):
    # Some large API responses retain a gzip payload after HTTP decoding.
    # Preserve bytes on disk; unwrap only for parsing, based on actual magic bytes.
    for _ in range(2):
        if not content.startswith(b'\x1f\x8b'):
            return content.decode('utf-8')
        content = gzip.decompress(content)
    raise ValueError('Unexpected nested gzip response')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    tmp.replace(path)


def tsv_rows(content):
    reader = csv.reader(io.StringIO(content), delimiter='\t')
    header = next(reader)
    if [s.casefold() for s in header] != [s.casefold() for s in LABELS]:
        raise ValueError(f'Unexpected TSV headers: {header}')
    rows = []
    for row in reader:
        if len(row) != len(FIELDS):
            raise ValueError('Malformed TSV row')
        rows.append(dict(zip(FIELDS, row)))
    return rows


def normalize(entry, issues):
    acc = entry.get('primaryAccession')
    def issue(kind, detail=None):
        issues.append({'accession': acc, 'kind': kind, 'detail': detail})
    if not isinstance(acc, str) or not re.fullmatch(r'[A-Z0-9]+', acc):
        issue('invalid_accession', acc)
    seq = entry.get('sequence', {})
    length = seq.get('length')
    if type(length) is not int or length <= 0:
        issue('invalid_sequence_length', length)
    elif not isinstance(seq.get('value'), str) or len(seq['value']) != length:
        issue('sequence_value_length_mismatch')
    if entry.get('organism', {}).get('taxonId') != 9606 or entry.get('entryType') != 'UniProtKB reviewed (Swiss-Prot)':
        issue('selection_criteria_mismatch')
    desc = entry.get('proteinDescription', {})
    name = desc.get('recommendedName', {}).get('fullName', {}).get('value')
    if not name:
        # Explicit alternative only when a submitted name actually exists.
        submitted = [n.get('fullName', {}).get('value') for n in desc.get('submissionNames', [])]
        name = next((n for n in submitted if n), '')
        if not name:
            issue('missing_protein_name')
    genes = sorted({g['geneName']['value'] for g in entry.get('genes', []) if g.get('geneName', {}).get('value')})
    refs = entry.get('uniProtKBCrossReferences', [])
    gene_ids = sorted({r['id'] for r in refs if r.get('database') == 'GeneID'})
    if any(not re.fullmatch(r'\d+', g) for g in gene_ids):
        issue('invalid_gene_id', gene_ids)
    go = set()
    categories = {'BP': set(), 'MF': set(), 'CC': set()}
    go_occurrences = []
    evidence_missing = eco_missing = 0
    for ref in refs:
        if ref.get('database') != 'GO':
            continue
        gid = ref.get('id')
        if not isinstance(gid, str) or not re.fullmatch(r'GO:\d{7}', gid):
            issue('invalid_go_id', gid)
        # Keep observed string identifiers even when invalid; fail quality gate.
        if isinstance(gid, str):
            go.add(gid)
            go_occurrences.append(gid)
        terms = [p.get('value') for p in ref.get('properties', []) if p.get('key') == 'GoTerm']
        if len(terms) != 1 or not isinstance(terms[0], str) or not re.fullmatch(r'[PFC]:.+', terms[0]):
            issue('go_category_error', {'id': gid, 'terms': terms})
        elif isinstance(gid, str):
            categories[{'P': 'BP', 'F': 'MF', 'C': 'CC'}[terms[0][0]]].add(gid)
        if not any(p.get('key') == 'GoEvidenceType' and p.get('value') for p in ref.get('properties', [])):
            evidence_missing += 1
        if not ref.get('evidences'):
            eco_missing += 1
    if go != set().union(*categories.values()):
        issue('go_union_mismatch')
    if sum(map(len, categories.values())) != len(set().union(*categories.values())):
        issue('go_cross_category_overlap')
    return {'accession': acc, 'protein_name': name, 'gene_name': ';'.join(genes),
            'gene_id': ';'.join(gene_ids), 'sequence_length': length,
            'go_total_count': len(go), 'go_bp_count': len(categories['BP']),
            'go_mf_count': len(categories['MF']), 'go_cc_count': len(categories['CC']),
            '_go': go, '_categories': categories, '_genes': genes, '_gene_ids': gene_ids,
            '_go_duplicates': {g: n for g, n in Counter(go_occurrences).items() if n > 1},
            '_evidence_missing': evidence_missing, '_eco_missing': eco_missing}


def compare(item, row, issues):
    acc = item['accession']
    def mismatch(field, value=None):
        issues.append({'accession': acc, 'kind': 'json_tsv_mismatch', 'detail': {'field': field, 'tsv': value}})
    if not row['length'].isdigit() or int(row['length']) != item['sequence_length']:
        mismatch('length', row['length'])
    if row['organism_id'] != '9606' or row['reviewed'] != 'reviewed':
        mismatch('selection_criteria')
    # TSV adds alternative names, EC numbers, and nested chain descriptions.
    # Compare the JSON canonical name as a complete leading name, not synonyms.
    name = item['protein_name']
    if not name or not (row['protein_name'] == name or any(row['protein_name'].startswith(name + suffix) for suffix in (' (', ' ['))):
        mismatch('canonical_protein_name', row['protein_name'])
    if {s.strip() for s in row['gene_primary'].split(';') if s.strip()} != set(item['_genes']):
        mismatch('gene_primary', row['gene_primary'])
    if {s.strip() for s in row['xref_geneid'].split(';') if s.strip()} != set(item['_gene_ids']):
        mismatch('gene_id', row['xref_geneid'])
    for field, expected in [('go_id', item['_go']), ('go_p', item['_categories']['BP']),
                            ('go_f', item['_categories']['MF']), ('go_c', item['_categories']['CC'])]:
        cell = row[field]
        tokens = [s.strip() for s in cell.split(';') if s.strip()]
        pattern = r'GO:\d{7}' if field == 'go_id' else r'.+ \[GO:\d{7}\]'
        if any(not re.fullmatch(pattern, t) for t in tokens):
            mismatch(field + '_format', cell)
        if set(re.findall(r'GO:\d{7}', cell)) != expected:
            mismatch(field, cell)


def inspect_collection(directory, manifest):
    directory = Path(directory)
    items, tsv, issues = {}, {}, []
    duplicate_json, duplicate_tsv = [], []
    fingerprints = []
    for fmt in ('json', 'tsv'):
        pages = manifest['pages'][fmt]
        if not pages:
            raise ValueError(f'No {fmt} pages')
        for index, page in enumerate(pages):
            if page['snapshot'] != manifest['snapshot']:
                raise ValueError('Mixed snapshots in raw manifest')
            headers = {k.lower(): v for k, v in page['headers'].items()}
            if (headers.get('x-uniprot-release') != manifest['snapshot']['release'] or
                headers.get('x-uniprot-release-date') != manifest['snapshot']['release_date'] or
                headers.get('x-total-results') != str(manifest['snapshot']['total_results'])):
                raise ValueError('Raw page headers disagree with snapshot')
            url = urlparse(page['url'])
            query = parse_qs(url.query)
            if (url.scheme != 'https' or url.netloc != 'rest.uniprot.org' or url.path != '/uniprotkb/search' or
                query.get('query') != [QUERY] or query.get('format') != [fmt] or
                query.get('includeIsoform') != ['false'] or query.get('size') != [str(manifest['page_size'])] or
                (fmt == 'tsv' and query.get('fields') != [','.join(FIELDS)])):
                raise ValueError('Raw manifest request settings mismatch')
            if (index == 0 and 'cursor' in query) or (index and pages[index - 1]['next_url'] != page['url']):
                raise ValueError('Broken raw pagination chain')
            if index == len(pages) - 1 and page['next_url'] is not None:
                raise ValueError('Raw pagination is incomplete')
            path = directory / page['file']
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Raw path escapes collection directory')
            if digest(path) != page['sha256']:
                raise ValueError(f'Raw checksum mismatch: {path}')
            fingerprints.append({'file': page['file'], 'sha256': page['sha256']})
            if fmt == 'json':
                entries = json.loads(decode_body(path.read_bytes()))['results']
                if len(entries) != page['count']:
                    raise ValueError('JSON page count mismatch')
                for entry in entries:
                    item = normalize(entry, issues)
                    acc = item['accession']
                    if acc in items:
                        duplicate_json.append(acc)
                    items[acc] = item
            else:
                rows = tsv_rows(decode_body(path.read_bytes()))
                if len(rows) != page['count']:
                    raise ValueError('TSV page count mismatch')
                for row in rows:
                    acc = row['accession']
                    if acc in tsv:
                        duplicate_tsv.append(acc)
                    tsv[acc] = row
    only_json, only_tsv = sorted(items.keys() - tsv.keys()), sorted(tsv.keys() - items.keys())
    for acc in sorted(items.keys() & tsv.keys()):
        compare(items[acc], tsv[acc], issues)
    total = manifest['snapshot']['total_results']
    counts_match = all(sum(p['count'] for p in manifest['pages'][fmt]) == total for fmt in ('json', 'tsv')) and len(items) == len(tsv) == total
    gene_groups = defaultdict(set)
    for acc, item in items.items():
        for gid in item['_gene_ids']:
            gene_groups[gid].add(acc)
    shared = {g: sorted(v) for g, v in sorted(gene_groups.items()) if len(v) > 1}
    counts = Counter(i['kind'] for i in issues)
    for kind in ('invalid_sequence_length', 'sequence_value_length_mismatch', 'invalid_go_id',
                 'go_category_error', 'go_union_mismatch', 'go_cross_category_overlap', 'json_tsv_mismatch'):
        counts.setdefault(kind, 0)
    report = {'passed': counts_match and not duplicate_json and not duplicate_tsv and not only_json and not only_tsv and not issues,
              'api_total_results': total, 'json_unique_accessions': len(items), 'tsv_unique_accessions': len(tsv),
              'counts_match': counts_match, 'duplicate_json_accessions': duplicate_json,
              'duplicate_tsv_accessions': duplicate_tsv, 'only_json_accessions': only_json, 'only_tsv_accessions': only_tsv,
              'go_zero_entries': sum(i['go_total_count'] == 0 for i in items.values()),
              'gene_id_missing_entries': sum(not i['_gene_ids'] for i in items.values()),
              'gene_id_multiple_entries': sum(len(i['_gene_ids']) > 1 for i in items.values()),
              'gene_id_missing_accessions': sorted(a for a, i in items.items() if not i['_gene_ids']),
              'gene_id_multiple_mappings': {a: i['_gene_ids'] for a, i in sorted(items.items()) if len(i['_gene_ids']) > 1},
              'shared_gene_id_count': len(shared),
              'accessions_sharing_gene_id_count': len(set().union(*map(set, shared.values()))) if shared else 0,
              'shared_gene_ids': shared, 'issue_counts': dict(sorted(counts.items())), 'issues': issues,
              'json_tsv_mismatch_accession_count': len({i['accession'] for i in issues if i['kind'] == 'json_tsv_mismatch'}),
              'go_duplicate_entry_count': sum(bool(i['_go_duplicates']) for i in items.values()),
              'go_duplicate_ids': {a: i['_go_duplicates'] for a, i in sorted(items.items()) if i['_go_duplicates']},
              'go_refs_without_evidence_type': sum(i['_evidence_missing'] for i in items.values()),
              'go_refs_without_eco_array': sum(i['_eco_missing'] for i in items.values()),
              'raw_checksums': fingerprints}
    return items, report
