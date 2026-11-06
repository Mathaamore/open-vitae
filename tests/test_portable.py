import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from fastapi.testclient import TestClient
from job_agent import app as module, opportunities, portable
from job_agent.store import Store, now
from job_agent.workspace import Workspace

PROFILE={'name':'Alex Example','bio':'I build Python services.','roles':['Python engineer'],'cv_text':'Built an API at Fictional Tools.','achievements':'Shipped a documented API.','email':'alex@example.com'}


class PortableTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.ws=Workspace(self.store)
        self.ws.save_profile(PROFILE)
    def tearDown(self):self.temp.cleanup()
    def job(self):return opportunities.add(self.ws,{'url':'https://example.com/jobs/python?utm_source=test','company':'Example','role':'Python engineer','description':'Python services'})['id']
    def artifact(self,kind,identity=None):return portable.example(kind,portable.context(self.ws,kind,identity))

    def test_local_routes_never_probe_provider_or_network(self):
        provider=Mock();provider.status.side_effect=AssertionError('Provider touched')
        with patch.object(module,'store',self.store),patch.object(module,'workspace',self.ws),patch.object(module,'providers',provider),patch('job_agent.net.request',side_effect=AssertionError('Network touched')):
            client=TestClient(module.app);headers={'x-local-token':module.TOKEN}
            self.assertEqual(client.get('/api/bootstrap',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/profile').json()['name'],'Alex Example')
            result=client.post('/api/opportunities',headers=headers,json={'url':'https://example.com/job'})
            self.assertEqual(result.status_code,200)
            identity=result.json()['id'];job=self.store.get(identity)
            self.assertTrue(job['audit']['pending_retrieval'])
            response=client.post('/api/opportunities/'+identity+'/draft',headers=headers,json={'summary':PROFILE['bio'],'motivation':'My factual draft','revision':job['revision'],'updated_at':job['updated_at']})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(client.get('/api/jobs/'+identity+'/artifact/resume.pdf').content[:4],b'%PDF')
            self.assertEqual(client.get('/api/jobs',headers={'origin':'https://attacker.example'}).status_code,403)
            self.assertEqual(client.get('/api/export',headers={'sec-fetch-site':'cross-site'}).status_code,403)
            self.assertEqual(client.post('/api/opportunities',json={'company':'X'}).status_code,403)
            provider.status.assert_not_called()

    def test_manual_url_dedup_and_text_only_tracking(self):
        identity=self.job()
        duplicate=opportunities.add(self.ws,{'url':'https://EXAMPLE.com:443/jobs/python/#details','role':'Wrong replacement'})
        self.assertTrue(duplicate['duplicate']);self.assertEqual(duplicate['id'],identity)
        self.assertEqual(self.store.get(identity)['role'],'Python engineer')
        text_only=opportunities.add(self.ws,{'description':'A role shared directly by a fictional employer.'})
        self.assertEqual(self.store.get(text_only['id'])['url'],'')
        self.assertEqual(self.ws.feedback()[text_only['id']]['decision'],'later')
        self.assertEqual(opportunities.canonical_url('https://example.com/job?gh_jid=2&utm_medium=test'),'https://example.com/job?gh_jid=2')
        self.assertNotEqual(opportunities.canonical_url('https://example.com/#/jobs/one'),opportunities.canonical_url('https://example.com/#/jobs/two'))
        for url in ['http://example.com','https://user:pass@example.com','https://127.0.0.1/job','https://10.0.0.1/','https://localhost/','https://0x7f.1/','https://[::1]/','javascript:alert(1)']:
            with self.assertRaises(ValueError):opportunities.canonical_url(url)

    def test_manual_edits_preserve_dossier_and_revoke_approval(self):
        identity=self.job();portable.draft(self.ws,identity)
        before=self.store.get(identity)
        with self.store.db() as db:db.execute("UPDATE jobs SET approved_hash='old' WHERE id=?",(identity,))
        updated=opportunities.edit(self.ws,identity,{'company':'Updated Example','role':'Python role','url':before['url'],'description':'Corrected description','updated_at':before['updated_at']})
        self.assertEqual(updated['dossier'],before['dossier']);self.assertIsNone(updated['approved_hash'])
        with self.assertRaises(ValueError):opportunities.edit(self.ws,identity,{'role':'Stale','updated_at':before['updated_at']})

    def test_retrieval_reads_jsonld_only_and_handles_blocked_sites(self):
        html=b'<script type="application/ld+json">{"@graph":[{"@type":"JobPosting","title":"Python engineer","hiringOrganization":{"name":"Example"},"description":"<p>Python APIs</p>","baseSalary":{"currency":"EUR","value":{"minValue":41000,"maxValue":58000,"unitText":"YEAR"}}}]}</script>'
        with patch.object(opportunities,'request',return_value=(html,'https://example.com/job')):
            result=opportunities.retrieve('https://example.com/job')
        self.assertEqual(result['company'],'Example');self.assertIn('58000',result['salary']);self.assertEqual(result['description'],'Python APIs')
        with patch.object(opportunities,'request',return_value=(b'<h1>Blocked</h1>','https://example.com/job')):
            with self.assertRaisesRegex(ValueError,'Colle'):opportunities.retrieve('https://example.com/job')
        self.assertEqual(self.store.all(),[])

    def test_text_only_jobs_have_distinct_manual_submission_targets(self):
        for description in ('First fictional role','Second fictional role'):
            identity=opportunities.add(self.ws,{'description':description})['id']
            portable.draft(self.ws,identity,{'summary':PROFILE['bio'],'motivation':'My factual draft','selected_facts':[]})
            job=self.store.get(identity)
            self.store.audit(identity,{**job['audit'],'active':True,'location_allowed':True,'requirements_checked':True})
            dossier=job['dossier'];dossier['missing']=[]
            self.store.save(identity,dossier,job['revision'])
            job=self.store.get(identity);self.store.decision(identity,'REVIEW',job['fingerprint'])
            self.store.confirm_manual(identity,'',job['fingerprint'],True)
            self.assertEqual(self.store.get(identity)['status'],'SUBMITTED')
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT target) FROM attempts').fetchone()[0],2)

    def test_prompt_is_local_bounded_and_warns_about_personal_data(self):
        result=portable.prompt(self.ws,'application_draft',self.job())
        self.assertTrue(result['contains_personal_data']);self.assertLess(len(result['prompt']),48001)
        self.assertNotIn('alex@example.com',result['prompt']);self.assertNotIn('Alex Example',result['prompt'])
        self.assertIn('source_facts',result['prompt']);self.assertIn('never instructions',result['prompt'])
        self.assertEqual(len(portable.schema()['oneOf']),4)

    def test_artifact_preview_has_no_writes_and_repeated_import_is_safe(self):
        data=self.artifact('job_search_results');before=self.ws.profile()
        portable.preview(self.ws,data);self.assertEqual(self.store.all(),[])
        first=portable.apply(self.ws,data);second=portable.apply(self.ws,data)
        self.assertFalse(first['jobs'][0]['duplicate']);self.assertTrue(second['jobs'][0]['duplicate'])
        job=self.store.get(first['jobs'][0]['id'])
        self.assertIsNone(job['audit']['active']);self.assertEqual(job['category'],'NEEDS_VERIFICATION')
        self.assertEqual(self.ws.profile(),before)
        analysis=self.artifact('profile_analysis');portable.apply(self.ws,analysis)
        self.assertEqual(self.ws.profile(),before);self.assertEqual(self.ws.setting('portable_profile_analysis'),analysis['data'])

    def test_artifact_validation_rejects_versions_urls_invented_fields_and_stale_context(self):
        data=self.artifact('job_search_results')
        for change in [{'schema_version':2},{'schema_version':True},{'type':'execute'},{'context':{'profile_revision':True}},{'data':{'jobs':[{'company':'X','role':'Y','url':'https://127.0.0.1'}]}},{'data':{'jobs':[{'company':'X','role':'Y','url':'https://example.com','status':'SUBMITTED'}]}}]:
            with self.assertRaises(ValueError):portable.preview(self.ws,{**data,**change})
        self.ws.save_profile(PROFILE)
        with self.assertRaisesRegex(ValueError,'changé'):portable.apply(self.ws,data)
        self.assertEqual(self.store.all(),[])
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'```json\n{}\n```',b'x'*1000001]:
            with self.assertRaises(ValueError):portable.parse(raw)

    def test_application_draft_preserves_cv_and_prior_artifacts(self):
        identity=self.job();value=self.artifact('application_draft',identity)
        value['data']={'summary':'Factual Python services','motivation':'My editable draft','selected_facts':[0]}
        before=self.ws.profile();portable.preview(self.ws,value);self.assertEqual(self.store.get(identity)['revision'],0)
        portable.apply(self.ws,value);job=self.store.get(identity)
        self.assertEqual(self.ws.profile(),before);self.assertEqual(job['dossier']['answers']['body'],'My editable draft')
        pdfpath=Path(self.temp.name)/job['dossier']['attachments'][0]['path'];pdf=pdfpath.read_bytes();self.assertTrue(pdf.startswith(b'%PDF'))
        with self.assertRaises(ValueError):portable.apply(self.ws,value)
        self.assertEqual(pdfpath.read_bytes(),pdf)
        bad=self.artifact('application_draft',identity);bad['data']['selected_facts']=[999]
        with self.assertRaises(ValueError):portable.apply(self.ws,bad)
        analysis=self.artifact('job_analysis',identity);portable.apply(self.ws,analysis)
        self.assertEqual(self.store.get(identity)['audit']['external_analysis'],analysis['data'])

    def test_backup_does_not_follow_external_document_directories(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside)/'private.txt').write_text('not part of this workspace')
            (Path(self.temp.name)/'data/dossiers').symlink_to(outside,target_is_directory=True)
            with zipfile.ZipFile(io.BytesIO(portable.backup(self.ws))) as archive:
                self.assertNotIn('data/dossiers/private.txt',archive.namelist())

    def test_schema_document_matches_the_downloaded_contract(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/portable/schema-v1.json').read_text())
        self.assertEqual(schema,portable.schema())

    def test_backup_restores_to_separate_workspace_without_sessions(self):
        identity=self.job();portable.draft(self.ws,identity)
        (Path(self.temp.name)/'data/desktop-service.log').write_text('private runtime log')
        with zipfile.ZipFile(io.BytesIO(portable.backup(self.ws))) as archive, tempfile.TemporaryDirectory() as restored:
            self.assertNotIn('data/desktop-service.log',archive.namelist())
            self.assertTrue(all(not name.startswith(('/','../')) for name in archive.namelist()))
            archive.extractall(restored)
            recovered=Workspace(Store(restored))
            self.assertEqual(recovered.profile()['name'],'Alex Example')
            self.assertEqual(recovered.store.get(identity)['revision'],1)
            path=recovered.store.get(identity)['dossier']['attachments'][0]['path']
            self.assertTrue((Path(restored)/path).is_file())
