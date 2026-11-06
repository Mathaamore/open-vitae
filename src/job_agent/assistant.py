"""Local Codex app-server client. No credentials or model output enter the dossier automatically."""

from .i18n import tr
import atexit
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse


class AssistantError(ValueError):
    pass


def login_url(value):
    url = urlparse(value)
    if url.scheme != 'https' or url.hostname not in {'auth.openai.com', 'chatgpt.com'} or url.username or url.password:
        raise AssistantError(tr('assistant.adresse_de_connexion_openai_inattendue'))
    return value




class CodexAssistant:
    def __init__(self, root):
        self.root = Path(root)
        self.home = self.root / 'data/assistant-session'
        self.process = None
        self.reader = None
        self.pending = {}
        self.events = queue.Queue()
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.sequence = 0
        self.login_id = None
        self.login_error = None
        atexit.register(self.close)

    def binary(self):
        return os.environ.get('JOB_AGENT_CODEX') or shutil.which('codex')

    def start(self):
        if self.process and self.process.poll() is None:
            return
        binary = self.binary()
        if not binary:
            raise AssistantError(tr('assistant.codex_est_introuvable_utilise_la_version_mac_qui'))
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.home.stat().st_mode & 0o7777 != 0o700:
            self.home.chmod(0o700)
        work = self.home / 'empty-workspace'
        work.mkdir(exist_ok=True, mode=0o700)
        env = {k: v for k, v in os.environ.items() if k not in {'OPENAI_API_KEY', 'ACCESS_TOKEN', 'CHATGPT_ACCESS_TOKEN'}}
        env['CODEX_HOME'] = str(self.home)
        args = [binary, 'app-server', '-c', 'cli_auth_credentials_store="keyring"',
                '-c', 'features.shell_tool=false', '-c', 'features.apply_patch_freeform=false',
                '-c', 'features.web_search=false', '-c', 'web_search="disabled"',
                '-c', 'features.multi_agent=false', '-c', 'features.image_generation=false',
                '-c', 'features.view_image=false', '-c', 'features.tool_suggest=false',
                '-c', 'features.code_mode_host=false']
        try:
            self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True, cwd=work, env=env)
        except OSError:
            raise AssistantError(tr('assistant.couldn_t_start_the_chatgpt_connection_try_reconnecting')) from None
        self.reader = threading.Thread(target=self.read, args=(self.process,), daemon=True)
        self.reader.start()
        self.request('initialize', {'clientInfo': {'name': 'candidatures_local', 'title': 'Open Vitæ', 'version': '0.3.1'}})
        self.send({'method': 'initialized', 'params': {}})

    def send(self, value):
        with self.lock:
            try:
                self.process.stdin.write(json.dumps(value) + '\n')
                self.process.stdin.flush()
            except (OSError, AttributeError):
                raise AssistantError(tr('assistant.the_chatgpt_connection_was_interrupted_reconnect_and_try')) from None

    def read(self, process):
        try:
            for line in process.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if 'id' in value and 'method' in value:
                    # This writing assistant never approves tools, commands, file access or permissions.
                    self.send({'id': value['id'], 'error': {'code': -32601, 'message': 'Tools are unavailable in this writing assistant'}})
                elif 'id' in value:
                    with self.lock:
                        target = self.pending.get(value['id'])
                    if target:
                        target.put(value)
                else:
                    if value.get('method') == 'account/login/completed':
                        params = value.get('params', {})
                        # A cancelled earlier attempt must not overwrite the current sign-in.
                        if params.get('loginId') == self.login_id:
                            self.login_id = None
                            self.login_error = None if params.get('success') else tr('assistant.sign_in_didn_t_finish_try_connecting_again')
                    self.events.put(value)
        finally:
            with self.lock:
                for target in self.pending.values():
                    target.put({'error': {'message': 'Codex stopped'}})

    def request(self, method, params=None, timeout=25):
        with self.lock:
            self.sequence += 1
            identity = self.sequence
            target = queue.Queue()
            self.pending[identity] = target
        try:
            self.send({'id': identity, 'method': method, 'params': params or {}})
            try:
                response = target.get(timeout=timeout)
            except queue.Empty:
                raise AssistantError(tr('assistant.chatgpt_is_taking_too_long_to_respond_try')) from None
            if 'error' in response:
                raise AssistantError(tr('assistant.chatgpt_couldn_t_complete_this_request_check_the'))
            return response['result']
        finally:
            with self.lock:
                self.pending.pop(identity, None)

    def status(self):
        if not self.binary():
            return {'available': False, 'connected': False}
        with self.operation:
            self.start()
            account = self.request('account/read', {'refreshToken': False}).get('account') or {}
            return {'available': True, 'connected': account.get('type') == 'chatgpt',
                    'email': account.get('email'), 'plan': account.get('planType'),
                    'pending': bool(self.login_id), 'error': self.login_error}

    def login(self):
        with self.operation:
            self.start()
            if self.login_id:
                self.request('account/login/cancel', {'loginId': self.login_id})
            result = self.request('account/login/start', {'type': 'chatgpt'})
            self.login_id = result.get('loginId')
            self.login_error = None
            return {'url': login_url(result['authUrl'])}

    def logout(self):
        with self.operation:
            self.start()
            if self.login_id:
                self.request('account/login/cancel', {'loginId': self.login_id})
            self.request('account/logout')
            self.login_id = None
            self.login_error = None
        return {'connected': False}

    def suggest(self, content):
        result = self.complete(content,
            'Edit one application answer. Use only supplied facts. Keep its language and meaning. Never invent enthusiasm, experience or consent. Respect word limits. Return JSON with text and notes.',
            {'type': 'object', 'properties': {'text': {'type': 'string'}, 'notes': {'type': 'string'}}, 'required': ['text', 'notes'], 'additionalProperties': False})
        result.pop('_model', None); result.pop('_usage', None)
        if not isinstance(result.get('text'), str) or not result['text'].strip() or not isinstance(result.get('notes'), str):
            raise AssistantError(tr('assistant.the_suggested_revision_could_not_be_read_your'))
        return result

    def complete(self, content, instructions, schema=None, max_output=1600):
        if not self.operation.acquire(blocking=False):
            raise AssistantError(tr('assistant.a_request_is_already_running_wait_for_it'))
        thread_id = None
        try:
            self.start()
            account = self.request('account/read', {'refreshToken': False}).get('account') or {}
            if account.get('type') != 'chatgpt':
                raise AssistantError(tr('assistant.connecte_ton_compte_chatgpt_avant_de_demander_une'))
            while not self.events.empty():
                self.events.get_nowait()
            catalog = self.request('model/list', {'includeHidden': False}).get('data', [])
            small = next((m for m in catalog if 'mini' in m.get('model', '').lower() and not m.get('hidden')), None)
            chosen = small or next((m for m in catalog if m.get('isDefault')), None)
            model = chosen.get('model') if chosen else None
            efforts = [e.get('reasoningEffort') for e in (chosen or {}).get('supportedReasoningEfforts', [])]
            thread_options = {'model': model} if model else {}
            result = self.request('thread/start', {'ephemeral': True, 'sandbox': 'read-only',
                'approvalPolicy': 'never', 'baseInstructions': instructions + f' Keep your response under approximately {max_output} output tokens.',
                'cwd': str(self.home / 'empty-workspace'), 'serviceName': 'candidatures',
                'config': {'project_doc_max_bytes': 0}, **thread_options})
            thread_id = result['thread']['id']
            turn_options = {'effort': 'low'} if 'low' in efforts else {}
            self.request('turn/start', {'threadId': thread_id, 'input': [{'type': 'text', 'text': content}],
                'approvalPolicy': 'never', 'sandboxPolicy': {'type': 'readOnly', 'networkAccess': False},
                'outputSchema': schema, **turn_options})
            usage = {}
            end = time.monotonic() + 120
            answer = None
            while time.monotonic() < end:
                try:
                    event = self.events.get(timeout=min(2, max(.01, end-time.monotonic())))
                except queue.Empty:
                    continue
                params = event.get('params', {})
                if params.get('threadId') != thread_id:
                    continue
                if event.get('method') == 'thread/tokenUsage/updated':
                    usage = params.get('tokenUsage', {}).get('last', {})
                if event.get('method') == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
                    answer = params['item'].get('text')
                if event.get('method') == 'turn/completed':
                    if params.get('turn', {}).get('status') != 'completed':
                        raise AssistantError(tr('assistant.the_request_didn_t_finish_check_your_account'))
                    try:
                        output = json.loads(answer or '')
                    except ValueError:
                        raise AssistantError(tr('assistant.the_response_could_not_be_used_your_original')) from None
                    if not isinstance(output, dict) or len(json.dumps(output)) > 40000:
                        raise AssistantError(tr('assistant.the_response_could_not_be_read_try_again'))
                    return {**output, '_model': model or result.get('model', 'catalogue Codex'), '_usage': usage}
            raise AssistantError(tr('assistant.the_request_timed_out_after_two_minutes_your'))
        finally:
            # Stop any timed-out turn and discard its isolated, ephemeral workspace.
            if thread_id:
                self.close()
            self.operation.release()

    def close(self):
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if self.reader and self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
