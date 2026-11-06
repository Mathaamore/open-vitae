import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from job_agent.store import Store, now
from job_agent.workspace import Workspace, extract_resume
from job_agent.providers import Providers
from job_agent import app as module, packets, sources
from job_agent.net import public_url

PROFILE={'name':'Alex Example','bio':'I build useful products.','roles':['Python engineer'],'locations':['France'],
         'remote':'remote','strengths':'Python, APIs','achievements':'Built a production API with a team.',
         'expectations':'A product team','email':'alex@example.com','phone':'','portfolio':'','cv_text':'2024–2026 · Engineer at Example\nBuilt a production API with a team.'}

class ProductTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root);self.ws=Workspace(self.store)
    def tearDown(self):self.temp.cleanup()
    def offer(self,identity='one',role='Python engineer'):
        self.store.import_jobs([{'id':identity,'company':'Example','role':role,'url':'https://example.com/job/'+identity}])
        self.store.audit(identity,{'checked_at':now(),'sources':['https://example.com'],'remote':True,'location':'France','description':'Python APIs product team','scores':{}})
    def test_profile_validation_and_import(self):
        with self.assertRaises(ValueError):self.ws.save_profile({'name':'Alex'})
        result=self.ws.save_profile(PROFILE);self.assertEqual(result['revision'],1)
        result=self.ws.save_profile(PROFILE);self.assertEqual(result['revision'],2)
        self.assertEqual(self.ws.profile()['name'],'Alex Example')
        text=extract_resume(b'A documented experience building an API with a product team.','resume.txt')
        self.assertIn('documented',text)
        for filename in ['resume.exe','resume.doc']:
            with self.assertRaises(ValueError):extract_resume(b'hello',filename)
        pdf=packets.pdf_bytes(PROFILE,'Python engineer','I build useful products.',['Built a production API with a team.'])
        self.assertIn('Alex',extract_resume(pdf,'resume.pdf'))
    def test_daily_budget_including_failures_and_exact_cache(self):
        self.ws.set_setting('daily_limit',1)
        run=self.ws.reserve('chat','chatgpt','facts')
        self.ws.finish_run(run,{'text':'Result'},'test-model',{'input_tokens':5})
        self.assertEqual(self.ws.cached('chat','facts'),{'text':'Result'})
        self.assertIsNone(self.ws.cached('chat','changed facts'))
        with self.assertRaises(ValueError):self.ws.reserve('chat','chatgpt','again')
        self.assertEqual(self.ws.usage()['requests'],1)
    def test_feedback_is_explicit_and_changes_ranking_without_editing_profile(self):
        self.ws.save_profile(PROFILE);self.offer();self.offer('two','Java engineer')
        before=self.ws.profile();a=sources.recommendations(self.ws);self.assertEqual(a[0]['id'],'one')
        self.ws.decide('one','reject','role');self.assertNotIn('one',[j['id'] for j in sources.recommendations(self.ws)])
        self.ws.decide('one','reset');self.assertIn('one',[j['id'] for j in sources.recommendations(self.ws)])
        self.assertEqual(before,self.ws.profile())
        self.assertTrue(self.ws.queue('one'));self.assertFalse(self.ws.queue('one'))
    def test_private_destinations_and_mixed_dns_are_rejected(self):
        for url in ['http://example.com','https://user:password@example.com','https://example.com:444']:
            with self.assertRaises(ValueError):public_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):public_url('https://example.com')
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('1.1.1.1',443)),(2,1,6,'',('10.0.0.1',443))]):
            with self.assertRaises(ValueError):public_url('https://example.com')
    def test_source_failures_are_visible_and_expired_offers_stay_out(self):
        self.ws.save_profile(PROFILE)
        with patch.object(sources,'json_request',side_effect=ValueError('Unavailable')):
            result=sources.refresh(self.ws)
        self.assertEqual(len(result['errors']),3)
        self.assertEqual(result['imported'],0)
        self.offer()
        with self.store.db() as db:
            job=self.store.get('one');audit={**job['audit'],'expiry':time.time()-1};db.execute('UPDATE jobs SET audit=? WHERE id=?',(json.dumps(audit),'one'))
        self.assertEqual(sources.recommendations(self.ws),[])
    def test_prepare_keeps_facts_verbatim_and_leaves_unknown_consents_blank(self):
        self.ws.save_profile(PROFILE);self.offer()
        form={'url':'https://example.com/job/one','inspected':True,'text':'Example makes APIs.', 'fields':[
            {'key':'name','label':'Full name','type':'text','required':True},
            {'key':'why','label':'Why this role?','type':'textarea','required':True},
            {'key':'resume','label':'CV','type':'file','required':True},
            {'key':'consent','label':'Agree','type':'checkbox','required':True}]}
        provider=Mock();provider.complete.return_value={'summary':'I build useful products.','selected_facts':[0], 'company_summary':'Example makes APIs.','product_summary':'APIs','team_summary':'Non confirmée','answers':{'why':'I build useful products.'}}
        with patch.object(packets,'inspect_offer',return_value=form):packets.prepare(self.ws,provider,'one')
        job=self.store.get('one');self.assertEqual(job['revision'],1)
        self.assertEqual(job['dossier']['answers']['name'],'Alex Example')
        self.assertEqual(job['dossier']['answers']['consent'],'')
        self.assertEqual(job['status'],'NEEDS_INPUT')
        self.assertTrue((self.root/'data/dossiers/one/resume.pdf').read_bytes().startswith(b'%PDF'))
        before=job['fingerprint']
        packets.prepare(self.ws,provider,'one');self.assertEqual(self.store.get('one')['fingerprint'],before)
        self.assertEqual(provider.complete.call_count,1)
    def test_provider_reuses_cache_and_does_not_silently_switch_models(self):
        codex=Mock();codex.status.return_value={'connected':True};codex.complete.return_value={'text':'A reply','_model':'catalog-mini','_usage':{'outputTokens':4}}
        provider=Providers(self.ws,codex)
        first=provider.complete('chat',{'facts':'approved'});second=provider.complete('chat',{'facts':'approved'})
        self.assertEqual(first,second);self.assertEqual(codex.complete.call_count,1)
        self.assertEqual(self.ws.usage()['requests'],1)
    def test_invalid_model_output_is_not_cached_and_keys_are_not_saved_in_settings(self):
        codex=Mock();codex.status.return_value={'connected':True};codex.complete.return_value={'text':''}
        provider=Providers(self.ws,codex)
        def validate(result):
            if not result.get('text'):raise ValueError('empty reply')
        with self.assertRaises(ValueError):provider.complete('chat',{},validator=validate)
        self.assertEqual(self.ws.usage()['runs'][0]['status'],'failed')
        self.assertIsNone(self.ws.cached('chat',json.dumps({'task':'chat','facts':{}},ensure_ascii=False)))
        secrets=Mock();secrets.get_password.return_value='fictional-test-key'
        provider=Providers(self.ws,codex,secrets)
        with patch('job_agent.providers.json_request',return_value={'data':[]}):provider.connect('claude','fictional-test-key')
        with self.store.db() as db:
            stored=' '.join(row['value'] for row in db.execute('SELECT value FROM settings'))
        self.assertNotIn('fictional-test-key',stored)
        secrets.set_password.assert_called_once()

    def test_chat_preferences_require_confirmation_and_cannot_change_facts(self):
        self.ws.save_profile(PROFILE)
        provider=Mock();provider.status.return_value={'connected':True,'provider':'chatgpt'}
        provider.complete.return_value={'text':'Une piste à discuter.','preferences':{'roles':['Data engineer']}}
        with patch.object(module,'store',self.store),patch.object(module,'workspace',self.ws),patch.object(module,'providers',provider):
            client=TestClient(module.app);headers={'x-local-token':module.TOKEN};before=self.ws.profile()
            result=client.post('/api/chat',json={'text':'Je cherche plutôt de la data.'},headers=headers)
            self.assertEqual(result.status_code,200)
            self.assertEqual(self.ws.profile(),before)
            body={'revision':before['revision'],'preferences':result.json()['proposed_preferences']}
            response=client.post('/api/profile/preferences',json=body,headers=headers)
            self.assertEqual(response.status_code,200)
            after=self.ws.profile();self.assertEqual(after['roles'],['Data engineer']);self.assertEqual(after['cv_text'],before['cv_text'])
            self.assertEqual(client.post('/api/profile/preferences',json=body,headers=headers).status_code,409)
            bad={'revision':after['revision'],'preferences':{'achievements':'An invented result'}}
            self.assertEqual(client.post('/api/profile/preferences',json=bad,headers=headers).status_code,409)

    def test_source_configuration_and_draft_api_validate_before_persistence(self):
        self.ws.save_profile(PROFILE)
        provider=Mock();provider.status.return_value={'connected':True,'provider':'chatgpt'}
        with patch.object(module,'store',self.store),patch.object(module,'workspace',self.ws),patch.object(module,'providers',provider):
            client=TestClient(module.app);headers={'x-local-token':module.TOKEN}
            self.assertEqual(client.put('/api/sources',json={'boards':['ashby:example']},headers=headers).status_code,200)
            self.assertEqual(client.put('/api/sources',json={'boards':['https://127.0.0.1/']},headers=headers).status_code,409)
            self.assertEqual(client.get('/api/sources').json()['boards'],['ashby:example'])
            self.assertEqual(client.put('/api/profile/onboarding',json={'step':0,'fields':{'api_key':'not allowed'}},headers=headers).status_code,409)
            self.assertIsNone(self.ws.setting('onboarding_draft'))
            self.assertEqual(client.post('/api/discovery/cancel',json={}).status_code,403)

    def test_api_gates_data_and_profile_then_retains_manual_submission(self):
        provider=Mock();provider.status.return_value={'connected':False,'provider':'chatgpt'}
        with patch.object(module,'store',self.store),patch.object(module,'workspace',self.ws),patch.object(module,'providers',provider):
            client=TestClient(module.app);headers={'x-local-token':module.TOKEN}
            self.assertEqual(client.get('/api/jobs').status_code,401)
            self.assertEqual(client.get('/api/bootstrap',headers=headers).status_code,200)
            provider.status.return_value={'connected':True,'provider':'chatgpt'}
            self.assertEqual(client.get('/api/jobs').status_code,409)
            self.assertEqual(client.put('/api/profile',json=PROFILE,headers=headers).status_code,200)
            self.assertEqual(client.get('/api/jobs').status_code,200)
            self.assertEqual(client.post('/api/jobs/no/decision',json={'choice':'GO'},headers=headers).status_code,409)
            self.assertEqual(client.get('/api/providers').status_code,403)

if __name__=='__main__':unittest.main()
