"""Local opportunity editing and explicit, read-only retrieval of public job metadata."""
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .net import request
from .store import canonical, digest, now


def text(value, name, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise ValueError(f'{name} : texte attendu, {limit} caractères maximum.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{name} est requis.')
    return value


def canonical_url(value):
    value = text(value, 'URL', 4096)
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').encode('idna').decode().lower().rstrip('.')
        if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443) or re.search(r'\s|\\',value):
            raise ValueError()
        try:
            address=ipaddress.ip_address(host)
        except ValueError:
            try:address=ipaddress.ip_address(socket.inet_aton(host))
            except OSError:address=None
        if address is not None and not address.is_global:
            raise ValueError()
        if address is None and ('.' not in host or not re.fullmatch(r'[a-z0-9._-]+',host)) or host.endswith(('.local','.localhost','.invalid')):
            raise ValueError()
        authority='['+host+']' if address is not None and address.version==6 else host
        # shortcut: plain fragments are page anchors; add other posting-ID formats when a source needs them.
        fragment=parsed.fragment if parsed.fragment.startswith(('/','!')) else ''
        query = [(key,val) for key,val in parse_qsl(parsed.query,keep_blank_values=True) if not key.lower().startswith('utm_') and key.lower() not in {'fbclid','gclid'}]
        return urlunsplit(('https',authority,parsed.path.rstrip('/') or '/',urlencode(sorted(query)),fragment))
    except (ValueError, UnicodeError):
        raise ValueError('Utilise une URL HTTPS publique sans identifiants ni adresse locale.') from None


def fields(value):
    if not isinstance(value,dict) or set(value)-{'company','role','url','description','location','salary'}:
        raise ValueError('Champs d’offre invalides.')
    result={key:text(value.get(key,''),key,limit) for key,limit in {'company':200,'role':300,'description':18000,'location':400,'salary':500}.items()}
    result['url']=canonical_url(value.get('url',''))
    if not any(result.values()):
        raise ValueError('Ajoute une URL, une description ou les informations du poste.')
    result['company']=result['company'] or 'Entreprise à préciser'
    result['role']=result['role'] or 'Poste à compléter'
    return result


def find_duplicate(store, url):
    if url:
        for job in store.all():
            try:
                if canonical_url(job['url']) == url:
                    return job
            except ValueError:
                continue
    return None


def add(workspace, value, source='Ajout manuel'):
    value=fields(value)
    duplicate=find_duplicate(workspace.store,value['url'])
    if duplicate:
        return {'id':duplicate['id'],'duplicate':True}
    identity='offer-'+digest(value['url'])[:20] if value['url'] else 'job-'+uuid.uuid4().hex
    workspace.store.import_jobs([{'id':identity,'company':value['company'],'role':value['role'],'url':value['url'],'manual':True}])
    workspace.store.audit(identity,{'checked_at':now(),'sources':[value['url']] if value['url'] else ['local:manual'],
        'source':source,'source_url':value['url'],'description':value['description'],'location':value['location'],
        'salary':value['salary'],'pending_retrieval':bool(value['url'] and not value['description']),
        'active':None,'requirements_checked':False,'scores':{},'warnings':['Informations non vérifiées. Vérifie le poste et les conditions auprès de l’employeur.']})
    workspace.decide(identity,'later')
    return {'id':identity,'duplicate':False}


def edit(workspace, identity, value):
    job=workspace.store.get(identity)
    normalized=fields({key:val for key,val in value.items() if key!='updated_at'})
    duplicate=find_duplicate(workspace.store,normalized['url'])
    if duplicate and duplicate['id'] != identity:
        raise ValueError('Cette URL est déjà enregistrée dans une autre offre.')
    audit={**job['audit'],'title':normalized['role'],**{key:normalized[key] for key in ('description','location','salary')},
           'source_url':normalized['url'],'pending_retrieval':bool(normalized['url'] and not normalized['description']),
           'active':None,'requirements_checked':False,'location_allowed':None,'france_allowed':None,
           'scores':{},'company_context':None,'external_analysis':None,'requirements':[],'blockers':[],'published_at':None,
           'warnings':['Informations modifiées manuellement. Vérifie l’annonce et relis le dossier existant.']}
    with workspace.store.db() as db:
        cursor=db.execute("UPDATE jobs SET company=?,role=?,url=?,audit=?,status='NEEDS_INPUT',approved_hash=NULL,updated_at=? WHERE id=? AND updated_at=? AND status NOT IN ('SUBMITTED','SUBMITTING','SUBMISSION_UNCERTAIN')",
            (normalized['company'],normalized['role'],normalized['url'],canonical(audit),now(),identity,value.get('updated_at')))
        if cursor.rowcount != 1:
            raise ValueError('L’offre a changé ou son envoi est verrouillé. Recharge sa fiche.')
        workspace.store.event(db,identity,'OPPORTUNITY_EDITED',{})
    return workspace.store.get(identity)


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__();self.collect=False;self.buffer=[];self.documents=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('type','').lower()=='application/ld+json':
            self.collect=True;self.buffer=[]
    def handle_data(self,data):
        if self.collect:self.buffer.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.collect:
            self.collect=False
            try:self.documents.append(json.loads(''.join(self.buffer)))
            except (ValueError,RecursionError):pass


def retrieve(url):
    url=canonical_url(url)
    if not url:raise ValueError('Ajoute une URL avant de récupérer l’annonce.')
    content,resolved=request(url)
    parser=Metadata();parser.feed(content.decode('utf-8',errors='replace'))
    pending=list(parser.documents)
    posting=None
    while pending:
        node=pending.pop()
        if isinstance(node,list):pending.extend(node)
        elif isinstance(node,dict):
            kind=node.get('@type')
            if kind=='JobPosting' or isinstance(kind,list) and 'JobPosting' in kind:
                posting=node;break
            graph=node.get('@graph')
            if isinstance(graph,list):pending.extend(graph)
    if not posting:
        raise ValueError('Aucune fiche JobPosting lisible. Colle la description ou complète les champs ; ton offre est conservée.')
    from .sources import plain
    org=posting.get('hiringOrganization')
    location=posting.get('jobLocation')
    if isinstance(location,list):location=next((item for item in location if isinstance(item,dict)),{})
    address=location.get('address') if isinstance(location,dict) else None
    place=', '.join(str(address[key]) for key in ('addressLocality','addressRegion','addressCountry') if isinstance(address,dict) and isinstance(address.get(key),str))
    pay=posting.get('baseSalary')
    salary=''
    if isinstance(pay,dict) and isinstance(pay.get('currency'),str):
        amount=pay.get('value')
        if isinstance(amount,dict):
            values=[str(amount[key]) for key in ('minValue','maxValue') if type(amount.get(key)) in (int,float)]
            if not values and type(amount.get('value')) in (int,float):values=[str(amount['value'])]
            if values:salary=' – '.join(values)+' '+pay['currency']+' / '+str(amount.get('unitText') or 'période non précisée')
    return fields({'url':url,'company':org.get('name','') if isinstance(org,dict) else '',
        'role':posting.get('title',''),'description':plain(posting.get('description',''))[:18000],
        'location':place,'salary':salary[:500]})
