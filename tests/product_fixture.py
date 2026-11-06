"""Explicitly fake providers and sources for isolated browser QA. Never imported by the app."""
import os
from job_agent import app as module
from job_agent import sources, packets
from job_agent.store import now

class FakeProvider:
    def __init__(self):self.connected=False;self.name='Gemini'
    def status(self,fresh=False):return {'available':True,'connected':self.connected,'name':self.name,'provider':'gemini'}
    def connect(self,provider,key=None):self.connected=True;self.name={'chatgpt':'ChatGPT','claude':'Claude','gemini':'Gemini'}[provider];return {'connected':True}
    def disconnect(self):self.connected=False;return {'connected':False}
    def complete(self,task,payload,max_output=1600,**kwargs):
        if task=='prepare_application':
            return {'summary':'I build useful products with Python.','selected_facts':[0], 'company_summary':'Example builds a production tool.','product_summary':'A production tool used by teams.','team_summary':'Équipe non confirmée.', 'answers':{'body':'I build useful products with Python and enjoy working with product teams.'}}
        if task=='rewrite':return {'text':'A shorter factual version.','notes':'Réponse fictive de test.'}
        return {'text':'On peut préciser le type d’équipe qui te convient avant la recherche.','preferences':{'expectations':'Une petite équipe produit'}}

module.providers=FakeProvider()
for identity,company,role in [('offer-one','Example Tools','Python Product Engineer'),('offer-two','Second Example','Data Engineer')]:
    module.store.import_jobs([{'id':identity,'company':company,'role':role,'url':'https://example.com/'+identity}])
    module.store.audit(identity,{'checked_at':now(),'sources':['https://example.com'],'remote':True,'location':'France','description':'Production tools, Python APIs and small product teams.','scores':{}})

def refresh(workspace,query=''):
    result={'imported':2,'errors':[],'cached':False,'time':0,'checked_at':now(),'sources':['Local QA fixture']}
    workspace.set_setting('last_discovery',result);return result
sources.refresh=refresh
packets.inspect_offer=lambda url:{'url':url,'inspected':True,'text':'Example builds production tools with a small product engineering team.', 'fields':[
    {'key':'name','label':'Full name','type':'text','required':True},
    {'key':'email','label':'E-mail','type':'email','required':True},
    {'key':'body','label':'Why this role?','type':'textarea','required':True},
    {'key':'resume','label':'CV','type':'file','required':True},
    {'key':'consent','label':'Test local : consentement explicite','type':'checkbox','required':True}]}
app=module.app
