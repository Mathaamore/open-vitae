"""Back up the existing SQLite database before changing its schema."""

from .i18n import tr
import os
import sqlite3
import tempfile
from pathlib import Path

SCHEMA_VERSION = 1


def prepare_database(path):
    path = Path(path)
    if not path.exists():
        return
    with sqlite3.connect(path) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError(tr('migrations.this_workspace_was_saved_by_a_newer_version'))
        if version == SCHEMA_VERSION:
            return
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError(tr('migrations.your_workspace_needs_recovery_keep_a_copy_and'))
        directory = path.parent / 'backups'
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / f'before-schema-{SCHEMA_VERSION}.sqlite3'
        if target.exists():
            with sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro', uri=True) as backup:
                if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or not backup.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError(tr('migrations.the_recovery_backup_is_incomplete_keep_your_workspace'))
            return
        # Publish a complete recovery point; interruption cannot leave an empty backup.
        fd, temporary = tempfile.mkstemp(dir=directory, prefix='.migration-')
        os.close(fd)
        try:
            with sqlite3.connect(temporary) as backup:
                db.backup(backup)
            os.link(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
