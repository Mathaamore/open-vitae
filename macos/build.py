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
import tomllib
import base64
import re

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--release', action='store_true', help='Require Developer ID, Sparkle and hardened runtime signing')
args = parser.parse_args()
version = tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
release = json.loads((root/'macos/release.json').read_text())
identity = os.environ.get('MACOS_SIGN_IDENTITY', '-')
sparkle = Path(os.environ['SPARKLE_ROOT']) if os.environ.get('SPARKLE_ROOT') else None
feed = os.environ.get('SPARKLE_FEED_URL', '')
public_key = os.environ.get('SPARKLE_PUBLIC_KEY', '')
if args.release:
    if not identity.startswith('Developer ID Application:') or not sparkle or not (sparkle/'Sparkle.framework').is_dir():
        raise SystemExit('Release builds require a Developer ID Application identity and SPARKLE_ROOT.')
    if not re.fullmatch(r'https://[^\s]+', feed) or len(base64.b64decode(public_key, validate=True)) != 32:
        raise SystemExit('Release builds require an HTTPS Sparkle feed and a 32-byte Ed25519 public key.')
    with (sparkle/'Sparkle.framework/Resources/Info.plist').open('rb') as file:
        sparkle_version = plistlib.load(file)['CFBundleShortVersionString']
    if tuple(int(part) for part in sparkle_version.split('.')) < (2, 9, 6):
        raise SystemExit('Release builds require Sparkle 2.9.6 or newer for signed feeds and security fixes.')
    if not feed.endswith('/appcast.xml'):
        raise SystemExit('The stable HTTPS update feed must end with /appcast.xml.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit('A release requires a semantic version.')
build = root / 'build/macos'
dist = root / 'dist'
build.mkdir(parents=True, exist_ok=True)
dist.mkdir(exist_ok=True)
os.environ['PYINSTALLER_CONFIG_DIR'] = str(build/'pyinstaller-cache')

def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True, cwd=root)

codex = os.environ.get('CODEX_BINARY') or shutil.which('codex')
if not codex:
    raise SystemExit('Install the official Codex CLI before building.')
codex = Path(codex).resolve()
with codex.open('rb') as binary:
    if binary.read(4) not in {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'}:
        raise SystemExit('CODEX_BINARY must point to the official native macOS binary, not the npm launcher.')
swift_flags = ['-F', str(sparkle), '-framework', 'Sparkle', '-Xlinker', '-rpath', '-Xlinker', '@executable_path/../Frameworks'] if args.release else []
run('swiftc', *swift_flags, '-target', 'arm64-apple-macos14.0', '-parse-as-library', root/'macos/Candidatures.swift', '-o', build/'Candidatures',
    '-framework', 'AppKit', '-framework', 'WebKit', '-module-cache-path', '/tmp/candidatures-swift-cache')
browser_cache=Path(os.environ.get('CANDIDATURES_BROWSER_CACHE','/tmp/candidatures-browsers'))
if not any(browser_cache.glob('chromium_headless_shell-*')):
    raise SystemExit('Download the Playwright headless browser first; see macos/README.md.')
run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--name', 'candidatures-service',
    '--paths', root/'src', '--add-data', str(root/'src/job_agent/web')+':job_agent/web',
    '--add-data',str(root/'src/job_agent/locales')+':job_agent/locales',
    '--collect-all','playwright','--collect-all','pdfplumber','--collect-all','pdfminer','--collect-all','pypdfium2','--copy-metadata','open-vitae','--copy-metadata','keyring','--hidden-import','keyring.backends.macOS',
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
shutil.copytree(root/'macos/en.lproj',resources/'en.lproj')
if args.release:
    (contents/'Frameworks').mkdir()
    shutil.copytree(sparkle/'Sparkle.framework', contents/'Frameworks/Sparkle.framework', symlinks=True)
shutil.copy2(build/'Candidatures', contents/'MacOS/Candidatures')
shutil.copytree(build/'service-dist/candidatures-service', resources/'service', symlinks=True)
shutil.copy2(Path(codex).resolve(), resources/'codex')
shutil.copy2(root/'macos/Codex-LICENSE.txt', resources/'Codex-LICENSE.txt')
shutil.copy2(root/'LICENSE',resources/'LICENSE')
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',resources/'THIRD_PARTY_NOTICES.md')
shutil.copytree(browser_cache,resources/'browsers',symlinks=True)
licenses=resources/'licenses';licenses.mkdir()
inventory=[]
for name in ['fastapi','starlette','uvicorn','h11','pydantic','pydantic_core','typing_extensions','anyio','click','playwright','pyee','greenlet','pypdf','pdfplumber','pdfminer.six','pypdfium2','cryptography','cffi','pycparser','reportlab','pillow','charset-normalizer','keyring','jaraco.classes','jaraco.context','jaraco.functools','more-itertools','pyinstaller']:
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
        'CFBundleIdentifier': release['bundle_id'], 'CFBundleExecutable': 'Candidatures',
        'CFBundlePackageType': 'APPL', 'CFBundleDevelopmentRegion': 'en', 'CFBundleLocalizations': ['en'], 'CFBundleShortVersionString': version, 'CFBundleVersion': str(release['build']),
        'CFBundleIconFile': 'AppIcon', 'LSMinimumSystemVersion': release['minimum_macos'], 'NSHighResolutionCapable': True,
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
        'NSHumanReadableCopyright': 'Open Vitæ',
        **({'SUFeedURL': feed, 'SUPublicEDKey': public_key, 'SUAutomaticallyUpdate': False, 'SUVerifyUpdateBeforeExtraction': True, 'SURequireSignedFeed': True} if args.release else {})}, f)
if args.release:
    # Sign nested code from the inside out; --deep is verification, not a signing plan.
    magic = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'}
    for path in sorted(app.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if path.is_symlink():
            continue
        if path.is_file():
            with path.open('rb') as binary:
                is_code = binary.read(4) in magic
            if is_code:
                entitlements = ['--entitlements', root/'macos/browser.entitlements'] if path.is_relative_to(resources/'browsers') and path.stat().st_mode & 0o111 else []
                run('codesign', '--force', '--options', 'runtime', '--timestamp', '--sign', identity, *entitlements, path)
        elif path.suffix in {'.framework', '.app', '.xpc'}:
            run('codesign', '--force', '--options', 'runtime', '--timestamp', '--sign', identity, path)
    run('codesign', '--force', '--options', 'runtime', '--timestamp', '--sign', identity, app)
else:
    run('codesign', '--force', '--sign', '-', resources/'codex')
    run('codesign', '--force', '--deep', '--sign', '-', app)
run('codesign', '--verify', '--deep', '--strict', app)
run('ditto', '-c', '-k', '--keepParent', app, dist/'Open-vitae-Mac.zip')
print(f'Built {app}\nArchive: {dist / "Open-vitae-Mac.zip"}\nPrivate data was not bundled.')
