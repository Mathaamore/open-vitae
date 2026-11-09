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
    def test_saved_job_preparation_uses_connected_ai_and_deduplicates_the_queue(self):
        self.store.import_jobs([{'id':'one','company':'Example','role':'Engineer','url':'https://example.com/job'}])
        self.workspace.set_setting('local_mode',True)
        job=self.store.get('one');body={'revision':job['revision'],'updated_at':job['updated_at']}
        headers={'X-Local-Token':module.TOKEN}
        with patch.object(module.preparation_worker,'submit') as submit:
            first=self.client.post('/api/jobs/one/prepare',json=body,headers=headers)
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json()['preparation']['state'],'queued')
            self.assertEqual(self.client.post('/api/jobs/one/prepare',json=body,headers=headers).status_code,200)
            self.assertEqual(submit.call_count,1)
            submit.assert_called_once_with(module.run_preparation,'one',0,job['updated_at'])
        self.assertFalse(self.workspace.setting('local_mode'))
        self.assertEqual(self.workspace.setting('provider'),'chatgpt')
        self.assertIsNone(self.store.get('one')['dossier'])
        self.provider.status.return_value={'connected':False}
        self.assertEqual(self.client.post('/api/jobs/one/prepare',json=body,headers=headers).status_code,409)

    def test_failed_ai_preparation_is_not_reported_as_a_manual_success(self):
        self.store.import_jobs([{'id':'one','company':'Example','role':'Engineer','url':'https://example.com/job'}])
        with patch.object(module.packets,'prepare',side_effect=ValueError('Fictional provider failure')):
            module.run_preparation('one',0,self.store.get('one')['updated_at'])
        self.assertEqual(self.workspace.preparation('one')['state'],'failed')
        self.assertIsNone(self.store.get('one')['dossier'])

    def test_tracking_requires_a_token_and_exports_the_history_without_saving_a_dossier(self):
        self.store.import_jobs([{'id':'one','company':'Fictional Tools','role':'Engineer','url':'https://example.com/job'}])
        value={'stage':'INTERVIEW','note':'Meet the team.','occurred_on':'2026-11-10','expected_updated_at':None}
        self.assertEqual(self.client.post('/api/jobs/one/tracking',json=value).status_code,403)
        response=self.client.post('/api/jobs/one/tracking',json=value,headers={'x-local-token':module.TOKEN})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['tracking']['stage'],'INTERVIEW')
        self.assertIsNone(response.json()['dossier'])
        exported=self.client.get('/api/export').json()['jobs'][0]
        self.assertEqual(exported['tracking']['stage'],'INTERVIEW')
        self.assertIn('Meet the team.',exported['history']['events'][0]['details'])

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

    def test_source_settings_are_local_partial_and_validate_before_saving(self):
        headers={'X-Local-Token':module.TOKEN}
        with patch.object(module.sources, 'json_request') as network:
            response=self.client.get('/api/sources')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['catalog_version'],1)
            self.assertEqual(len(response.json()['catalog']),16)
            value=self.client.put('/api/sources',json={'boards':['smartrecruiters:example'],'preferences':{'remotive':'off'}},headers=headers)
            self.assertEqual(value.status_code,200,value.text)
            self.client.put('/api/sources',json={'boards':['ashby:example']},headers=headers)
            self.assertEqual(self.client.get('/api/sources').json()['preferences'],{'remotive':'off'})
            bad=self.client.put('/api/sources',json={'boards':[],'preferences':{'remoteok':'invalid'}},headers=headers)
            self.assertEqual(bad.status_code,409)
            self.assertEqual(self.client.get('/api/sources').json()['boards'],['ashby:example'])
            self.assertEqual(self.client.put('/api/sources',json={'preferences':{} }).status_code,403)
            network.assert_not_called()

if __name__=='__main__':unittest.main()
