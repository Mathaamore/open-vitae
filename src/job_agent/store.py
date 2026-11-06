from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(os.environ.get('JOB_AGENT_ROOT', Path(__file__).resolve().parents[2])).resolve()
WEIGHTS = {'technical': 25, 'ownership': 25, 'growth': 20, 'remote': 15, 'compensation': 10, 'culture': 5}
LOCKED = {'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNCERTAIN'}


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to((root / 'data').resolve()) or not path.is_file():
        raise ValueError('Artifact must exist inside the private data directory')
    return path


def score(audit):
    reasons = audit.get('scores', {})
    known = {k: v for k, v in reasons.items() if k in WEIGHTS and v.get('value') is not None}
    for value in known.values():
        if not 0 <= value['value'] <= 100 or not value.get('reason'):
            raise ValueError('Each score needs a value from 0 to 100 and evidence')
    # Unknown criteria contribute no points; coverage is always shown beside the score.
    return round(sum(WEIGHTS[k] * v['value'] / 100 for k, v in known.items()), 1), sum(WEIGHTS[k] for k in known)


def category(audit):
    if audit.get('active') is False:
        return 'CLOSED'
    if audit.get('blockers'):
        return 'INELIGIBLE'
    if not (audit.get('active') is True and audit.get('location_allowed', audit.get('france_allowed')) is True and audit.get('requirements_checked')):
        return 'NEEDS_VERIFICATION'
    return 'STRETCH' if audit.get('stretch') else 'PRIORITY'


class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        private = self.root / 'data'
        private.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Avoid asking macOS to change metadata on an already private workspace.
        if private.stat().st_mode & 0o7777 != 0o700:
            private.chmod(0o700)
        self.path = private / 'agent.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, original TEXT NOT NULL, company TEXT NOT NULL,
                role TEXT NOT NULL, url TEXT NOT NULL, audit TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'DISCOVERED', dossier TEXT,
                revision INTEGER NOT NULL DEFAULT 0, approved_hash TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS versions (
                job_id TEXT NOT NULL, revision INTEGER NOT NULL, dossier TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(job_id, revision)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, job_id TEXT, action TEXT NOT NULL,
                details TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                job_id TEXT PRIMARY KEY, dossier_hash TEXT NOT NULL,
                state TEXT NOT NULL, receipt TEXT, created_at TEXT NOT NULL
            );
            ''')
        with self.db() as db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(attempts)')}
            if 'target' not in columns:
                db.execute('ALTER TABLE attempts ADD COLUMN target TEXT')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS attempts_target ON attempts(target)')
        if self.path.stat().st_mode & 0o7777 != 0o600:
            self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, db, job_id, action, details):
        db.execute('INSERT INTO events(job_id,action,details,created_at) VALUES(?,?,?,?)',
                   (job_id, action, canonical(details), now()))

    def get(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (str(job_id),)).fetchone()
        if row is None:
            raise ValueError('Unknown opportunity')
        job = dict(row)
        for key in ('original', 'audit', 'dossier'):
            job[key] = json.loads(job[key]) if job[key] else None
        job['score'], job['coverage'] = score(job['audit'])
        job['category'] = category(job['audit'])
        job['fingerprint'] = self.fingerprint(job) if job['dossier'] else None
        return job

    def all(self):
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM jobs ORDER BY company,role')]
        return sorted([self.get(i) for i in ids], key=lambda j: -j['score'])

    def import_jobs(self, rows, expected=None):
        if not isinstance(rows, list) or (expected is not None and len(rows) != expected):
            raise ValueError(f'Expected a list of {expected or "all"} opportunities')
        ids = []
        normalized = []
        for item in rows:
            if not isinstance(item, dict) or 'id' not in item or isinstance(item['id'], bool) or not isinstance(item['id'], (str, int)):
                raise ValueError('Every opportunity requires its original string/integer id')
            job_id = str(item['id'])
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',job_id):
                raise ValueError('Unsafe opportunity id; original entry was not changed or imported')
            if not job_id or job_id in ids:
                raise ValueError('Missing or duplicate id; nothing was imported')
            ids.append(job_id)
            company = item.get('company') or item.get('entreprise')
            role = item.get('role') or item.get('title') or item.get('poste')
            url = item.get('url') or item.get('official_url') or item.get('url_officielle') or item.get('lien')
            if not all(isinstance(v, str) and v.strip() for v in (company, role, url)):
                raise ValueError(f'{job_id}: company, role and official url required; source keys: {list(item)}')
            if not url.startswith('https://'):
                raise ValueError(f'{job_id}: official HTTPS URL required')
            normalized.append((job_id, canonical(item), company, role, url, now()))
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for values in normalized:
                existing = db.execute('SELECT original FROM jobs WHERE id=?', (values[0],)).fetchone()
                if existing and existing[0] != values[1]:
                    raise ValueError(f'{values[0]} already exists with different source data; no overwrite')
                db.execute('INSERT OR IGNORE INTO jobs(id,original,company,role,url,updated_at) VALUES(?,?,?,?,?,?)', values)
            self.event(db, None, 'IMPORT', {'count': len(rows), 'ids': ids, 'source_hash': digest(rows)})
        return len(rows)

    def audit(self, job_id, audit):
        score(audit)
        if not audit.get('checked_at') or not audit.get('sources'):
            raise ValueError('Audit requires sources and verification time')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None or row[0] in LOCKED:
                raise ValueError('Unknown or submission-locked opportunity')
            state = 'CLOSED' if category(audit) == 'CLOSED' else 'VERIFIED' if category(audit) in {'PRIORITY','STRETCH'} else 'NEEDS_INPUT'
            db.execute('UPDATE jobs SET audit=?,status=?,approved_hash=NULL,updated_at=? WHERE id=?',
                       (canonical(audit), state, now(), job_id))
            self.event(db, job_id, 'AUDIT', audit)

    def fingerprint(self, job):
        dossier = job['dossier']
        hashes = {}
        for f in dossier.get('attachments', []):
            try: hashes[f['path']] = file_hash(artifact(self.root, f['path']))
            except ValueError: hashes[f['path']] = 'MISSING'
        return digest({'id': job['id'], 'url': job['url'], 'revision': job['revision'],
                       'dossier': dossier, 'files': hashes, 'audit': job['audit']})

    def readiness(self, job):
        dossier = job['dossier']
        if not dossier:
            return ['Dossier absent']
        problems = list(dossier.get('missing', []))
        for attachment in dossier.get('attachments', []):
            try: artifact(self.root, attachment['path'])
            except ValueError: problems.append('Pièce jointe absente ou invalide')
        if job['category'] not in {'PRIORITY', 'STRETCH'}:
            problems.append('Éligibilité et annonce à vérifier')
        if not dossier.get('attachments') or not any(f['path'].endswith('.pdf') for f in dossier['attachments']):
            problems.append('CV PDF absent')
        if not dossier.get('form'):
            problems.append('Formulaire actuel non inspecté')
        for field in (dossier.get('form') or {}).get('fields', []):
            if field.get('required') and (dossier.get('answers', {}).get(field['key']) in (None, '', []) or field.get('type') == 'checkbox' and not field.get('options') and dossier.get('answers', {}).get(field['key']) is not True):
                problems.append('Réponse requise : ' + field['label'])
            answer = dossier.get('answers', {}).get(field['key'])
            if field.get('type') == 'file' and answer and answer not in {f['path'] for f in dossier.get('attachments', []) if f.get('send', True)}:
                problems.append('Fichier à téléverser absent des pièces approuvées : ' + field['label'])
            if field.get('selection_count') is not None and isinstance(answer,list) and len(answer) != field['selection_count']:
                problems.append('Sélectionner exactement ' + str(field['selection_count']) + ' choix : ' + field['label'])
        return problems

    def save(self, job_id, dossier, revision):
        # Validate artifacts before opening the transaction; they are rehashed on approval and send.
        for entry in dossier.get('attachments', []):
            artifact(self.root, entry['path'])
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,revision,dossier,approved_hash FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None or row['status'] in LOCKED:
                raise ValueError('Opportunity locked; uncertain sends must be reconciled manually')
            if row['revision'] != revision:
                raise ValueError('Dossier changed in another tab; reload before saving')
            if row['dossier'] == canonical(dossier) and (not row['approved_hash'] or row['approved_hash'] == self.get(job_id)['fingerprint']):
                return
            new_revision = revision + 1
            archive = self.root / 'data/versions' / digest(job_id)[:16] / str(new_revision)
            archive.mkdir(parents=True,exist_ok=True)
            snapshots = []
            for attachment in dossier.get('attachments', []):
                source = artifact(self.root,attachment['path'])
                target = archive / (file_hash(source)[:12] + '-' + source.name)
                if not target.exists(): shutil.copyfile(source,target)
                snapshots.append({'original':attachment['path'],'snapshot':str(target.relative_to(self.root)),'sha256':file_hash(target)})
            (archive / 'manifest.json').write_text(canonical({'dossier':dossier,'files':snapshots}))
            job = self.get(job_id)
            job['dossier'] = dossier
            status = 'NEEDS_INPUT' if self.readiness(job) else 'APPLICATION_READY'
            db.execute('INSERT INTO versions VALUES(?,?,?,?)', (job_id, new_revision, canonical(dossier), now()))
            db.execute('UPDATE jobs SET dossier=?,revision=?,status=?,approved_hash=NULL,updated_at=? WHERE id=?',
                       (canonical(dossier), new_revision, status, now(), job_id))
            self.event(db, job_id, 'DOSSIER_SAVED', {'revision': new_revision})

    def decision(self, job_id, choice, fingerprint):
        if choice not in {'GO', 'REVIEW', 'SKIP', 'LATER'}:
            raise ValueError('Expected REVIEW, GO, SKIP or LATER')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self.get(job_id)
            if job['status'] in LOCKED:
                raise ValueError('Submission already attempted; duplicate prohibited')
            if fingerprint != job['fingerprint']:
                raise ValueError('Dossier changed; review the current version')
            if choice in {'GO', 'REVIEW'}:
                if (choice == 'GO' and job['status'] != 'APPLICATION_READY') or self.readiness(job):
                    raise ValueError('Complète le dossier avant de le valider')
                state, approved = ('APPROVED' if choice == 'GO' else 'REVIEWED'), fingerprint
            else:
                state, approved = ('SKIPPED' if choice == 'SKIP' else 'NEEDS_INPUT'), None
            db.execute('UPDATE jobs SET status=?,approved_hash=?,updated_at=? WHERE id=?', (state, approved, now(), job_id))
            self.event(db, job_id, choice, {'revision': job['revision'], 'fingerprint': fingerprint})

    def claim(self, job_id, form):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self.get(job_id)
            if job['status'] != 'APPROVED' or self.readiness(job) or job['approved_hash'] != job['fingerprint']:
                raise ValueError('An explicit GO for the exact current dossier is required')
            if canonical(form) != canonical(job['dossier']['form']):
                db.execute('UPDATE jobs SET status="NEEDS_INPUT",approved_hash=NULL WHERE id=?', (job_id,))
                self.event(db, job_id, 'FORM_CHANGED', {})
                mismatch = True
            else:
                mismatch = False
                try:
                    parsed = urlparse(form.get('url',job['url']))
                    target = parsed.netloc.lower() + '/' + form['applicationId'] if form.get('applicationId') else parsed.netloc.lower() + parsed.path.rstrip('/').removesuffix('/application')
                    db.execute('INSERT INTO attempts(job_id,dossier_hash,state,receipt,created_at,target) VALUES(?,?,?,?,?,?)', (job_id, job['fingerprint'], 'SUBMITTING', None, now(),target))
                except sqlite3.IntegrityError:
                    raise ValueError('An attempt already exists; duplicate prohibited') from None
                db.execute('UPDATE jobs SET status="SUBMITTING" WHERE id=?', (job_id,))
                self.event(db, job_id, 'SUBMITTING', {'fingerprint': job['fingerprint']})
        if mismatch:
            raise ValueError('Form changed; approval revoked, review required')
        return job

    def finish(self, job_id, receipt=None):
        state = 'SUBMITTED' if receipt else 'SUBMISSION_UNCERTAIN'
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM attempts WHERE job_id=? AND state="SUBMITTING"', (job_id,)).fetchone():
                raise ValueError('No active submission attempt')
            db.execute('UPDATE attempts SET state=?,receipt=? WHERE job_id=?', (state, canonical(receipt), job_id))
            db.execute('UPDATE jobs SET status=?,updated_at=? WHERE id=?', (state, now(), job_id))
            self.event(db, job_id, state, receipt or {'reason': 'No verified confirmation; automatic retries prohibited'})

    def history(self, job_id):
        with self.db() as db:
            return {'events': [dict(r) for r in db.execute('SELECT * FROM events WHERE job_id=? ORDER BY id DESC', (job_id,))],
                    'versions': [dict(r) for r in db.execute('SELECT * FROM versions WHERE job_id=? ORDER BY revision DESC', (job_id,))]}

    def confirm_manual(self, job_id, confirmation, fingerprint=None, declared_sent=False):
        if declared_sent is True:
            if confirmation is not None and not isinstance(confirmation, str):
                raise ValueError('La note doit être du texte')
            confirmation = (confirmation or '').strip() or 'Envoi déclaré par l’utilisateur, sans justificatif joint.'
        elif not isinstance(confirmation,str) or len(confirmation.strip()) < 15:
            raise ValueError('Paste the actual application confirmation or email sent receipt')
        job = self.get(job_id)
        if job['status'] not in {'REVIEWED','APPROVED','MANUAL_ACTION_REQUIRED','SUBMISSION_UNCERTAIN'} or job['fingerprint'] != job['approved_hash']:
            raise ValueError('An approved unchanged dossier is required before recording a manual confirmation')
        if job['status'] == 'REVIEWED':
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                job = self.get(job_id)
                if job['status'] != 'REVIEWED' or fingerprint != job['fingerprint'] or fingerprint != job['approved_hash']:
                    raise ValueError('Le dossier a changé : recharge et relis la version actuelle')
                form = job['dossier']['form']
                parsed = urlparse(form.get('url',job['url']))
                target = parsed.netloc.lower() + '/' + form['applicationId'] if form.get('applicationId') else parsed.netloc.lower() + parsed.path.rstrip('/').removesuffix('/application')
                receipt = {'confirmation':confirmation.strip(),'verified_by':'user','checked_at':now()}
                try:
                    db.execute('INSERT INTO attempts(job_id,dossier_hash,state,receipt,created_at,target) VALUES(?,?,?,?,?,?)',
                               (job_id,fingerprint,'SUBMITTED',canonical(receipt),now(),target))
                except sqlite3.IntegrityError:
                    raise ValueError('Un envoi est déjà enregistré pour cette candidature') from None
                db.execute('UPDATE jobs SET status="SUBMITTED",updated_at=? WHERE id=?',(now(),job_id))
                self.event(db,job_id,'MANUAL_CONFIRMATION',receipt)
            return
        if job['status'] == 'SUBMISSION_UNCERTAIN':
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM attempts WHERE job_id=? AND state="SUBMISSION_UNCERTAIN"',(job_id,)).fetchone():
                    raise ValueError('No uncertain attempt to reconcile')
                receipt={'confirmation':confirmation,'verified_by':'user','checked_at':now()}
                db.execute('UPDATE attempts SET state="SUBMITTED",receipt=? WHERE job_id=?',(canonical(receipt),job_id))
                db.execute('UPDATE jobs SET status="SUBMITTED",updated_at=? WHERE id=?',(now(),job_id))
                self.event(db,job_id,'MANUAL_CONFIRMATION',receipt)
        else:
            with self.db() as db:
                db.execute('UPDATE jobs SET status="APPROVED" WHERE id=? AND status="MANUAL_ACTION_REQUIRED"',(job_id,))
            self.claim(job_id,job['dossier']['form'])
            self.finish(job_id,{'confirmation':confirmation,'verified_by':'user','checked_at':now()})
