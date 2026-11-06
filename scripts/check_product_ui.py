"""Full journey on a temporary workspace, fake providers and fake sources; zero real submissions."""
from pathlib import Path
import os,socket,subprocess,sys,tempfile,time,urllib.request
from playwright.sync_api import sync_playwright,expect
from job_agent.store import Store
root=Path.cwd();out=root/'data/qa';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    workspace=Path(tmp)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'PYTHONPATH':str(root/'src')+':'+str(root/'tests'),'JOB_AGENT_ROOT':str(workspace)}
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','product_fixture:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        url=f'http://127.0.0.1:{port}'
        for _ in range(80):
            try:urllib.request.urlopen(url+'/api/session',timeout=.2);break
            except Exception:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url)
            expect(page.locator('#connection-step')).to_be_visible()
            expect(page).to_have_title('Open Vitæ')
            assert page.locator('.welcome-bar .brand-wordmark').evaluate('(image)=>image.complete && image.naturalWidth>0')
            assert page.request.get(url+'/static/favicon.svg').ok
            assert page.request.get(url+'/static/app-icon.png').ok
            assert page.request.get(url+'/api/jobs').status==200
            page.screenshot(path=str(out/'product-connection.png'))
            page.set_viewport_size({'width':375,'height':812});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/'product-connection-mobile.png'))
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('[data-provider="gemini"]').click();page.locator('#provider-key').fill('local-test-key-not-real');page.locator('#connect-provider').click()
            expect(page.locator('#profile-step')).to_be_visible()
            form=page.locator('#profile-form');form.locator('[name="name"]').fill('Alex Example');form.locator('[name="email"]').fill('alex@example.com');form.locator('[name="bio"]').fill('I build useful products with Python.')
            page.locator('#cv-upload').set_input_files({'name':'resume.txt','mimeType':'text/plain','buffer':b'2024-2026 Engineer at Example. Built production APIs with a product team.'})
            expect(page.locator('#cv-import-status')).to_contain_text('caractères extraits')
            page.screenshot(path=str(out/'product-onboarding.png'))
            page.locator('#profile-next').click()
            expect(page.locator('#draft-status')).to_contain_text('Brouillon enregistré')
            page.wait_for_timeout(500)
            page.reload();expect(page.locator('[data-profile-step="1"]')).to_be_visible()
            expect(form.locator('[name="name"]')).to_have_value('Alex Example')
            assert 'Built production APIs' in form.locator('[name="cv_text"]').input_value()
            form.locator('[name="roles"]').fill('Python engineer, Product engineer');form.locator('[name="locations"]').fill('France');form.locator('[name="remote"]').select_option('remote');page.locator('#profile-next').click()
            form.locator('[name="strengths"]').fill('Python, APIs');form.locator('[name="achievements"]').fill('Built a production API with a team.');page.locator('#profile-save').click()
            expect(page.locator('#explore')).to_be_visible();page.locator('#first-search').click();expect(page.locator('.offer-suggestion')).to_have_count(2)
            expect(page.locator('#chat-log')).to_contain_text('pistes dans la sélection')
            page.screenshot(path=str(out/'product-search.png'))
            page.locator('#chat-input').fill('Je préfère une petite équipe produit.');page.locator('#chat-send').click();expect(page.locator('#chat-log')).to_contain_text('On peut préciser')
            page.get_by_role('button',name='Appliquer ces critères').click()
            expect(page.get_by_role('button',name='Critères enregistrés')).to_be_visible()
            page.locator('[data-id="offer-two"][data-interest="reject"]').click();expect(page.locator('.offer-suggestion')).to_have_count(1)
            page.get_by_role('button',name='Annuler',exact=True).click();expect(page.locator('.offer-suggestion')).to_have_count(2)
            page.locator('[data-id="offer-two"][data-interest="reject"]').click();expect(page.locator('.offer-suggestion')).to_have_count(1)
            page.locator('[data-id="offer-one"][data-interest="accept"]').click();expect(page.locator('.offer-suggestion')).to_have_count(0)
            page.locator('[data-screen="dashboard"]').click();expect(page.locator('#rows [data-open="offer-one"]')).to_be_visible()
            for _ in range(100):
                job=Store(workspace).get('offer-one')
                if job['revision']:break
                time.sleep(.1)
            assert job['revision']==1,job
            page.locator('[data-open="offer-one"]').click();expect(page.locator('#panel-dossier')).to_be_visible()
            page.locator('#tab-offre').click();page.locator('#eligibility-checked').check();page.locator('#form-checked').check();page.locator('#confirm-checks').click()
            expect(page.locator('#message')).to_contain_text('vérifications')
            page.locator('#tab-dossier').click();page.locator('[data-bool="consent"]').check();page.locator('#save').click();expect(page.locator('#review-dossier')).to_be_visible()
            page.screenshot(path=str(out/'product-dossier.png'))
            import shutil
            shutil.copyfile(workspace/'data/dossiers/offer-one/resume.pdf',out/'product-resume.pdf')
            page.locator('#review-dossier').click();expect(page.locator('#record-receipt')).to_be_visible();page.locator('#record-receipt').click();expect(page.locator('#panel-suivi')).to_be_visible()
            assert Store(workspace).get('offer-one')['status']=='SUBMITTED'
            page.locator('#back').click()
            for width in (375,768,1024,1440):
                page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Dashboard overflow {width}'
            page.screenshot(path=str(out/'product-dashboard.png'))
            page.emulate_media(color_scheme='dark',reduced_motion='reduce')
            page.screenshot(path=str(out/'product-dashboard-dark.png'))
            page.locator('#assistant-open').click();expect(page.locator('#settings-screen')).to_be_visible()
            page.locator('#source-boards').fill('ashby:example');page.locator('#save-source-boards').click()
            expect(page.locator('#message')).to_contain_text('Sources enregistrées')
            page.locator('[data-screen="explore"]').click();page.set_viewport_size({'width':375,'height':812});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/'product-search-mobile.png'))
            assert not errors,errors
            browser.close()
        print('Integrated journey passed: optional provider connection, onboarding, local CV import, chat, offer feedback, preparation, factual PDF, explicit checks/consent, manual sent record, responsive UI. Fake providers/sources and temporary data only.')
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        if proc.returncode not in (0,-15) and proc.stderr:print(proc.stderr.read().decode()[-2500:])
