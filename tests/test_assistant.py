import json
import io
from types import SimpleNamespace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from job_agent.assistant import AssistantError, CodexAssistant, login_url

FAKE = r'''
import sys,json,os
logged=False
for line in sys.stdin:
 value=json.loads(line);method=value['method'];identity=value.get('id')
 if identity is None:continue
 with open(os.environ['CODEX_HOME']+'/requests.jsonl','a') as f:f.write(json.dumps(value)+'\n')
 result={}
 if method=='account/read':result={'account':{'type':'chatgpt','email':'test@example.com','planType':'plus'} if logged else None}
 elif method=='account/login/start':
  logged=True;result={'loginId':'test-login','authUrl':'https://auth.openai.com/authorize?test=1'}
 elif method=='account/logout':logged=False
 elif method=='thread/start':result={'thread':{'id':'thread-test'}}
 elif method=='turn/start':result={'turn':{'id':'turn-test'}}
 print(json.dumps({'id':identity,'result':result}),flush=True)
 if method=='turn/start':
  print(json.dumps({'method':'item/completed','params':{'threadId':'thread-test','item':{'type':'agentMessage','text':json.dumps({'text':'Une proposition sincère.','notes':'Vérifie les faits.'})}}}),flush=True)
  print(json.dumps({'method':'turn/completed','params':{'threadId':'thread-test','turn':{'id':'turn-test','status':'completed'}}}),flush=True)
'''

class AssistantTest(unittest.TestCase):
    def test_official_login_urls_only(self):
        self.assertTrue(login_url('https://auth.openai.com/authorize').startswith('https:'))
        for url in ['javascript:alert(1)','http://auth.openai.com/a','https://auth.openai.com.evil.test','https://evil@chatgpt.com']:
            with self.assertRaises(AssistantError):login_url(url)


    def test_old_login_completion_does_not_cancel_the_current_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant=CodexAssistant(tmp)
            assistant.login_id='current-login'
            def completion(identity, success):
                event={'method':'account/login/completed','params':{'loginId':identity,'success':success}}
                assistant.read(SimpleNamespace(stdout=io.StringIO(json.dumps(event)+'\n')))
            completion('old-login',False)
            self.assertEqual(assistant.login_id,'current-login')
            self.assertIsNone(assistant.login_error)
            completion('current-login',False)
            self.assertIsNone(assistant.login_id)
            self.assertTrue(assistant.login_error)

    def test_protocol_connection_generation_and_isolated_read_only_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/'fake-codex';binary.write_text('#!'+sys.executable+'\n'+FAKE);binary.chmod(0o700)
            assistant=CodexAssistant(root)
            with patch.dict(os.environ,{'JOB_AGENT_CODEX':str(binary)}):
                try:
                    self.assertFalse(assistant.status()['connected'])
                    with self.assertRaises(AssistantError):assistant.suggest('not connected')
                    self.assertIn('auth.openai.com',assistant.login()['url'])
                    self.assertTrue(assistant.status()['connected'])
                    result=assistant.suggest('selected context')
                    self.assertEqual(result['text'],'Une proposition sincère.')
                    requests=[json.loads(line) for line in (assistant.home/'requests.jsonl').read_text().splitlines()]
                    thread=next(r['params'] for r in requests if r['method']=='thread/start')
                    self.assertTrue(thread['ephemeral']);self.assertEqual(thread['sandbox'],'read-only')
                    self.assertEqual(thread['approvalPolicy'],'never')
                    self.assertEqual(Path(thread['cwd']).parent,assistant.home)
                    turn=next(r['params'] for r in requests if r['method']=='turn/start')
                    self.assertEqual(turn['sandboxPolicy'],{'type':'readOnly','networkAccess':False})
                    self.assertEqual(turn['input'][0]['text'],'selected context')
                finally:assistant.close()

if __name__=='__main__':unittest.main()
