import unittest
from unittest.mock import patch
from backend import sec_discovery as sec, studio


def payload():
    return {'cik': '0000001234', 'name': 'Orchard Fixture Corp', 'filings': {'recent': {
        'accessionNumber': ['0000001234-26-000001'], 'filingDate': ['2026-11-17'],
        'form': ['10-K'], 'primaryDocument': ['orchard.htm']}}}


class SecDiscoveryTest(unittest.TestCase):
    def test_destination_and_declared_contact(self):
        url, agent = sec.submissions_request('1234', 'fixture@example.invalid')
        self.assertEqual(url, 'https://data.sec.gov/submissions/CIK0000001234.json')
        self.assertEqual(agent, 'ALMG/1.0 fixture@example.invalid')
        for cik, contact in [('0', 'a@b.com'), ('../1234', 'a@b.com'), ('1234', 'a@b.com\r\nInjected: yes'), ('1234', '')]:
            with self.assertRaises(ValueError):
                sec.submissions_request(cik, contact)

    def test_metadata_identity_and_safe_filing_urls(self):
        rows = sec.filing_candidates(payload(), '1234')
        self.assertEqual(rows[0]['source'], 'https://www.sec.gov/Archives/edgar/data/1234/000000123426000001/orchard.htm')
        self.assertEqual(rows[0]['reuse_status'], 'unverified')
        for field, value in [('primaryDocument', '../escape.htm'), ('primaryDocument', 'https://evil.invalid'),
                             ('filingDate', '2026-99-01'), ('form', '10-K\n'), ('accessionNumber', 'invalid')]:
            item = payload(); item['filings']['recent'][field] = [value]
            self.assertEqual(sec.filing_candidates(item, '1234'), [])
        with self.assertRaises(ValueError):
            sec.filing_candidates(payload(), '4321')
        item = payload(); item['filings']['recent']['form'] = []
        with self.assertRaises(ValueError):
            sec.filing_candidates(item, '1234')

    def test_worker_requests_only_approved_submissions(self):
        job = {}
        with patch.object(studio, 'request_json', return_value=payload()) as request, patch.object(studio, 'activity'), patch.object(studio, 'update') as update, patch.object(studio.time, 'sleep'):
            studio.search_filings(job, '1234', 'fixture@example.invalid')
        request.assert_called_once_with('https://data.sec.gov/submissions/CIK0000001234.json',
            headers={'User-Agent': 'ALMG/1.0 fixture@example.invalid'}, opener=studio.DISCOVERY)
        self.assertEqual(update.call_args.kwargs['status'], 'filing_candidates')
        self.assertEqual(len(update.call_args.kwargs['filing_candidates']), 1)

    def test_company_matching_is_bounded_local_and_validated(self):
        catalog = {'fields': ['cik', 'name', 'ticker', 'exchange'], 'data': [
            [1234, 'Orchard Fixture Corp', 'ORCH', 'Nasdaq'],
            [1234, 'Orchard Duplicate', 'ORCH.B', 'Nasdaq'],
            [4321, 'Astronomy Fixture', 'STAR', None],
            [0, 'Orchard bad CIK', 'BAD', 'X'], [999, 'Orchard\nInvalid', 'BAD', 'X']]}
        rows = sec.company_candidates(catalog, 'oRcH')
        self.assertEqual([row['cik'] for row in rows], ['1234'])
        self.assertEqual(sec.company_candidates(catalog, 'orchard fixture')[0]['ticker'], 'ORCH')
        self.assertEqual(sec.company_candidates(catalog, 'missing'), [])
        with self.assertRaises(ValueError):
            sec.company_candidates({'fields': [], 'data': []}, 'orchard')
        with patch.object(studio, 'request_json', return_value=catalog) as request, patch.object(studio, 'activity'), patch.object(studio, 'update') as update, patch.object(studio.time, 'sleep'):
            studio.search_companies({}, 'orchard', 'fixture@example.invalid')
        request.assert_called_once_with(sec.COMPANY_CATALOG_URL, headers={'User-Agent': 'ALMG/1.0 fixture@example.invalid'}, opener=studio.DISCOVERY)
        self.assertEqual(update.call_args.kwargs['status'], 'company_candidates')
        many = {**catalog, 'data': [[i, f'Orchard {i}', 'O', 'X'] for i in range(1, 30)]}
        self.assertEqual(len(sec.company_candidates(many, 'orchard')), 20)
