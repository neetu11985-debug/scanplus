"""Synthetic-only storage security checks; not live-provider/deployment evidence."""
import concurrent.futures
import hashlib
import os
import stat
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from encrypted_storage import EncryptedStore, SecureStorageError, canonical_phone

# Deliberately public fixture keys, never production secrets.
KEY = bytes(range(32))
NEXT_KEY = bytes(range(32, 64))
PHONE = '+12025550123'
OTHER_PHONE = '+12025550124'
OWNER = 'synthetic-owner-alpha'


class EncryptedStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.path = Path(self.tmp.name) / 'secure.sqlite'
        self.now = 1000.0
        self.store = self.open()

    def open(self, keys=None, active=1):
        return EncryptedStore(self.path, {1: KEY} if keys is None else keys, active,
                              clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def rows(self, purpose='phone'):
        with sqlite3.connect(self.path) as conn:
            return conn.execute('SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records WHERE purpose=?', (purpose,)).fetchall()

    def mutate(self, sql, params=()):
        with sqlite3.connect(self.path) as conn:
            conn.execute(sql, params)

    def test_disk_contains_no_plaintext_phone_owner_credentials_report_or_expiry(self):
        self.store.put_phone(OWNER, PHONE, 1234567890123)
        self.store.put_credential('fixture-provider', 'synthetic-secret-only')
        self.store.put_report(OWNER, 'Private fixture report ' + PHONE, 1234567890123)
        disk = self.path.read_bytes()
        for value in (PHONE, PHONE[1:], OWNER, 'synthetic-secret-only', 'fixture-provider',
                      'Private fixture report', '1234567890123'):
            self.assertNotIn(value.encode(), disk)
        self.assertNotIn(hashlib.sha256(PHONE.encode()).digest(), disk)

    def test_randomized_ciphertext_and_owner_scoped_blind_lookup(self):
        record = self.store.put_phone(OWNER, PHONE, 2000)
        before = self.rows()[0]
        self.assertEqual(record, self.store.put_phone(OWNER, PHONE, 2000))
        after = self.rows()[0]
        self.assertEqual(before[3], after[3])
        self.assertNotEqual(before[4:], after[4:])
        other = self.store.put_phone('different-owner', PHONE, 2000)
        self.assertNotEqual(record, other)
        self.assertNotEqual(self.rows()[0][3], self.rows()[1][3])
        self.assertEqual(self.store.find_phone(OWNER, PHONE), record)
        self.assertIsNone(self.store.find_phone('unknown', PHONE))
        self.assertIsNone(self.store.get_phone(record, 'different-owner'))
        self.assertFalse(self.store.delete_phone(record, 'different-owner'))

    def test_restart_and_credentials(self):
        record = self.store.put_phone(OWNER, PHONE, 2000)
        self.store.put_credential('synthetic-api', 'fixture-value')
        self.store.close()
        self.store = self.open()
        self.assertEqual(PHONE, self.store.get_phone(record, OWNER))
        self.assertEqual(['synthetic-api'], self.store.list_credential_names())
        self.assertEqual('fixture-value', self.store.get_credential('synthetic-api'))
        self.store.put_credential('synthetic-api', 'fixture-replacement')
        self.assertEqual('fixture-replacement', self.store.get_credential('synthetic-api'))
        self.assertTrue(self.store.delete_credential('synthetic-api'))
        self.assertIsNone(self.store.get_credential('synthetic-api'))

    def test_missing_wrong_and_invalid_keys_fail_closed(self):
        self.store.put_phone(OWNER, PHONE, 2000)
        for keys, active in (({}, 1), ({1: b'short'}, 1), ({1: NEXT_KEY}, 1),
                             ({2: NEXT_KEY}, 2), ({1: KEY}, 2), ({True: KEY}, 1)):
            with self.subTest(keys=list(keys), active=active):
                with self.assertRaises(SecureStorageError) as exc:
                    self.open(keys, active)
                self.assertNotIn(PHONE, str(exc.exception))

    def test_expiry_prune_and_delete(self):
        record = self.store.put_phone(OWNER, PHONE, 1001)
        self.store.put_credential('synthetic-api', 'fixture-value', 1001)
        self.now = 1001
        self.assertIsNone(self.store.find_phone(OWNER, PHONE))
        self.assertIsNone(self.store.get_credential('synthetic-api'))
        self.assertEqual(2, self.store.prune())
        self.assertIsNone(self.store.get_phone(record, OWNER))
        record = self.store.put_phone(OWNER, PHONE, 2000)
        self.assertTrue(self.store.delete_phone(record, OWNER))
        self.assertFalse(self.store.delete_phone(record, OWNER))
        record = self.store.put_phone(OWNER, PHONE, 2000)
        self.now = 2000
        self.assertIsNone(self.store.get_phone(record, OWNER))
        self.assertEqual([], self.rows())

    def test_e164_and_expiry_validation(self):
        self.assertEqual(PHONE, canonical_phone(PHONE))
        for value in ('2025550123', '+02025550123', '+1 2025550123', '+12025550123\n',
                      '+1234567890123456', '+12', '+1234567', None, 123):
            with self.subTest(value=value), self.assertRaises(SecureStorageError):
                self.store.put_phone(OWNER, value, 2000)
        for expiry in (None, float('nan'), float('inf'), -1, True, 999):
            with self.subTest(expiry=expiry), self.assertRaises(SecureStorageError):
                self.store.put_phone(OWNER, PHONE, expiry)

    def test_tamper_ciphertext_and_context_swap(self):
        a = self.store.put_phone(OWNER, PHONE, 2000)
        b = self.store.put_phone(OWNER, OTHER_PHONE, 2000)
        rows = {row[1]: row for row in self.rows()}
        self.mutate('UPDATE encrypted_records SET nonce=?,ciphertext=? WHERE id=?',
                    (rows[b][4], rows[b][5], a))
        with self.assertRaises(SecureStorageError):
            self.store.get_phone(a, OWNER)
        with self.assertRaises(SecureStorageError):
            self.open()

    def test_tamper_authenticated_purpose_version_and_index(self):
        record = self.store.put_phone(OWNER, PHONE, 2000)
        row = self.rows()[0]
        for field, value in (('purpose', 'credential'), ('version', 2), ('lookup', b'x'*32),
                             ('ciphertext', bytes([row[5][0] ^ 1]) + row[5][1:])):
            with self.subTest(field=field):
                self.mutate('UPDATE encrypted_records SET '+field+'=? WHERE id=?', (value, record))
                with self.assertRaises(SecureStorageError):
                    self.store.prune()
                self.mutate('UPDATE encrypted_records SET purpose=?,version=?,lookup=?,ciphertext=? WHERE id=?',
                            (row[0], row[2], row[3], row[5], record))

    def test_reports_require_owner_and_expire(self):
        report = 'Synthetic text report\n' + PHONE
        report_id = self.store.put_report(OWNER, report, 2000)
        self.assertEqual(report, self.store.get_report(report_id, OWNER))
        self.assertIsNone(self.store.get_report(report_id, 'other'))
        self.assertFalse(self.store.delete_report(report_id, 'other'))
        self.assertIsNone(self.store.get_phone(report_id, OWNER))
        self.now = 2000
        self.assertIsNone(self.store.get_report(report_id, OWNER))
        self.assertEqual([], self.rows('report'))
        report_id = self.store.put_report(OWNER, report, 3000)
        self.assertTrue(self.store.delete_report(report_id, OWNER))
        self.assertIsNone(self.store.get_report(report_id, OWNER))

    def test_rotation_reencrypts_and_reindexes_with_new_only_restart(self):
        record = self.store.put_phone(OWNER, PHONE, 2000)
        report = self.store.put_report(OWNER, 'Synthetic report', 2000)
        self.store.put_credential('fixture', 'secret-fixture')
        before = self.rows()[0]
        self.store.rotate(2, NEXT_KEY)
        after = self.rows()[0]
        self.assertEqual(2, after[2])
        self.assertNotEqual(before[3:], after[3:])
        self.assertEqual(record, self.store.find_phone(OWNER, PHONE))
        self.store.close()
        self.store = self.open({2: NEXT_KEY}, 2)
        self.assertEqual(PHONE, self.store.get_phone(record, OWNER))
        self.assertEqual('Synthetic report', self.store.get_report(report, OWNER))
        self.assertEqual('secret-fixture', self.store.get_credential('fixture'))
        with self.assertRaises(SecureStorageError):
            self.open({1: KEY}, 1)

    def test_active_version_change_requires_atomic_rotation(self):
        self.store.put_phone(OWNER, PHONE, 2000)
        with self.assertRaises(SecureStorageError):
            self.open({1: KEY, 2: NEXT_KEY}, 2)
        self.assertEqual({1}, {row[2] for row in self.store._rows()})

    def test_stale_writer_cannot_replay_paid_bundle_after_rotation(self):
        stale = self.open()
        try:
            report = self.store.put_paid_bundle(OWNER, 'fixture-payment', PHONE, 'Synthetic', 2000)
            self.store.rotate(2, NEXT_KEY)
            before = self.store._rows()
            for operation in (
                    lambda: stale.put_paid_bundle(OWNER, 'fixture-payment', PHONE, 'Synthetic', 2000),
                    lambda: stale.put_phone(OWNER, OTHER_PHONE, 2000),
                    lambda: stale.get_report(report, OWNER),
                    lambda: stale.rotate(3, b'Z' * 32)):
                with self.assertRaises(SecureStorageError):
                    operation()
                self.assertEqual(before, self.store._rows())
            reopened = self.open({2: NEXT_KEY}, 2)
            try:
                self.assertEqual(report, reopened.put_paid_bundle(
                    OWNER, 'fixture-payment', PHONE, 'Synthetic', 2000))
            finally:
                reopened.close()
        finally:
            stale.close()

    def test_marker_deleted_after_open_blocks_writes(self):
        self.mutate("DELETE FROM encrypted_records WHERE purpose='key_check'")
        with self.assertRaises(SecureStorageError):
            self.store.put_phone(OWNER, PHONE, 2000)
        self.assertEqual([], self.rows())

    def test_failed_rotation_rolls_back_every_record_and_key_state(self):
        record = self.store.put_phone(OWNER, PHONE, 2000)
        before = self.rows()
        original = self.store._save
        calls = []
        def fail_second(*args):
            calls.append(args)
            if len(calls) == 2:
                raise OSError('synthetic injected failure')
            return original(*args)
        with patch.object(self.store, '_save', side_effect=fail_second):
            with self.assertRaises(SecureStorageError):
                self.store.rotate(2, NEXT_KEY)
        self.assertEqual(before, self.rows())
        self.assertEqual(PHONE, self.store.get_phone(record, OWNER))
        self.store.rotate(2, NEXT_KEY)  # Failed key was not retained.

    def test_failed_write_does_not_commit_and_next_write_succeeds(self):
        original = self.store._save
        def fail_after_insert(*args):
            original(*args)
            raise ValueError('fixture only')
        with patch.object(self.store, '_save', side_effect=fail_after_insert):
            with self.assertRaises(SecureStorageError):
                self.store.put_phone(OWNER, PHONE, 2000)
        self.assertEqual([], self.rows())
        self.assertIsNotNone(self.store.put_phone(OWNER, PHONE, 2000))

    def test_legacy_database_requires_explicit_migration(self):
        legacy = Path(self.tmp.name) / 'legacy.sqlite'
        with sqlite3.connect(legacy) as conn:
            conn.execute('CREATE TABLE records (data TEXT)')
            conn.execute('INSERT INTO records VALUES (?)', ('synthetic-hash-only',))
        legacy.chmod(0o600)
        with self.assertRaises(SecureStorageError):
            EncryptedStore(legacy, {1: KEY}, 1)
        with sqlite3.connect(legacy) as conn:
            self.assertEqual([('records',)], conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())

    def test_file_path_rejects_symlinks_hardlinks_nonregular_and_open_modes(self):
        target = Path(self.tmp.name) / 'target'
        target.write_bytes(b'fixture-only')
        target.chmod(0o600)
        symlink = Path(self.tmp.name) / 'symlink.sqlite'
        symlink.symlink_to(target)
        hardlink = Path(self.tmp.name) / 'hardlink.sqlite'
        os.link(target, hardlink)
        fifo = Path(self.tmp.name) / 'fifo.sqlite'
        os.mkfifo(fifo, 0o600)
        directory = Path(self.tmp.name) / 'directory.sqlite'
        directory.mkdir(mode=0o700)
        public = Path(self.tmp.name) / 'public.sqlite'
        public.write_bytes(b'')
        public.chmod(0o640)
        for path in (symlink, hardlink, fifo, directory, public):
            with self.subTest(path=path.name), self.assertRaises(SecureStorageError):
                EncryptedStore(path, {1: KEY}, 1)
        self.assertEqual(0o640, stat.S_IMODE(public.stat().st_mode))
        self.assertEqual(b'fixture-only', target.read_bytes())

    def test_parent_must_be_private_and_not_symlink(self):
        public_dir = Path(self.tmp.name) / 'public'
        public_dir.mkdir(mode=0o755)
        public_dir.chmod(0o755)
        with self.assertRaises(SecureStorageError):
            EncryptedStore(public_dir / 'data.sqlite', {1: KEY}, 1)
        self.assertFalse((public_dir / 'data.sqlite').exists())
        linked_dir = Path(self.tmp.name) / 'linked'
        linked_dir.symlink_to(Path(self.tmp.name), target_is_directory=True)
        with self.assertRaises(SecureStorageError):
            EncryptedStore(linked_dir / 'data.sqlite', {1: KEY}, 1)
        fresh = Path(self.tmp.name) / 'fresh' / 'nested' / 'data.sqlite'
        with_store = EncryptedStore(fresh, {1: KEY}, 1)
        with_store.close()
        self.assertEqual(0o700, stat.S_IMODE(fresh.parent.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(fresh.parent.parent.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(fresh.stat().st_mode))

    def test_unsafe_journal_symlink_is_rejected(self):
        path = Path(self.tmp.name) / 'fresh.sqlite'
        target = Path(self.tmp.name) / 'journal-target'
        target.write_text('synthetic-data')
        Path(str(path) + '-journal').symlink_to(target)
        with self.assertRaises(SecureStorageError):
            EncryptedStore(path, {1: KEY}, 1)
        self.assertEqual('synthetic-data', target.read_text())

    def test_report_restart_missing_owner_and_encrypted_disk(self):
        text = 'Synthetic report text: ' + PHONE
        report_id = self.store.put_report(OWNER, text, 2000)
        self.store.close()
        self.store = self.open()
        self.assertEqual(text, self.store.get_report(report_id, OWNER))
        self.assertIsNone(self.store.get_report('missing-report-id', OWNER))
        self.assertIsNone(self.store.get_report(report_id, 'wrong-owner'))
        with self.assertRaises(SecureStorageError):
            self.store.get_report(report_id, None)
        self.assertNotIn(text.encode(), self.path.read_bytes())
        self.now = 2000
        self.assertIsNone(self.store.get_report(report_id, OWNER))

    def test_paid_bundle_atomic_replay_across_restart_and_conflicts(self):
        payment_ref = 'synthetic-payment-reference'
        text = 'Synthetic paid report ' + PHONE
        report_id = self.store.put_paid_bundle(OWNER, payment_ref, PHONE, text, 2000)
        self.assertEqual(text, self.store.get_report(report_id, OWNER))
        self.assertEqual(1, len(self.rows('phone')))
        self.assertEqual(1, len(self.rows('report')))
        self.assertEqual(1, len(self.rows('payment_claim')))
        self.assertNotIn(payment_ref.encode(), self.path.read_bytes())
        self.store.close()
        self.store = self.open()
        self.assertEqual(report_id, self.store.put_paid_bundle(OWNER, payment_ref, PHONE, text, 2500))
        for phone, report_text in ((OTHER_PHONE, text), (PHONE, 'Different synthetic report')):
            with self.assertRaises(SecureStorageError):
                self.store.put_paid_bundle(OWNER, payment_ref, phone, report_text, 2000)
        self.assertEqual(1, len(self.rows('report')))
        self.assertIsNone(self.store.get_report(report_id, 'wrong-owner'))
        self.store.rotate(2, NEXT_KEY)
        self.assertEqual(report_id, self.store.put_paid_bundle(OWNER, payment_ref, PHONE, text, 2500))
        self.now = 2000
        with self.assertRaises(SecureStorageError):
            self.store.put_paid_bundle(OWNER, payment_ref, PHONE, text, 2500)
        self.assertEqual(3, self.store.prune())  # Replay did not extend retention.

    def test_paid_bundle_failure_at_every_write_leaves_no_partial_data(self):
        original = self.store._save
        for failure_at in (1, 2, 3):
            calls = []
            def fail_after_insert(*args):
                calls.append(args)
                original(*args)
                if len(calls) == failure_at:
                    raise ValueError('synthetic failure')
            with patch.object(self.store, '_save', side_effect=fail_after_insert):
                with self.assertRaises(SecureStorageError):
                    self.store.put_paid_bundle(OWNER, 'synthetic-payment', PHONE, 'Synthetic text', 2000)
            for purpose in ('phone', 'report', 'payment_claim'):
                self.assertEqual([], self.rows(purpose))
        self.assertIsNotNone(self.store.put_paid_bundle(OWNER, 'synthetic-payment', PHONE, 'Synthetic text', 2000))

    def test_paid_bundle_concurrent_replay_is_idempotent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.store.put_paid_bundle(
                OWNER, 'synthetic-payment', PHONE, 'Synthetic report', 2000), range(12)))
        self.assertEqual(1, len(set(results)))
        for purpose in ('phone', 'report', 'payment_claim'):
            self.assertEqual(1, len(self.rows(purpose)))

    def test_threaded_writes_remain_atomic_and_unique(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.store.put_phone(OWNER, PHONE, 2000), range(12)))
        self.assertEqual(1, len(set(results)))
        self.assertEqual(1, len(self.rows()))


if __name__ == '__main__':
    unittest.main()
