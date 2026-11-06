import json
import io
import zipfile
from pathlib import Path
import sqlite3
import tempfile
import unittest
from job_agent.store import Store
from job_agent.migrations import SCHEMA_VERSION
from job_agent import portable
from job_agent.workspace import Workspace


class TrackingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root)
        self.store.import_jobs([{'id':'one','company':'Fictional Tools','role':'Engineer','url':'https://example.com/job'}])
    def tearDown(self):self.temp.cleanup()
    def update(self,stage,note='',day='2026-11-06',expected=None):
        self.store.update_tracking('one',{'stage':stage,'note':note,'occurred_on':day,'expected_updated_at':expected})

    def test_interview_rejection_and_notes_survive_reopening_without_changing_materials(self):
        workspace=Workspace(self.store)
        workspace.save_profile({'name':'Alex Example','bio':'I build APIs.','cv_text':'Built an API.','roles':['Engineer']})
        portable.draft(workspace,'one')
        before=self.store.get('one');pdf=self.root/before['dossier']['attachments'][0]['path'];content=pdf.read_bytes()
        self.update('INTERVIEW','First conversation with the team.','2026-11-10')
        current=self.store.get('one')
        self.update(None,'Technical interview planned.','2026-11-12',current['tracking']['updated_at'])
        current=self.store.get('one')
        self.update('REJECTED','Role filled internally.','2026-11-18',current['tracking']['updated_at'])
        reopened=Store(self.root).get('one')
        self.assertEqual(reopened['tracking']['stage'],'REJECTED')
        for field in ('status','dossier','revision','approved_hash','fingerprint','updated_at','audit'):
            self.assertEqual(before[field],reopened[field],field)
        self.assertEqual(pdf.read_bytes(),content)
        events=[json.loads(row['details']) for row in self.store.history('one')['events'] if row['action']=='TRACKING_UPDATED']
        self.assertEqual([row['stage'] for row in events],['REJECTED','INTERVIEW','INTERVIEW'])
        self.assertEqual(events[0]['occurred_on'],'2026-11-18')
        self.assertEqual(events[0]['note'],'Role filled internally.')

    def test_invalid_and_stale_updates_do_not_write_events(self):
        for patch in ({'stage':'UNKNOWN'},{'stage':[]},{'note':'x'*2001},{'occurred_on':'2026-02-30'},{'occurred_on':'20261106'},{'stage':None}):
            value={'stage':'INTERVIEW','note':'','occurred_on':'2026-11-06','expected_updated_at':None,**patch}
            with self.assertRaises(ValueError):self.store.update_tracking('one',value)
        self.assertIsNone(self.store.get('one')['tracking'])
        self.update('APPLIED')
        with self.assertRaises(ValueError):self.update('REJECTED',expected=None)
        self.assertEqual(self.store.get('one')['tracking']['stage'],'APPLIED')
        self.assertEqual(sum(row['action']=='TRACKING_UPDATED' for row in self.store.history('one')['events']),1)

    def test_submitted_documents_remain_locked_after_an_outcome_update(self):
        with self.store.db() as db:db.execute("UPDATE jobs SET status='SUBMITTED' WHERE id='one'")
        self.update('REJECTED','Employer reply received.')
        self.assertEqual(self.store.get('one')['status'],'SUBMITTED')
        with self.assertRaises(ValueError):self.store.save('one',{'attachments':[]},0)

    def test_backup_restores_recruitment_stage_and_notes(self):
        self.update('OFFER','Fictional written offer received.')
        with tempfile.TemporaryDirectory() as restored:
            with zipfile.ZipFile(io.BytesIO(portable.backup(Workspace(self.store)))) as archive:archive.extractall(restored)
            store=Store(restored)
            self.assertEqual(store.get('one')['tracking']['stage'],'OFFER')
            self.assertIn('Fictional written offer received.',store.history('one')['events'][0]['details'])

    def test_schema_one_upgrade_creates_a_recovery_point_and_keeps_saved_jobs(self):
        with self.store.db() as db:
            db.execute('DROP TABLE application_tracking');db.execute('PRAGMA user_version=1')
        upgraded=Store(self.root)
        self.assertEqual(upgraded.get('one')['company'],'Fictional Tools')
        self.assertIsNone(upgraded.get('one')['tracking'])
        with sqlite3.connect(self.root/f'data/backups/before-schema-{SCHEMA_VERSION}.sqlite3') as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT company FROM jobs').fetchone()[0],'Fictional Tools')
