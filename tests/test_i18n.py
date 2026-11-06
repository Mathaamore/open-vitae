import unittest
from job_agent.i18n import catalog, tr, system_text, legacy_messages


class CopyTests(unittest.TestCase):
    def test_missing_locale_falls_back_to_english(self):
        key=next(iter(catalog()))
        self.assertEqual(tr(key,locale='zz'),tr(key))
        self.assertEqual(catalog('../../etc'),catalog('en'))

    def test_only_known_system_notices_are_rewritten(self):
        source='Mon expérience en développement — équipe française'
        self.assertEqual(system_text(source),source)
        old,key=next(iter(legacy_messages().items()))
        self.assertEqual(system_text(old),tr(key))
