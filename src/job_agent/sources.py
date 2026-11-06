"""Public job feeds, local ranking and explicit feedback. Discovery uses no model tokens."""

from .i18n import tr
from datetime import datetime, timezone
from urllib.parse import urlencode
from html import unescape
import re
import math
import time
import unicodedata

from .net import json_request
from . import ats
from .opportunities import canonical_url
from .store import digest, now

SOURCES = [('Arbeitnow · Europe', 'https://www.arbeitnow.com/api/job-board-api'),
           ('Arbeitnow · UK', 'https://www.arbeitnow.co.uk/api/job-board-api')]


def plain(value):
    return unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))).strip()


def terms(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if not unicodedata.combining(c))
    value = re.sub(r'full[ -]?stack', 'fullstack', value)
    return set(re.findall(r'[\w+#]{2,}', value)) - {'avec', 'dans', 'pour', 'une', 'des', 'les', 'le', 'la', 'de', 'du', 'et', 'en', 'un', 'au', 'ce', 'to', 'of', 'in', 'on', 'by', 'or', 'the', 'and', 'with', 'from', 'engineer', 'senior', 'developer', 'software'}


def rank(job, profile, feedback, jobs):
    audit = job.get('audit') or {}
    title = job['role'].casefold()
    location = str(audit.get('location', ''))
    description = plain(audit.get('description', ''))[:16000]
    role_terms = terms(' '.join(profile.get('roles', [])))
    title_hits = role_terms & terms(title)
    skill_hits = terms(profile.get('strengths', '')) & terms(description)
    points = len(title_hits) * 8 + min(len(skill_hits), 5)
    if not title_hits and not skill_hits:
        points -= 15
    reasons = []
    if title_hits:
        reasons.append(tr('sources.role_match') + ', '.join(sorted(title_hits)[:3]))
    if skill_hits:
        reasons.append(tr('sources.relevant_skills') + ', '.join(sorted(skill_hits)[:3]))
    remote = audit.get('remote')
    if profile.get('remote') == 'remote':
        points += 5 if remote is True else -10 if remote is False else 0
        if remote is True:
            reasons.append(tr('sources.listed_as_remote'))
    if profile.get('remote') == 'office' and remote is True:
        points -= 10
    if profile.get('salary_min') and isinstance(audit.get('salary_annual_max_eur'), (int, float)) and audit['salary_annual_max_eur'] < profile['salary_min']:
        points -= 20
    places = profile.get('locations', [])
    if any(place.casefold() in location.casefold() for place in places):
        points += 5; reasons.append(tr('sources.matches_a_preferred_location'))
    # Feedback affects matching features, not unrelated facts or a hidden personality profile.
    history = {entry['id']: entry for entry in jobs}
    adjustment = 0
    for identity, entry in feedback.items():
        previous = history.get(identity)
        if not previous or entry['decision'] == 'later':
            continue
        overlap = len(terms(previous['role']) & terms(title))
        if overlap and (entry['decision'] == 'accept' or entry['reason'] == 'role'):
            adjustment += min(2, overlap) * (1 if entry['decision'] == 'accept' else -1)
        if entry['decision'] == 'reject' and entry['reason'] == 'location' and previous['audit'].get('location') == location:
            adjustment -= 3
        if previous['company'] == job['company'] and entry['reason'] == 'company':
            adjustment -= 5
    points += max(-8, min(8, adjustment))
    if not reasons:
        reasons.append(tr('sources.possible_match_there_is_limited_supporting_detail'))
    checks = [tr('sources.check_which_countries_are_eligible_for_remote_work') if remote else tr('sources.work_arrangement_needs_checking')]
    if not audit.get('salary'):
        checks.append(tr('sources.salary_not_provided'))
    maximum = audit.get('salary_annual_max_eur')
    if profile.get('salary_min') and isinstance(maximum, (int, float)) and maximum < profile['salary_min']:
        checks.append(tr('sources.listed_salary_is_below_your_minimum'))
    if profile.get('remote') == 'remote' and remote is False:
        checks.append(tr('sources.this_role_does_not_match_your_remote_work'))
    return points, reasons[:3], checks


def refresh(workspace, query='', progress=None, cancelled=None):
    last = workspace.setting('last_discovery')
    configured = ats.boards(workspace.setting('source_boards', []))
    signature = digest({'query': query, 'profile': workspace.profile(), 'boards': configured})
    if last and last.get('signature') == signature and not last.get('errors') and not last.get('cancelled') and time.time() - last['time'] < 86400:
        return {'cached': True, **last}
    errors, imported = [], 0
    known = {job['id']: job for job in workspace.store.all()}
    known_urls = set()
    for job in known.values():
        try: known_urls.add(canonical_url(job['url']))
        except ValueError: pass
    profile = workspace.profile() or {}
    search = urlencode({'q': query or (profile.get('roles') or [''])[0], 'country': {'france':'FR','fr':'FR','germany':'DE','deutschland':'DE','united kingdom':'GB','uk':'GB','spain':'ES','espagne':'ES','belgium':'BE','belgique':'BE','united states':'US','canada':'CA'}.get((profile.get('locations') or [''])[0].casefold(), ''), 'sort': 'relevant'})
    feeds = SOURCES + [('Himalayas', 'https://himalayas.app/jobs/api/search?' + search)] + [(board, ats.endpoint(board)) for board in configured]
    for index, (source, endpoint) in enumerate(feeds):
        if cancelled and cancelled():
            break
        if progress:
            progress({'source': source, 'completed': index, 'total': len(feeds), 'imported': imported})
        try:
            data = json_request(endpoint)
            if source in configured:
                rows = ats.postings(source, data)
            elif isinstance(data, dict):
                rows = data.get('jobs') if source == 'Himalayas' else data.get('data')
            else:
                raise ValueError(tr('sources.format_de_source_invalide'))
            if not isinstance(rows, list):
                raise ValueError(tr('sources.format_de_source_invalide'))
            for raw in rows[:100]:
                if cancelled and cancelled():
                    break
                if not isinstance(raw, dict):
                    continue
                if source == 'Himalayas':
                    if any(not isinstance(raw.get(key), (int,float)) or isinstance(raw.get(key), bool) or not math.isfinite(raw[key]) for key in ('pubDate','expiryDate')):
                        continue
                    restrictions = raw.get('locationRestrictions') or []
                    if not isinstance(restrictions, list) or any(not isinstance(item,str) for item in restrictions):
                        continue
                    raw = {**raw, 'url': raw.get('applicationLink'), 'company_name': raw.get('companyName'),
                        'created_at': raw.get('pubDate', 0) / 1000, 'expiry': raw.get('expiryDate', 0) / 1000,
                        'location': ', '.join(raw.get('locationRestrictions') or ['Worldwide']), 'remote': True,
                        'salary': f"{raw.get('minSalary') or '—'}–{raw.get('maxSalary') or '—'} {raw.get('currency') or ''} / {raw.get('salaryPeriod') or 'annual'}" if raw.get('minSalary') or raw.get('maxSalary') else None,
                        'salary_annual_max_eur': raw.get('maxSalary') if raw.get('currency') == 'EUR' and raw.get('salaryPeriod', 'annual') == 'annual' else None}
                    if not isinstance(raw['expiry'], (int, float)) or raw['expiry'] <= time.time():
                        continue
                url, company, title = raw.get('url'), raw.get('company_name'), raw.get('title')
                if not all(isinstance(value, str) and value.strip() for value in (url, company, title)) or not url.startswith('https://'):
                    continue
                try: url = canonical_url(url)
                except ValueError: continue
                if url in known_urls: continue
                identity = 'offer-' + digest(url)[:20]
                if identity in known:
                    continue
                created = raw.get('created_at')
                if isinstance(created, (int, float)) and (isinstance(created, bool) or not 0 < created <= time.time() + 86400 or time.time() - created > 45 * 86400):
                    continue
                salary_max = raw.get('salary_annual_max_eur')
                if type(salary_max) not in (int, float) or not math.isfinite(salary_max) or not 0 <= salary_max <= 10000000:
                    salary_max = None
                workspace.store.import_jobs([{'id': identity, 'company': company[:200], 'role': title[:300], 'url': url}])
                description = plain(raw.get('description', ''))[:18000]
                workspace.store.audit(identity, {'checked_at': now(), 'sources': [url], 'source': source,
                    'source_url': ('https://himalayas.app/' if source == 'Himalayas' else url), 'expiry': raw.get('expiry') if source == 'Himalayas' else None, 'description': description, 'location': str(raw.get('location') or '')[:400],
                    'salary': raw.get('salary') if isinstance(raw.get('salary'), str) else None, 'salary_annual_max_eur': salary_max,
                    'remote': raw.get('remote') if isinstance(raw.get('remote'), bool) else None,
                    'active': None, 'france_allowed': None, 'requirements_checked': False,
                    'published_at': datetime.fromtimestamp(created, timezone.utc).isoformat() if isinstance(created, (int, float)) else None,
                    'scores': {}, 'warnings': [tr('sources.found_on_a_company_board_confirm_the_current') if raw.get('employer_board') else tr('sources.found_through_a_job_feed_check_that_the')]})
                known[identity] = True; known_urls.add(url); imported += 1
        except (ValueError, OSError, OverflowError) as error:
            errors.append({'source': source, 'message': str(error)[:300]})
    result = {'time': time.time(), 'checked_at': now(), 'imported': imported, 'errors': errors,
              'sources': [name for name, _ in feeds], 'signature': signature, 'cancelled': bool(cancelled and cancelled())}
    workspace.set_setting('last_discovery', result)
    return {'cached': False, **result}


def recommendations(workspace, query=''):
    profile = workspace.profile()
    if not profile:
        raise ValueError(tr('sources.complete_your_profile_before_searching_for_jobs'))
    feedback = workspace.feedback()
    jobs = workspace.store.all()
    ranked = []
    for job in jobs:
        if job['audit'].get('expiry') and job['audit']['expiry'] <= time.time():
            continue
        if job.get('tracking') or job['status'] == 'SUBMITTED' or job['category'] in {'CLOSED', 'INELIGIBLE'} or feedback.get(job['id'], {}).get('decision') in {'accept', 'reject', 'later'}:
            continue
        if profile.get('strict_constraints'):
            remote = job['audit'].get('remote')
            maximum = job['audit'].get('salary_annual_max_eur')
            if (profile.get('remote') == 'remote' and remote is False or
                profile.get('remote') == 'office' and remote is True or
                profile.get('salary_min') and isinstance(maximum, (int, float)) and maximum < profile['salary_min']):
                continue
        points, reasons, checks = rank(job, profile, feedback, jobs)
        if query:
            points += min(12, len(terms(query) & terms(job['role'] + ' ' + job['company'] + ' ' + str(job['audit'].get('description', '')))) * 3)
        if points > 0:
            ranked.append((points, job, reasons, checks))
    ranked.sort(key=lambda entry: (-entry[0], entry[1]['company']))
    return [{'id': job['id'], 'company': job['company'], 'role': job['audit'].get('title') or job['role'], 'url': job['url'],
        'location': job['audit'].get('location') or tr('sources.location_not_provided'), 'salary': job['audit'].get('salary') or tr('sources.salary_not_provided'),
        'description': plain(job['audit'].get('description') or job['audit'].get('summary') or '')[:1100],
        'reasons': reasons, 'checks': checks, 'source': job['audit'].get('source', tr('sources.saved_job')),
        'source_url': job['audit'].get('source_url') or job['url'], 'published_at': job['audit'].get('published_at')}
        for _, job, reasons, checks in ranked[:12]]
