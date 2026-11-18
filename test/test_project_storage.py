"""Project persistence across replacement backend installations."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from backend import project_storage as storage


class ProjectStorageTest(unittest.TestCase):
    def test_legacy_backup_survives_release_replacement_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / 'release-one' / 'runs' / 'chat.sqlite3'
            legacy.parent.mkdir(parents=True)
            with closing(sqlite3.connect(legacy)) as db, db:
                db.execute('CREATE TABLE fixture (text TEXT)')
                db.execute("INSERT INTO fixture VALUES ('saved page')")
            with patch.dict(os.environ, {}, clear=True), patch.object(storage.sys, 'platform', 'darwin'), patch.object(Path, 'home', return_value=root):
                stable = storage.project_database(legacy.parent.parent)
                self.assertNotEqual(stable, legacy)
                self.assertTrue(legacy.exists())
                with closing(sqlite3.connect(stable)) as db, db:
                    self.assertEqual(db.execute('SELECT text FROM fixture').fetchone()[0], 'saved page')
                    db.execute("UPDATE fixture SET text='updated page'")
                self.assertEqual(storage.project_database(root / 'release-two'), stable)
                storage.project_database(legacy.parent.parent)
                with closing(sqlite3.connect(stable)) as db, db:
                    self.assertEqual(db.execute('SELECT text FROM fixture').fetchone()[0], 'updated page')
                with closing(sqlite3.connect(legacy)) as db, db:
                    self.assertEqual(db.execute('SELECT text FROM fixture').fetchone()[0], 'saved page')

    def test_explicit_locations_are_respected_without_migration(self):
        with patch.dict(os.environ, {'STUDIO_CHAT_DB': '/tmp/explicit.sqlite3', 'STUDIO_DATA': '/tmp/data'}, clear=True):
            self.assertEqual(storage.project_database('/tmp/backend'), Path('/tmp/explicit.sqlite3'))
        with patch.dict(os.environ, {'STUDIO_DATA': '/tmp/data'}, clear=True):
            self.assertEqual(storage.project_database('/tmp/backend'), Path('/tmp/data/chat.sqlite3'))

    def test_fresh_install_restores_settings_and_reuses_saved_sources(self):
        from backend import chat_history as history
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snapshot = {'format': 'almg-project', 'version': 1,
                'project': {'name': 'Portable orchard', 'instructions': 'Keep source evidence.',
                    'source_website': 'https://example.org/', 'enabled_providers': ['wikipedia']},
                'reference_files': [{'name': 'notes.txt', 'content': 'Fixture reference'}],
                'pages': [{'source': 'https://example.org/fruit', 'title': 'Fruit', 'text': 'Fruit grows in orchards.',
                    'updated': 1234, 'metadata': {'provider': 'project_website',
                        'reuse_approval': {'source': 'https://example.org/fruit', 'permission_basis': 'Fixture owner permission.'}}}]}
            with patch.dict(os.environ, {}, clear=True), patch.object(storage.sys, 'platform', 'darwin'), patch.object(Path, 'home', return_value=root):
                database = storage.project_database(root / 'fresh-release/backend')
                self.assertFalse(database.exists())
                with patch.object(history, 'DATABASE', database):
                    self.assertEqual(history.list_projects(), [])
                    restored = history.restore_project_data(json.loads(json.dumps(snapshot)))
                    self.assertEqual(history.export_project_data(restored['id']), snapshot)
                    page = history.search_project_pages(restored['id'], 'orchards')[0]
                    rows = history.approved_project_pages(restored['id'], {'confirmed': True,
                        'approved_scope': 'saved_project_text',
                        'approved_pages': [{'source': page['source'], 'revision': page['revision']}]})
                    self.assertEqual(rows[0]['collection_origin'], 'project_index')
                    self.assertEqual(rows[0]['text'], snapshot['pages'][0]['text'])
                    with self.assertRaises(ValueError):
                        history.approved_project_pages(restored['id'], {'confirmed': False})
