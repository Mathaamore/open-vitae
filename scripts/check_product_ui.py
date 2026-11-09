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
            external_reads=[]
            page.route('https://**/*',lambda route:(external_reads.append(route.request.url),route.abort()))
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
            page.locator('#optional-ai').click();page.locator('[data-provider="gemini"]').click();page.locator('#provider-key').fill('local-test-key-not-real');page.locator('#connect-provider').click()
            expect(page.locator('#profile-step')).to_be_visible()
            form=page.locator('#profile-form');form.locator('[name="name"]').fill('Alex Example');form.locator('[name="email"]').fill('alex@example.com');form.locator('[name="bio"]').fill('I build useful products with Python.')
            import io
            from reportlab.pdfgen import canvas
            cv=io.BytesIO();cv_page=canvas.Canvas(cv);cv_page.setFont('Helvetica',11)
            cv_page.drawString(40,780,'2024-2026 Engineer at Example. Built production APIs with a product team.');cv_page.save()
            page.locator('#cv-upload').set_input_files({'name':'fictional-resume.pdf','mimeType':'application/pdf','buffer':cv.getvalue()})
            expect(page.locator('#cv-import-status')).to_contain_text('characters imported')
            expect(page.locator('#cv-import-status')).to_contain_text('One-page PDF saved')
            assert len(form.locator('[name="cv_template"]').input_value())==64
            expect(page.locator('#cv-template-clear')).to_be_visible()
            page.screenshot(path=str(out/'product-onboarding.png'))
            page.locator('#profile-next').click()
            expect(page.locator('#draft-status')).to_contain_text('Progress saved')
            page.wait_for_timeout(500)
            page.reload();expect(page.locator('[data-profile-step="1"]')).to_be_visible()
            expect(form.locator('[name="name"]')).to_have_value('Alex Example')
            assert len(form.locator('[name="cv_template"]').input_value())==64
            assert 'Built production APIs' in form.locator('[name="cv_text"]').input_value()
            form.locator('[name="search_countries"]').fill('FR, GB');form.locator('[name="roles"]').fill('Python engineer, Product engineer');form.locator('[name="locations"]').fill('France');form.locator('[name="remote"]').select_option('remote');page.locator('#profile-next').click()
            form.locator('[name="strengths"]').fill('Python, APIs');form.locator('[name="achievements"]').fill('Built a production API with a team.');page.locator('#profile-save').click()
            expect(page.locator('#explore')).to_be_visible();page.locator('#first-search').click();expect(page.locator('.offer-suggestion')).to_have_count(2)
            expect(page.locator('#chat-log')).to_contain_text('jobs in your selection')
            expect(page.locator('#source-collection-note')).to_contain_text('Collection reached its limit')
            page.locator('.external-sources summary').click()
            expect(page.locator('.external-sources a').first).to_be_visible()
            assert not external_reads, 'External sources must not be requested before a link is opened'
            page.locator('.external-sources summary').click()
            # Results scroll independently of the frame and the pinned message field.
            page.locator('#recommendations-list').evaluate("node=>{for(let i=0;i<20;i++){const copy=node.firstElementChild.cloneNode(true);copy.dataset.qaClone='true';node.append(copy)}}")
            for width,height in ((1440,900),(1280,720),(1024,768),(840,580),(375,812)):
                page.set_viewport_size({'width':width,'height':height})
                if width<=1000:page.locator('[data-discovery-pane="jobs"]').click()
                assert page.evaluate('document.documentElement.scrollHeight<=innerHeight'),str(page.evaluate("Object.fromEntries(['html','body','#workspace-root','.app-shell','#main','#explore','.explore-grid','.recommendations-column','#recommendations-list'].map(s=>{const n=document.querySelector(s);return [s,{height:n.clientHeight,scroll:n.scrollHeight,bottom:n.getBoundingClientRect().bottom,overflow:getComputedStyle(n).overflow,rows:getComputedStyle(n).gridTemplateRows}]}))"))
                assert page.locator('#main').evaluate('(node)=>node.scrollHeight<=node.clientHeight'),f'Discovery frame scroll {width}'
                assert page.locator('#recommendations-list').evaluate('(node)=>node.scrollHeight>node.clientHeight'),f'Missing results scroll {width}'
                assert page.locator('.sidebar').evaluate('(node)=>node.scrollHeight<=node.clientHeight'),f'Sidebar scroll {width}'
                page.locator('#recommendations-list').evaluate('(node)=>node.scrollTop=node.scrollHeight')
                if width<=1000:page.locator('[data-discovery-pane="conversation"]').click()
                assert page.locator('#chat-input').evaluate('(node)=>node.getBoundingClientRect().bottom<=innerHeight'),f'Composer obscured {width}'
            page.locator('[data-qa-clone]').evaluate_all('(nodes)=>nodes.forEach(node=>node.remove())')
            page.locator('#recommendations-list').evaluate('(node)=>node.scrollTop=0')
            page.set_viewport_size({'width':1440,'height':1000})
            page.screenshot(path=str(out/'product-search.png'))
            page.locator('#chat-input').fill('Je préfère une petite équipe produit.');page.locator('#chat-send').click();expect(page.locator('#chat-log')).to_contain_text('We can refine')
            page.get_by_role('button',name='Apply preferences').click()
            expect(page.get_by_role('button',name='Preferences updated')).to_be_visible()
            page.locator('[data-id="offer-two"][data-interest="reject"]').click();expect(page.locator('.offer-suggestion')).to_have_count(1)
            page.get_by_role('button',name='Undo',exact=True).click();expect(page.locator('.offer-suggestion')).to_have_count(2)
            page.locator('[data-id="offer-two"][data-interest="reject"]').click();expect(page.locator('.offer-suggestion')).to_have_count(1)
            page.locator('[data-id="offer-one"][data-interest="later"]').click();expect(page.locator('.offer-suggestion')).to_have_count(0)
            page.locator('[data-screen="dashboard"]').click();expect(page.locator('#rows [data-open="offer-one"]')).to_be_visible()
            page.locator('[data-open="offer-one"]').click()
            page.locator('#translate-description').click()
            expect(page.locator('.job-description').first).to_have_text('We build product tools with Python and APIs for teams.')
            expect(page.get_by_text('Show original description',exact=True)).to_be_visible()
            page.locator('[data-prepare-job="offer-one"]').click()
            expect(page.locator('#tools-screen')).to_be_hidden()
            for _ in range(100):
                job=Store(workspace).get('offer-one')
                if job['revision']:break
                time.sleep(.1)
            assert job['revision']==1,job
            expect(page.locator('#panel-dossier')).to_be_visible()
            expect(page.locator('[data-answer="body"]')).to_have_value('I build useful products with Python and enjoy working with product teams.')
            page.screenshot(path=str(out/'product-ai-prepared.png'))
            page.locator('#tab-offre').click();page.locator('#eligibility-checked').check();page.locator('#form-checked').check();page.locator('#confirm-checks').click()
            expect(page.locator('#message')).to_contain_text('Checks saved')
            page.locator('#tab-dossier').click();page.locator('[data-bool="consent"]').check();page.locator('#save').click();expect(page.locator('#review-dossier')).to_be_visible()
            page.screenshot(path=str(out/'product-dossier.png'))
            import shutil
            shutil.copyfile(workspace/job['dossier']['attachments'][0]['path'],out/'product-resume.pdf')
            from pypdf import PdfReader
            assert len(PdfReader(out/'product-resume.pdf').pages)==1
            page.locator('#review-dossier').click();expect(page.locator('#record-receipt')).to_be_visible();page.locator('#record-receipt').click();expect(page.locator('#panel-suivi')).to_be_visible()
            assert Store(workspace).get('offer-one')['status']=='SUBMITTED'
            page.locator('#tracking-open').click()
            page.locator('#tracking-stage').select_option('INTERVIEW')
            page.locator('#tracking-date').fill('2026-11-10')
            page.locator('#tracking-note').fill('First interview with the fictional product team.')
            page.locator('[data-screen="dashboard"]').click()
            expect(page.locator('#review')).to_be_visible()
            page.locator('#save-tracking').click()
            expect(page.locator('.timeline')).to_contain_text('First interview with the fictional product team.')
            expect(page.locator('#tracking-stage')).to_have_value('INTERVIEW')
            page.reload()
            expect(page.locator('#tracking-stage')).to_have_value('INTERVIEW')
            expect(page.locator('[data-screen="dashboard"]')).to_have_attribute('aria-current','page')
            expect(page.locator('.timeline')).to_contain_text('2026-11-10')
            page.screenshot(path=str(out/'product-tracking.png'))
            page.locator('#tracking-stage').select_option('REJECTED')
            page.locator('#tracking-note').fill('Position filled internally; fictional employer feedback.')
            page.locator('#save-tracking').click()
            expect(page.locator('#tracking-stage')).to_have_value('REJECTED')
            assert Store(workspace).get('offer-one')['status']=='SUBMITTED'
            assert Store(workspace).get('offer-one')['tracking']['stage']=='REJECTED'

            page.locator('#back').click()
            page.locator('[data-view="closed"]').click();expect(page.locator('#rows')).to_contain_text('Rejected')
            page.locator('[data-view="sent"]').click();expect(page.locator('#rows [data-open]')).to_have_count(0)
            page.locator('[data-view="all"]').click()
            for width in (375,768,1024,1440):
                page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Dashboard overflow {width}'
            page.locator('[data-layout="grid"]').click();expect(page.locator('.table-wrap')).to_have_attribute('data-layout','grid')
            assert page.locator('.layout-switch [aria-pressed=true]').count()==1
            page.screenshot(path=str(out/'product-dashboard.png'))
            page.locator('[data-layout="list"]').click();expect(page.locator('.table-wrap')).to_have_attribute('data-layout','list')
            page.emulate_media(color_scheme='dark',reduced_motion='reduce')
            page.screenshot(path=str(out/'product-dashboard-dark.png'))
            page.locator('#assistant-open').click();expect(page.locator('#settings-screen')).to_be_visible()
            page.emulate_media(reduced_motion='reduce')
            page.locator('[data-settings-tab="sources"]').click()
            expect(page.locator('.source-choice')).to_have_count(16)
            expect(page.locator('[data-source-preference="remotive"]')).to_have_value('auto')
            page.locator('[data-source-preference="remotive"]').select_option('off')
            page.locator('#save-source-preferences').click()
            expect(page.locator('#message')).to_contain_text('Source choices saved')
            expect(page.locator('[data-source-preference="remotive"]')).to_have_value('off')
            page.locator('[data-source-preference="remoteok"]').focus()
            page.keyboard.press('ArrowDown');page.keyboard.press('Tab')
            assert page.evaluate('document.activeElement !== document.body')
            page.screenshot(path=str(out/'product-sources.png'))
            page.set_viewport_size({'width':375,'height':812})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('[data-source-preference="remotive"]').scroll_into_view_if_needed()
            page.screenshot(path=str(out/'product-sources-mobile.png'))
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#source-boards').fill('smartrecruiters:example');page.locator('#save-source-boards').click()
            expect(page.locator('#message')).to_contain_text('Sources saved')
            page.locator('[data-screen="explore"]').click();page.set_viewport_size({'width':375,'height':812});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(out/'product-search-mobile.png'))
            page.locator('[data-discovery-pane="conversation"]').click()
            # A long transcript cannot push the composer out of a laptop window.
            page.locator('#chat-log').evaluate("node => {for(let i=0;i<80;i++){const p=document.createElement('p');p.textContent='Fictional conversation entry '.repeat(20);node.append(p)}}")
            for width,height in ((1280,720),(1024,768),(840,580),(768,1000),(375,812)):
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate('window.scrollTo(0,0)')
                assert page.locator('#chat-input').evaluate('(node)=>{const r=node.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight}'),f'Composer hidden at {width}x{height}'
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'Discovery overflow {width}'
                assert page.evaluate('document.documentElement.scrollHeight<=innerHeight'),f'Body scroll {width}'
                assert page.locator('#main').evaluate('(node)=>node.scrollHeight<=node.clientHeight'),f'Nested page scroll {width}'
                assert page.locator('.sidebar').evaluate('(node)=>node.scrollHeight<=node.clientHeight'),f'Sidebar scroll {width}'
            page.set_viewport_size({'width':1280,'height':720})
            page.screenshot(path=str(out/'product-chat-laptop.png'))
            page.set_viewport_size({'width':375,'height':812})
            page.locator('[data-discovery-pane="jobs"]').click()
            expect(page.locator('.recommendations-column')).to_be_visible()
            expect(page.locator('.conversation-column')).to_be_hidden()
            page.locator('[data-discovery-pane="conversation"]').click()
            expect(page.locator('#chat-input')).to_be_visible()
            page.set_viewport_size({'width':1280,'height':720})
            page.locator('#assistant-open').click()
            # Exercise the OAuth UI without signing in or sending data to a real provider.
            state={'connected':False,'available':True,'provider':'chatgpt','name':'ChatGPT','pending':True}
            page.route('**/api/providers',lambda route:route.fulfill(json=state))
            page.route('**/api/providers/connect',lambda route:route.fulfill(json={'url':'https://auth.openai.com/authorize?fictional=1'}))
            page.locator('[data-screen="explore"]').click()
            page.locator('#assistant-open').click()
            expect(page.locator('#connected-provider-detail')).to_contain_text('No AI connected')
            expect(page.locator('#provider-disconnect')).to_be_hidden()
            page.locator('[data-screen="explore"]').click()
            page.locator('#chat-input').fill('Keep this fictional message while I connect.')
            page.get_by_role('button',name='Connect AI',exact=True).click()
            expect(page.locator('#connection-dialog')).to_be_visible()
            page.locator('#connection-close').click()
            expect(page.locator('#chat-input')).to_have_value('Keep this fictional message while I connect.')
            page.locator('#assistant-open').click()
            page.locator('#provider-change').click()
            expect(page.locator('#connection-dialog')).to_be_visible()
            expect(page.locator('#workspace-root')).to_be_visible()
            page.locator('[data-provider="chatgpt"]').click()
            page.locator('#connect-provider').click()
            expect(page.locator('#oauth-continue')).to_have_attribute('href','https://auth.openai.com/authorize?fictional=1')
            expect(page.locator('#connection-progress')).to_contain_text('1 of 2')
            page.screenshot(path=str(out/'product-connect-chatgpt.png'))
            state.update(pending=False,error='Sign-in did not finish. Try again.')
            page.locator('#connection-check').click()
            expect(page.locator('#gate-message')).to_contain_text('Sign-in did not finish')
            expect(page.locator('#connection-retry')).to_be_visible()
            state.pop('error');state['pending']=True
            page.locator('#connection-retry').click()
            expect(page.locator('#oauth-continue')).to_be_visible()
            state.update(connected=True,pending=False,email='fictional@example.com')
            page.locator('#connection-check').click()
            expect(page.locator('#connection-dialog')).not_to_be_visible()
            expect(page.locator('#settings-screen')).to_be_visible()
            expect(page.locator('#connected-provider-detail')).to_have_text('fictional@example.com')
            expect(page.locator('#sidebar-ai-status')).to_contain_text('Connected to ChatGPT')
            # Escape restores the shared connection panel and does not hide the workspace.
            page.locator('#provider-change').click();page.keyboard.press('Escape')
            expect(page.locator('#connection-dialog')).not_to_be_visible()
            page.locator('#provider-change').click()
            expect(page.locator('#connection-dialog [data-provider="chatgpt"]')).to_be_visible()
            page.locator('#connection-close').click()
            page.unroute('**/api/providers');page.unroute('**/api/providers/connect')
            page.reload()
            expect(page.locator('#sidebar-ai-status')).to_contain_text('Connected to Gemini')
            page.locator('#add-job').click()
            expect(page.locator('#manual-details')).not_to_have_attribute('open','')
            assert page.locator('#manual-job-dialog').evaluate('(node)=>node.scrollHeight<=node.clientHeight'), 'Collapsed add job dialog scrolls'
            page.screenshot(path=str(out/'product-add-job.png'))
            page.locator('#manual-details').click()
            expect(page.locator('#manual-job-form [name="description"]')).to_be_visible()
            page.locator('#manual-close').click()
            page.locator('#assistant-open').click()
            for tab in ('account','sources','data'):
                page.locator(f'[data-settings-tab="{tab}"]').click()
                expect(page.locator(f'[data-settings-panel="{tab}"]')).to_be_visible()
                assert page.locator('[data-settings-panel]:visible').count()==1
                assert page.evaluate('document.documentElement.scrollHeight<=innerHeight')
            page.screenshot(path=str(out/'product-settings.png'))
            page.locator('[data-screen="tools-screen"]').click();page.locator('#home-link').click()
            expect(page.locator('#dashboard')).to_be_visible();expect(page.locator('#tools-screen')).to_be_hidden()
            assert not errors,errors
            browser.close()
        print('Integrated journey passed: optional provider connection, onboarding, local CV import, chat, offer feedback, preparation, factual PDF, explicit checks/consent, manual sent record, responsive UI. Fake providers/sources and temporary data only.')
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        if proc.returncode not in (0,-15) and proc.stderr:print(proc.stderr.read().decode()[-2500:])
