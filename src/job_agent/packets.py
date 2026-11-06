"""Read public forms, prepare grounded drafts and produce a portable PDF; never submit."""

from .i18n import tr
from html import escape, unescape
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import urljoin, urlsplit

from .net import public_url, request
from .store import LOCKED, digest, now


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.text = []; self.fields = []; self.labels = {}; self.label = None
        self.current = None; self.skip = 0; self.link = None; self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {'script', 'style', 'noscript'}:
            self.skip += 1
        if tag == 'label':
            self.label = a.get('for')
        if tag == 'a' and a.get('href'):
            self.link = {'url': a['href'], 'text': ''}
        if tag in {'input', 'textarea', 'select'} and a.get('type') not in {'hidden', 'submit', 'button', 'password'}:
            key = a.get('name') or a.get('id')
            if key:
                item = {'key': key[:200], 'label': a.get('aria-label') or a.get('placeholder') or key,
                        'type': a.get('type') or ('textarea' if tag == 'textarea' else 'select' if tag == 'select' else 'text'),
                        'required': 'required' in a, 'id': a.get('id', key)}
                if item['type'] == 'select':
                    item['options'] = []
                self.fields.append(item); self.current = item if tag == 'select' else None
        if tag == 'option' and self.current:
            self.current['options'].append({'value': a.get('value', ''), 'label': ''})

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self.skip = max(0, self.skip - 1)
        if tag == 'label':
            self.label = None
        if tag == 'select':
            self.current = None
        if tag == 'a' and self.link:
            self.links.append(self.link); self.link = None

    def handle_data(self, data):
        if self.skip:
            return
        data = data.strip()
        if not data:
            return
        self.text.append(data)
        if self.label:
            self.labels[self.label] = (self.labels.get(self.label, '') + ' ' + data).strip()
        if self.link:
            self.link['text'] += data + ' '
        if self.current and self.current.get('options'):
            self.current['options'][-1]['label'] += data

    def result(self):
        unique = {}
        for field in self.fields:
            field['label'] = self.labels.get(field.pop('id'), field['label'])[:2000]
            # Search, newsletter and authentication fields aren't an application form.
            if field['key'] in {'__proto__','prototype','constructor'} or re.search(r'search|newsletter|password|csrf|captcha', field['key'], re.I):
                continue
            unique[field['key']] = field
        return list(unique.values())[:50]


def fallback_fields():
    return [{'key': 'name', 'label': tr('packets.full_name'), 'type': 'text', 'required': True},
            {'key': 'email', 'label': tr('packets.email'), 'type': 'email', 'required': False},
            {'key': 'body', 'label': tr('packets.application_introduction'), 'type': 'textarea', 'required': True},
            {'key': 'resume', 'label': 'CV', 'type': 'file', 'required': True}]


def inspect_offer(url):
    content, resolved = request(url)
    if content.startswith(b'%PDF'):
        raise ValueError(tr('packets.this_listing_is_a_pdf_check_the_application'))
    parser = Page(); parser.feed(content.decode('utf-8', errors='replace'))
    # Follow an explicitly labelled application link from an aggregator, not arbitrary links.
    apply = next((link for link in parser.links if re.search(r'apply (?:for|now)|postuler', link['text'], re.I) and urljoin(resolved, link['url']).startswith('https://') and urlsplit(urljoin(resolved, link['url'])).hostname != urlsplit(resolved).hostname), None)
    if apply:
        content, resolved = request(urljoin(resolved, apply['url']))
        parser = Page(); parser.feed(content.decode('utf-8', errors='replace'))
    fields = parser.result()
    exact = any(field['type'] in {'email', 'file'} for field in fields)
    browser_error = None
    if not exact:
        try:
            from playwright.sync_api import sync_playwright
            from .browser import INVENTORY
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(headless=True)
                except Exception:
                    browser = pw.chromium.launch(channel='chrome', headless=True)
                try:
                    context = browser.new_context(accept_downloads=False, service_workers='block')
                    def route(route):
                        if route.request.resource_type in {'image', 'media', 'font'}:
                            return route.abort()
                        try:
                            public_url(route.request.url)
                        except Exception:
                            return route.abort()
                        route.continue_()
                    context.route('**/*', route)
                    page = context.new_page(); page.set_default_timeout(10000)
                    page.goto(resolved, wait_until='domcontentloaded', timeout=25000)
                    inventory = page.evaluate(INVENTORY)
                    candidate = [field for field in inventory['fields'] if field.get('key') not in {'__proto__','prototype','constructor'}]
                    if any(field.get('type') in {'email', 'file'} for field in candidate):
                        fields, exact = candidate[:50], True
                    parser.text = [page.locator('body').inner_text()[:20000]]
                    resolved = page.url
                finally:
                    browser.close()
        except Exception:
            browser_error = tr('packets.the_application_form_could_not_be_read_check')
    if not exact:
        fields = fallback_fields()
    return {'url': resolved, 'fields': fields, 'inspected': exact,
            'text': re.sub(r'\s+', ' ', ' '.join(parser.text))[:18000], 'warning': browser_error}


def facts(profile):
    source = profile.get('achievements', '') + '\n' + profile.get('cv_text', '')
    return [line.strip(' •\t') for line in source.splitlines() if len(line.strip()) > 8][:220]


def pdf_bytes(profile, role, summary, selected):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    font = Path(__file__).parent/'web/geist-variable.ttf'
    if 'CandidateGeist' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CandidateGeist', str(font)))
    styles = getSampleStyleSheet()
    base = ParagraphStyle('candidate', fontName='CandidateGeist', fontSize=9, leading=13, textColor=colors.HexColor('#262a30'), spaceAfter=5)
    title = ParagraphStyle('candidate-title', parent=base, fontSize=22, leading=26, spaceAfter=8)
    section = ParagraphStyle('candidate-section', parent=base, fontSize=11, leading=16, spaceBefore=12, spaceAfter=6)
    story = [Paragraph(escape(profile['name']), title), Paragraph(escape(role), section)]
    contact = ' · '.join(profile.get(key, '') for key in ('email', 'phone') if profile.get(key))
    if contact:
        story.append(Paragraph(escape(contact), base))
    if profile.get('portfolio'):
        story.append(Paragraph(f'<link href="{escape(profile["portfolio"])}">{escape(profile["portfolio"])}</link>', base))
    story.extend([Spacer(1, 8), Paragraph(escape(summary or profile['bio']), base)])
    if selected:
        story.append(Paragraph(tr('packets.relevant_achievements'), section))
        story.extend(Paragraph('• ' + escape(text), base) for text in selected)
    if profile.get('strengths'):
        story.extend([Paragraph(tr('packets.skills_and_strengths'), section), Paragraph(escape(profile['strengths']).replace('\n', '<br/>'), base)])
    if profile.get('cv_text'):
        story.append(Paragraph(tr('packets.experience'), section))
        story.extend(Paragraph(escape(line), base) for line in profile['cv_text'].splitlines() if line.strip())
    out = io.BytesIO()
    SimpleDocTemplate(out, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=35, bottomMargin=35,
                      title=profile['name']+' — '+role, author=profile['name']).build(story)
    return out.getvalue()


def prepare(workspace, providers, job_id, replace=False, expected_revision=None, expected_updated_at=None):
    store = workspace.store
    job = store.get(job_id)
    if job['status'] in LOCKED:
        raise ValueError(tr('portable.this_application_has_a_recorded_or_uncertain_submission_2'))
    if expected_revision is not None and (job['revision'] != expected_revision or job['updated_at'] != expected_updated_at):
        raise ValueError(tr('packets.your_profile_or_application_changed_during_preparation_start'))
    if job['revision'] and not replace:
        workspace.preparation(job_id, 'ready', tr('packets.your_existing_materials_and_edits_have_been_kept'))
        return
    profile = workspace.profile()
    if not profile:
        raise ValueError(tr('packets.complete_your_profile_before_preparing_application_materials'))
    original_profile = digest(profile)
    workspace.preparation(job_id, 'preparing', tr('packets.reading_the_listing_and_application_questions'))
    try:
        info = inspect_offer(job['url'])
        context_url = info['url']
        context_basis = 'public_page'
    except (ValueError, OSError):
        info = {'url':job['url'], 'fields':fallback_fields(), 'inspected':False,
                'text':job['audit'].get('description','')[:18000], 'warning':tr('packets.the_employer_s_page_could_not_be_read')}
        context_url = job['audit'].get('source_url') or job['url']
        context_basis = 'job_feed'
    source_facts = []
    size = 0
    for fact in facts(profile):
        if size + len(fact) > 12000:
            break
        source_facts.append(fact); size += len(fact)
    text_fields = [field for field in info['fields'] if field.get('type') == 'textarea' or re.search(r'why|motivat|cover|pitch|challenge|experience|body', field['key'], re.I)][:10]
    question_keys = {field['key'] for field in text_fields}
    workspace.preparation(job_id, 'preparing', tr('packets.preparing_your_cv_and_answers_from_your_experience'))
    def validate(result):
        summary = result.get('summary')
        selected = result.get('selected_facts', [])
        generated = result.get('answers', {})
        if not isinstance(summary, str) or len(summary) > 2000 or not isinstance(selected, list) or len(selected) > 5 or any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < min(120, len(source_facts)) for i in selected):
            raise ValueError(tr('packets.the_summary_or_selected_facts_could_not_be'))
        if not isinstance(generated, dict) or any(key not in question_keys or not isinstance(text, str) or len(text) > 8000 for key, text in generated.items()):
            raise ValueError(tr('packets.the_suggested_answers_could_not_be_used_your'))
        for key in ('company_summary', 'product_summary', 'team_summary'):
            if not isinstance(result.get(key), str) or len(result[key]) > 3000:
                raise ValueError(tr('packets.the_company_brief_could_not_be_read_check'))
    result = providers.complete('prepare_application', {
        'instruction': 'Return JSON: summary (short factual candidate summary), selected_facts (up to 5 integer indices from facts), company_summary (only from offer text; say unknown when missing), product_summary, team_summary (unknown if absent), answers (object question-key to answer string). Never answer consents or demographic questions. Facts selected for the CV remain verbatim. No invented accomplishments or product familiarity.',
        'profile': {key: profile.get(key) for key in ('bio', 'strengths', 'expectations')},
        'facts': source_facts[:120], 'offer': {'company': job['company'], 'role': job['role'], 'text': info['text'][:12000]},
        'questions': [{'key': field['key'], 'label': field['label'][:1500]} for field in text_fields]}, max_output=4000, validator=validate)
    validate(result)
    summary, selected, generated = result['summary'], result['selected_facts'], result['answers']
    if digest(workspace.profile()) != original_profile or store.get(job_id)['revision'] != job['revision'] or store.get(job_id)['updated_at'] != job['updated_at']:
        raise ValueError(tr('packets.your_profile_or_application_changed_during_preparation_start'))
    folder = store.root/'data/dossiers'/job_id/('ai-'+uuid.uuid4().hex); folder.mkdir(parents=True, exist_ok=True)
    path = str((folder/'resume.pdf').relative_to(store.root))
    pdf = pdf_bytes(profile, job['role'], summary, [source_facts[i] for i in selected])
    answers = {}
    for field in info['fields']:
        key, label, kind = field['key'], field.get('label', '').casefold(), field.get('type')
        if kind == 'file':
            answers[key] = path if re.search(r'cv|resume|curriculum', label, re.I) else ''
        elif kind in {'checkbox', 'radio', 'select'}:
            answers[key] = [] if kind == 'checkbox' and field.get('options') else ''
        elif key in generated:
            answers[key] = generated[key]
        elif kind == 'email' or 'email' in key.casefold():
            answers[key] = profile.get('email', '')
        elif kind == 'tel' or re.search(r'phone|téléphone', label):
            answers[key] = profile.get('phone', '')
        elif re.search(r'^(full.?name|name|nom complet|nom)$', label, re.I):
            answers[key] = profile['name']
        elif 'portfolio' in label:
            answers[key] = profile.get('portfolio', '')
        else:
            answers[key] = ''
    missing = [] if info['inspected'] else [tr('portable.check_the_exact_questions_on_the_employer_s')]
    audit = {**job['audit'], 'checked_at': now(), 'sources': list(dict.fromkeys(job['audit'].get('sources', []) + [info['url']])),
             'description': info['text'], 'application_url': info['url'],
             'company_context': {'company': {'summary': result['company_summary'], 'product': result['product_summary'],
                 'sources': [context_url], 'basis': context_basis, 'checked_on': now()[:10]}, 'role': {'team': None, 'scope': result['team_summary'], 'sources': [context_url]}},
             'warnings': list(dict.fromkeys(job['audit'].get('warnings', []) + ([info['warning']] if info.get('warning') else []) + [tr('packets.ai_assisted_draft_review_the_facts_before_using')]))}
    # Source/form retrieval is not proof of geographic eligibility or of an open position.
    (folder/'resume.pdf').write_bytes(pdf)
    (folder/'resume.json').write_text(json.dumps({'profile_revision': profile['revision'], 'summary': summary, 'selected_facts': [source_facts[i] for i in selected]}, ensure_ascii=False))
    (folder/'tailoring.json').write_text(json.dumps({'source': info['url'], 'exact_form': info['inspected'], 'facts_verbatim': True}, ensure_ascii=False))
    (folder/'motivation.txt').write_text(next(iter(generated.values()), ''))
    store.save(job_id, {'answers': answers, 'motivation': '', 'missing': missing,
        'form': {key: value for key, value in info.items() if key in {'url', 'fields', 'inspected'}},
        'attachments': [{'label': tr('portable.cv_draft'), 'path': path}],
        'submission': {'mode': 'manual', 'reason': tr('packets.complete_and_send_this_application_on_the_employer')}}, job['revision'], expected_updated_at=job['updated_at'], audit=audit)
    workspace.preparation(job_id, 'ready', tr('packets.your_materials_are_ready_to_review_check_any'))
