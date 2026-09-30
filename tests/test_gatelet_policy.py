"""Gatelet policy regression tests; PyYAML is installed in CI."""
from pathlib import Path
import unittest

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
READ_AND_DRAFT = {'search', 'read_message', 'create_draft', 'list_drafts'}
DENIED = {'send', 'reply', 'archive'}


@unittest.skipUnless(yaml, 'install PyYAML to verify Gatelet policies')
class MailPolicyTests(unittest.TestCase):
    def policy(self, name):
        path = ROOT / 'policies' / name
        assert yaml is not None
        policy = yaml.safe_load(path.read_text())
        self.assertEqual(policy['account'].startswith('YOUR_'), True)
        return policy['operations']

    def test_gmail_no_archive_bypass_through_move_or_label(self):
        operations = self.policy('gmail.yaml')
        allowed = READ_AND_DRAFT | {'list_labels'}
        self.assertEqual({op for op, config in operations.items() if config['allow']}, allowed)
        self.assertTrue(DENIED | {'move', 'label'} <= {op for op, config in operations.items() if not config['allow']})

    def test_outlook_move_is_restricted_to_inbox(self):
        operations = self.policy('outlook-mail.yaml')
        allowed = READ_AND_DRAFT | {'move', 'list_folders'}
        self.assertEqual({op for op, config in operations.items() if config['allow']}, allowed)
        self.assertTrue(DENIED <= {op for op, config in operations.items() if not config['allow']})
        self.assertEqual(operations['move']['constraints'], [
            {'field': 'folderId', 'rule': 'must_be_one_of', 'value': ['Inbox']}
        ])
        self.assertIn('archive', operations['move']['guards']['protected_folders'])


if __name__ == '__main__':
    unittest.main()
