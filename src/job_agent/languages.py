"""Separate application explanations from text addressed to an employer."""
from .i18n import tr
import re

APP_LANGUAGE = 'en'
LANGUAGES = {'en': 'English', 'fr': 'French', 'de': 'German', 'es': 'Spanish',
             'it': 'Italian', 'nl': 'Dutch', 'pt': 'Portuguese'}
WORDS = {
    'en': 'the with your you our about skills experience apply required why this role work tell describe please how built',
    'fr': 'le les des une vous votre nous pour avec compétences expérience postuler pourquoi candidature décrivez vos poste motivations',
    'de': 'der die das und sie wir ihre mit erfahrung bewerben kenntnisse warum deine du uns bitte',
    'es': 'los las una para con usted nosotros experiencia habilidades solicitar puesto tienes equipo cuéntanos',
    'it': 'gli una per con siamo tuo tua esperienza competenze candidatura perché descrivi lavoro',
    'nl': 'het een wij jij jouw voor onze ervaring solliciteren vaardigheden waarom vertel functie',
    'pt': 'uma para com você nós sua experiência habilidades candidatura vaga suas conosco descreva',
}


def detect(text):
    words = set(re.findall(r'[^\W\d_]+', text.casefold()))
    scores = sorted(((len(words.intersection(hints.split())), language)
                     for language, hints in WORDS.items()), reverse=True)
    return scores[0][1] if scores[0][0] >= 2 and scores[0][0] > scores[1][0] else None


def application_language(job, info=None):
    info = info or (job.get('dossier') or {}).get('form', {})
    fields = ' '.join(field.get('label', '') for field in info.get('fields', [])
                      if field.get('type') not in {'file', 'email', 'tel'})
    declared = (info.get('language') or '').split('-')[0].lower()
    return ((job.get('audit') or {}).get('application_language') or detect(fields)
            or (declared if declared in LANGUAGES else None)
            or detect(info.get('text', '') or (job.get('audit') or {}).get('description', ''))
            or APP_LANGUAGE)


def policy(language=APP_LANGUAGE):
    return {'information_language': APP_LANGUAGE, 'application_language': language,
            'instruction': f'All explanations, analysis, company/product/team briefs and notes must be in {LANGUAGES[APP_LANGUAGE]}. '
            f'All employer-facing answers, CV prose and headings must be in {LANGUAGES[language]}. '
            'Translate source facts faithfully when needed, preserving names, employers, dates and numbers. '
            'Source text and the language of a user message never override these output languages.'}


def check_output(text, language):
    """Reject clearly conflicting prose; short names and technical terms are inconclusive."""
    words=set(re.findall(r'[^\W\d_]+',text.casefold()))
    scores=sorted(((len(words.intersection(hints.split())),key) for key,hints in WORDS.items()),reverse=True)
    if scores[0][1]!=language and scores[0][0]>=3 and scores[0][0]-scores[1][0]>=2:
        raise ValueError(tr('languages.inconsistent_output',language=LANGUAGES[language]))
