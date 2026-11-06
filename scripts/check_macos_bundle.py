"""Smoke-test bundled executables without a provider account or candidate data."""
import io
import json
import os
from pathlib import Path
import plistlib
import select
import signal
import subprocess
import tempfile
import time
import tomllib
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    app = ROOT/'dist/Open Vitae.app'
    resources = app/'Contents/Resources'
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    assert info['CFBundleShortVersionString'] == tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    with tempfile.TemporaryDirectory(prefix='open-vitae-bundle-') as tmp:
        env = {**os.environ, 'JOB_AGENT_ROOT':tmp, 'CODEX_HOME':str(Path(tmp)/'codex'),
               'JOB_AGENT_CODEX':str(resources/'codex'), 'PLAYWRIGHT_BROWSERS_PATH':str(resources/'browsers')}
        (Path(tmp)/'codex').mkdir()
        subprocess.run([str(resources/'codex'),'--version'],env=env,check=True,timeout=20)
        browsers = list((resources/'browsers').glob('chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell'))
        assert browsers, 'Bundled Apple Silicon browser missing'
        subprocess.run([str(browsers[-1]),'--version'],env=env,check=True,timeout=20)
        with (Path(tmp)/'service.log').open('w+') as log:
            process = subprocess.Popen([str(resources/'service/candidatures-service'),tmp],env=env,stdout=subprocess.PIPE,stderr=log)
            try:
                assert select.select([process.stdout],[],[],30)[0], 'Frozen service startup timed out'
                handshake=json.loads(process.stdout.readline())
                assert 'port' in handshake, handshake
                url=f'http://127.0.0.1:{handshake["port"]}'
                for attempt in range(60):
                    try:
                        with urlopen(url+'/api/session',timeout=1) as response:
                            assert json.load(response)['token']
                        break
                    except OSError:
                        if process.poll() is not None:
                            log.seek(0);raise AssertionError(log.read()[-3000:])
                        time.sleep(.1)
                else:
                    raise AssertionError('Frozen service did not become ready')
                with urlopen(url+'/static/favicon.svg',timeout=2) as response:
                    assert response.status == 200
                with urlopen(url+'/api/session',timeout=2) as response:
                    token=json.load(response)['token']
                def send(path,value,method='POST',raw=False):
                    data=value if raw else json.dumps(value).encode()
                    request=Request(url+path,data=data,method=method,headers={
                        'X-Local-Token':token,'Content-Type':'application/octet-stream' if raw else 'application/json'})
                    with urlopen(request,timeout=20) as response:return json.load(response)
                from reportlab.pdfgen import canvas
                from pypdf import PdfReader
                source=io.BytesIO();page=canvas.Canvas(source)
                page.drawString(40,780,'Alex Example - Engineer at Fictional Tools')
                page.drawString(40,760,'Built APIs with our product team.');page.save()
                imported=send('/api/profile/import?name=fictional.pdf',source.getvalue(),raw=True)
                assert imported['template'] and 'Fictional Tools' in imported['text']
                send('/api/profile',{'name':'Alex Example','bio':'I build useful products.',
                    'roles':['Engineer'],'cv_text':imported['text'],'cv_template':imported['template']},method='PUT')
                added=send('/api/opportunities',{'company':'Fictional Tools','role':'Engineer','description':'We build tools with our product team.'})
                with urlopen(url+'/api/jobs/'+added['id'],timeout=2) as response:job=json.load(response)
                prepared=send('/api/opportunities/'+added['id']+'/draft',{'revision':job['revision'],
                    'updated_at':job['updated_at'],'summary':'I build useful products.','motivation':''})
                attachment=Path(tmp)/prepared['dossier']['attachments'][0]['path']
                assert len(PdfReader(attachment).pages)==1

            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
    print('Bundle passed: signatures, version, native Codex/browser, frozen service startup, local assets, PDF import and one-page template export. No provider account used.')


if __name__ == '__main__':
    main()
