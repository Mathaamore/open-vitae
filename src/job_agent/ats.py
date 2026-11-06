"""Read-only public employer boards; no application POSTs or site scraping."""

from .i18n import tr
from datetime import datetime
import re

ENDPOINTS = {
    'greenhouse': 'https://boards-api.greenhouse.io/v1/boards/{}/jobs?content=true',
    'lever': 'https://api.lever.co/v0/postings/{}?mode=json&limit=100',
    'lever-eu': 'https://api.eu.lever.co/v0/postings/{}?mode=json&limit=100',
    'ashby': 'https://api.ashbyhq.com/posting-api/job-board/{}',
}


def boards(value):
    if not isinstance(value, list) or len(value) > 6:
        raise ValueError(tr('ats.ajoute_au_maximum_six_tableaux_employeurs'))
    result = []
    for item in value:
        if not isinstance(item, str) or not re.fullmatch(r'(greenhouse|lever|lever-eu|ashby):[A-Za-z0-9_-]{1,80}', item):
            raise ValueError(tr('ats.utilise_greenhouse_entreprise_lever_entreprise_lever_eu_entreprise'))
        if item not in result:
            result.append(item)
    return result


def endpoint(board):
    kind, slug = boards([board])[0].split(':')
    return ENDPOINTS[kind].format(slug)


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.timestamp() if date.tzinfo else None
    except (ValueError, OverflowError):
        return None


def postings(board, data):
    kind, slug = board.split(':')
    rows = data if kind.startswith('lever') else data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(tr('ats.format_du_tableau_employeur_invalide'))
    result = []
    for raw in rows[:100]:
        if not isinstance(raw, dict):
            continue
        if kind == 'greenhouse':
            location = raw.get('location') or {}
            job = {'url': raw.get('absolute_url'), 'title': raw.get('title'),
                   'location': location.get('name') if isinstance(location, dict) else '',
                   'description': raw.get('content'), 'updated_at': raw.get('updated_at')}
            # updated_at is not a publication date.
        elif kind.startswith('lever'):
            categories = raw.get('categories') or {}
            workplace = raw.get('workplaceType')
            job = {'url': raw.get('hostedUrl'), 'title': raw.get('text'),
                   'location': categories.get('location') if isinstance(categories, dict) else '',
                   'description': raw.get('descriptionPlain'),
                   'remote': True if workplace == 'remote' else False if workplace in ('on-site', 'hybrid') else None}
            # The public list does not guarantee an original publication date.
        else:
            if raw.get('isListed') is not True:
                continue
            job = {'url': raw.get('jobUrl'), 'title': raw.get('title'), 'location': raw.get('location'),
                   'description': raw.get('descriptionPlain'), 'created_at': timestamp(raw.get('publishedAt')),
                   'remote': raw.get('isRemote') if isinstance(raw.get('isRemote'), bool) else None}
        result.append({**job, 'company_name': slug, 'employer_board': True})
    return result
