"""Keep a private PDF layout and refuse overflowing one-page exports."""
from .i18n import tr
import hashlib
import io
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, TTFError


def font():
    if 'CandidateGeist' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CandidateGeist', str(Path(__file__).parent/'web/geist-variable.ttf')))
    return 'CandidateGeist'


def source_path(workspace, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{64}', identity):
        raise ValueError(tr('resume.import_your_pdf_again_to_select_a_valid_cv'))
    base = workspace.store.root/'data/resume-sources'
    path = base/(identity+'.pdf')
    if base.is_symlink() or not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError(tr('resume.your_cv_template_is_missing_import_the_pdf_again'))
    return path


def import_source(workspace, data, filename):
    if Path(filename).suffix.lower() != '.pdf':
        return {'template': '', 'template_message': tr('resume.text_imported_to_reuse_your_layout_import_a_one')}
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) != 1:
        return {'template': '', 'template_message': tr('resume.text_imported_your_pdf_has_multiple_pages_import_a')}
    # Keep the original private and immutable; no generated version overwrites it.
    identity = hashlib.sha256(data).hexdigest()
    folder = workspace.store.root/'data/resume-sources'
    if folder.is_symlink():raise ValueError(tr('resume.your_cv_template_is_missing_import_the_pdf_again'))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(identity+'.pdf')
    if not path.exists():path.write_bytes(data)
    return {'template': identity, 'template_message': tr('resume.one_page_pdf_saved_as_your_cv_layout_adapted')}


def layout(workspace, profile):
    identity = profile.get('cv_template')
    if not identity:return None
    import pdfplumber
    path = source_path(workspace, identity)
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 1:raise ValueError(tr('resume.use_a_one_page_pdf_as_your_cv_template'))
        page = pdf.pages[0]
        if page.rotation or any(not char['upright'] for char in page.chars):
            raise ValueError(tr('resume.this_cv_uses_rotated_text_export_a_pdf_with'))
        words = page.extract_words(extra_attrs=['fontname','size','non_stroking_color'], return_chars=True)
        lines = []
        for word in sorted(words, key=lambda w: (round(w['top'], 1), w['x0'])):
            previous = lines[-1] if lines else None
            if (previous and abs(previous['top']-word['top']) < 2
                    and previous['fontname'] == word['fontname'] and previous['color'] == word['non_stroking_color']
                    and abs(previous['size']-word['size']) < .1
                    and 0 <= word['x0']-previous['x1'] < max(16, word['size']*2)):
                previous['text'] += ' '+word['text'];previous['x1'] = word['x1']
            else:
                lines.append({'text': word['text'], 'x0': word['x0'], 'x1': word['x1'],
                              'top': word['top'], 'bottom': word['bottom'], 'size': word['size'],
                              'baseline': word['chars'][0]['matrix'][5],
                              'fontname': word['fontname'], 'color': word['non_stroking_color']})
        if not lines or len(lines) > 180 or sum(len(line['text']) for line in lines) > 12000:
            raise ValueError(tr('resume.this_pdf_layout_could_not_be_read_safely_use'))
        for line in lines:
            neighbours = [other['x0'] for other in lines
                          if other['x0'] >= line['x1']+3 and other is not line]
            line['width'] = min(neighbours, default=page.width-24)-line['x0']-3
        return {'path': path, 'width': page.width, 'height': page.height, 'lines': lines}


def render_template(template, texts):
    from reportlab.pdfgen import canvas
    if not isinstance(texts, list) or len(texts) != len(template['lines']) or any(
            not isinstance(text, str) or not text.strip() or len(text)>2000 or '\n' in text for text in texts):
        raise ValueError(tr('resume.the_cv_text_does_not_match_your_template_prepare'))
    reader = PdfReader(template['path'])
    writer = PdfWriter();writer.add_page(reader.pages[0])
    if texts == [line['text'] for line in template['lines']]:
        out=io.BytesIO();writer.write(out);return out.getvalue()
    fonts = {}
    resources=writer.pages[0]['/Resources'].get_object()
    font_resources=resources.get('/Font',{})
    if hasattr(font_resources,'get_object'):font_resources=font_resources.get_object()
    for resource in font_resources.values():
        resource = resource.get_object()
        descriptor = resource.get('/FontDescriptor')
        if descriptor:
            descriptor = descriptor.get_object()
            if descriptor.get('/FontFile2'):
                data = descriptor['/FontFile2'].get_object().get_data()
                name = 'Resume'+hashlib.sha256(data).hexdigest()[:16]
                try:
                    if name not in pdfmetrics.getRegisteredFontNames():
                        pdfmetrics.registerFont(TTFont(name, io.BytesIO(data)))
                    fonts[str(resource.get('/BaseFont', '')).lstrip('/')] = name
                except (ValueError, KeyError, TTFError):
                    pass
    overlay=io.BytesIO();page=canvas.Canvas(overlay,pagesize=(template['width'],template['height']))
    standard={'Helvetica','Helvetica-Bold','Helvetica-Oblique','Helvetica-BoldOblique','Times-Roman','Times-Bold','Times-Italic','Times-BoldItalic','Courier','Courier-Bold','Courier-Oblique','Courier-BoldOblique'}
    for line, text in zip(template['lines'],texts):
        name = fonts.get(line['fontname'], line['fontname'] if line['fontname'] in standard else font())
        face = pdfmetrics.getFont(name).face
        if name in standard:
            if any(ord(char)>255 for char in text):name=font()
        elif any(ord(char) not in getattr(face,'charWidths',{}) for char in text):name=font()
        if name==font() and any(ord(char) not in pdfmetrics.getFont(name).face.charWidths for char in text):
            raise ValueError(tr('resume.the_cv_contains_characters_unavailable_in_its_export_font'))
        size = line['size']
        width = pdfmetrics.stringWidth(text,name,size)
        if width > line['width']:size *= line['width']/width
        if size < min(8, line['size']) or size < line['size']*.75:
            raise ValueError(tr('resume.the_adapted_cv_does_not_fit_your_one_page'))
        color = line['color']
        if isinstance(color,(tuple,list)) and len(color)==3:page.setFillColorRGB(*color)
        elif isinstance(color,(tuple,list)) and len(color)==4:page.setFillColorCMYK(*color)
        else:page.setFillGray(color[0] if isinstance(color,(tuple,list)) else color or 0)
        page.setFont(name,size);page.drawString(line['x0'],line['baseline'],text)
    page.save()
    writer.remove_text()
    writer.pages[0].merge_page(PdfReader(overlay).pages[0])
    out=io.BytesIO();writer.write(out)
    assert len(PdfReader(io.BytesIO(out.getvalue())).pages)==1
    return out.getvalue()


def validate_text(data, profile, language, template, selected, require_template=False):
    from .languages import detect, check_output
    lines = data.get('cv_lines')
    if lines is not None or template and require_template:
        if (not template or not isinstance(lines, list)
                or len(lines) != len(template['lines'])
                or any(not isinstance(line, str) or not line.strip()
                       or len(line) > 2000 or '\n' in line for line in lines)):
            raise ValueError(tr('resume.the_cv_result_does_not_match_your_template_prepare'))
    if 'cv' in data:
        if template:
            raise ValueError(tr('resume.use_cv_lines_to_adapt_the_imported_pdf_template'))
        cv = data['cv']
        if (not isinstance(cv, dict)
                or not {'text', 'strengths', 'selected'}.issubset(cv)
                or set(cv) - {'text', 'strengths', 'selected', 'role'}):
            raise ValueError(tr('resume.the_translated_cv_could_not_be_read_prepare_it'))
        if (any(not isinstance(cv[key], str) or len(cv[key]) > 12000
                for key in ('text', 'strengths'))
                or 'role' in cv and (not isinstance(cv['role'], str) or len(cv['role']) > 300)
                or not isinstance(cv['selected'], list) or not isinstance(selected, list)
                or len(cv['selected']) != len(selected)
                or any(not isinstance(text, str) or not text.strip() or len(text) > 3000
                       for text in cv['selected'])):
            raise ValueError(tr('resume.the_translated_cv_could_not_be_read_prepare_it'))
        if profile.get('cv_text', '').strip() and not cv['text'].strip():
            raise ValueError(tr('resume.the_translated_cv_could_not_be_read_prepare_it'))
        check_output(' '.join([cv['text'], cv['strengths'], *cv['selected']]), language)
    if lines:
        check_output(' '.join(lines), language)
    source = (' '.join(line['text'] for line in template['lines']) if template
              else profile.get('cv_text', '') + ' ' + profile.get('strengths', ''))
    if not data.get('cv') and not lines and detect(source) not in (None, language):
        raise ValueError(tr('resume.the_cv_translation_is_missing_prepare_again_or_import'))
