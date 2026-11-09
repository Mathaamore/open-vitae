"""Normalize documented public feeds without inferring missing candidate eligibility."""
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

from .ats import timestamp


def date(value):
    if not isinstance(value, str):
        return None
    parsed = timestamp(value)
    if parsed is not None:
        return parsed
    try:
        item = parsedate_to_datetime(value)
        return item.timestamp() if item.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def postings(source, data):
    if source == 'We Work Remotely':
        if not isinstance(data, bytes):
            raise ValueError('Invalid RSS feed.')
        try:
            text = data.decode('utf-8-sig')
            if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                raise ValueError('Invalid RSS feed.')
            root = ET.fromstring(text)
        except (ET.ParseError, UnicodeError):
            raise ValueError('Invalid RSS feed.') from None
        if root.tag != 'rss' or root.find('channel') is None:
            raise ValueError('Invalid RSS feed.')
        items = root.findall('./channel/item')
        rows = []
        for raw in items[:100]:
            title = raw.findtext('title') or ''
            company, separator, role = title.partition(': ')
            # The official RSS title is "Company: Role"; do not invent an employer.
            if not separator:
                continue
            rows.append({'url': raw.findtext('link'), 'company_name': company, 'title': role,
                         'description': raw.findtext('description'), 'remote': True,
                         'created_at': date(raw.findtext('pubDate'))})
        return rows, len(items) >= 100
    rows = data if source == 'Remote OK' else data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError('Invalid public feed format.')
    result = []
    for raw in rows[:101]:
        if not isinstance(raw, dict):
            continue
        if source == 'Remotive':
            job = {'url': raw.get('url'), 'title': raw.get('title'), 'company_name': raw.get('company_name'),
                   'location': raw.get('candidate_required_location'), 'description': raw.get('description'),
                   'salary': raw.get('salary'), 'created_at': date(raw.get('publication_date'))}
        elif source == 'Remote OK':
            if 'position' not in raw:  # The first object contains feed legal metadata.
                continue
            job = {'url': raw.get('url'), 'title': raw.get('position'), 'company_name': raw.get('company'),
                   'location': raw.get('location'), 'description': raw.get('description'), 'created_at': date(raw.get('date'))}
        elif source == 'Jobicy':
            maximum = raw.get('salaryMax')
            job = {'url': raw.get('url'), 'title': raw.get('jobTitle'), 'company_name': raw.get('companyName'),
                   'location': raw.get('jobGeo'), 'description': raw.get('jobDescription') or raw.get('jobExcerpt'),
                   'created_at': date(raw.get('pubDate')),
                   'salary': f"{raw.get('salaryMin') or '—'}–{maximum or '—'} {raw.get('salaryCurrency') or ''} / {raw.get('salaryPeriod') or 'unknown'}" if raw.get('salaryMin') or maximum else None,
                   'salary_annual_max_eur': maximum if raw.get('salaryCurrency') == 'EUR' and raw.get('salaryPeriod') == 'yearly' else None}
        else:
            raise ValueError('Unknown public feed.')
        result.append({**job, 'remote': True})
    return result[:100], len(result) >= 100 or bool(isinstance(data, dict) and data.get('hasMore') is True)
