import io
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch
from backend import studio


def response(ids):
    return {'query': {'pages': {str(i): {'title': f'File:Fixture {i}.jpg', 'imageinfo': [{
        'url': f'https://upload.wikimedia.org/fixture/{i}.jpg', 'mime': 'image/jpeg',
        'extmetadata': {'LicenseShortName': {'value': 'CC BY 4.0'}}}]} for i in ids}}}


class CommonsQueriesTest(unittest.TestCase):
    def test_all_queries_are_searched_with_cross_query_deduplication(self):
        requests = []
        def search(url, **kwargs):
            query = parse_qs(urlsplit(url).query)['gsrsearch'][0]
            requests.append(query)
            return response([1, 2, 3] if query == 'orchard' else [3, 4, 5])
        with patch.object(studio, 'request_json', side_effect=search), patch.object(studio, 'activity'), patch.object(studio, 'update') as update:
            studio.search_images({'plan': {'queries': ['orchard', 'astronomy']}})
        self.assertEqual(requests, ['orchard', 'astronomy'])
        rows = update.call_args.kwargs['image_candidates']
        self.assertEqual(len(rows), 5)
        self.assertEqual([row['approved_query'] for row in rows], ['orchard'] * 3 + ['astronomy'] * 2)

    def test_total_cap_stops_before_contacting_more_queries(self):
        with patch.object(studio, 'request_json', side_effect=[response(range(20)), response(range(20, 40))]) as request, patch.object(studio, 'activity'), patch.object(studio, 'update') as update:
            studio.search_images({'plan': {'queries': ['one', 'two', 'must not contact']}})
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(update.call_args.kwargs['image_candidates']), 40)

    def test_total_limit_needs_explicit_approval(self):
        job = {'id': 'fixture', 'status': 'approval', 'recipe': 'text_to_image', 'plan': {'queries': ['one', 'two']}}
        body = json.dumps({'approved_provider': 'commons', 'approved_queries': ['one', 'two'], 'approved_result_limit': 20}).encode()
        handler = Mock(path='/jobs/fixture/search-images', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
        with patch.object(studio, 'JOBS', {'fixture': job}), patch.object(studio.threading, 'Thread') as worker:
            studio.Handler.do_POST(handler)
        handler.respond.assert_called_once_with({'error': 'Approve the Commons total result limit first.'}, 400)
        worker.assert_not_called()
        self.assertEqual(job['status'], 'approval')
