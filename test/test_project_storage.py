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
