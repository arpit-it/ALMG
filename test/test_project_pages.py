import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import chat_history as history


class ProjectPagesTest(unittest.TestCase):
    def test_index_is_project_scoped_persistent_and_updates_by_source(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            first = history.create_project('First')['id']
            second = history.create_project('Second')['id']
            row = {'source': 'https://example.org/fruit', 'text': 'Fruit cultivation and harvest revenue.',
                   'provider': 'project_website', 'collection_scope': 'website_page_preview',
                   'reuse_approval': {'permission_basis': 'Local fixture permission'}}
            history.index_project_pages(first, [row])
            self.assertEqual(history.search_project_pages(second), [])
            found = history.search_project_pages(first, 'fruit harvest')
            self.assertEqual(found[0]['text'], row['text'])
            self.assertEqual(found[0]['metadata']['reuse_approval'], row['reuse_approval'])
            history.index_project_pages(first, [{**row, 'text': 'Updated orchard text.'}])
            self.assertEqual(len(history.search_project_pages(first)), 1)
            self.assertEqual(history.search_project_pages(first, 'harvest'), [])
            self.assertEqual(history.search_project_pages(first, 'orchard')[0]['source'], row['source'])
            self.assertEqual(history.search_project_pages(first, "' OR 1=1 --"), [])
            with self.assertRaises(ValueError):
                history.search_project_pages(first, 'x' * 161)

    def test_saved_text_reuse_requires_current_revision_and_permission(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            project = history.create_project('Reuse')['id']
            row = {'source': 'https://example.org/fruit', 'text': 'Fruit cultivation and harvest revenue.',
                   'provider': 'project_website', 'reuse_approval': {'source': 'https://example.org/fruit', 'permission_basis': 'Local fixture permission reviewed.'}}
            history.index_project_pages(project, [row])
            page = history.search_project_pages(project)[0]
            decision = {'approved_pages': [{'source': page['source'], 'revision': page['revision']}],
                        'confirmed': True, 'approved_scope': 'saved_project_text'}
            rows = history.approved_project_pages(project, decision)
            self.assertEqual(rows[0]['text'], row['text'])
            self.assertEqual(rows[0]['source_provider'], 'project_website')
            self.assertEqual(rows[0]['collection_origin'], 'project_index')
            with self.assertRaises(ValueError):
                history.approved_project_pages(project, {**decision, 'confirmed': False})
            history.index_project_pages(project, [{**row, 'text': 'Changed saved text.'}])
            with self.assertRaises(ValueError):
                history.approved_project_pages(project, decision)
            other = history.create_project('Other')['id']
            with self.assertRaises(ValueError):
                history.approved_project_pages(other, decision)
