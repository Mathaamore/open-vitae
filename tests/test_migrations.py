import sqlite3
import tempfile
import unittest
from pathlib import Path

from job_agent.store import Store
from job_agent.migrations import SCHEMA_VERSION


class MigrationTest(unittest.TestCase):
    def test_legacy_upgrade_preserves_data_and_recovery_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            with store.db() as db:
                db.execute('CREATE TABLE legacy_fact (text TEXT)')
                db.execute("INSERT INTO legacy_fact VALUES ('fictional fact')")
                db.execute('PRAGMA user_version=0')
            Store(tmp)
            backup = Path(tmp)/'data/backups/before-schema-1.sqlite3'
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('SELECT text FROM legacy_fact').fetchone()[0], 'fictional fact')
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            content = backup.read_bytes()
            Store(tmp)
            self.assertEqual(backup.read_bytes(), content)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            with store.db() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)

    def test_newer_schema_is_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            with store.db() as db:
                db.execute('PRAGMA user_version=999')
            before = store.path.read_bytes()
            with self.assertRaises(ValueError):
                Store(tmp)
            self.assertEqual(store.path.read_bytes(), before)

    def test_incomplete_recovery_point_blocks_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            with store.db() as db:
                db.execute('PRAGMA user_version=0')
            directory=Path(tmp)/'data/backups';directory.mkdir()
            (directory/'before-schema-1.sqlite3').touch()
            with self.assertRaises(ValueError):
                Store(tmp)
            with store.db() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
