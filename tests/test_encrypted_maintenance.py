import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch
from tool.prune_encrypted import main


class EncryptedMaintenanceTests(unittest.TestCase):
    def test_default_never_constructs_store(self):
        factory = Mock()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(factory), 2)
        factory.assert_not_called()

    def test_opt_in_requires_sandbox_profile(self):
        factory = Mock()
        with patch.dict(os.environ, {'SCANPLUS_ENCRYPTED_MAINTENANCE': '1'}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(factory), 2)
        factory.assert_not_called()

    def test_explicit_cleanup_closes_store_and_reports_count(self):
        store = Mock(); store.prune.return_value = 3
        output = io.StringIO()
        with patch.dict(os.environ, SCANPLUS_ENCRYPTED_MAINTENANCE='1', SCANPLUS_RELEASE_PROFILE='sandbox'), contextlib.redirect_stdout(output):
            self.assertEqual(main(lambda: store), 0)
        store.prune.assert_called_once(); store.close.assert_called_once()
        self.assertEqual(output.getvalue(), 'Expired encrypted rows removed: 3\n')

    def test_failure_redacts_exception_and_closes_store(self):
        store = Mock(); store.prune.side_effect = ValueError('private synthetic credential must not appear')
        output = io.StringIO()
        with patch.dict(os.environ, SCANPLUS_ENCRYPTED_MAINTENANCE='1', SCANPLUS_RELEASE_PROFILE='sandbox'), contextlib.redirect_stdout(output):
            self.assertEqual(main(lambda: store), 1)
        store.close.assert_called_once()
        self.assertNotIn('private synthetic credential', output.getvalue())
