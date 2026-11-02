"""Regression tests using saved sample and mocked network only."""
import copy
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import uniprot_dataset as data

spec = importlib.util.spec_from_file_location('collector', ROOT / 'scripts/02_collect_uniprot.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
SAMPLE = ROOT / 'data/raw/20261030T072135Z_8fce6346'


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((SAMPLE / 'sample.json').read_text(encoding='utf-8'))
        self.rows = data.tsv_rows((SAMPLE / 'sample.tsv').read_text(encoding='utf-8'))

    def test_original_sample_cross_validation_and_zero(self):
        issues = []
        items = {e['primaryAccession']: data.normalize(e, issues) for e in self.payload['results']}
        for row in self.rows:
            data.compare(items[row['accession']], row, issues)
        self.assertEqual(issues, [])
        self.assertEqual(items['A0JP26']['go_total_count'], 0)
        self.assertEqual(items['A0A0C5B5G6']['gene_id'], '')

    def test_duplicate_and_bad_category_are_visible(self):
        entry = copy.deepcopy(self.payload['results'][0])
        ref = next(r for r in entry['uniProtKBCrossReferences'] if r['database'] == 'GO')
        baseline = data.normalize(entry, [])
        entry['uniProtKBCrossReferences'].append(copy.deepcopy(ref))
        issues = []
        item = data.normalize(entry, issues)
        self.assertEqual(item['go_total_count'], baseline['go_total_count'])
        self.assertTrue(item['_go_duplicates'])
        self.assertFalse(issues)
        ref['properties'] = [{'key': 'GoTerm', 'value': 'X:unknown'}]
        data.normalize(entry, issues)
        self.assertTrue(any(i['kind'] == 'go_category_error' for i in issues))

    def test_bad_id_length_and_union_are_not_silent(self):
        entry = copy.deepcopy(self.payload['results'][0])
        entry['sequence']['length'] = -1
        ref = next(r for r in entry['uniProtKBCrossReferences'] if r['database'] == 'GO')
        ref['id'] = 'GO:bad'
        ref['properties'] = []
        issues = []
        data.normalize(entry, issues)
        self.assertTrue({'invalid_go_id', 'invalid_sequence_length', 'go_category_error', 'go_union_mismatch'} <= {i['kind'] for i in issues})

    def test_gzip_and_url_guard(self):
        original = (SAMPLE / 'sample.json').read_bytes()
        self.assertEqual(data.decode_body(gzip.compress(original)), original.decode('utf-8'))
        collector.check_url(collector.first_url('json', 500), 'json', 500)
        with self.assertRaises(ValueError):
            collector.check_url(collector.first_url('json', 500).replace('rest.uniprot.org', 'example.org'), 'json', 500)
        with self.assertRaises(ValueError):
            collector.check_url(collector.first_url('json', 500).replace('reviewed%3Atrue', 'reviewed%3Afalse'), 'json', 500)

    def test_core_field_mismatch_and_multiple_gene_ids(self):
        entry = copy.deepcopy(self.payload['results'][1])
        entry['uniProtKBCrossReferences'].append({'database': 'GeneID', 'id': '999999'})
        issues = []
        item = data.normalize(entry, issues)
        self.assertEqual(item['gene_id'], '100128908;999999')
        row = self.rows[1].copy()
        row.update(length='0', protein_name='different', gene_primary='wrong', go_id='GO:1234567')
        data.compare(item, row, issues)
        fields = {i['detail']['field'] for i in issues if i['kind'] == 'json_tsv_mismatch'}
        self.assertTrue({'length', 'canonical_protein_name', 'gene_primary', 'gene_id', 'go_id'} <= fields)

    def test_multiple_primary_gene_names_use_semicolon(self):
        entry = copy.deepcopy(self.payload['results'][1])
        entry['genes'].append({'geneName': {'value': 'OTHER'}})
        row = self.rows[1].copy()
        row['gene_primary'] = 'CIROP; OTHER'
        issues = []
        item = data.normalize(entry, issues)
        data.compare(item, row, issues)
        self.assertEqual(issues, [])
        self.assertEqual(item['gene_name'], 'CIROP;OTHER')

    def test_tsv_cleaved_description_is_not_part_of_canonical_name(self):
        issues = []
        item = data.normalize(self.payload['results'][1], issues)
        row = self.rows[1].copy()
        row['protein_name'] = item['protein_name'] + ' [Cleaved into: example product]'
        data.compare(item, row, issues)
        self.assertEqual(issues, [])
        row['protein_name'] = item['protein_name'] + 'UNEXPECTED'
        data.compare(item, row, issues)
        self.assertTrue(any(i['detail'].get('field') == 'canonical_protein_name' for i in issues))

    def response(self, status, body=b'{}', total='10', release='2026_03'):
        response = requests.Response()
        response.status_code = status
        response._content = body
        response.url = collector.first_url('json', 5)
        response.headers.update({'X-Total-Results': total, 'X-UniProt-Release': release,
                                 'X-UniProt-Release-Date': '02-September-2026'})
        return response

    def test_retry_bounded_and_nonretryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'errors').mkdir()
            client = collector.Client(directory)
            with patch.object(client.session, 'get', side_effect=[self.response(429), self.response(503), self.response(200)]) as get, patch.object(collector.time, 'sleep') as sleep:
                self.assertEqual(client.get('https://rest.uniprot.org/test').status_code, 200)
                self.assertEqual(get.call_count, 3)
                self.assertEqual(sleep.call_count, 2)
            with patch.object(client.session, 'get', return_value=self.response(503)) as get, patch.object(collector.time, 'sleep'):
                with self.assertRaises(requests.HTTPError):
                    client.get('https://rest.uniprot.org/test')
                self.assertEqual(get.call_count, 4)
            with patch.object(client.session, 'get', return_value=self.response(400)) as get:
                with self.assertRaises(requests.HTTPError):
                    client.get('https://rest.uniprot.org/test')
                self.assertEqual(get.call_count, 1)
            client.session.close()

    def test_resume_reuses_verified_page_and_snapshot_drift_fails(self):
        from urllib.parse import parse_qs, urlparse
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            calls = []
            interrupt = [True]
            def get(client, url):
                q = parse_qs(urlparse(url).query)
                calls.append(url)
                if q['size'] == ['1']:
                    return self.response(200, json.dumps({'results': self.payload['results'][:1]}).encode())
                fmt = q['format'][0]
                page = 1 if 'cursor' not in q else 2
                if interrupt[0] and page == 2:
                    raise requests.ConnectionError('simulated interruption')
                selection = slice((page - 1) * 5, page * 5)
                if fmt == 'json':
                    body = json.dumps({'results': self.payload['results'][selection]}).encode()
                else:
                    import csv, io
                    text = io.StringIO()
                    writer = csv.writer(text, delimiter='\t', lineterminator='\n')
                    writer.writerow(data.LABELS)
                    writer.writerows([[row[f] for f in data.FIELDS] for row in self.rows[selection]])
                    body = text.getvalue().encode()
                response = self.response(200, body)
                if page == 1:
                    response.headers['Link'] = '<' + collector.first_url(fmt, 5) + '&cursor=next>; rel="next"'
                return response
            argv = ['collect', '--run-dir', str(directory), '--page-size', '5']
            with patch.object(sys, 'argv', argv), patch.object(collector.Client, 'get', get):
                self.assertEqual(collector.main(), 1)
                manifest = json.loads((directory / 'manifest.json').read_text())
                self.assertEqual(len(manifest['pages']['json']), 1)
                checksum = manifest['pages']['json'][0]['sha256']
                calls.clear()
                interrupt[0] = False
                self.assertEqual(collector.main(), 0)
                self.assertNotIn(collector.first_url('json', 5), calls)
                manifest = json.loads((directory / 'manifest.json').read_text())
                self.assertEqual(manifest['status'], 'complete')
                self.assertEqual(checksum, manifest['pages']['json'][0]['sha256'])
            # A current release change must invalidate completion even with cached pages.
            with patch.object(sys, 'argv', argv), patch.object(collector.Client, 'get', return_value=self.response(200, release='2099_01')):
                self.assertEqual(collector.main(), 1)
                self.assertEqual(json.loads((directory / 'manifest.json').read_text())['status'], 'failed')
            with patch.object(sys, 'argv', argv), patch.object(collector.Client, 'get', return_value=self.response(200, total='11')):
                self.assertEqual(collector.main(), 1)
            page = directory / manifest['pages']['json'][0]['file']
            page.write_bytes(page.read_bytes() + b' ')
            with self.assertRaises(ValueError):
                data.inspect_collection(directory, manifest)


if __name__ == '__main__':
    unittest.main()
