"""Check the Git index before committing; never prints the content of a finding."""
from pathlib import Path, PurePosixPath
import re
import subprocess

BLOCKED = {'.aws', '.codex', '.env', '.git', '.venv', 'applications', 'legacy', 'data', 'inputs', 'node_modules', 'dist', 'build', '__pycache__'}
SUFFIXES = {'.pdf', '.docx', '.eml', '.sqlite', '.sqlite3', '.db', '.pem', '.key', '.p12', '.pyc', '.zip', '.dmg'}
PATTERNS = [
    ('private home path', r'/Users/[A-Za-z0-9._-]+/(?:Documents|Desktop|Downloads|Library)/'),
    ('personal email', r'[A-Za-z0-9._%+-]+@(?:gmail|hotmail|outlook|icloud)\.com'),
    ('private key', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('provider secret', r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16})\b'),
]


def problems(name, content):
    path = PurePosixPath(name)
    found = []
    if path.is_absolute() or '..' in path.parts or any(ord(c) < 32 for c in name):
        return ['invalid path']
    if any(part in BLOCKED or part.endswith('.app') for part in path.parts) or path.suffix.lower() in SUFFIXES or path.name.startswith('.env') or path.name in {'.DS_Store','auth.json','credentials.json'}:
        found.append('private or generated file')
    if len(content) > 5 * 1024 * 1024:
        found.append('file exceeds 5 MiB')
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        return found
    for label, pattern in PATTERNS:
        # Upstream license notices can contain their authors' public email addresses.
        if label == 'personal email' and (path.name.endswith('-OFL.txt') or path.name == 'Codex-LICENSE.txt'):
            continue
        if re.search(pattern, text, re.I if label == 'personal email' else 0):
            found.append(label)
    return found


def main():
    root = Path(__file__).resolve().parents[1]
    names = subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    checked = 0
    failures = []
    for name in filter(None,names):
        metadata = subprocess.check_output(['git','ls-files','--stage','--',name],cwd=root).decode()
        if metadata.startswith(('120000 ', '160000 ')):
            failures.append((name, ['symlink or submodule requires explicit review']));continue
        blob = subprocess.check_output(['git','show',':'+name],cwd=root)
        checked += 1
        if issues := problems(name,blob):
            failures.append((name,issues))
    if not checked:
        raise SystemExit('Nothing staged or tracked to inspect.')
    for name, issues in failures:
        print(name + ': ' + ', '.join(issues))
    if failures:
        raise SystemExit('Repository check failed; no secret contents were printed.')
    print(f'Repository check passed: {checked} indexed files; no blocked artifacts or matching secret patterns.')


if __name__ == '__main__':
    main()
