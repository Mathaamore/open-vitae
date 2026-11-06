import io
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from job_agent import app, languages, opportunities, packets, portable, resume
from job_agent.store import Store, now
from job_agent.workspace import Workspace, extract_resume
from tests.test_product import PROFILE


def source_pdf():
    out=io.BytesIO();page=canvas.Canvas(out,pagesize=(595,842))
    page.setFillColorRGB(.13,.29,.25);page.rect(0,0,180,842,fill=1,stroke=0)
    page.setFillColorRGB(1,1,1);page.setFont('Helvetica-Bold',18);page.drawString(24,780,'Alex Example')
    page.setFont('Helvetica',10);page.drawString(24,745,'alex@example.com')
    page.setFillColorRGB(0,0,0);page.setFont('Helvetica-Bold',14);page.drawString(210,780,'Experience')
    page.setFont('Helvetica',10);page.drawString(210,750,'2024 - Example Tools')
    page.drawString(210,730,'Built an API with our product team.')
    page.save();return out.getvalue()


class ResumeLanguageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ws=Workspace(Store(self.temp.name))
        self.ws.save_profile(PROFILE)
        self.identity=opportunities.add(self.ws,{'company':'Example','role':'Engineer','description':'We build software with our product team.'})['id']
    def tearDown(self):self.temp.cleanup()
    def template(self):
        imported=resume.import_source(self.ws,source_pdf(),'fictional.pdf')
        self.ws.save_profile({**self.ws.profile(),'cv_text':extract_resume(resume.source_path(self.ws,imported['template']).read_bytes(),'source.pdf'),'cv_template':imported['template']})
        return resume.layout(self.ws,self.ws.profile())
    def test_form_language_overrides_source_and_page_language(self):
        job=self.ws.store.get(self.identity)
        info={'language':'en','fields':[{'label':'Pourquoi souhaitez-vous travailler avec nous ?','type':'textarea'}]}
        self.assertEqual(languages.application_language(job,info),'fr')
        info={'language':'nl-NL','fields':[]}
        self.assertEqual(languages.application_language(job,info),'nl')
        job['audit']['application_language']='de'
        self.assertEqual(languages.application_language(job,info),'de')
        self.assertEqual(languages.policy('fr')['information_language'],'en')
        with self.assertRaises(ValueError):opportunities.fields({'description':'Example','application_language':{'bad':'fr'}})
    def test_import_keeps_source_profile_and_backup_without_paths_from_client(self):
        with patch.object(app,'workspace',self.ws):
            client=TestClient(app.app)
            original=source_pdf()
            response=client.post('/api/profile/import?name=fictional.pdf',content=original,headers={'x-local-token':app.TOKEN,'content-type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
            data=response.json();self.assertIn('Alex Example',data['text'])
            self.assertEqual(resume.source_path(self.ws,data['template']).read_bytes(),original)
            self.ws.save_profile({**self.ws.profile(),'cv_text':data['text'],'cv_template':data['template']})
        import zipfile
        with zipfile.ZipFile(io.BytesIO(portable.backup(self.ws))) as backup:
            self.assertIn('data/resume-sources/'+data['template']+'.pdf',backup.namelist())
        for invalid in ('../secret',True,'f'*64):
            with self.assertRaises(ValueError):self.ws.save_profile({**PROFILE,'cv_template':invalid})
    def test_template_is_one_page_and_original_graphics_survive_translation(self):
        template=self.template();original=template['path'].read_bytes()
        texts=[line['text'].replace('Experience','Expérience').replace('Built an API with our product team.','API créée avec notre équipe produit.') for line in template['lines']]
        result=resume.render_template(template,texts)
        page=PdfReader(io.BytesIO(result)).pages[0]
        self.assertEqual(len(PdfReader(io.BytesIO(result)).pages),1)
        self.assertIn('Expérience',page.extract_text())
        self.assertIn('API créée',page.extract_text())
        self.assertNotIn('Built an API',page.extract_text())
        self.assertIn(b'180 842 re',page.get_contents().get_data())
        self.assertEqual(template['path'].read_bytes(),original)
        with self.assertRaisesRegex(ValueError,'does not fit'):
            resume.render_template(template,['An overflowing sentence '*40 for line in template['lines']])
    def test_generated_pdf_refuses_multiple_pages_without_cutting_source(self):
        profile={**PROFILE,'cv_text':'\n'.join('Documented experience at Fictional Tools '+str(i) for i in range(200))}
        with self.assertRaisesRegex(ValueError,'one readable page'):
            packets.pdf_bytes(profile,'Engineer','Summary',[])
        pdf=packets.pdf_bytes(PROFILE,'Ingénieur','Résumé',[],language='fr')
        self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
        self.assertIn('Compétences',PdfReader(io.BytesIO(pdf)).pages[0].extract_text())
    def test_multi_page_source_is_text_only_and_no_template_is_silently_chosen(self):
        writer=PdfWriter();writer.add_blank_page(595,842);writer.add_blank_page(595,842)
        out=io.BytesIO();writer.write(out)
        result=resume.import_source(self.ws,out.getvalue(),'source.pdf')
        self.assertEqual(result['template'],'')
        self.assertIn('multiple pages',result['template_message'])
    def test_prepare_uses_two_languages_and_template_without_changing_source(self):
        template=self.template()
        original_text=self.ws.profile()['cv_text']
        provider=Mock()
        def complete(task,payload,**kwargs):
            self.assertEqual(payload['output_languages']['information_language'],'en')
            self.assertEqual(payload['output_languages']['application_language'],'fr')
            lines=[line['text'].replace('Experience','Expérience').replace('Built an API with our product team.','API créée avec notre équipe produit.') for line in payload['cv_template_lines']]
            return {'summary':'Je crée des API.','selected_facts':[], 'company_summary':'Example builds APIs.', 'product_summary':'APIs','team_summary':'Unknown','answers':{'why':'Je crée des API.'},'cv_lines':lines}
        provider.complete.side_effect=complete
        form={'url':'https://example.com/job','inspected':True,'language':'fr','text':'Nous créons des logiciels pour les équipes.', 'fields':[{'key':'why','label':'Pourquoi souhaitez-vous travailler avec nous ?','type':'textarea'}]}
        with patch.object(packets,'inspect_offer',return_value=form):packets.prepare(self.ws,provider,self.identity)
        job=self.ws.store.get(self.identity)
        self.assertEqual(job['dossier']['answers']['why'],'Je crée des API.')
        self.assertEqual(job['audit']['company_context']['company']['summary'],'Example builds APIs.')
        self.assertEqual(self.ws.profile()['cv_text'],original_text)
        path=self.ws.store.root/job['dossier']['attachments'][0]['path']
        self.assertIn('Expérience',PdfReader(path).pages[0].extract_text())
    def test_portable_prompt_and_import_support_translated_template(self):
        template=self.template()
        job=self.ws.store.get(self.identity)
        opportunities.edit(self.ws,self.identity,{'company':'Example','role':'Engineer','description':'Nous créons des logiciels pour les équipes.','application_language':'fr','updated_at':job['updated_at']})
        prompt=portable.prompt(self.ws,'application_draft',self.identity)['prompt']
        self.assertIn('cv_template_lines',prompt)
        self.assertIn('"application_language": "fr"',prompt)
        value=portable.example('application_draft',portable.context(self.ws,'application_draft',self.identity))
        value['data']['cv_lines']=[line['text'].replace('Experience','Expérience').replace('Built an API with our product team.','API créée avec notre équipe produit.') for line in template['lines']]
        portable.apply(self.ws,value)
        value['data']['cv_lines']=['missing entries']
        with self.assertRaises(ValueError):portable.validate(self.ws,value)

    def test_wrong_language_is_rejected_without_replacing_existing_materials(self):
        from job_agent import portable
        portable.draft(self.ws,self.identity)
        before=self.ws.store.get(self.identity)
        provider=Mock();provider.complete.return_value={'summary':'I build useful products.','selected_facts':[],
            'company_summary':'Nous créons des logiciels pour les équipes avec une expérience utile.',
            'product_summary':'APIs','team_summary':'Unknown','answers':{}}
        form={'url':'https://example.com/job','inspected':True,'text':'We build useful products with our team.','fields':[],'language':'en'}
        with patch.object(packets,'inspect_offer',return_value=form):
            with self.assertRaisesRegex(ValueError,'English'):
                packets.prepare(self.ws,provider,self.identity,replace=True)
        self.assertEqual(self.ws.store.get(self.identity)['fingerprint'],before['fingerprint'])
        with self.assertRaisesRegex(ValueError,'French'):
            languages.check_output('The role requires experience with your skills and our team.','fr')

    def test_plain_cv_translation_has_localized_sections_and_keeps_profile(self):
        profile={**PROFILE,'cv_text':'Expérience dans une équipe avec des API pour les clients.'}
        self.ws.save_profile(profile)
        provider=Mock();provider.complete.return_value={'summary':'I build useful products.','selected_facts':[0],
            'company_summary':'Example builds APIs.','product_summary':'APIs','team_summary':'Unknown','answers':{},
            'cv':{'role':'Python engineer','text':'Experience building APIs with the team for our clients.','strengths':'Python, APIs','selected':['Built a production API with a team.']}}
        form={'url':'https://example.com/job','inspected':True,'text':'The role requires experience with our products.','language':'en','fields':[]}
        with patch.object(packets,'inspect_offer',return_value=form):packets.prepare(self.ws,provider,self.identity)
        job=self.ws.store.get(self.identity);pdf=PdfReader(self.ws.store.root/job['dossier']['attachments'][0]['path'])
        self.assertEqual(len(pdf.pages),1)
        self.assertNotIn('Expérience',pdf.pages[0].extract_text())
        self.assertEqual(self.ws.profile()['cv_text'],profile['cv_text'])

    def test_corrected_text_cannot_silently_use_a_stale_pdf_layout(self):
        self.template()
        before=self.ws.profile()
        with self.assertRaisesRegex(ValueError,'differs from the PDF'):
            self.ws.save_profile({**before,'cv_text':'Corrected experience with a fictional company and team.'})
        self.assertEqual(self.ws.profile(),before)
        self.ws.save_profile({**before,'cv_text':'Corrected experience with a fictional company and team.','cv_template':''})
        self.assertEqual(self.ws.profile()['cv_template'],'')

    def test_embedded_font_template_can_be_reused(self):
        pdf=packets.pdf_bytes(PROFILE,'Engineer','I build products.',[])
        imported=resume.import_source(self.ws,pdf,'fictional.pdf')
        profile={**self.ws.profile(),'cv_template':imported['template'],'cv_text':extract_resume(pdf,'fictional.pdf')}
        self.ws.save_profile(profile)
        template=resume.layout(self.ws,profile)
        texts=[line['text'].replace('Experience','Expérience') for line in template['lines']]
        result=resume.render_template(template,texts)
        self.assertIn('Expérience',PdfReader(io.BytesIO(result)).pages[0].extract_text())

    def test_questions_detect_all_supported_languages_without_using_profile_language(self):
        for language,question in {
            'en':'Why this role? Tell us about your experience.',
            'fr':'Pourquoi ce poste ? Décrivez votre expérience.',
            'de':'Warum bewerben Sie sich? Ihre Erfahrung und Kenntnisse.',
            'es':'Cuéntanos tu experiencia para este puesto.',
            'it':'Descrivi le tue competenze per questo lavoro.',
            'nl':'Vertel waarom jouw ervaring bij onze functie past.',
            'pt':'Descreva sua experiência para esta vaga.',
        }.items():
            self.assertEqual(languages.application_language({'audit':{}},{'fields':[{'label':question,'type':'textarea'}]}),language)
