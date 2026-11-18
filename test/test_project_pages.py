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

    def test_export_contains_saved_providers_references_and_full_index(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            project = history.create_project('Portable fixture')['id']
            other = history.create_project('Other')['id']
            history.update_project(project, 'Fixture instructions', 'https://example.org/archive/', ['wikipedia', 'project_website'])
            history.add_project_file(project, 'notes.txt', 'Local fixture reference.')
            row = {'source': 'https://example.org/fruit', 'text': 'Fruit cultivation and harvest revenue.',
                   'provider': 'project_website', 'collection_scope': 'website_page_preview',
                   'reuse_approval': {'source': 'https://example.org/fruit', 'permission_basis': 'Fixture content permission.'}}
            history.index_project_pages(project, [row])
            history.index_project_pages(other, [{**row, 'source': 'https://other.org/private'}])
            exported = history.export_project_data(project)
            self.assertEqual((exported['format'], exported['version']), ('almg-project', 1))
            self.assertEqual(exported['project']['enabled_providers'], ['wikipedia', 'project_website'])
            self.assertEqual(exported['project']['source_website'], 'https://example.org/archive/')
            self.assertEqual(exported['reference_files'], [{'name': 'notes.txt', 'content': 'Local fixture reference.'}])
            self.assertEqual([page['source'] for page in exported['pages']], [row['source']])
            self.assertEqual(exported['pages'][0]['text'], row['text'])
            self.assertEqual(exported['pages'][0]['metadata']['reuse_approval'], row['reuse_approval'])
            self.assertNotIn('id', exported['project'])
