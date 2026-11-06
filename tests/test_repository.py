import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('repository_check',Path(__file__).resolve().parents[1]/'scripts/check_repository.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


class RepositoryCheckTest(unittest.TestCase):
    def test_runtime_data_and_credentials_are_rejected(self):
        for name in ['inputs/profile.txt','legacy/application-workbench/code.py','data/agent.sqlite3','.env.local','dist/App.app/a','auth.json','key.pem']:
            self.assertTrue(check.problems(name,b'content'),name)
    def test_secrets_and_private_contacts_are_rejected_without_echoing_them(self):
        for value in ['sk-'+('a'*30), 'AIza'+('b'*35), '/Users/'+'candidate/Documents/cv', 'candidate'+'@gmail.com']:
            result=check.problems('source.py',value.encode())
            self.assertTrue(result)
            self.assertNotIn(value,str(result))
    def test_fictional_data_and_licensed_assets_are_allowed(self):
        self.assertEqual(check.problems('tests/fixture.py',b'alex@example.com'),[])
        self.assertEqual(check.problems('web/logo.svg',b'<svg viewBox="0 0 256 256"/>'),[])
        self.assertEqual(check.problems('web/Geist-OFL.txt',('author'+'@gmail.com').encode()),[])
