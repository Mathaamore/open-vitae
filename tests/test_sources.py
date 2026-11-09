import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from job_agent import ats, sources, source_catalog, public_feeds
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
            ws = Workspace(Store(Path(tmp)));ws.save_profile(PROFILE);ws.set_setting('source_preferences', {key:'off' for key in ('remotive','remoteok','jobicy','wwr')})
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
            ws=Workspace(Store(tmp));ws.save_profile(PROFILE);ws.set_setting('source_preferences', {key:'off' for key in ('remotive','remoteok','jobicy','wwr')})
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

    def test_selection_uses_only_explicit_preferences_and_preserves_unknown_roles(self):
        def chosen(profile, overrides=None):
            return {s['id'] for s in source_catalog.selection(profile, overrides) if s['selected']}
        self.assertIn('remotive', chosen(PROFILE))
        self.assertNotIn('remotive', chosen({**PROFILE, 'remote':'office'}))
        self.assertIn('remotive', chosen({**PROFILE, 'remote':'office'}, {'remotive':'on'}))
        self.assertNotIn('remotive', chosen(PROFILE, {'remotive':'off'}))
        self.assertIn('euraxess', chosen({**PROFILE,'roles':['Chercheur en biologie']}))
        self.assertIn('reliefweb', chosen({**PROFILE,'roles':['Humanitarian coordinator']}))
        self.assertIn('arbeitnow', chosen({**PROFILE,'roles':['Unknown profession'],'locations':['Paris']}))
        self.assertEqual(source_catalog.countries({'locations':['Paris'],'bio':'France','cv_text':'Sweden'}), [])
        self.assertEqual(source_catalog.countries({'locations':['Berlin, Germany','France'],'search_countries':['US']}), ['US','DE','FR'])
        self.assertNotIn('arbeitnow-uk', chosen({**PROFILE,'search_countries':['FR']}))
        self.assertNotIn('arbeitnow', chosen({**PROFILE,'search_countries':['US']}))

    def test_bounded_rotation_visits_all_roles_countries_without_private_context(self):
        profile={**PROFILE,'roles':['Python','Designer'],'search_countries':['FR','GB'],'email':'private@example.com','cv_text':'private experience'}
        urls=[dict(source_catalog.feeds(profile, {}, rotation=i))['Himalayas'] for i in range(4)]
        from urllib.parse import urlsplit, parse_qs
        self.assertEqual({(parse_qs(urlsplit(url).query)['q'][0],parse_qs(urlsplit(url).query)['country'][0]) for url in urls}, {('Python','FR'),('Python','GB'),('Designer','FR'),('Designer','GB')})
        self.assertTrue(all('private' not in url for url in urls))
        self.assertLessEqual(len(source_catalog.feeds(profile, {})), 7)
        self.assertEqual(len([url for name,url in source_catalog.feeds(profile, {}) if name=='We Work Remotely']),1)

    def test_new_feed_contracts_and_attribution(self):
        for name,raw in [
            ('Remotive', {'url':'https://remotive.com/a','company_name':'Example','title':'Python','candidate_required_location':'Europe','publication_date':'unknown'}),
            ('Remote OK', {'url':'https://remoteok.com/a','company':'Example','position':'Python','location':'US','date':'2026-11-09T12:00:00Z'}),
            ('Jobicy', {'url':'https://jobicy.com/a','companyName':'Example','jobTitle':'Python','jobGeo':'Canada','pubDate':'unknown','salaryMax':80000,'salaryCurrency':'EUR','salaryPeriod':'yearly'})]:
            data=[{'legal':'metadata'},raw] if name=='Remote OK' else {'jobs':[raw]}
            rows,cut=public_feeds.postings(name,data)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['url'],raw['url'])
            self.assertEqual(rows[0]['company_name'],'Example')
            self.assertIs(rows[0]['remote'],True)
            self.assertFalse(cut)
        rss=b'<rss><channel><item><title>Example: Python</title><link>https://weworkremotely.com/a</link><pubDate>Mon, 09 Nov 2026 12:00:00 GMT</pubDate></item><item><title>No employer</title></item></channel></rss>'
        rows,_=public_feeds.postings('We Work Remotely',rss)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['company_name'],'Example')
        self.assertIsNotNone(rows[0]['created_at'])
        for data in [b'<!DOCTYPE rss><rss/>',b'<invalid>',b'<html/>', '<!DOCTYPE rss><rss/>'.encode('utf-16')]:
            with self.assertRaises(ValueError):public_feeds.postings('We Work Remotely',data)
        for name in ('Remotive','Remote OK','Jobicy'):
            with self.assertRaises(ValueError):public_feeds.postings(name,{'jobs':{}})
        smart=ats.postings('smartrecruiters:example',{'content':[{'id':'123','name':'Python','location':{'city':'Paris','country':'FR'}}]})[0]
        self.assertEqual(smart['url'],'https://jobs.smartrecruiters.com/example/123')
        self.assertIsNone(smart['created_at'])
        self.assertEqual(ats.postings('smartrecruiters:example',{'content':[{'id':'../invalid'}]}),[])

    def test_source_cache_partial_retry_limits_and_disabled_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile(PROFILE)
            ws.set_setting('source_preferences',{s['id']:'off' for s in source_catalog.CATALOG if s['id'] not in ('remotive','jobicy')})
            def feed(url):
                if 'remotive' in url:raise ValueError('offline')
                return {'jobs':[{'url':'https://jobicy.com/fictional','companyName':'Example','jobTitle':'Python'}],'hasMore':True}
            with patch.object(sources,'json_request',side_effect=feed) as read, patch.object(sources,'request') as rss:
                first=sources.refresh(ws)
                self.assertEqual(first['imported'],1)
                self.assertIn('Jobicy',first['truncated'])
                second=sources.refresh(ws)
                self.assertEqual(read.call_count,2)
                self.assertIn('Jobicy',second['cached_sources'])
                self.assertIn('Remotive',second['limited_sources'])
                rss.assert_not_called()
                self.assertEqual(ws.store.all()[0]['audit']['source_url'],'https://jobicy.com/fictional')
                with patch.object(sources.time,'time',return_value=time.time()+21601):
                    sources.refresh(ws)
                    self.assertEqual(read.call_count,3)
            self.assertEqual(len(ws.store.all()),1)

    def test_countries_validate_and_old_clients_keep_saved_countries(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile({**PROFILE,'search_countries':['JP','FR','JP']})
            self.assertEqual(ws.save_profile(PROFILE)['search_countries'],['JP','FR'])
            for bad in ('FR',['France'],['ZZ'],[{}]):
                with self.assertRaises(ValueError):ws.save_profile({**PROFILE,'search_countries':bad})
            for bad in ({'unknown':'on'},{'remotive':[]},[]):
                with self.assertRaises(ValueError):source_catalog.preferences(bad)

    def test_failed_source_does_not_stall_rotation_and_jobicy_limit_is_source_wide(self):
        from urllib.parse import urlsplit, parse_qs
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile({**PROFILE,'roles':['Python','Designer']})
            ws.set_setting('source_preferences',{s['id']:'off' for s in source_catalog.CATALOG if s['id'] != 'himalayas'})
            with patch.object(sources,'json_request',side_effect=ValueError('offline')) as read:
                sources.refresh(ws);sources.refresh(ws)
                self.assertEqual(read.call_args_list[0],read.call_args_list[1])
                started=time.time()
                with patch.object(sources.time,'time',return_value=started+86300):sources.refresh(ws)
                with patch.object(sources.time,'time',return_value=started+86401):sources.refresh(ws)
                self.assertEqual(parse_qs(urlsplit(read.call_args.args[0]).query)['q'],['Designer'])
            ws.set_setting('source_preferences',{s['id']:'off' for s in source_catalog.CATALOG if s['id'] != 'jobicy'})
            with patch.object(sources,'json_request',return_value={'jobs':[]}) as read:
                sources.refresh(ws,'Python');result=sources.refresh(ws,'Designer')
                self.assertEqual(read.call_count,1)
                self.assertIn('Jobicy',result['limited_sources'])

    def test_new_imports_deduplicate_and_reject_unsafe_listing_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace(Store(tmp));ws.save_profile(PROFILE)
            ws.set_setting('source_preferences',{s['id']:'off' for s in source_catalog.CATALOG if s['id'] not in ('remotive','remoteok')})
            remotive={'jobs':[{'url':'https://example.com/shared','company_name':'Example','title':'Python'}, {'url':'https://127.0.0.1/private','company_name':'Example','title':'Python'}, {'url':'javascript:alert(1)','company_name':'Example','title':'Python'}]}
            remoteok=[{'url':'https://example.com/shared','company':'Example','position':'Python'}]
            with patch.object(sources,'json_request',side_effect=[remotive,remoteok]):
                self.assertEqual(sources.refresh(ws)['imported'],1)
            self.assertEqual(len(ws.store.all()),1)
