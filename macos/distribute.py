"""Notarize a release app, then make a signed drag-to-Applications installer."""
import hashlib
import os
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def main():
    app = ROOT / 'dist/Open Vitae.app'
    if not os.environ.get('NOTARY_KEYCHAIN_PROFILE'):
        raise SystemExit('Configure NOTARY_KEYCHAIN_PROFILE before notarizing a release.')
    with (app/'Contents/Info.plist').open('rb') as file:
        import plistlib
        info = plistlib.load(file)
    version = tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    if info.get('CFBundleShortVersionString') != version or not info.get('SUPublicEDKey'):
        raise SystemExit('Build the matching release app with Sparkle first.')
    run('codesign', '--verify', '--deep', '--strict', app)
    run('xcrun', 'notarytool', 'submit', ROOT/'dist/Open-vitae-Mac.zip', '--keychain-profile', os.environ['NOTARY_KEYCHAIN_PROFILE'], '--wait')
    run('xcrun', 'stapler', 'staple', app)
    run('xcrun', 'stapler', 'validate', app)
    run('spctl', '--assess', '--type', 'execute', '--verbose=2', app)
    # Recreate the update archive only after stapling the application.
    (ROOT/'dist/Open-vitae-Mac.zip').unlink()
    run('ditto', '-c', '-k', '--keepParent', app, ROOT/'dist/Open-vitae-Mac.zip')
    stage = ROOT/'build/macos/dmg'
    stage.mkdir(exist_ok=True)
    import shutil
    if (stage/app.name).exists():
        shutil.rmtree(stage/app.name)
    shutil.copytree(app, stage/app.name, symlinks=True)
    (stage/'Applications').unlink(missing_ok=True)
    (stage/'Applications').symlink_to('/Applications')
    (stage/'Installer.txt').write_text('Glisse Open Vitae dans Applications, puis ouvre Open Vitæ.\nTes données restent dans ton espace local lors des mises à jour.\n')
    dmg = ROOT/'dist/Open-vitae-Mac.dmg'
    run('hdiutil', 'create', '-ov', '-volname', 'Open Vitæ', '-srcfolder', stage, '-format', 'UDZO', dmg)
    run('codesign', '--timestamp', '--sign', os.environ['MACOS_SIGN_IDENTITY'], dmg)
    run('xcrun', 'notarytool', 'submit', dmg, '--keychain-profile', os.environ['NOTARY_KEYCHAIN_PROFILE'], '--wait')
    run('xcrun', 'stapler', 'staple', dmg)
    run('xcrun', 'stapler', 'validate', dmg)
    checksums = []
    for path in (dmg, ROOT/'dist/Open-vitae-Mac.zip'):
        with path.open('rb') as file:
            checksums.append(f'{hashlib.file_digest(file, "sha256").hexdigest()}  {path.name}\n')
    (ROOT/'dist/SHA256SUMS').write_text(''.join(checksums))
    print('Signed and notarized artifacts created. Clean-Mac and real-provider verification is still required before publication.')


if __name__ == '__main__':
    main()
