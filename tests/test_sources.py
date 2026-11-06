import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from job_agent import ats, sources
from job_agent.store import Store
from job_agent.workspace import Workspace

PROFILE = {'name':'Alex Example','bio':'Python developer','roles':['Python'],'achievements':'Built an API','remote':'remote','strengths':'Python'}


class SourcesTest(unittest.TestCase):
    def test_board_inputs_cannot_select_arbitrary_urls(self):
        for value in [['https://localhost'], ['ashby:../private'], ['lever:a/b'], ['other:example'], ['ashby:example']*7]:
            with self.assertRaises(ValueError):
                ats.boards(value)
        self.assertEqual(ats.boards(['lever:example','lever:example']), ['lever:example'])

    def test_official_board_formats_do_not_invent_freshness(self):
        greenhouse = ats.postings('greenhouse:example', {'jobs':[{'absolute_url':'https://example.com/a','title':'Python','updated_at':'2026-11-06T12:00:00Z','location':{'name':'Paris'}}]})[0]
        self.assertNotIn('created_at', greenhouse)
        lever = ats.postings('lever:example', [{'hostedUrl':'https://example.com/b','text':'Python','workplaceType':'remote','categories':{'location':'France'}}])[0]
        self.assertIs(lever['remote'], True)
        self.assertEqual(lever['location'], 'France')
        ashby = ats.postings('ashby:example', {'jobs':[{'isListed':False}, {'isListed':True,'title':'Python','jobUrl':'https://example.com/c','publishedAt':'not a date'}]})
        self.assertEqual(len(ashby), 1)
        self.assertIsNone(ashby[0]['created_at'])

    def test_source_progress_cancel_partial_results_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace(Store(Path(tmp)));ws.save_profile(PROFILE)
            ws.set_setting('source_boards', ['lever:example'])
            progress=[]
            def feed(url):
                return {'data':[{'url':'https://example.com/job','company_name':'Example','title':'Python','remote':True,'created_at':time.time()}]}
            with patch.object(sources, 'json_request', side_effect=feed) as request:
                result=sources.refresh(ws, progress=progress.append, cancelled=lambda:bool(ws.store.all()))
            self.assertTrue(result['cancelled'])
            self.assertEqual(result['imported'], 1)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(progress[0]['completed'], 0)
            with patch.object(sources,'json_request',side_effect=ValueError('offline')) as request:
                result=sources.refresh(ws)
                self.assertEqual(request.call_count, 4)
                self.assertFalse(result['cached'])
                sources.refresh(ws)
                self.assertEqual(request.call_count, 8)
            self.assertEqual(len(ws.store.all()), 1)

    def test_malformed_optional_source_fields_do_not_break_discovery(self):
        malformed=ats.postings('lever:example',[{'workplaceType':{},'text':'Python','hostedUrl':'https://example.com/job'}])
        self.assertIsNone(malformed[0]['remote'])
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile(PROFILE)
            listing={'applicationLink':'https://example.com/job','companyName':'Example','title':'Python','pubDate':time.time()*1000,'expiryDate':float('nan')}
            with patch.object(sources,'json_request',side_effect=[{'data':[]},{'data':[]},{'jobs':[listing]}]):
                self.assertEqual(sources.refresh(ws)['imported'],0)
            self.assertEqual(ws.store.all(),[])

    def test_onboarding_drafts_are_bounded_and_not_candidate_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp))
            draft={'step':1,'fields':{'name':'Alex Example','roles':'Python','cv_text':'An unfinished import'}}
            ws.save_onboarding(draft)
            self.assertIsNone(ws.profile())
            self.assertEqual(Workspace(Store(tmp)).setting('onboarding_draft'), draft)
            for bad in [{'step':True,'fields':{}},{'step':0,'fields':{'api_key':'secret'}},{'step':0,'fields':{'cv_text':'a'*30001}}]:
                with self.assertRaises(ValueError):ws.save_onboarding(bad)
            ws.save_profile(PROFILE)
            self.assertIsNone(ws.setting('onboarding_draft'))

    def test_explicit_constraints_exclude_known_conflicts_but_not_unknowns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile({**PROFILE,'roles':['Python APIs product'],'strict_constraints':True,'salary_min':50000})
            for identity,audit in [('office',{'remote':False}),('low',{'salary_annual_max_eur':49000}),('unknown',{})]:
                ws.store.import_jobs([{'id':identity,'company':'Example','role':'Python APIs product','url':'https://example.com/'+identity}])
                ws.store.audit(identity,{'checked_at':'2026-11-06T12:00:00Z','sources':['https://example.com'],**audit})
            self.assertEqual([offer['id'] for offer in sources.recommendations(ws)], ['unknown'])
            ws.save_profile({**PROFILE,'roles':['Python APIs product'],'strict_constraints':False,'salary_min':50000})
            self.assertIn('office',[offer['id'] for offer in sources.recommendations(ws)])
