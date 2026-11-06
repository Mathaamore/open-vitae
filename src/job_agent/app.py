from __future__ import annotations

import json
import secrets
import time
import re
from threading import Lock, Event
from importlib.metadata import version
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .store import Store, artifact, LOCKED, now
from .assistant import CodexAssistant
from .workspace import Workspace, extract_resume, preference_patch
from .providers import Providers, CATALOG
from . import sources, packets, opportunities, portable
from starlette.concurrency import run_in_threadpool

app = FastAPI(title='Open Vitæ', docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','testserver'])
store = Store()
assistant = CodexAssistant(store.root)
workspace = Workspace(store)
providers = Providers(workspace, assistant)
preparation_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dossier")
discovery_lock = Lock()
discovery_cancel = Event()
discovery_status = {'state': 'idle'}
TOKEN = secrets.token_urlsafe(32)
WEB = Path(__file__).parent / 'web'
context_file = store.root / 'data/company-context.json'
COMPANY_CONTEXT = json.loads(context_file.read_text()) if context_file.is_file() else {'companies': {}, 'roles': {}}


@app.middleware('http')
async def local_only(request: Request, call_next):
    origin=request.headers.get('origin')
    if origin and (request.method not in {'GET','HEAD'} or request.url.path.startswith('/api/')) and (urlparse(origin).hostname not in {'127.0.0.1','localhost'} or urlparse(origin).netloc != request.headers.get('host')):
        return JSONResponse({'error':'Local origin required'}, status_code=403)
    if request.method not in {'GET','HEAD'} or request.url.path.startswith(('/api/assistant', '/api/providers', '/api/bootstrap')):
        if request.headers.get('x-local-token') != TOKEN:
            return JSONResponse({'error':'Reload the local dashboard'}, status_code=403)
    if request.url.path.startswith('/api/') and request.headers.get('sec-fetch-site') == 'cross-site':
        return JSONResponse({'error':'Local origin required'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self'; object-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"
    return response


@app.exception_handler(ValueError)
async def invalid(request, exc):
    return JSONResponse({'error':str(exc)},status_code=409)


@app.get('/')
def index(): return FileResponse(WEB/'index.html')


@app.get('/api/session')
def session(): return {'token':TOKEN}


@app.get('/api/jobs')
def jobs():
    feedback = workspace.feedback()
    return [{**{k:v for k,v in job.items() if k not in {'dossier','original','approved_hash'}}, 'interest': feedback.get(job['id'], {}).get('decision'), 'preparation': workspace.preparation(job['id'])} for job in store.all()]


@app.get('/api/jobs/{job_id}')
def job(job_id: str):
    result = store.get(job_id)
    result['context'] = {
        'company': COMPANY_CONTEXT['companies'].get(result['company']),
        'role': COMPANY_CONTEXT['roles'].get(job_id),
    }
    if result['audit'].get('company_context'):
        result['context'] = result['audit']['company_context']
    result['preparation'] = workspace.preparation(job_id)
    result['problems'] = store.readiness(result)
    result['history'] = store.history(job_id)
    return result


async def payload(request):
    try: data=await request.json()
    except ValueError: raise ValueError('JSON invalide') from None
    if not isinstance(data,dict): raise ValueError('Objet JSON requis')
    return data


@app.put('/api/jobs/{job_id}')
async def save(job_id: str, request: Request):
    data = await payload(request)
    current = store.get(job_id)
    if not isinstance(data,dict) or not isinstance(data.get('answers'),dict) or not isinstance(data.get('motivation'),str):
        raise ValueError('Answers and motivation required')
    dossier = current['dossier']
    if not dossier: raise ValueError('Prepare the dossier first')
    # The UI may edit answers, not eligibility, form schema, recipient or delivery plan.
    dossier['answers'] = data['answers']
    dossier['motivation'] = data['motivation']
    store.save(job_id,dossier,data.get('revision'))
    return job(job_id)



@app.post('/api/jobs/{job_id}/decision')
async def decide(job_id: str, request: Request):
    data = await payload(request)
    if data.get('choice') == 'GO':
        raise ValueError('Mode préparation uniquement : aucun envoi depuis cette interface')
    store.decision(job_id,data.get('choice'),data.get('fingerprint'))
    return job(job_id)


@app.post('/api/jobs/{job_id}/confirmation')
async def confirmation(job_id: str, request: Request):
    data=await payload(request)
    store.confirm_manual(job_id,data.get('confirmation'),data.get('fingerprint'),data.get('declared_sent',False))
    return job(job_id)


@app.get('/api/jobs/{job_id}/email')
def email(job_id: str):
    from .delivery import build_email
    current = store.get(job_id)
    if not current['dossier'] or current['dossier']['submission'].get('mode') != 'email':
        raise ValueError('This dossier is not an email application')
    # Downloading a draft is preparation; it never sends mail.
    message = build_email(current,store.root,current['dossier']['submission'].get('sender',''))
    return Response(message.as_bytes(),media_type='message/rfc822',headers={'Content-Disposition':f'attachment; filename="application-{job_id}.eml"'})


@app.get('/api/jobs/{job_id}/artifact/{filename}')
def document(job_id: str, filename: str):
    allowed = {'resume.pdf','resume.html','resume.json','tailoring.json','motivation.txt'}
    if filename not in allowed or job_id not in {j['id'] for j in store.all()}:
        raise ValueError('Unknown dossier artifact')
    current = store.get(job_id)
    files = (current.get('dossier') or {}).get('attachments',[])
    pdf = next((entry['path'] for entry in files if entry.get('path','').endswith('/resume.pdf')),None)
    relative = str(Path(pdf).parent/filename) if pdf and '/local-' in pdf else f'data/dossiers/{job_id}/{filename}'
    return FileResponse(artifact(store.root,relative))

@app.get('/api/assistant')
def assistant_status():
    return providers.status(fresh=True)


@app.post('/api/assistant/login')
def assistant_login():
    result=providers.connect('chatgpt')
    workspace.set_setting('provider','chatgpt')
    workspace.set_setting('local_mode',False)
    return result


@app.post('/api/assistant/logout')
def assistant_logout():
    result=providers.disconnect()
    workspace.set_setting('local_mode',True)
    return result


@app.post('/api/jobs/{job_id}/suggestion')
async def suggestion(job_id: str, request: Request):
    from starlette.concurrency import run_in_threadpool
    data = await payload(request)
    current = store.get(job_id)
    if current['status'] in LOCKED or not current['dossier']:
        raise ValueError('Ce dossier ne peut pas être modifié.')
    if data.get('revision') != current['revision']:
        raise ValueError('Le dossier a changé. Recharge-le avant de continuer.')
    field = next((f for f in current['dossier'].get('form', {}).get('fields', []) if f['key'] == data.get('field')), None)
    if not field or field.get('type') in {'file', 'checkbox', 'radio', 'select'}:
        raise ValueError('Choisis une réponse écrite dans ce dossier.')
    text, instruction = data.get('text'), data.get('instruction', '')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 20000 or not isinstance(instruction, str) or len(instruction) > 1000:
        raise ValueError('Texte ou consigne invalide.')
    context = {'company': COMPANY_CONTEXT['companies'].get(current['company']), 'role': COMPANY_CONTEXT['roles'].get(job_id)}
    profile = workspace.profile()
    if not profile:
        raise ValueError('Complète ton profil avant de reformuler.')
    def validate(result):
        if not isinstance(result.get('text'), str) or not result['text'].strip() or len(result['text']) > 20000 or not isinstance(result.get('notes'), str):
            raise ValueError('La proposition reçue est invalide.')
    result = await run_in_threadpool(providers.complete, 'rewrite', {'profile': {key: (value[:10000] if isinstance(value, str) else value) for key, value in profile.items() if key in {'bio','strengths','achievements','cv_text','expectations'}}, 'context': context, 'question': field.get('label'),
        'original': text, 'instruction': instruction, 'format': 'Return JSON with text and notes.'}, validator=validate)
    validate(result)
    return result


@app.get('/api/bootstrap')
def bootstrap():
    cached = getattr(providers,'cached',None)
    connection = cached[2] if isinstance(cached,tuple) and len(cached)==3 and not workspace.setting('local_mode',False) else {'connected':False,'provider':workspace.setting('provider'),'name':'Mode local · IA facultative'}
    return {'connection': connection, 'onboarded': bool(workspace.profile()),
            'profile': workspace.profile_draft(),
            'onboarding': workspace.setting('onboarding_draft'),
            'profile_analysis':workspace.setting('portable_profile_analysis'), 'providers': CATALOG, 'version': version('open-vitae')}


@app.get('/api/providers')
def provider_status():
    return {**providers.status(fresh=True), 'options': CATALOG}


@app.post('/api/providers/connect')
async def connect_provider(request: Request):
    data = await payload(request)
    result = await run_in_threadpool(providers.connect, data.get('provider'), data.get('key'))
    workspace.set_setting('provider',data.get('provider'))
    workspace.set_setting('local_mode',False)
    return result


@app.post('/api/providers/disconnect')
def disconnect_provider():
    result=providers.disconnect()
    workspace.set_setting('local_mode',True)
    return result


@app.post('/api/providers/local')
def local_mode():
    workspace.set_setting('local_mode',True)
    return {'local':True}


@app.post('/api/opportunities')
async def add_opportunity(request: Request):
    return opportunities.add(workspace,await payload(request))


@app.put('/api/opportunities/{job_id}')
async def edit_opportunity(job_id: str, request: Request):
    return opportunities.edit(workspace,job_id,await payload(request))


@app.post('/api/opportunities/retrieve')
async def retrieve_opportunity(request: Request):
    data=await payload(request)
    return await run_in_threadpool(opportunities.retrieve,data.get('url',''))


@app.get('/api/portable/schema')
def portable_schema():
    return portable.schema()


@app.post('/api/portable/prompt')
async def portable_prompt(request: Request):
    data=await payload(request)
    return portable.prompt(workspace,data.get('type'),data.get('job_id'))


async def portable_payload(request):
    buffer=bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        if len(buffer)>1_000_000:raise ValueError('Le fichier JSON doit faire au maximum 1 Mo.')
    return portable.parse(bytes(buffer))


@app.post('/api/portable/preview')
async def preview_portable(request: Request):
    return portable.preview(workspace,await portable_payload(request))


@app.post('/api/portable/import')
async def import_portable(request: Request):
    return await run_in_threadpool(portable.apply,workspace,await portable_payload(request))


@app.post('/api/opportunities/{job_id}/draft')
async def local_draft(job_id: str, request: Request):
    value=await payload(request)
    ctx=portable.context(workspace,'application_draft',job_id)
    if value.get('revision') != ctx['job_revision'] or value.get('updated_at') != ctx['job_updated_at']:raise ValueError('Le dossier a changé. Recharge-le.')
    data={'summary':value.get('summary',''),'motivation':value.get('motivation',''),'selected_facts':[]}
    portable.validate(workspace,{'schema_version':1,'type':'application_draft','context':ctx,'data':data})
    await run_in_threadpool(portable.draft,workspace,job_id,data,ctx['job_revision'],ctx['job_updated_at'])
    return job(job_id)


@app.get('/api/export')
def export_workspace():
    return {'schema_version':1,'profile':workspace.profile(),'jobs':store.all(),'feedback':workspace.feedback(),
            'profile_analysis':workspace.setting('portable_profile_analysis')}


@app.post('/api/backup')
async def backup_workspace():
    content=await run_in_threadpool(portable.backup,workspace)
    return Response(content,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="open-vitae-backup.zip"'})

@app.get('/api/profile')
def profile():
    return workspace.profile_draft()


@app.put('/api/profile')
async def save_profile(request: Request):
    return workspace.save_profile(await payload(request))


@app.put('/api/profile/onboarding')
async def save_onboarding(request: Request):
    return workspace.save_onboarding(await payload(request))


@app.get('/api/sources')
def source_boards():
    return {'boards': workspace.setting('source_boards', [])}


@app.put('/api/sources')
async def save_source_boards(request: Request):
    data = await payload(request)
    boards = sources.ats.boards(data.get('boards'))
    workspace.set_setting('source_boards', boards)
    return {'boards': boards}


@app.post('/api/profile/import')
async def import_profile(request: Request):
    buffer = bytearray()
    async for part in request.stream():
        buffer.extend(part)
        if len(buffer) > 8000000:
            raise ValueError('Le CV doit faire moins de 8 Mo.')
    text = await run_in_threadpool(extract_resume, bytes(buffer), request.query_params.get('name', ''))
    return {'text': text, 'characters': len(text)}


@app.get('/api/recommendations')
def recommendations():
    return {'offers': sources.recommendations(workspace), 'last_search': workspace.setting('last_discovery'), 'feedback_count': len(workspace.feedback())}


def refresh_discovery(query):
    if not discovery_lock.acquire(blocking=False):
        raise ValueError('Une recherche est déjà en cours. Tu peux suivre sa progression ou l’annuler.')
    discovery_cancel.clear()
    discovery_status.clear()
    discovery_status.update({'state': 'running', 'source': 'Préparation des sources', 'completed': 0, 'imported': 0})
    try:
        status = sources.refresh(workspace, query, discovery_status.update, discovery_cancel.is_set)
        discovery_status.update({'state': 'cancelled' if status.get('cancelled') else 'done', 'imported': status['imported']})
    except BaseException:
        discovery_cancel.set()
        discovery_status.update({'state': 'failed'})
        raise
    finally:
        discovery_lock.release()
    return status


@app.get('/api/discovery/status')
def search_status():
    return dict(discovery_status)


@app.post('/api/discovery/cancel')
def cancel_search():
    discovery_cancel.set()
    return {'cancelling': discovery_status.get('state') == 'running'}


@app.post('/api/discovery')
async def discover(request: Request):
    data = await payload(request)
    query = data.get('query', '')
    if not isinstance(query, str) or len(query) > 500:
        raise ValueError('Recherche invalide.')
    if not workspace.profile():
        raise ValueError('Complète ton profil avant de chercher.')
    status = await run_in_threadpool(refresh_discovery, query)
    offers = sources.recommendations(workspace, query)
    workspace.message('user', 'Recherche d’offres' + (': ' + query if query else ' selon mon profil'))
    workspace.message('assistant', f"{len(offers)} pistes dans la sélection, dont {status['imported']} nouvelles offres collectées. Tu peux retenir une offre pour préparer son dossier, ou passer avec un motif pour affiner la suite.")
    return {'search': status, 'offers': offers, 'feedback_count': len(workspace.feedback())}


def run_preparation(job_id):
    try:
        packets.prepare(workspace, providers, job_id)
    except Exception as error:
        text = str(error) if isinstance(error, ValueError) else 'La préparation a échoué. Le dossier existant est conservé.'
        if not store.get(job_id)['revision']:
            try:
                portable.draft(workspace,job_id)
                workspace.preparation(job_id,'ready','IA indisponible. Un brouillon local modifiable a été conservé : '+text[:300])
                return
            except Exception:
                pass
        workspace.preparation(job_id, 'failed', text[:1000])


@app.post('/api/jobs/{job_id}/interest')
async def interest(job_id: str, request: Request, background: BackgroundTasks):
    data = await payload(request)
    if not workspace.profile():
        raise ValueError('Complète ton profil avant de choisir une offre.')
    current = store.get(job_id)
    if current['status'] in LOCKED:
        raise ValueError('Cette candidature est déjà verrouillée dans le suivi.')
    expiry = current['audit'].get('expiry')
    if data.get('decision') == 'accept' and (current['category'] in {'CLOSED','INELIGIBLE'} or isinstance(expiry, (int,float)) and expiry <= time.time()):
        raise ValueError('Cette offre n’est plus disponible ou comporte un point bloquant documenté.')
    workspace.decide(job_id, data.get('decision'), data.get('reason', ''))
    if data.get('decision') == 'accept' and not current['revision']:
        if workspace.setting('local_mode',False) or not workspace.setting('provider'):
            await run_in_threadpool(portable.draft,workspace,job_id)
        elif workspace.queue(job_id):
            background.add_task(preparation_worker.submit, run_preparation, job_id)
    return {'decision': data['decision'], 'preparation': workspace.preparation(job_id)}


@app.post('/api/jobs/{job_id}/checks')
async def checks(job_id: str, request: Request):
    data = await payload(request)
    current = store.get(job_id)
    if current['status'] in LOCKED or not current['dossier'] or data.get('revision') != current['revision'] or data.get('eligibility_checked') is not True or data.get('form_checked') is not True:
        raise ValueError('Vérifie l’annonce, l’éligibilité et les questions du formulaire avant de confirmer.')
    audit = {**current['audit'], 'active': True, 'location_allowed': True, 'requirements_checked': True,
             'manual_verification': {'by': 'user', 'at': now(), 'scope': 'opening, eligibility and application fields'}}
    store.audit(job_id, audit)
    dossier = current['dossier']
    dossier['missing'] = [item for item in dossier.get('missing', []) if not item.startswith('Questions exactes du formulaire')]
    store.save(job_id, dossier, current['revision'])
    return job(job_id)


@app.get('/api/chat')
def chat_history():
    return {'messages': workspace.messages()}


@app.post('/api/chat')
async def chat(request: Request):
    data = await payload(request)
    text = data.get('text')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000 or not workspace.profile():
        raise ValueError('Ajoute un message de moins de 3 000 caractères et complète ton profil.')
    workspace.message('user', text.strip())
    history = [{key: row[key] for key in ('role','text')} for row in workspace.messages()[-6:]]
    profile = workspace.profile()
    def validate(result):
        if not isinstance(result.get('text'), str) or not 1 <= len(result['text'].strip()) <= 8000:
            raise ValueError('La réponse reçue est invalide. Ton profil n’a pas été changé.')
        preference_patch(result.get('preferences'))
        query = result.get('search_query')
        if query is not None and (not isinstance(query,str) or len(query) > 180 or '@' in query or re.search(r'\d{7,}',query) or profile['name'].casefold() in query.casefold()):
            raise ValueError('La recherche proposée contient des éléments inattendus. Aucun critère n’a été modifié.')
    result = await run_in_threadpool(providers.complete, 'conversation', {
        'instruction': 'Return JSON with text (short conversational French answer), optional search_query (only professional role/skill terms, no name/contact/private context, only when the user asks for offers), and optional preferences (only roles array, locations array, remote enum remote/hybrid/office/flexible, expectations string). Preference changes require user confirmation: never say they are saved. Never claim search/submission has already happened. Never invent listings. Stay focused on this job search.',
        'profile': {key: value for key, value in profile.items() if key not in {'cv_text', 'email', 'phone'}},
        'history': history, 'feedback': [{'decision': row['decision'], 'reason': row['reason']} for row in workspace.feedback().values()][-8:]}, validator=validate)
    validate(result)
    answer = result['text'].strip()
    offers = None
    if result.get('search_query'):
        search = await run_in_threadpool(refresh_discovery, result['search_query'])
        offers = sources.recommendations(workspace, result['search_query'])
        answer += f"\n\n{len(offers)} pistes sont dans la sélection. " + ('Certaines sources sont indisponibles ; les offres conservées restent visibles.' if search['errors'] else 'Tu peux retenir celles qui méritent un dossier.')
    workspace.message('assistant', answer)
    return {'text': answer, 'offers': offers, 'proposed_preferences': result.get('preferences'), 'profile_revision': profile['revision']}


@app.post('/api/profile/preferences')
async def apply_preferences(request: Request):
    data = await payload(request)
    profile = workspace.profile()
    if not profile or data.get('revision') != profile['revision']:
        raise ValueError('Le profil a changé. Repars de ses critères actuels.')
    patch = preference_patch(data.get('preferences'))
    if not patch:
        raise ValueError('Aucun critère à appliquer.')
    return workspace.save_profile({**profile, **patch})



@app.get('/api/usage')
def usage():
    return workspace.usage()


@app.put('/api/usage')
async def usage_limit(request: Request):
    data = await payload(request)
    limit = data.get('limit')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError('Choisis entre 1 et 100 demandes par jour.')
    workspace.set_setting('daily_limit', limit)
    return workspace.usage()



app.mount('/static',StaticFiles(directory=WEB),name='static')
