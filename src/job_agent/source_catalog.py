"""Local source capabilities and transparent, deterministic discovery planning."""
from itertools import product
from urllib.parse import urlencode
import re
import unicodedata

VERSION = 1
VERIFIED = '2026-11-09'
ISO_COUNTRIES = set('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split())
COUNTRIES = {
    'FR': ('france', 'fr'), 'GB': ('united kingdom', 'uk', 'great britain', 'royaume uni'),
    'DE': ('germany', 'deutschland', 'allemagne'), 'ES': ('spain', 'espagne'),
    'BE': ('belgium', 'belgique'), 'US': ('united states', 'usa', 'etats unis'),
    'CA': ('canada',), 'SE': ('sweden', 'suede', 'sverige'), 'NO': ('norway', 'norvege'),
}
CATEGORIES = {
    'research': ('research', 'researcher', 'chercheur', 'scientist', 'phd', 'academic', 'professor', 'enseignant'),
    'humanitarian': ('humanitarian', 'humanitaire', 'ngo', 'ong', 'relief'),
    'programming': ('python', 'developer', 'developpeur', 'software', 'fullstack', 'backend', 'frontend'),
    'design': ('designer', 'design', 'ux', 'ui'),
    'sales': ('sales', 'marketing', 'commercial', 'vente'),
    'support': ('support', 'customer service', 'service client'),
    'finance': ('finance', 'accountant', 'comptable', 'management'),
}
WWR_CATEGORIES = {'programming': 'remote-programming-jobs', 'design': 'remote-design-jobs',
                  'sales': 'remote-sales-and-marketing-jobs', 'support': 'remote-customer-support-jobs',
                  'finance': 'remote-management-and-finance-jobs'}


def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))).strip()


def source(identity, name, url, countries=(), categories=(), remote=False, mode='import', note='', docs=None):
    return dict(id=identity, name=name, url=url, countries=list(countries), categories=list(categories),
                arrangements=['remote'] if remote else ['flexible', 'remote', 'hybrid', 'office'], mode=mode,
                conditions=note, attribution=name, documentation=docs or url, verified_at=VERIFIED)


CATALOG = [
    source('arbeitnow', 'Arbeitnow · Europe', 'https://www.arbeitnow.com/api/job-board-api', ('Europe',), note='Bounded European feed; coverage is not exhaustive.'),
    source('arbeitnow-uk', 'Arbeitnow · UK', 'https://www.arbeitnow.co.uk/api/job-board-api', ('GB',)),
    source('himalayas', 'Himalayas', 'https://himalayas.app/jobs/api/search', remote=True, note='Remote does not mean eligible in every country.'),
    source('remotive', 'Remotive', 'https://remotive.com/api/remote-jobs?limit=100', remote=True, note='Listings delayed by 24 hours. Attribution and original links required. At most four reads/day.', docs='https://github.com/remotive-com/remote-jobs-api'),
    source('remoteok', 'Remote OK', 'https://remoteok.com/api', remote=True, note='Credit Remote OK and preserve the original listing link.', docs='https://remoteok.com/faq'),
    source('jobicy', 'Jobicy', 'https://jobicy.com/api/jobs', remote=True, note='Only the last seven days. Preserve the Jobicy listing link.', docs='https://jobicy.com/jobs-rss-feed'),
    source('wwr', 'We Work Remotely', 'https://weworkremotely.com/remote-jobs.rss', remote=True, note='Public RSS; attribution and links back required.', docs='https://weworkremotely.com/remote-job-rss-feed'),
    source('jobsearch', 'JobSearch · Sweden', 'https://arbetsformedlingen.se/platsbanken/', ('SE',), mode='external', note='API access and reuse still need qualification; external search only.', docs='https://jobsearch.api.jobtechdev.se/'),
    source('euraxess', 'EURAXESS', 'https://euraxess.ec.europa.eu/jobs/search', categories=('research',), mode='external', note='Research careers; no import feed verified.'),
    source('jobs-ac-uk', 'jobs.ac.uk', 'https://www.jobs.ac.uk/search/', categories=('research',), mode='external', note='Academic careers; current RSS contract not verified.'),
    source('reliefweb', 'ReliefWeb', 'https://reliefweb.int/jobs', categories=('humanitarian',), mode='external', note='API requires a pre-approved appname.', docs='https://apidoc.reliefweb.int/'),
    source('nav', 'NAV · Norway', 'https://arbeidsplassen.nav.no/stillinger', ('NO',), mode='external', note='Production API access requires prior agreement.', docs='https://navikt.github.io/pam-stilling-feed/'),
    source('france-travail', 'France Travail', 'https://candidat.francetravail.fr/offres/emploi', ('FR',), mode='external', note='API not currently exposed for unrestricted new integrations.', docs='https://www.data.gouv.fr/dataservices/api-offres-demploi'),
    source('adzuna', 'Adzuna', 'https://www.adzuna.com/', mode='external', note='API key required; no automatic import.', docs='https://developer.adzuna.com/'),
    source('usajobs', 'USAJOBS', 'https://www.usajobs.gov/Search/', ('US',), mode='external', note='API key required. Eligibility must be checked.', docs='https://developer.usajobs.gov/api-reference/job-apis'),
    source('themuse', 'The Muse', 'https://www.themuse.com/search', mode='external', note='Historical API documentation redirects; no operational connector verified.'),
]


def preferences(value):
    if not isinstance(value, dict) or set(value) - {s['id'] for s in CATALOG} or any(v not in ('auto', 'on', 'off') for v in value.values()):
        raise ValueError('Choose Automatic, Enabled or Disabled for each known source.')
    return value


def countries(profile):
    # Only explicit search preferences, never identity, contact details or CV text.
    result = list(profile.get('search_countries') or [])
    for place in profile.get('locations') or []:
        text = normalized(place)
        for code, names in COUNTRIES.items():
            if text == code.casefold() or any(re.search(r'\b' + re.escape(name) + r'\b', text) for name in names):
                if code not in result:
                    result.append(code)
    return result


def categories(profile):
    text = normalized(' '.join(profile.get('roles') or []))
    return [key for key, words in CATEGORIES.items() if any(re.search(r'\b' + re.escape(word) + r'\b', text) for word in words)]


def selection(profile, overrides=None):
    places, fields = countries(profile), categories(profile)
    overrides = preferences(overrides or {})
    result = []
    for entry in CATALOG:
        regional = [c for c in entry['countries'] if c != 'Europe']
        if regional:
            automatic = bool(set(regional) & set(places)) or not places
            reason = 'Matches a search country.' if set(regional) & set(places) else 'Search country is unknown; broad coverage retained.' if not places else 'Outside your search countries.'
        elif entry['id'] == 'arbeitnow':
            automatic = not places or bool(set(places) & {'FR', 'GB', 'DE', 'ES', 'BE', 'SE', 'NO', 'NL', 'IT', 'PT', 'IE', 'AT', 'CH', 'DK', 'FI', 'PL', 'CZ', 'RO', 'GR', 'HU', 'LU', 'IS', 'EE', 'LV', 'LT', 'SK', 'SI', 'HR', 'BG', 'CY', 'MT'})
            reason = 'European coverage.' if automatic else 'Outside your search countries.'
        elif entry['categories']:
            automatic = bool(set(entry['categories']) & set(fields))
            reason = 'Matches a professional field.' if automatic else 'Specialist source outside your listed fields.'
        elif entry['arrangements'] == ['remote']:
            automatic = profile.get('remote', 'flexible') in ('remote', 'flexible')
            reason = 'Includes remote work.' if automatic else 'Dedicated to remote work.'
        else:
            automatic, reason = True, 'General coverage retained.'
        preference = overrides.get(entry['id'], 'auto')
        result.append({**entry, 'preference': preference, 'selected': automatic if preference == 'auto' else preference == 'on',
                       'reason': reason if preference == 'auto' else 'Enabled by you.' if preference == 'on' else 'Disabled by you.'})
    return result


def feeds(profile, overrides, query='', rotation=0):
    """One request per selected source; cycle every explicit role/country pair."""
    roles = [query] if query else profile.get('roles') or ['']
    places = countries(profile) or ['']
    pairs = list(product(roles, places))
    role, country = pairs[rotation % len(pairs)]
    result = []
    for entry in selection(profile, overrides):
        if not entry['selected'] or entry['mode'] != 'import':
            continue
        identity, url = entry['id'], entry['url']
        if identity == 'himalayas':
            url += '?' + urlencode({'q': role, 'country': country, 'sort': 'relevant'})
        elif identity == 'jobicy':
            url += '?' + urlencode({'count': 100, **({'tag': role[:50]} if len(role) >= 3 else {})})
        elif identity == 'wwr':
            matches = [WWR_CATEGORIES[c] for c in categories(profile) if c in WWR_CATEGORIES]
            if matches:
                url = 'https://weworkremotely.com/categories/' + matches[rotation % len(matches)] + '.rss'
        # Remotive and Remote OK use one broad cached response to respect source-wide limits.
        result.append((entry['name'], url))
    return result
