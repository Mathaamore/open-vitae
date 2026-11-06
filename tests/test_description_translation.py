import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from job_agent import app, languages, opportunities, packets
from job_agent.store import Store, digest
from job_agent.workspace import Workspace


class DescriptionTranslationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.ws=Workspace(self.store)
        self.identity=opportunities.add(self.ws,{'company':'Fictional Tools','role':'Engineer','description':'Nous créons des outils pour les équipes avec une expérience produit.'})['id']
        self.provider=Mock();self.provider.complete.return_value={'text':'We build tools for product teams.'}
        self.patches=[patch.object(app,'store',self.store),patch.object(app,'workspace',self.ws),patch.object(app,'providers',self.provider)]
        for item in self.patches:item.start()
        self.client=TestClient(app.app);self.headers={'x-local-token':app.TOKEN}
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()
    def translate(self):
        return self.client.post('/api/jobs/'+self.identity+'/translate-description',json={'updated_at':self.store.get(self.identity)['updated_at']},headers=self.headers)
    def test_english_verified_form_wins_over_french_description_and_labels(self):
        info={'inspected':True,'language':'en-GB','text':'Description française pour les équipes.', 'fields':[{'type':'textarea','label':'Votre expérience avec les équipes ?'}]}
        self.assertEqual(languages.application_language(self.store.get(self.identity),info),'en')
        parser=packets.Page();parser.feed('<html lang="fr"><form lang="en"><input name="email" type="email"><textarea name="body">Why this role?</textarea></form></html>')
        self.assertEqual(parser.result()[0]['language'],'en')
    def test_translation_is_explicit_preserves_source_and_uses_no_candidate_context(self):
        before=self.store.get(self.identity)
        self.assertTrue(self.client.get('/api/jobs/'+self.identity).json()['description_needs_translation'])
        self.provider.complete.assert_not_called()
        self.assertEqual(self.client.post('/api/jobs/'+self.identity+'/translate-description',json={}).status_code,403)
        response=self.translate();self.assertEqual(response.status_code,200,response.text)
        result=response.json();self.assertEqual(result['display_description'],'We build tools for product teams.')
        self.assertTrue(result['description_translated'])
        after=self.store.get(self.identity)
        self.assertEqual(after['audit']['description'],before['audit']['description'])
        for key in ('dossier','revision','updated_at','status','approved_hash'):
            self.assertEqual(after[key],before[key])
        task,payload=self.provider.complete.call_args.args
        self.assertEqual(task,'translate_job_description')
        self.assertEqual(set(payload),{'instruction','output_languages','description'})
        self.assertEqual(payload['output_languages']['information_language'],'en')
    def test_stale_translation_is_hidden_and_stale_requests_do_not_spend_tokens(self):
        original=self.store.get(self.identity)
        self.translate()
        opportunities.edit(self.ws,self.identity,{'description':'Une autre description pour les équipes et les clients.','updated_at':original['updated_at']})
        result=self.client.get('/api/jobs/'+self.identity).json()
        self.assertFalse(result['description_translated'])
        self.assertIn('autre',result['display_description'])
        self.provider.complete.reset_mock()
        response=self.client.post('/api/jobs/'+self.identity+'/translate-description',json={'updated_at':original['updated_at']},headers=self.headers)
        self.assertEqual(response.status_code,409);self.provider.complete.assert_not_called()
    def test_wrong_language_and_concurrent_edits_do_not_replace_source(self):
        self.provider.complete.return_value={'text':'Nous travaillons avec les équipes pour des produits utiles.'}
        self.assertEqual(self.translate().status_code,409)
        self.assertNotIn('description_translation',self.store.get(self.identity)['audit'])
        def edit(*args,**kwargs):
            job=self.store.get(self.identity)
            opportunities.edit(self.ws,self.identity,{'description':'Changed while translating.','updated_at':job['updated_at']})
            return {'text':'We build tools.'}
        self.provider.complete.side_effect=edit
        self.assertEqual(self.translate().status_code,409)
        self.assertEqual(self.store.get(self.identity)['audit']['description'],'Changed while translating.')

    def test_old_french_answers_are_flagged_without_being_rewritten(self):
        source={'audit':{'description':'We build products with our team.'},'dossier':{
            'form':{'inspected':True,'language':'en','fields':[{'key':'why','type':'textarea','label':'Why this role?'}]},
            'answers':{'why':'Nous travaillons avec les équipes pour des produits utiles.'}}}
        shown=app.present_job(source)
        self.assertTrue(shown['materials_language_mismatch'])
        self.assertEqual(shown['dossier']['answers'],source['dossier']['answers'])
