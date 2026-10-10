"""Account naming without creating a window or accessing Discord."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app import App


class AccountNamingTests(unittest.TestCase):
    def test_verified_identity_is_bound_to_token(self):
        panel = SimpleNamespace(token=SimpleNamespace(get=lambda: 'DUMMY_TEST_ONLY'), confirmed_account=None)
        App.remember_account(panel, dict(id='123456789012345678',username='example.user'),'DUMMY_TEST_ONLY')
        self.assertEqual(panel.confirmed_account['username'],'example.user')
        with self.assertRaises(ValueError):
            App.remember_account(panel, dict(id='999999999999999999',username='wrong.account'),'STALE_DUMMY')
        self.assertEqual(panel.confirmed_account['username'],'example.user')

    def test_zip_default_uses_confirmed_username(self):
        panel=SimpleNamespace(confirmed_account=dict(username='example.user',id='123456789012345678'),tr=lambda s:s)
        with patch('app.filedialog.asksaveasfilename',return_value='') as dialog:
            App.export_named(panel,dict(token='DUMMY_TEST_ONLY'),False,'English')
        self.assertEqual(dialog.call_args.kwargs['initialfile'],'example.user.zip')
