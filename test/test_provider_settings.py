import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import chat_history, studio


class ProviderSettingsTest(unittest.TestCase):
    def test_provider_selection_is_project_scoped_and_persists(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(chat_history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            one = chat_history.create_project('One')['id']
            two = chat_history.create_project('Two')['id']
            self.assertEqual(chat_history.project_details(one)['enabled_providers'], list(chat_history.DISCOVERY_PROVIDERS))
            chat_history.update_project(one, 'Keep instructions', enabled_providers=['wikipedia', 'loc'])
            self.assertEqual(chat_history.project_details(one)['enabled_providers'], ['wikipedia', 'loc'])
            self.assertEqual(chat_history.list_projects()[0]['enabled_providers'], ['wikipedia', 'loc'])
            self.assertIn('crossref', chat_history.project_details(two)['enabled_providers'])
            chat_history.update_project(one, 'Updated instructions')
            self.assertEqual(chat_history.project_details(one)['enabled_providers'], ['wikipedia', 'loc'])
            with self.assertRaises(ValueError):
                studio.require_enabled_provider({'project_id': one}, 'search-bibliography', {})
            studio.require_enabled_provider({'project_id': one}, 'prepare', {'mode': 'web'})
            for invalid in (['unknown'], ['wikipedia', 'wikipedia'], 'wikipedia'):
                with self.assertRaises(ValueError):
                    chat_history.update_project(one, '', enabled_providers=invalid)
            chat_history.update_project(one, '', enabled_providers=[])
            with self.assertRaises(ValueError):
                studio.require_enabled_provider({'project_id': one}, 'prepare', {'mode': 'web'})

    def test_disabled_commons_blocks_existing_result_downloads(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(chat_history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            project = chat_history.create_project('Offline images')['id']
            chat_history.update_project(project, '', enabled_providers=['wikipedia'])
            for action in ('search-images', 'download-images'):
                with self.assertRaisesRegex(ValueError, 'disabled'):
                    studio.require_enabled_provider({'project_id': project}, action, {})
            chat_history.update_project(project, '', enabled_providers=['commons'])
            studio.require_enabled_provider({'project_id': project}, 'download-images', {})
