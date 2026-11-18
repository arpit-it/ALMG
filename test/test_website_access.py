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

    def test_access_rule_decision_is_scoped_to_current_guidance(self):
        review = access.robots_review('https://example.org/archive/', 200, b'User-agent: *\nDisallow: /private/\n')
        decision = {'approved_website': review['website'], 'confirmed': True, 'approved_scope': 'website_access_rules',
                    'access_basis': 'Local fixture site access policy reviewed.'}
        evidence = access.access_rule_evidence(review, decision, review['website'])
        self.assertEqual(evidence['scope'], 'website_access_rules')
        self.assertEqual(evidence['guidance_sha256'], access.guidance_checksum(review))
        self.assertNotEqual(evidence['guidance_sha256'], access.guidance_checksum({**review, 'robots_text': 'User-agent: *\nDisallow: /\n'}))
        self.assertEqual(review['reuse_status'], 'unverified')
        for changes in ({'confirmed': False}, {'approved_scope': 'content_reuse'}, {'approved_website': 'https://other.org'}, {'access_basis': 'short'}):
            with self.assertRaises(ValueError):
                access.access_rule_evidence(review, {**decision, **changes}, review['website'])
        with self.assertRaises(ValueError):
            access.access_rule_evidence(review, decision, 'https://other.org')
        malformed = {**review, 'robots_url': 'https://other.org/robots.txt'}
        with self.assertRaises(ValueError):
            access.access_rule_evidence(malformed, decision, review['website'])
        refreshed = access.robots_review(review['website'], 200, b'User-agent: *\nDisallow: /\n')
        self.assertNotIn('access_approval', refreshed)

    def test_robots_uses_specific_combined_groups_and_longest_match(self):
        text = 'User-agent: *\nDisallow: /\nUser-agent: ALMG\nDisallow: /private/\nUser-agent: almg\nAllow: /private/public/\n'
        check = lambda path: access.robots_path_decision('https://example.org' + path, text)['robots_decision']
        self.assertEqual(check('/archive/'), 'allowed')
        self.assertEqual(check('/private/data'), 'disallowed')
        self.assertEqual(check('/private/public/data'), 'allowed')
        tie = 'User-agent: *\nDisallow: /archive\nAllow: /archive\n'
        self.assertEqual(access.robots_path_decision('https://example.org/archive', tie)['robots_decision'], 'allowed')

    def test_robots_wildcards_anchors_and_percent_encoded_paths(self):
        text = 'User-agent: *\nDisallow: /*.pdf$\nDisallow: /%7Eprivate/\nDisallow: /ツ/\nDisallow: /encoded%2Fslash\n'
        check = lambda path: access.robots_path_decision('https://example.org' + path, text)['robots_decision']
        for path in ('/a/b.pdf', '/~private/file', '/%E3%83%84/file', '/encoded%2fslash'):
            self.assertEqual(check(path), 'disallowed', path)
        for path in ('/a.pdf/more', '/encoded/slash', '/other'):
            self.assertEqual(check(path), 'allowed', path)
        self.assertEqual(access.robots_path_decision('https://example.org', '', 404)['robots_decision'], 'undetermined')
        self.assertEqual(access.robots_path_decision('https://example.org', 'User-agent: *\nDisallow: broken')['robots_decision'], 'undetermined')
        self.assertEqual(access.robots_review('https://example.org/private/', 200, b'User-agent: *\nDisallow: /private/')['robots_decision'], 'disallowed')

    def discovery_review(self):
        review = access.robots_review('https://example.org/archive/', 200, b'User-agent: ALMG\nDisallow: /private/\nCrawl-delay: 5\n')
        review['access_approval'] = access.access_rule_evidence(review, {'approved_website': review['website'],
            'confirmed': True, 'approved_scope': 'website_access_rules', 'access_basis': 'Local fixture access policy reviewed.'}, review['website'])
        return review

    def test_discovery_requires_current_access_and_robots_allow(self):
        review = self.discovery_review()
        self.assertEqual(access.require_discovery_access(review, review['website']), 5)
        for changed in ({'access_approval': {}}, {'robots_text': 'User-agent: *\nDisallow: /'}, {'reviewed_at': 1}):
            with self.assertRaises(ValueError):
                access.require_discovery_access({**review, **changed}, review['website'])
        with self.assertRaises(ValueError):
            access.require_discovery_access(review, 'https://other.org')

    def test_discovery_lists_only_safe_allowed_same_origin_links(self):
        review = self.discovery_review()
        html = b'''<a href="fruit">Fruit</a><a href="fruit#part">Duplicate</a><a href="/private/data">Blocked</a>
        <a href="https://other.org/page">Other</a><a href="http://example.org/page">HTTP</a>
        <a href="/archive/%2e%2e/escape">Escape</a><a href="/search?q=fruit">Query</a><img src="image.jpg">
        <a href="/stars">Stars</a>'''
        rows = access.discovered_links(review['website'], html, review)
        self.assertEqual([row['source'] for row in rows], ['https://example.org/archive/fruit', 'https://example.org/stars'])
        self.assertTrue(all(row['reuse_status'] == 'unverified' for row in rows))
        many = ''.join(f'<a href="/page{i}">Page</a>' for i in range(30)).encode()
        self.assertEqual(len(access.discovered_links(review['website'], many, review)), 20)
        with self.assertRaises(ValueError):
            access.discovered_links(review['website'], b'x' * (access.SEED_LIMIT + 1), review)

    def test_discovery_fetches_only_seed_with_bounded_read(self):
        review = self.discovery_review()
        response = MagicMock(status=200)
        response.getheader.return_value = 'text/html'
        response.read.return_value = b'<a href="fruit">Fruit</a>'
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch.object(access, 'public_address', return_value='93.184.216.34'), patch.object(access.socket, 'create_connection'), patch.object(access.ssl, 'create_default_context'), patch.object(access, 'HTTPSConnection', return_value=connection), patch.object(access.time, 'sleep'):
            rows = access.fetch_seed_links(review, review['website'])
        self.assertEqual(len(rows), 1)
        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.args[:2], ('GET', '/archive/'))
        response.read.assert_called_once_with(access.SEED_LIMIT + 1)
