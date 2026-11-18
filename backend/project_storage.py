"""Stable project database location, independent of the installed app version."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile


def project_database(backend_directory):
    """Honor explicit locations and safely copy a legacy database on first use."""
    if os.environ.get('STUDIO_CHAT_DB'):
        return Path(os.environ['STUDIO_CHAT_DB'])
    if os.environ.get('STUDIO_DATA'):
        return Path(os.environ['STUDIO_DATA']) / 'chat.sqlite3'
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support' / 'ALMG'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'ALMG'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'ALMG'
    destination = root / 'chat.sqlite3'
    legacy = Path(backend_directory) / 'runs' / 'chat.sqlite3'
    if not destination.exists() and legacy.is_file():
        root.mkdir(parents=True, exist_ok=True)
        # SQLite backup includes committed WAL data. Publish atomically without
        # replacing a database created by another backend during migration.
        descriptor, temporary = tempfile.mkstemp(prefix='.project-migration-', dir=root)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(legacy.resolve().as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                pass
        finally:
            Path(temporary).unlink(missing_ok=True)
    return destination
