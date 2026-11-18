import unittest
from unittest.mock import patch, MagicMock
from backend import website_access as access, studio


class WebsiteAccessTest(unittest.TestCase):
    def test_destination_and_public_address_validation(self):
        self.assertEqual(access.robots_url('https://example.org/archive/'), 'https://example.org/robots.txt')
        for site in ('http://example.org', 'https://user@example.org', 'https://127.0.0.1', 'https://example.org?x=1', 'https://example.org\n'):
            with self.assertRaises(ValueError):
                access.robots_url(site)
        for values in (['127.0.0.1'], ['93.184.216.34', '10.0.0.1'], ['::1'], ['224.0.0.1']):
            with patch.object(access.socket, 'getaddrinfo', return_value=[(0, 0, 0, '', (v, 443)) for v in values]):
                with self.assertRaises(ValueError):
                    access.public_address('example.org')

    def test_review_does_not_grant_access_or_reuse(self):
        result = access.robots_review('https://example.org/archive/', 200, b'User-agent: *\nDisallow: /private/\n')
        self.assertEqual(result['access_status'], 'unverified')
        self.assertEqual(result['reuse_status'], 'unverified')
        self.assertIn('Disallow: /private/', result['robots_text'])
        self.assertEqual(access.robots_review('https://example.org', 404, b'')['robots_status'], 404)
        for status, body in ((302, b''), (503, b''), (200, b'x' * 65537), (200, b'\xff')):
            with self.assertRaises(ValueError):
                access.robots_review('https://example.org', status, body)

    def test_network_request_is_pinned_bounded_and_does_not_follow_links(self):
        response = MagicMock(status=200)
        response.getheader.return_value = 'text/plain; charset=utf-8'
        response.read.return_value = b'User-agent: *\nDisallow: /\n'
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch.object(access, 'public_address', return_value='93.184.216.34'), patch.object(access.socket, 'create_connection') as connect, patch.object(access.ssl, 'create_default_context') as context, patch.object(access, 'HTTPSConnection', return_value=connection):
            access.fetch_robots('https://example.org/archive/')
        connect.assert_called_once_with(('93.184.216.34', 443), timeout=30)
        context.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname='example.org')
        self.assertEqual(connection.request.call_args.args[:2], ('GET', '/robots.txt'))
        response.read.assert_called_once_with(65537)
        connection.close.assert_called_once()

    def test_worker_records_only_guidance(self):
        result = access.robots_review('https://example.org', 200, b'User-agent: *\nDisallow: /\n')
        with patch.object(access, 'fetch_robots', return_value=result) as fetch, patch.object(studio, 'activity'), patch.object(studio, 'update') as update:
            studio.review_website_access({}, 'https://example.org')
        fetch.assert_called_once_with('https://example.org')
        self.assertEqual(update.call_args.kwargs['status'], 'website_access_review')
