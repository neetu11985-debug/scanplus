"""Encrypted, local backend storage. Callers must authenticate before using this service.

Keys are injected from an owner-managed secret store, never stored in SQLite. This
module performs no network calls. Credential reads are for trusted provider code,
not an admin HTTP response. Phone reads require the authenticated owner's opaque ID.

Rotation: retain old version keys, call rotate(new_version, new_key), then update
all application instances' injected keyrings before retiring old keys. Rotation is
atomic locally; coordinate a maintenance window across processes. Backups require
their historical keys. Deletion cannot erase older backups or filesystem snapshots.

Migration: create a fresh encrypted database; explicitly import only authorized
plaintext records through these APIs, verify, and retire old stores/backups per
retention policy. Existing synthetic hashes cannot be reversed into phone numbers;
do not invent a migration or copy weak hashes as lookup indexes.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock
import time
import uuid

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class SecureStorageError(Exception):
    """A deliberately non-secret-bearing storage failure."""


def canonical_phone(value):
    """Accept only already canonical E.164 syntax; no country/format guessing.

    The project accepts 8–15 digits. Syntax does not prove allocation or ownership.
    """
    if not isinstance(value, str) or not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
        raise SecureStorageError('Invalid phone format')
    return value


def _label(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise SecureStorageError('Invalid identifier')
    return value


def _key(version, key):
    if type(version) is not int or version < 1 or not isinstance(key, bytes) or len(key) != 32:
        raise SecureStorageError('Encryption configuration unavailable')
    return key


def _json(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False).encode()


def _private_database_path(path):
    """Fail closed on unsafe local paths; never chmod existing user files.

    The private containing directory prevents other OS users swapping the file
    between the no-follow open and SQLite's path-based open. Same-user hostile
    processes and privileged OS users remain outside this boundary.
    """
    path = Path(os.path.abspath(path))
    parent = path.parent
    for directory in reversed((parent, *parent.parents)):
        try:
            info = directory.lstat()
        except FileNotFoundError:
            directory.mkdir(mode=0o700)
            info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise SecureStorageError('Secure storage unavailable')
    info = parent.lstat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise SecureStorageError('Secure storage unavailable')

    def check_file(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise SecureStorageError('Secure storage unavailable')

    for candidate in (path, *(Path(str(path) + suffix) for suffix in ('-journal', '-wal', '-shm'))):
        try:
            check_file(candidate.lstat())
        except FileNotFoundError:
            pass
    # O_NONBLOCK prevents a raced FIFO from blocking; fstat then rejects it.
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        check_file(os.fstat(fd))
    finally:
        os.close(fd)
    return str(path)


class EncryptedStore:
    """Trusted backend API; do not expose this object to untrusted callers.

    Production callers must use put_paid_bundle after independently verifying a
    completed payment; standalone put_phone/put_report are trusted internal APIs.
    owner_id must be taken from an authenticated session, never a request field.
    Credential APIs require separate application-level admin/service authorization.
    Do not log arguments, decrypted results, or raw database exceptions.
    """
    def __init__(self, path, keys, active_version, clock=time.time):
        self._lock = RLock()
        self._clock = clock
        self._keys = {}
        if not isinstance(keys, dict) or not keys:
            raise SecureStorageError('Encryption configuration unavailable')
        for version, key in keys.items():
            _key(version, key)
            self._keys[version] = self._derive(key)
        if type(active_version) is not int or active_version not in self._keys:
            raise SecureStorageError('Encryption configuration unavailable')
        self._active = active_version
        self._ready = False
        self.path = str(path)
        self._conn = None
        try:
            if self.path != ':memory:':
                self.path = _private_database_path(self.path)
            self._conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            self._conn.execute('PRAGMA secure_delete=ON')
            self._conn.execute('PRAGMA journal_mode=DELETE')
            with self._transaction():
                existing = {row[0] for row in self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if existing - {'encrypted_records'}:
                    # Never silently mix encrypted records into a legacy plaintext DB.
                    raise SecureStorageError('Secure storage unavailable')
                self._conn.execute('''CREATE TABLE IF NOT EXISTS encrypted_records (
                    purpose TEXT NOT NULL, id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    lookup BLOB NOT NULL, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL,
                    UNIQUE(purpose, lookup))''')
                rows = self._rows()
                if rows:
                    for row in rows:
                        self._open(row)  # Fail closed on missing/wrong keys or tampered rows.
                    self._verify_marker(self._marker())
                else:
                    self._save('key_check', 'key-check', {'marker': 'scanplus-v1', 'expires': None})
            self._ready = True
        except Exception:
            if self._conn is not None:
                self._conn.close()
            raise SecureStorageError('Secure storage unavailable') from None

    @staticmethod
    def _derive(master):
        def derive(purpose):
            return HKDF(algorithm=hashes.SHA256(), length=32,
                        salt=b'scanplus-storage-v1', info=purpose).derive(master)
        return (derive(b'encryption-aesgcm'), derive(b'blind-index-hmac'))

    @contextmanager
    def _transaction(self):
        with self._lock:
            try:
                self._conn.execute('BEGIN IMMEDIATE')
                if self._ready:
                    self._verify_marker(self._marker())
                yield
                self._conn.commit()
            except BaseException as error:
                self._conn.rollback()
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise SecureStorageError('Secure storage unavailable') from None

    def _marker(self):
        return self._conn.execute(
            "SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records "
            "WHERE purpose='key_check' AND id='key-check'").fetchone()

    def _verify_marker(self, row):
        # Validate under the database write lock, not merely on startup. A stale
        # process must not write old blind indexes after another process rotates.
        # Only rotate() may change the active database version atomically.
        if (row is None or row[2] != self._active
                or self._open(row) != {'marker': 'scanplus-v1', 'expires': None}):
            raise SecureStorageError('Secure storage unavailable')
        versions = self._conn.execute('SELECT DISTINCT version FROM encrypted_records').fetchall()
        if {version[0] for version in versions} != {self._active}:
            raise SecureStorageError('Secure storage unavailable')

    def _rows(self):
        return self._conn.execute('SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records').fetchall()

    def _lookup(self, purpose, data, version):
        if purpose == 'phone':
            material = [purpose, data['owner'], data['phone']]
        elif purpose == 'payment_claim':
            material = [purpose, data['owner'], data['payment_ref']]
        elif purpose == 'report':
            material = [purpose, data['owner'], data['report_id']]
        elif purpose == 'credential':
            material = [purpose, data['name']]
        else:
            material = [purpose]
        return hmac.new(self._keys[version][1], _json(material), hashlib.sha256).digest()

    @staticmethod
    def _aad(purpose, record_id, version, lookup):
        return _json(['scanplus-storage-v1', purpose, record_id, version, lookup.hex()])

    def _open(self, row):
        purpose, record_id, version, lookup, nonce, ciphertext = row
        try:
            raw = AESGCM(self._keys[version][0]).decrypt(
                nonce, ciphertext, self._aad(purpose, record_id, version, lookup))
            data = json.loads(raw)
            if not hmac.compare_digest(lookup, self._lookup(purpose, data, version)):
                raise ValueError()
            return data
        except (InvalidTag, KeyError, ValueError, TypeError, UnicodeError):
            raise SecureStorageError('Secure storage unavailable') from None

    def _save(self, purpose, record_id, data):
        version = self._active
        lookup = self._lookup(purpose, data, version)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[version][0]).encrypt(
            nonce, _json(data), self._aad(purpose, record_id, version, lookup))
        self._conn.execute('''INSERT INTO encrypted_records VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET version=excluded.version, lookup=excluded.lookup,
            nonce=excluded.nonce, ciphertext=excluded.ciphertext''',
            (purpose, record_id, version, lookup, nonce, ciphertext))

    def _expiry(self, value, optional=False):
        if optional and value is None:
            return None
        if type(value) not in (float, int) or not math.isfinite(value) or value <= self._clock():
            raise SecureStorageError('Invalid expiration')
        return float(value)

    def _alive(self, data):
        return data['expires'] is None or data['expires'] > self._clock()

    def _find(self, purpose, data):
        for version in self._keys:
            lookup = self._lookup(purpose, data, version)
            row = self._conn.execute('''SELECT purpose,id,version,lookup,nonce,ciphertext
                FROM encrypted_records WHERE purpose=? AND lookup=?''', (purpose, lookup)).fetchone()
            if row:
                return row, self._open(row)
        return None, None

    def put_paid_bundle(self, owner_id, payment_ref, phone, text, expires_at):
        """Atomically persist verified-paid data. This API does NOT verify payment.

        The caller must validate payment completion, amount, purpose, and ownership
        with a trusted payment verifier before calling. Matching replays preserve
        the original report and expiry. Claims expire alongside user data: callers
        must reject stale payment reuse after retention/pruning with their payment
        verifier. Do not expose this method directly to arbitrary request data.
        """
        owner_id = _label(owner_id)
        payment_ref = _label(payment_ref)
        phone = canonical_phone(phone)
        expiry = self._expiry(expires_at)
        if not isinstance(text, str) or not text or len(text.encode()) > 2 * 1024 * 1024:
            raise SecureStorageError('Invalid report')
        claim = {'owner': owner_id, 'payment_ref': payment_ref}
        # This fingerprint is inside authenticated ciphertext, never an index.
        fingerprint = hashlib.sha256(_json([phone, text])).hexdigest()
        with self._transaction():
            row, previous = self._find('payment_claim', claim)
            if row:
                if not self._alive(previous) or not hmac.compare_digest(previous['fingerprint'], fingerprint):
                    raise SecureStorageError('Secure storage unavailable')
                report_row = self._conn.execute(
                    "SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records WHERE purpose='report' AND id=?",
                    (previous['report_id'],)).fetchone()
                if not report_row:
                    raise SecureStorageError('Secure storage unavailable')
                report = self._open(report_row)
                if report['owner'] != owner_id or not self._alive(report):
                    raise SecureStorageError('Secure storage unavailable')
                return previous['report_id']
            phone_data = {'owner': owner_id, 'phone': phone, 'expires': expiry}
            phone_row, old_phone = self._find('phone', phone_data)
            if phone_row:
                # A second valid purchase must not shorten a prior paid retention.
                phone_data['expires'] = max(old_phone['expires'], expiry)
            self._save('phone', phone_row[1] if phone_row else str(uuid.uuid4()), phone_data)
            report_id = str(uuid.uuid4())
            self._save('report', report_id, {'owner': owner_id, 'text': text,
                       'report_id': report_id, 'expires': expiry})
            claim.update({'report_id': report_id, 'fingerprint': fingerprint, 'expires': expiry})
            self._save('payment_claim', str(uuid.uuid4()), claim)
            return report_id

    def put_phone(self, owner_id, phone, expires_at):
        data = {'owner': _label(owner_id), 'phone': canonical_phone(phone),
                'expires': self._expiry(expires_at)}
        with self._transaction():
            row, _ = self._find('phone', data)
            record_id = row[1] if row else str(uuid.uuid4())
            self._save('phone', record_id, data)
            return record_id

    def get_phone(self, record_id, owner_id):
        _label(record_id)
        _label(owner_id)
        with self._transaction():
            row = self._conn.execute('''SELECT purpose,id,version,lookup,nonce,ciphertext
                FROM encrypted_records WHERE purpose='phone' AND id=?''', (record_id,)).fetchone()
            if not row:
                return None
            data = self._open(row)
            if not self._alive(data):
                self._conn.execute('DELETE FROM encrypted_records WHERE id=?', (record_id,))
                return None
            return data['phone'] if hmac.compare_digest(data['owner'].encode(), owner_id.encode()) else None

    def find_phone(self, owner_id, phone):
        data = {'owner': _label(owner_id), 'phone': canonical_phone(phone)}
        with self._transaction():
            row, payload = self._find('phone', data)
            return row[1] if row and self._alive(payload) else None

    def delete_phone(self, record_id, owner_id):
        _label(record_id)
        _label(owner_id)
        with self._transaction():
            row = self._conn.execute('''SELECT purpose,id,version,lookup,nonce,ciphertext
                FROM encrypted_records WHERE purpose='phone' AND id=?''', (record_id,)).fetchone()
            if not row or self._open(row)['owner'] != owner_id:
                return False
            self._conn.execute('DELETE FROM encrypted_records WHERE id=?', (record_id,))
            return True

    def put_report(self, owner_id, text, expires_at):
        if not isinstance(text, str) or not text or len(text.encode()) > 2 * 1024 * 1024:
            raise SecureStorageError('Invalid report')
        record_id = str(uuid.uuid4())
        data = {'owner': _label(owner_id), 'text': text, 'report_id': record_id,
                'expires': self._expiry(expires_at)}
        with self._transaction():
            self._save('report', record_id, data)
        return record_id

    def get_report(self, report_id, owner_id):
        _label(report_id)
        _label(owner_id)
        with self._transaction():
            row = self._conn.execute("SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records WHERE purpose='report' AND id=?", (report_id,)).fetchone()
            if not row:
                return None
            data = self._open(row)
            if not self._alive(data):
                self._conn.execute('DELETE FROM encrypted_records WHERE id=?', (report_id,))
                return None
            return data['text'] if hmac.compare_digest(data['owner'].encode(), owner_id.encode()) else None

    def delete_report(self, report_id, owner_id):
        _label(report_id)
        _label(owner_id)
        with self._transaction():
            row = self._conn.execute("SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records WHERE purpose='report' AND id=?", (report_id,)).fetchone()
            if not row or self._open(row)['owner'] != owner_id:
                return False
            self._conn.execute('DELETE FROM encrypted_records WHERE id=?', (report_id,))
            return True

    def put_credential(self, name, value, expires_at=None):
        if not isinstance(value, str) or not value or len(value) > 65536:
            raise SecureStorageError('Invalid credential')
        data = {'name': _label(name), 'value': value, 'expires': self._expiry(expires_at, optional=True)}
        with self._transaction():
            row, _ = self._find('credential', data)
            self._save('credential', row[1] if row else str(uuid.uuid4()), data)

    def get_credential(self, name):
        """Trusted service use only. Never return this value through an admin UI."""
        with self._transaction():
            row, data = self._find('credential', {'name': _label(name)})
            return data['value'] if row and self._alive(data) else None

    def list_credential_names(self):
        with self._transaction():
            return sorted(data['name'] for row in self._rows() if row[0] == 'credential'
                          for data in [self._open(row)] if self._alive(data))

    def delete_credential(self, name):
        with self._transaction():
            row, _ = self._find('credential', {'name': _label(name)})
            if row:
                self._conn.execute('DELETE FROM encrypted_records WHERE id=?', (row[1],))
            return bool(row)

    def prune(self):
        with self._transaction():
            ids = [(row[1],) for row in self._rows() if not self._alive(self._open(row))]
            self._conn.executemany('DELETE FROM encrypted_records WHERE id=?', ids)
            return len(ids)

    def rotate(self, new_version, new_key):
        """Atomically re-encrypt and re-index all records. Caller persists new key externally."""
        _key(new_version, new_key)
        if new_version in self._keys:
            raise SecureStorageError('Encryption version already exists')
        with self._lock:
            old_version = self._active
            try:
                with self._transaction():
                    records = [(row, self._open(row)) for row in self._rows()]
                    self._keys[new_version] = self._derive(new_key)
                    self._active = new_version
                    for row, data in records:
                        self._save(row[0], row[1], data)
            except BaseException:
                self._active = old_version
                self._keys.pop(new_version, None)
                raise

    def close(self):
        with self._lock:
            self._conn.close()
