"""Offline journey with fictional files, blocked external access and no provider."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'data/qa';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env={**os.environ,'PYTHONPATH':str(ROOT/'src')+':'+str(ROOT/'tests'),'JOB_AGENT_ROOT':tmp}
        process=subprocess.Popen([sys.executable,'-m','uvicorn','offline_fixture:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            url=f'http://127.0.0.1:{port}'
            for _ in range(80):
                try:urlopen(url+'/api/session',timeout=.2);break
                except OSError:time.sleep(.1)
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url+'/') or route.request.url.startswith(('blob:','data:')) else route.abort())
                page.goto(url);page.locator('#continue-local').click();expect(page.locator('#profile-step')).to_be_visible()
                form=page.locator('#profile-form');form.locator('[name="name"]').fill('Alex Example');form.locator('[name="bio"]').fill('I build useful Python services.')
                page.locator('#cv-upload').set_input_files({'name':'fictional.txt','mimeType':'text/plain','buffer':b'Built a production Python API at Fictional Tools.'})
                expect(page.locator('#cv-import-status')).to_contain_text('characters imported')
                page.locator('#profile-next').click();form.locator('[name="roles"]').fill('Python engineer');page.locator('#profile-next').click();page.locator('#profile-save').click()
                expect(page.locator('#explore')).to_be_visible();page.reload();expect(page.locator('#workspace-root')).to_be_visible()
                page.locator('[data-screen="tools-screen"]').click();expect(page.locator('#local-summary')).to_have_value('I build useful Python services.')
                expect(page.locator('#portable-notes')).to_contain_text('No insights imported')
                page.locator('#add-job').click();manual=page.locator('#manual-job-form')
                manual.locator('[name="url"]').fill('https://example.com/jobs/python?utm_source=offline')
                page.locator('#manual-retrieve').click();expect(page.locator('#manual-status')).to_contain_text('Save the link')
                manual.locator('[name="company"]').fill('Fictional Tools');manual.locator('[name="role"]').fill('Python engineer');page.locator('#manual-save').click()
                expect(page.locator('#job-title')).to_contain_text('Fictional Tools');identity=page.url.split('job=')[1].split('&')[0]
                page.locator('[data-edit-opportunity]').click();manual.locator('[name="description"]').fill('A documented Python role. Eligibility and salary unverified.');page.locator('#manual-save').click()
                page.locator('[data-local-tools]').click();expect(page.locator('#tools-screen')).to_be_visible()
                page.locator('#local-draft-details').click();page.locator('#local-motivation').fill('I build useful Python services.');page.locator('#local-draft').click()
                expect(page.locator('#panel-dossier')).to_be_visible();expect(page.locator('[data-answer="body"]')).to_have_value('I build useful Python services.')
                page.locator('[data-answer="body"]').fill('My edited factual draft.');page.locator('#save').click();expect(page.locator('#message')).to_contain_text('Changes saved')
                page.locator('#tab-offre').click();page.locator('#eligibility-checked').check();page.locator('#form-checked').check();page.locator('#confirm-checks').click()
                expect(page.locator('#review-dossier')).to_be_visible()
                page.locator('#review-dossier').click();page.locator('#record-receipt').click();expect(page.locator('#panel-suivi')).to_contain_text('Applied')
                page.locator('[data-local-tools]').click();page.locator('#portable-kind').select_option('job_search_results');page.locator('#portable-generate').click();expect(page.locator('#portable-prompt')).not_to_have_value('')
                prompt=page.locator('#portable-prompt').input_value();ctx=json.loads(prompt.split('EXPECTED SHAPE:\n')[1].split('\n\nSOURCE MATERIAL:')[0])['context']
                invalid={'schema_version':2,'type':'application_draft','context':ctx,'data':{}}
                page.locator('#portable-input').fill(json.dumps(invalid));page.locator('#portable-preview').click();expect(page.locator('#portable-status')).to_contain_text('result version')
                expect(page.locator('#portable-apply')).to_be_disabled()
                value={'schema_version':1,'type':'job_search_results','context':{'profile_revision':ctx['profile_revision']},'data':{'jobs':[{'company':'Fictional Tools','role':'Python engineer','url':'https://example.com/jobs/python#details'},{'company':'Another Example','role':'Python APIs','url':'https://example.com/jobs/api','description':'An externally proposed listing, unverified.'}]}}
                page.locator('#portable-file').set_input_files({'name':'jobs.json','mimeType':'application/json','buffer':json.dumps(value).encode()})
                page.locator('#portable-preview').click();expect(page.locator('#portable-status')).to_contain_text('existing job')
                page.locator('#portable-apply').click();expect(page.locator('#portable-status')).to_contain_text('Results imported')
                page.locator('#portable-preview').click();page.locator('#portable-apply').click();expect(page.locator('#portable-status')).to_contain_text('Results imported')
                page.locator('[data-screen="dashboard"]').click();expect(page.locator('#rows [data-open]')).to_have_count(2)
                page.locator('[data-view="saved"]').click();expect(page.locator('#rows [data-open]')).to_have_count(1)
                page.locator('[data-screen="tools-screen"]').click()
                with page.expect_download() as download:page.locator('#backup-data').click()
                assert download.value.suggested_filename=='open-vitae-backup.zip'
                page.evaluate('window.scrollTo(0,0)')
                page.locator('#tools-title').evaluate('(element)=>{element.tabIndex=-1;element.focus()}')
                page.screenshot(path=str(output/'offline-tools.png'),full_page=True)
                for width in (390,768,1024,1440):
                    page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
                page.emulate_media(color_scheme='dark',reduced_motion='reduce');page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'offline-tools-mobile.png'),full_page=True)
                assert not errors,errors
                browser.close()
            print('Offline journey passed: no provider/network, local profile/CV, pending URL, retrieval fallback, manual edits, PDF/draft edits, manual sent tracking, prompts, invalid JSON recovery, preview/confirm, canonical dedup, favorites, backup and responsive UI.')
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            if process.returncode not in (0,-15):print(process.stderr.read().decode()[-2500:])


if __name__=='__main__':main()
