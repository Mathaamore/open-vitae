import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from job_agent import app as module
from job_agent.store import Store, now
from job_agent.workspace import Workspace


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name))
        self.patcher=patch.object(module,'store',self.store);self.patcher.start()
        self.workspace=Workspace(self.store)
        self.workspace.save_profile({'name':'Test Candidate','bio':'A factual profile','roles':['Engineer'],'cv_text':'An approved professional experience','achievements':'','strengths':'','expectations':''})
        self.wp=patch.object(module,'workspace',self.workspace);self.wp.start()
        self.provider=Mock();self.provider.status.return_value={'connected':True,'provider':'chatgpt','name':'ChatGPT'}
        self.pp=patch.object(module,'providers',self.provider);self.pp.start()
        self.client=TestClient(module.app)
    def tearDown(self):self.pp.stop();self.wp.stop();self.patcher.stop();self.temp.cleanup()
    def test_local_read(self):
        response=self.client.get('/api/jobs');self.assertEqual(response.status_code,200);self.assertEqual(response.json(),[])
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_english_presentation_preserves_source_and_saved_data(self):
        from job_agent.i18n import legacy_messages, tr
        old,key=next(iter(legacy_messages().items()))
        source='Mon expérience — une équipe française'
        value={'description':source,'audit':{'warnings':[old]},'dossier':{'missing':[old],'answers':{'why':source},'motivation':source}}
        result=module.present_job(value)
        self.assertEqual(result['audit']['warnings'],[tr(key)])
        self.assertEqual(result['dossier']['missing'],[tr(key)])
        self.assertEqual(result['description'],source)
        self.assertEqual(result['dossier']['answers']['why'],source)
        self.assertEqual(result['dossier']['motivation'],source)
        self.assertEqual(value['dossier']['missing'],[old])

    def test_company_context_does_not_modify_application(self):
        self.store.import_jobs([{'id':'one','company':'Example','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('one',{'checked_at':now(),'sources':['https://example.com/job'],'company_context': {'company': {'summary': 'Documented product'}, 'role': {'scope': 'A product team'}}, 'scores': {}})
        before=self.store.get('one')
        response=self.client.get('/api/jobs/one')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['context']['company']['summary'],'Documented product')
        self.assertEqual(self.store.get('one'),before)

    def test_company_context_unknown_company(self):
        self.store.import_jobs([{'id':'new','company':'Unknown','role':'Engineer','url':'https://example.com/job'}])
        response=self.client.get('/api/jobs/new')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json()['context']['company'])

    def test_cross_origin_and_missing_token(self):
        self.assertEqual(self.client.post('/api/jobs/x/decision',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/jobs/x/decision',json={},headers={'origin':'https://attacker.example','x-local-token':module.TOKEN}).status_code,403)
    def test_go_is_disabled_in_preparation_interface(self):
        response=self.client.post('/api/jobs/anything/decision',json={'choice':'GO'},headers={'x-local-token':module.TOKEN})
        self.assertEqual(response.status_code,409)
        self.assertIn('cannot submit',response.json()['error'])
    def test_assistant_status_requires_local_token(self):
        self.assertEqual(self.client.get('/api/assistant').status_code,403)
        with patch.object(module.providers,'status',return_value={'available':True,'connected':False}):
            response=self.client.get('/api/assistant',headers={'x-local-token':module.TOKEN})
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['connected'])

    def test_suggestion_never_saves_or_submits_and_rejects_stale_or_locked_dossiers(self):
        self.store.import_jobs([{'id':'test','company':'Test','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('test',{'checked_at':now(),'sources':['https://example.com/job'],'active':True,'france_allowed':True,'requirements_checked':True})
        self.store.save('test',{'answers':{'why':'Original'},'motivation':'Original','missing':[],
            'form':{'fields':[{'key':'why','type':'textarea','label':'Why?'}]},'attachments':[]},0)
        before=self.store.get('test')
        headers={'x-local-token':module.TOKEN}
        data={'field':'why','text':'Current browser draft','instruction':'Shorter','revision':before['revision']}
        with patch.object(module.providers,'complete',return_value={'text':'Suggestion','notes':''}) as generate:
            response=self.client.post('/api/jobs/test/suggestion',json=data,headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['text'],'Suggestion')
            self.assertEqual(self.store.get('test'),before)
            self.assertEqual(generate.call_args.args[1]['original'],'Current browser draft')
            self.assertEqual(self.client.post('/api/jobs/test/suggestion',json={**data,'revision':0},headers=headers).status_code,409)
            self.assertEqual(self.client.post('/api/jobs/test/suggestion',json={**data,'field':'unknown'},headers=headers).status_code,409)
            with self.store.db() as db:db.execute("UPDATE jobs SET status='SUBMITTED' WHERE id='test'")
            self.assertEqual(self.client.post('/api/jobs/test/suggestion',json=data,headers=headers).status_code,409)
            self.assertEqual(generate.call_count,1)

    def test_dns_rebinding_host(self):
        self.assertEqual(self.client.get('/api/jobs',headers={'host':'attacker.example'}).status_code,400)

    def test_review_and_manual_receipt_do_not_send(self):
        self.store.import_jobs([{'id':'test','company':'Test','role':'Engineer','url':'https://example.com/job'}])
        self.store.audit('test',{'checked_at':now(),'sources':['https://example.com/job'],'active':True,'france_allowed':True,'requirements_checked':True})
        (self.store.root/'data/resume.pdf').write_bytes(b'%PDF-test')
        self.store.save('test',{'answers':{},'missing':[], 'form':{'url':'https://example.com/job','fields':[]},'attachments':[{'path':'data/resume.pdf'}]},0)
        fingerprint=self.store.get('test')['fingerprint']
        headers={'x-local-token':module.TOKEN}
        response=self.client.post('/api/jobs/test/decision',json={'choice':'REVIEW','fingerprint':fingerprint},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['status'],'REVIEWED')
        with self.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],0)
        response=self.client.post('/api/jobs/test/confirmation',json={'confirmation':'Application received by employer','fingerprint':'stale'},headers=headers)
        self.assertEqual(response.status_code,409)
        response=self.client.post('/api/jobs/test/confirmation',json={'confirmation':'','fingerprint':fingerprint,'declared_sent':True},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['status'],'SUBMITTED')

if __name__=='__main__':unittest.main()
