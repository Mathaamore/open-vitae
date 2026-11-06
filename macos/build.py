"""Build an Apple Silicon app with a bundled Python service and Codex; no user data copied."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import importlib.metadata

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
args = parser.parse_args()
build = root / 'build/macos'
dist = root / 'dist'
build.mkdir(parents=True, exist_ok=True)
dist.mkdir(exist_ok=True)
os.environ['PYINSTALLER_CONFIG_DIR'] = str(build/'pyinstaller-cache')

def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, cwd=root)

codex = shutil.which('codex')
if not codex:
    raise SystemExit('Install the official Codex CLI before building.')
run('swiftc', '-target', 'arm64-apple-macos14.0', '-parse-as-library', root/'macos/Candidatures.swift', '-o', build/'Candidatures',
    '-framework', 'AppKit', '-framework', 'WebKit', '-module-cache-path', '/tmp/candidatures-swift-cache')
browser_cache=Path(os.environ.get('CANDIDATURES_BROWSER_CACHE','/tmp/candidatures-browsers'))
if not any(browser_cache.glob('chromium_headless_shell-*')):
    raise SystemExit('Download the Playwright headless browser first; see macos/README.md.')
run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--name', 'candidatures-service',
    '--paths', root/'src', '--add-data', str(root/'src/job_agent/web')+':job_agent/web',
    '--collect-all','playwright','--copy-metadata','keyring','--hidden-import','keyring.backends.macOS',
    '--hidden-import', 'uvicorn.loops.asyncio', '--hidden-import', 'uvicorn.protocols.http.h11_impl',
    '--hidden-import', 'uvicorn.lifespan.on', '--exclude-module', 'pytest', '--exclude-module', 'numpy',
    '--exclude-module', 'pandas', '--exclude-module', 'matplotlib',
    '--distpath', build/'service-dist', '--workpath', build/'freeze', '--specpath', build, root/'macos/server.py')
app = dist/'Open Vitae.app'
if app.exists():
    shutil.rmtree(app)
contents = app/'Contents'
resources = contents/'Resources'
(contents/'MacOS').mkdir(parents=True)
resources.mkdir()
shutil.copy2(build/'Candidatures', contents/'MacOS/Candidatures')
shutil.copytree(build/'service-dist/candidatures-service', resources/'service', symlinks=True)
shutil.copy2(Path(codex).resolve(), resources/'codex')
shutil.copy2(root/'macos/Codex-LICENSE.txt', resources/'Codex-LICENSE.txt')
shutil.copy2(root/'LICENSE',resources/'LICENSE')
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',resources/'THIRD_PARTY_NOTICES.md')
shutil.copytree(browser_cache,resources/'browsers',symlinks=True)
licenses=resources/'licenses';licenses.mkdir()
inventory=[]
for name in ['fastapi','starlette','uvicorn','h11','pydantic','pydantic_core','typing_extensions','anyio','click','playwright','pyee','greenlet','pypdf','reportlab','pillow','charset-normalizer','keyring','jaraco.classes','jaraco.context','jaraco.functools','more-itertools','pyinstaller']:
    try: distribution=importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError: continue
    inventory.append({'name':name,'version':distribution.version,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License','See included license')})
    for entry in distribution.files or []:
        if any(marker in entry.name.lower() for marker in ['license','copying','notice']) and distribution.locate_file(entry).is_file():
            target=licenses/name/entry.name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(distribution.locate_file(entry),target)
(licenses/'inventory.json').write_text(json.dumps(inventory,indent=2))
iconset = build/'AppIcon.iconset'
iconset.mkdir(exist_ok=True)
shutil.copy2(root/'src/job_agent/web/app-icon.png', build/'icon.png')
for size in [16, 32, 128, 256, 512]:
    for scale in [1, 2]:
        run('sips', '-z', size*scale, size*scale, build/'icon.png', '--out', iconset/f'icon_{size}x{size}{"@2x" if scale == 2 else ""}.png')
run('iconutil', '-c', 'icns', iconset, '-o', resources/'AppIcon.icns')
with (contents/'Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleName': 'Open Vitæ', 'CFBundleDisplayName': 'Open Vitæ',
        'CFBundleIdentifier': 'xyz.mathaamore.candidatures', 'CFBundleExecutable': 'Candidatures',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.3.1', 'CFBundleVersion': '4',
        'CFBundleIconFile': 'AppIcon', 'LSMinimumSystemVersion': '14.0', 'NSHighResolutionCapable': True,
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
        'NSHumanReadableCopyright': 'Open Vitæ — application locale open source'}, f)
run('codesign', '--force', '--sign', '-', resources/'codex')
run('codesign', '--force', '--deep', '--sign', '-', app)
run('codesign', '--verify', '--deep', '--strict', app)
run('ditto', '-c', '-k', '--keepParent', app, dist/'Open-vitae-Mac.zip')
print(f'Built {app}\nArchive: {dist / "Open-vitae-Mac.zip"}\nPrivate data was not bundled.')
