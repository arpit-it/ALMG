import unittest
from backend import wikipedia_reuse as reuse


class WikipediaReuseTest(unittest.TestCase):
    def test_collection_requires_current_scoped_permission_for_every_selected_excerpt(self):
        row = {'source': 'https://en.wikipedia.org/wiki/Orchard', 'provider': 'wikipedia', 'title': 'Orchard',
               'text': 'Fruit orchards produce seasonal harvests and provide useful cultivation examples.'}
        decision = {'approved_url': row['source'], 'confirmed': True, 'approved_scope': 'wikipedia_excerpt',
                    'permission_basis': 'Local fixture licensing and attribution reviewed.'}
        with self.assertRaises(ValueError):
            reuse.approved_excerpt_rows([row], [row['source']])
        row['reuse_approval'] = reuse.excerpt_reuse_evidence(row, decision)
        row['reuse_status'] = 'user_approved'
        self.assertEqual(reuse.approved_excerpt_rows([row, {'source': 'other'}], [row['source']])[0]['collection_scope'], 'wikipedia_excerpt')
        for change in ({'text': 'Changed orchard excerpt long enough to require a new permission decision.'},
                       {'reuse_approval': {**row['reuse_approval'], 'scope': 'whole_article'}}, {'reuse_status': 'unverified'}):
            with self.assertRaises(ValueError):
                reuse.approved_excerpt_rows([{**row, **change}], [row['source']])
        for change in ({'confirmed': False}, {'approved_scope': 'whole_article'}, {'permission_basis': 'short'}, {'approved_url': 'other'}):
            with self.assertRaises(ValueError):
                reuse.excerpt_reuse_evidence(row, {**decision, **change})
        for urls in ([], ['other'], [row['source'], row['source']]):
            with self.assertRaises(ValueError):
                reuse.approved_excerpt_rows([row], urls)
        for source in ('https://evil.invalid/wiki/Orchard', 'https://en.wikipedia.org/wiki/..', row['source'] + '?x=1'):
            with self.assertRaises(ValueError):
                reuse.excerpt_checksum({**row, 'source': source})
