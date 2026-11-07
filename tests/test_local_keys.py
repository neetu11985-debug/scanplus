"""Local properties tests use only generated fake values; no real key is read."""
import contextlib
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tool import local_keys

FAKE = {
    'SCANPLUS_LOCAL_LIVE_TEST': '0',
    'SCANPLUS_SEARCH_PROVIDER': 'serper',
    'SCANPLUS_LOCAL_LIVE_PORT': '4175',
    'TWILIO_ACCOUNT_SID': 'AC' + '0' * 32,
    'TWILIO_AUTH_TOKEN': 'synthetic-twilio-token',
    'TWILIO_VERIFY_SERVICE_SID': 'VA' + '1' * 32,
    'SERPER_API_KEY': 'synthetic-serper-key',
    'BRAVE_SEARCH_API_KEY': '',
}

def source(values=None):
    return '\n'.join(name + '=' + value for name, value in (FAKE if values is None else values).items()) + '\n'


class LocalKeysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scanplus-fake-properties-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'fake.properties'

    def write(self, text, mode=0o600):
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode('utf-8') if isinstance(text, str) else text)
        return self.path

    def assert_private_error(self, text, expected):
        self.write(text)
        with self.assertRaises(local_keys.ConfigurationError) as error:
            local_keys.read_properties(self.path)
        self.assertIn(expected, str(error.exception))
        self.assertNotIn('SECRET-SENTINEL', str(error.exception))

    def invoke(self, *args):
        output = io.StringIO()
        with patch.object(local_keys, 'DEFAULT_FILE', self.path), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = local_keys.main(list(args))
        for value in (FAKE['TWILIO_AUTH_TOKEN'], FAKE['SERPER_API_KEY'], FAKE['TWILIO_ACCOUNT_SID']):
            self.assertNotIn(value, output.getvalue())
        return result, output.getvalue()

    def test_simple_crlf_bom_comments_and_quotes(self):
        self.write('\ufeff# notes\r\n! other notes\r\n' + source().replace('synthetic-serper-key', '"synthetic-serper-key"').replace('\n', '\r\n'))
        self.assertEqual(local_keys.read_properties(self.path), FAKE)

    def test_literal_equals_hash_and_no_shell_expansion(self):
        self.write('SERPER_API_KEY=$(never-run-this)#literal=tail\n')
        with patch('subprocess.run', side_effect=AssertionError('must not execute')), patch('os.system', side_effect=AssertionError('must not execute')):
            self.assertEqual(local_keys.read_properties(self.path)['SERPER_API_KEY'], '$(never-run-this)#literal=tail')

    def test_rejects_duplicate_without_value(self):
        self.assert_private_error('SERPER_API_KEY=SECRET-SENTINEL\nSERPER_API_KEY=other', 'Duplicate')

    def test_rejects_unknown_without_name_or_value(self):
        self.assert_private_error('SECRET-SENTINEL=also-secret', 'Unknown')

    def test_rejects_malformed_without_value(self):
        self.assert_private_error('SECRET-SENTINEL', 'Expected')

    def test_rejects_smart_quotes(self):
        self.assert_private_error('SERPER_API_KEY=“SECRET-SENTINEL”', 'smart quotes')

    def test_rejects_unclosed_quotes(self):
        self.assert_private_error('SERPER_API_KEY="SECRET-SENTINEL', 'Unmatched')

    def test_rejects_whitespace_inside_value(self):
        self.assert_private_error('SERPER_API_KEY=SECRET-SENTINEL extra', 'spaces')

    def test_rejects_rich_text(self):
        self.assert_private_error(r'{\rtf1 SECRET-SENTINEL}', 'plain text')

    def test_rejects_non_utf8(self):
        self.write(b'\xff')
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'UTF-8'):
            local_keys.read_properties(self.path)

    def test_rejects_oversize(self):
        self.write('#' * (local_keys.MAX_BYTES + 1))
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'large'):
            local_keys.read_properties(self.path)

    def test_rejects_group_readable_file(self):
        self.write(source(), 0o644)
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'owner-only'):
            local_keys.read_properties(self.path)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o644)

    def test_accepts_readonly_owner_file(self):
        self.write(source(), 0o400)
        self.assertEqual(local_keys.read_properties(self.path), FAKE)

    def test_rejects_wrong_owner(self):
        self.write(source())
        with patch.object(local_keys.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(local_keys.ConfigurationError, 'belong to you'):
                local_keys.read_properties(self.path)

    def test_rejects_symlink(self):
        target = Path(self.temp.name) / 'target'
        target.write_text(source())
        self.path.symlink_to(target)
        with self.assertRaises(local_keys.ConfigurationError):
            local_keys.read_properties(self.path)

    def test_rejects_hardlink(self):
        self.write(source())
        os.link(self.path, Path(self.temp.name) / 'another-link')
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'not a link'):
            local_keys.read_properties(self.path)

    def test_rejects_fifo_without_waiting(self):
        os.mkfifo(self.path, 0o600)
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'special file'):
            local_keys.read_properties(self.path)

    def test_missing_file_error_is_generic(self):
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'Cannot open'):
            local_keys.read_properties(self.path)

    def test_offline_check_never_starts_server_or_calls_provider(self):
        self.write(source())
        with patch('local_live_server.serve', side_effect=AssertionError('no server')), patch('live_scan.HTTPSJSONTransport.request', side_effect=AssertionError('no provider')):
            code, output = self.invoke('--check')
        self.assertEqual(code, 0)
        self.assertIn('NOT verified', output)
        self.assertIn('still disabled', output)

    def test_default_action_is_offline_check(self):
        self.write(source())
        with patch('local_live_server.serve', side_effect=AssertionError('no server')):
            self.assertEqual(self.invoke()[0], 0)

    def test_start_disabled_and_environment_cannot_enable_it(self):
        self.write(source())
        with patch.dict(os.environ, {'SCANPLUS_LOCAL_LIVE_TEST': '1'}), patch('local_live_server.serve') as serve:
            code, output = self.invoke('--start')
            serve.assert_not_called()
        self.assertEqual(code, 1)
        self.assertIn('disabled', output)

    def test_explicit_start_passes_values_in_memory_without_environment_changes(self):
        values = dict(FAKE, SCANPLUS_LOCAL_LIVE_TEST='1', SCANPLUS_LOCAL_LIVE_PORT='4188')
        self.write(source(values))
        with patch.dict(os.environ, {'SERPER_API_KEY': 'unrelated-inherited-value'}, clear=True), patch('local_live_server.serve') as serve:
            self.assertEqual(self.invoke('--start')[0], 0)
            self.assertEqual(dict(os.environ), {'SERPER_API_KEY': 'unrelated-inherited-value'})
            settings, port = serve.call_args.args
            self.assertEqual(settings.serper_key, FAKE['SERPER_API_KEY'])
            self.assertEqual(port, 4188)
            self.assertNotIn(FAKE['SERPER_API_KEY'], repr(settings))

    def test_missing_key_does_not_fall_back_to_environment_or_brave(self):
        values = dict(FAKE, SERPER_API_KEY='', BRAVE_SEARCH_API_KEY='synthetic-other-key')
        self.write(source(values))
        with patch.dict(os.environ, {'SERPER_API_KEY': 'inherited-value'}):
            code, output = self.invoke('--check')
        self.assertEqual(code, 1)
        self.assertIn('SERPER_API_KEY', output)
        self.assertNotIn('inherited-value', output)

    def test_explicit_brave_selection(self):
        values = dict(FAKE, SCANPLUS_SEARCH_PROVIDER='brave', SERPER_API_KEY='', BRAVE_SEARCH_API_KEY='synthetic-brave')
        settings, port = local_keys.validate(values)
        self.assertEqual(settings.search_provider, 'brave')
        self.assertEqual(settings.brave_key, 'synthetic-brave')
        self.assertEqual(settings.serper_key, '')

    def test_invalid_flags_provider_sids_and_ports(self):
        for field, value in (('SCANPLUS_LOCAL_LIVE_TEST', 'yes'), ('SCANPLUS_SEARCH_PROVIDER', 'unknown'),
                             ('TWILIO_ACCOUNT_SID', 'bad'), ('TWILIO_VERIFY_SERVICE_SID', 'bad'),
                             ('SCANPLUS_LOCAL_LIVE_PORT', 'oops'), ('SCANPLUS_LOCAL_LIVE_PORT', '80'),
                             ('SCANPLUS_LOCAL_LIVE_PORT', '99999')):
            with self.subTest(field=field, value=value):
                with self.assertRaises(local_keys.ConfigurationError):
                    local_keys.validate(dict(FAKE, **{field: value}))

    def test_empty_template_remains_disabled_and_unconfigured(self):
        # Read only the shareable empty example, never the owner's private file.
        example = local_keys.ROOT / 'scanplus.local.properties.example'
        self.write(example.read_text())
        values = local_keys.read_properties(self.path)
        self.assertEqual(values['SCANPLUS_LOCAL_LIVE_TEST'], '0')
        for name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID', 'SERPER_API_KEY', 'BRAVE_SEARCH_API_KEY'):
            self.assertEqual(values[name], '')
        with self.assertRaisesRegex(local_keys.ConfigurationError, 'Fill in'):
            local_keys.validate(values)


if __name__ == '__main__':
    unittest.main()
