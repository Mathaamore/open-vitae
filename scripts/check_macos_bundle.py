"""Smoke-test bundled executables without a provider account or candidate data."""
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
from urllib.request import urlopen

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
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
    print('Bundle passed: signatures, version, native Codex/browser, frozen service startup and local assets. No provider account used.')


if __name__ == '__main__':
    main()
