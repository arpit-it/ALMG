"""Offline acceptance coverage for provider consent and project selection."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from backend import chat_history, studio

QUERIES = ['orchard fruit', 'astronomy']


def cases():
    common = {'approved_queries': QUERIES, 'approved_result_limit': 20, 'approved_total_limit': 40}
    result = [
        ('wikipedia', 'prepare', 'classifier', {**common, 'mode': 'web', 'approved_provider': 'wikipedia'}, 'approved_provider'),
        ('commons', 'search-images', 'text_to_image', {**common, 'approved_provider': 'commons'}, 'approved_provider'),
    ]
    for provider, action in [('loc', 'search-catalog'), ('europe_pmc', 'search-publications'),
                             ('wikidata', 'search-entities'), ('federal_register', 'search-notices'), ('crossref', 'search-bibliography')]:
        result.append((provider, action, 'classifier', {**common, 'approved_provider': provider}, 'approved_provider'))
    result.extend([
        ('world_bank', 'load-indicators', 'classifier', {'approved_provider': 'world_bank', 'approved_scope': 'indicator_catalog', 'approved_page': 1, 'approved_result_limit': 20}, 'approved_provider'),
        ('sec_edgar', 'search-companies', 'classifier', {'approved_provider': 'sec_edgar', 'query': 'orchard', 'contact': 'fixture@example.invalid', 'approved_url': 'https://www.sec.gov/files/company_tickers_exchange.json', 'approved_result_limit': 20}, 'approved_url'),
        ('project_website', 'review-website-access', 'classifier', {'approved_website': 'https://example.org/archive/', 'approved_url': 'https://example.org/robots.txt', 'approved_byte_limit': 65536}, 'approved_url'),
    ])
    return result


class DiscoveryAcceptanceTest(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(chat_history, 'DATABASE', Path(folder) / 'chat.sqlite3'))
        self.project = chat_history.create_project('Consent fixture')['id']
        chat_history.update_project(self.project, '', 'https://example.org/archive/')

    def submit(self, action, recipe, body):
        job = {'id': 'fixture', 'project_id': self.project, 'status': 'approval', 'recipe': recipe,
               'plan': {'queries': QUERIES, 'labels': ['fruit', 'astronomy']}}
        encoded = json.dumps(body).encode()
        handler = Mock(path=f'/jobs/fixture/{action}', headers={'Content-Length': str(len(encoded))}, rfile=io.BytesIO(encoded))
        with patch.object(studio, 'JOBS', {'fixture': job}), patch.object(studio, 'store_job'), patch.object(studio.threading, 'Thread') as worker:
            studio.Handler.do_POST(handler)
        return job, worker, handler

    def test_all_providers_require_explicit_consent_before_worker_dispatch(self):
        for provider, action, recipe, body, required in cases():
            with self.subTest(provider=provider, consent='missing'):
                incomplete = {key: value for key, value in body.items() if key != required}
                job, worker, _ = self.submit(action, recipe, incomplete)
                self.assertEqual(job['status'], 'approval')
                worker.assert_not_called()
            with self.subTest(provider=provider, consent='approved'):
                job, worker, handler = self.submit(action, recipe, body)
                self.assertNotEqual(job['status'], 'approval')
                worker.return_value.start.assert_called_once()
                self.assertEqual(handler.respond.call_args.args[-1], 202)

    def test_disabled_project_providers_cannot_dispatch_even_with_consent(self):
        chat_history.update_project(self.project, '', enabled_providers=[])
        for provider, action, recipe, body, _ in cases():
            with self.subTest(provider=provider):
                job, worker, handler = self.submit(action, recipe, body)
                self.assertEqual(job['status'], 'approval')
                worker.assert_not_called()
                self.assertIn('disabled', handler.respond.call_args.args[0]['error'])
