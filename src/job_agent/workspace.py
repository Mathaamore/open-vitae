"""User-owned profile, feedback and bounded AI usage alongside the existing dossier store."""

from .i18n import tr
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .store import canonical, digest, now


class Workspace:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS feedback (job_id TEXT PRIMARY KEY, decision TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_runs (id TEXT PRIMARY KEY, task TEXT NOT NULL, provider TEXT NOT NULL, model TEXT, cache_key TEXT NOT NULL, status TEXT NOT NULL, usage TEXT, result TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preparations (job_id TEXT PRIMARY KEY, state TEXT NOT NULL, message TEXT NOT NULL, updated_at TEXT NOT NULL);
            ''')
            # A stopped app must not leave a fake spinner or reserve work forever.
            db.execute("UPDATE ai_runs SET status='interrupted' WHERE status='running'")
            db.execute("UPDATE preparations SET state='failed',message=? WHERE state IN ('queued','preparing')", (tr('queue.interrupted'),))

    def setting(self, key, default=None):
        with self.store.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.store.db() as db:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, canonical(value)))

    def profile(self):
        return self.setting('profile')

    def profile_draft(self):
        profile = self.profile()
        if profile:
            return profile
        legacy = self.store.root / 'inputs/profile/resume.json'
        if not legacy.is_file():
            return {}
        resume = json.loads(legacy.read_text())
        basics = resume.get('basics', {})
        text = []
        for section in ('experiences', 'projects', 'education'):
            for item in resume.get(section, []):
                text.append(' | '.join(str(item.get(k, '')) for k in ('title', 'place', 'date_bottom', 'date_top') if item.get(k)))
                text.extend(item.get('items', []))
        return {'name': basics.get('name', ''), 'email': basics.get('email', ''), 'phone': basics.get('phone', ''),
                'cv_text': '\n'.join(text)[:30000], 'strengths': '', 'achievements': '', 'roles': [], 'locations': [],
                'remote': 'flexible', 'bio': '', 'expectations': '', 'portfolio': ''}

    def save_profile(self, value):
        if not isinstance(value, dict):
            raise ValueError(tr('workspace.your_profile_could_not_be_read_check_the'))
        required = {'name': 120, 'bio': 2000, 'strengths': 4000, 'achievements': 10000, 'expectations': 4000}
        result = {}
        for key, limit in {**required, 'email': 254, 'phone': 80, 'portfolio': 500, 'availability': 120, 'cv_text': 30000}.items():
            text = value.get(key, '')
            if not isinstance(text, str) or len(text) > limit:
                raise ValueError(tr('workspace.check_the_profile_field_key', key=key))
            result[key] = text.strip()
        if not result['name'] or not result['bio'] or not (result['cv_text'] or result['achievements']):
            raise ValueError(tr('workspace.add_your_name_a_short_introduction_and_either'))
        for key in ('roles', 'locations'):
            items = value.get(key, [])
            if not isinstance(items, list) or len(items) > 10 or any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 120 for item in items):
                raise ValueError(tr('workspace.check_the_list_of_key_use_up_to', key=key))
            result[key] = list(dict.fromkeys(item.strip() for item in items))
        if not result['roles']:
            raise ValueError(tr('workspace.add_at_least_one_role_or_field_you'))
        from .source_catalog import ISO_COUNTRIES
        search_countries = value.get('search_countries', (self.profile() or {}).get('search_countries', []))
        if not isinstance(search_countries, list) or len(search_countries) > 10 or any(not isinstance(code, str) or code not in ISO_COUNTRIES for code in search_countries):
            raise ValueError('Use up to ten two-letter country codes, such as FR, GB or US.')
        result['search_countries'] = list(dict.fromkeys(search_countries))
        result['remote'] = value.get('remote', 'flexible')
        if result['remote'] not in {'remote', 'hybrid', 'office', 'flexible'}:
            raise ValueError(tr('workspace.choose_remote_hybrid_on_site_or_flexible'))
        minimum = value.get('salary_min')
        if minimum not in ('', None) and (not isinstance(minimum, int) or isinstance(minimum, bool) or not 0 <= minimum <= 1000000):
            raise ValueError(tr('workspace.enter_an_annual_salary_between_0_and_1'))
        result['salary_min'] = minimum or None
        if type(value.get('strict_constraints', False)) is not bool:
            raise ValueError(tr('workspace.check_the_preference_for_excluding_known_conflicts'))
        result['strict_constraints'] = value.get('strict_constraints', False)
        if result['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result['email']):
            raise ValueError(tr('workspace.enter_a_valid_email_address'))
        if result['portfolio'] and not result['portfolio'].startswith('https://'):
            raise ValueError(tr('workspace.use_an_https_link_for_your_portfolio'))
        template=value.get('cv_template',(self.profile() or {}).get('cv_template',''))
        if not isinstance(template,str):raise ValueError(tr('resume.import_a_valid_pdf_cv_template'))
        if template:
            from .resume import source_path
            path=source_path(self,template)
            source_text=extract_resume(path.read_bytes(),'template.pdf')
            if re.sub(r'\s+',' ',source_text).strip()!=re.sub(r'\s+',' ',result['cv_text']).strip():
                raise ValueError(tr('resume.source_text_changed'))
        result['cv_template']=template
        result['revision'] = (self.profile() or {}).get('revision', 0) + 1
        self.set_setting('profile', result)
        self.set_setting('onboarding_draft', None)
        return result

    def save_onboarding(self, value):
        if not isinstance(value, dict) or set(value) != {'step', 'fields'} or type(value['step']) is not int or not 0 <= value['step'] <= 2:
            raise ValueError(tr('workspace.this_setup_step_could_not_be_saved_reload'))
        limits = {'name': 120, 'bio': 2000, 'strengths': 4000, 'achievements': 10000, 'expectations': 4000,
                  'email': 254, 'phone': 80, 'portfolio': 500, 'availability': 120, 'cv_text': 30000,
                  'search_countries': 100, 'cv_template': 64, 'roles': 1000, 'locations': 1000, 'remote': 20, 'salary_min': 20, 'strict_constraints': 5}
        fields = value['fields']
        if not isinstance(fields, dict) or set(fields) - limits.keys() or any(not isinstance(text, str) or len(text) > limits[key] for key, text in fields.items()):
            raise ValueError(tr('workspace.your_progress_could_not_be_saved_check_the'))
        self.set_setting('onboarding_draft', value)
        return {'saved': True}

    def feedback(self):
        with self.store.db() as db:
            return {row['job_id']: dict(row) for row in db.execute('SELECT * FROM feedback')}

    def decide(self, job_id, decision, reason=''):
        if decision not in {'accept', 'reject', 'later', 'reset'} or not isinstance(reason, str) or len(reason) > 500:
            raise ValueError(tr('workspace.choose_save_prepare_or_dismiss_with_a_reason'))
        self.store.get(job_id)
        with self.store.db() as db:
            if decision == 'reset':
                db.execute('DELETE FROM feedback WHERE job_id=?', (job_id,))
                return
            db.execute('INSERT INTO feedback VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET decision=excluded.decision,reason=excluded.reason,created_at=excluded.created_at', (job_id, decision, reason.strip(), now()))

    def message(self, role, text):
        with self.store.db() as db:
            db.execute('INSERT INTO conversations(role,text,created_at) VALUES (?,?,?)', (role, text, now()))

    def messages(self):
        with self.store.db() as db:
            rows = db.execute('SELECT role,text,created_at FROM conversations ORDER BY id DESC LIMIT 40').fetchall()
        return [dict(row) for row in reversed(rows)]

    def cached(self, task, content, provider='chatgpt'):
        with self.store.db() as db:
            row = db.execute("SELECT result FROM ai_runs WHERE cache_key=? AND status='done' ORDER BY created_at DESC LIMIT 1", (digest({'task':task,'provider':provider,'content':content}),)).fetchone()
        return json.loads(row[0]) if row else None

    def invalidate_cache(self, task, content, provider):
        with self.store.db() as db:
            db.execute("UPDATE ai_runs SET status='invalid' WHERE cache_key=? AND status='done'", (digest({'task':task,'provider':provider,'content':content}),))

    def reserve(self, task, provider, content):
        identity = uuid.uuid4().hex
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute("SELECT COUNT(*) FROM ai_runs WHERE created_at>=?", (datetime.now(timezone.utc).strftime('%Y-%m-%d'),)).fetchone()[0]
            limit = self.setting('daily_limit', 20)
            if count >= limit:
                raise ValueError(tr('workspace.you_ve_reached_your_daily_limit_of_limit', limit=limit))
            db.execute('INSERT INTO ai_runs(id,task,provider,cache_key,status,created_at) VALUES (?,?,?,?,?,?)', (identity, task, provider, digest({'task':task,'provider':provider,'content':content}), 'running', now()))
        return identity

    def finish_run(self, identity, result, model, usage):
        with self.store.db() as db:
            db.execute("UPDATE ai_runs SET status='done',result=?,model=?,usage=? WHERE id=?", (canonical(result), model, canonical(usage), identity))

    def fail_run(self, identity):
        with self.store.db() as db:
            db.execute("UPDATE ai_runs SET status='failed' WHERE id=?", (identity,))

    def usage(self):
        with self.store.db() as db:
            rows = [dict(row) for row in db.execute('SELECT task,provider,model,status,usage,created_at FROM ai_runs WHERE created_at>=? ORDER BY created_at DESC', (datetime.now(timezone.utc).strftime('%Y-%m-%d'),))]
        return {'requests': len(rows), 'limit': self.setting('daily_limit', 20), 'runs': [{**row, 'usage': json.loads(row['usage'] or '{}')} for row in rows]}

    def queue(self, job_id):
        with self.store.db() as db:
            cursor = db.execute("INSERT INTO preparations VALUES (?,'queued',?,?) ON CONFLICT(job_id) DO UPDATE SET state='queued',message=excluded.message,updated_at=excluded.updated_at WHERE preparations.state NOT IN ('queued','preparing')", (job_id, tr('queue.start'), now()))
            return cursor.rowcount == 1

    def preparation(self, job_id, state=None, message=''):
        with self.store.db() as db:
            if state:
                db.execute('INSERT INTO preparations VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,message=excluded.message,updated_at=excluded.updated_at', (job_id, state, message, now()))
            row = db.execute('SELECT * FROM preparations WHERE job_id=?', (job_id,)).fetchone()
        return dict(row) if row else None


def preference_patch(value):
    if value is None:
        return None
    if not isinstance(value,dict) or not value or set(value) - {'roles','locations','remote','expectations'}:
        raise ValueError(tr('workspace.the_suggested_preferences_could_not_be_read_your'))
    for key in ('roles','locations'):
        if key in value and (not isinstance(value[key],list) or not 1 <= len(value[key]) <= 10 or any(not isinstance(item,str) or not 1 <= len(item.strip()) <= 120 for item in value[key])):
            raise ValueError(tr('workspace.check_the_suggested_roles_and_locations_before_applying'))
    if 'remote' in value and value['remote'] not in {'remote','hybrid','office','flexible'}:
        raise ValueError(tr('workspace.the_suggested_work_arrangement_is_not_supported'))
    if 'expectations' in value and (not isinstance(value['expectations'],str) or len(value['expectations']) > 4000):
        raise ValueError(tr('workspace.the_suggested_preferences_are_too_long_or_could'))
    return value


def extract_resume(data, filename):
    if len(data) > 8_000_000:
        raise ValueError(tr('app.le_cv_doit_faire_moins_de_8_mo'))
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        import io
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 12:
                raise ValueError(tr('workspace.choose_an_unprotected_pdf_of_up_to_12'))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception:
            raise ValueError(tr('workspace.couldn_t_read_this_pdf_use_an_unprotected')) from None
    elif suffix == '.docx':
        import io
        import zipfile
        import xml.etree.ElementTree as ET
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo('word/document.xml')
                if info.file_size > 2_000_000:
                    raise ValueError(tr('workspace.document_trop_volumineux'))
                document = ET.fromstring(archive.read(info))
                text = '\n'.join(''.join(p.itertext()) for p in document.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
        except Exception:
            raise ValueError(tr('workspace.couldn_t_read_this_word_document_try_a')) from None
    elif suffix in {'.txt', '.md'}:
        try:
            text = data.decode('utf-8')
        except UnicodeError:
            raise ValueError(tr('workspace.save_the_text_file_as_utf_8_and')) from None
    else:
        raise ValueError(tr('workspace.choose_a_text_pdf_docx_or_txt_file'))
    text = text.strip()
    if len(text) < 40:
        raise ValueError(tr('workspace.le_cv_contient_trop_peu_de_texte_lisible'))
    if len(text) > 30000:
        raise ValueError(tr('workspace.the_cv_is_too_long_keep_the_source'))
    return text
