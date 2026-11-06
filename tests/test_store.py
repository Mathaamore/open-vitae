import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_agent.store import Store, category, now


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root)
        self.store.import_jobs([{'id':'01','company':'Test','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('01',{'checked_at':now(),'sources':['https://example.com/job'],'active':True,'france_allowed':True,'requirements_checked':True})
        file=self.root/'data/resume.pdf';file.write_bytes(b'%PDF-test')
        self.dossier={'answers':{'name':'Test'},'missing':[],
                      'form':{'url':'https://example.com/job','fields':[{'key':'name','label':'Name','required':True}]},
                      'attachments':[{'path':'data/resume.pdf'}]}
        self.store.save('01',self.dossier,0)

    def tearDown(self): self.tmp.cleanup()

    def approve(self):
        job=self.store.get('01');self.store.decision('01','GO',job['fingerprint'])

    def test_private_workspace_permissions_are_not_reapplied(self):
        with patch.object(Path,'chmod',side_effect=AssertionError('Already private')):
            Store(self.root)
        private=self.root/'data';private.chmod(0o755);self.store.path.chmod(0o644)
        Store(self.root)
        self.assertEqual(private.stat().st_mode & 0o7777,0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o7777,0o600)

    def test_no_send_without_go(self):
        with self.assertRaises(ValueError): self.store.claim('01',self.dossier['form'])

    def test_exact_go_and_duplicate(self):
        self.approve();self.store.claim('01',self.dossier['form']);self.store.finish('01',{'confirmation':'verified'})
        self.assertEqual(self.store.get('01')['status'],'SUBMITTED')
        with self.assertRaises(ValueError):self.store.claim('01',self.dossier['form'])
        with self.assertRaises(ValueError):self.store.save('01',self.dossier,1)

    def test_edit_revokes_go(self):
        self.approve();edited=copy.deepcopy(self.dossier);edited['answers']['name']='Edited'
        self.store.save('01',edited,1)
        self.assertIsNone(self.store.get('01')['approved_hash'])
        with self.assertRaises(ValueError):self.store.claim('01',edited['form'])

    def test_attachment_changed(self):
        self.approve();(self.root/'data/resume.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.store.claim('01',self.dossier['form'])

    def test_form_change_revokes_go(self):
        self.approve()
        with self.assertRaises(ValueError):self.store.claim('01',{'fields':[]})
        self.assertIsNone(self.store.get('01')['approved_hash'])
        self.assertEqual(self.store.get('01')['status'],'NEEDS_INPUT')

    def test_timeout_cannot_retry(self):
        self.approve();self.store.claim('01',self.dossier['form']);self.store.finish('01')
        self.assertEqual(self.store.get('01')['status'],'SUBMISSION_UNCERTAIN')
        with self.assertRaises(ValueError):self.store.decision('01','GO',self.store.get('01')['fingerprint'])

    def test_atomic_import_and_preserves_id(self):
        with self.assertRaises(ValueError):self.store.import_jobs([{'id':'02','company':'B','role':'E','url':'https://example.org'}, {'id':'02'}])
        self.assertEqual(len(self.store.all()),1)
        self.assertEqual(self.store.get('01')['original']['id'],'01')

    def test_import_does_not_overwrite(self):
        with self.assertRaises(ValueError): self.store.import_jobs([{'id':'01','company':'Other','role':'Engineer','url':'https://example.com/job'}])
        self.assertEqual(self.store.get('01')['company'],'Test')

    def test_stale_edit_and_go(self):
        with self.assertRaises(ValueError):self.store.save('01',self.dossier,0)
        with self.assertRaises(ValueError):self.store.decision('01','GO','old')

    def test_unknown_and_blocking_are_independent_of_score(self):
        self.assertEqual(category({'active':True,'scores':{'technical':{'value':100,'reason':'test'}}}),'NEEDS_VERIFICATION')
        self.assertEqual(category({'active':True,'france_allowed':True,'requirements_checked':True,'blockers':['Required 10 years']}),'INELIGIBLE')

    def test_alias_duplicate_blocked(self):
        self.approve();self.store.claim('01',self.dossier['form']);self.store.finish('01',{'confirmation':'verified'})
        self.store.import_jobs([{'id':'alias','company':'Test','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('alias',{'checked_at':now(),'sources':['https://example.com/job'],'active':True,'france_allowed':True,'requirements_checked':True})
        self.store.save('alias',self.dossier,0)
        job=self.store.get('alias');self.store.decision('alias','GO',job['fingerprint'])
        with self.assertRaises(ValueError):self.store.claim('alias',self.dossier['form'])

    def test_manual_confirmation_requires_go_and_evidence(self):
        with self.assertRaises(ValueError):self.store.confirm_manual('01','Real confirmation from employer')
        self.approve()
        with self.assertRaises(ValueError):self.store.confirm_manual('01','ok')
        self.store.confirm_manual('01','Your application was successfully received by our team')
        self.assertEqual(self.store.get('01')['status'],'SUBMITTED')
        with self.assertRaises(ValueError):self.store.confirm_manual('01','Your application was successfully received by our team')

    def test_review_tracks_manual_send_without_authorizing_delivery(self):
        job=self.store.get('01')
        self.store.decision('01','REVIEW',job['fingerprint'])
        self.assertEqual(self.store.get('01')['status'],'REVIEWED')
        with self.assertRaises(ValueError):self.store.claim('01',self.dossier['form'])
        with self.assertRaises(ValueError):self.store.confirm_manual('01','ok',job['fingerprint'])
        with self.assertRaises(ValueError):self.store.confirm_manual('01','Application received by the employer','stale')
        self.store.confirm_manual('01','Application received by the employer',job['fingerprint'])
        self.assertEqual(self.store.get('01')['status'],'SUBMITTED')
        receipt=json.loads(self.store.history('01')['events'][0]['details'])
        self.assertEqual(receipt['verified_by'],'user')
        with self.assertRaises(ValueError):self.store.confirm_manual('01','Application received by the employer',job['fingerprint'])

    def test_explicit_self_report_needs_no_receipt(self):
        job=self.store.get('01');self.store.decision('01','REVIEW',job['fingerprint'])
        with self.assertRaises(ValueError):self.store.confirm_manual('01','',job['fingerprint'])
        with self.assertRaises(ValueError):self.store.confirm_manual('01','','stale',declared_sent=True)
        self.store.confirm_manual('01','',job['fingerprint'],declared_sent=True)
        self.assertEqual(self.store.get('01')['status'],'SUBMITTED')
        receipt=json.loads(self.store.history('01')['events'][0]['details'])
        self.assertEqual(receipt['verified_by'],'user')
        self.assertIn('sans justificatif',receipt['confirmation'])

    def test_edit_or_pdf_change_invalidates_manual_review(self):
        job=self.store.get('01');self.store.decision('01','REVIEW',job['fingerprint'])
        (self.root/'data/resume.pdf').write_bytes(b'changed PDF')
        with self.assertRaises(ValueError):self.store.confirm_manual('01','Application received by the employer',job['fingerprint'])
        edited=copy.deepcopy(self.dossier);edited['answers']['name']='Edited'
        self.store.save('01',edited,job['revision'])
        self.assertEqual(self.store.get('01')['status'],'APPLICATION_READY')
        self.assertIsNone(self.store.get('01')['approved_hash'])

    def test_manual_confirmation_blocks_alias_duplicate(self):
        job=self.store.get('01');self.store.decision('01','REVIEW',job['fingerprint'])
        self.store.confirm_manual('01','Application received by the employer',job['fingerprint'])
        self.store.import_jobs([{'id':'alias','company':'Test','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('alias',{'checked_at':now(),'sources':['https://example.com/job'],'active':True,'france_allowed':True,'requirements_checked':True})
        self.store.save('alias',self.dossier,0)
        alias=self.store.get('alias');self.store.decision('alias','REVIEW',alias['fingerprint'])
        with self.assertRaises(ValueError):self.store.confirm_manual('alias','Application received by the employer',alias['fingerprint'])

    def test_immutable_snapshot(self):
        manifests=list((self.root/'data/versions').glob('*/*/manifest.json'))
        self.assertEqual(len(manifests),1)
        manifest=json.loads(manifests[0].read_text())
        snapshot=self.root/manifest['files'][0]['snapshot']
        (self.root/'data/resume.pdf').write_bytes(b'edited')
        self.assertEqual(snapshot.read_bytes(),b'%PDF-test')

    def test_unapproved_upload_file(self):
        edited=copy.deepcopy(self.dossier)
        edited['form']['fields'].append({'key':'upload','label':'Resume','type':'file','required':True})
        edited['answers']['upload']='data/other.pdf'
        self.store.save('01',edited,1)
        with self.assertRaises(ValueError):self.approve()

    def test_artifact_escape(self):
        escaped=copy.deepcopy(self.dossier);escaped['attachments']=[{'path':'../private.pdf'}]
        with self.assertRaises(ValueError):self.store.save('01',escaped,1)

    def test_missing_answers(self):
        edited=copy.deepcopy(self.dossier);edited['answers']={};self.store.save('01',edited,1)
        with self.assertRaises(ValueError):self.approve()


if __name__=='__main__':unittest.main()
