"""Opt-in, bounded local test diagnostics. Never accepts raw exception text."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import stat
import threading

from search_diagnostics import search_diagnostic

MAX_LOG_BYTES = 64 * 1024


class DiagnosticLogError(ValueError):
    pass


class LocalDiagnosticLog:
    """Append only, owner-only, no symlinks. Stop at 64 KiB; never rotate/delete."""
    def __init__(self, path):
        self.path = Path(path)
        self.status = 'ready'
        self.lock = threading.Lock()
        try:
            fd = self._open()
            try:
                if os.fstat(fd).st_size >= MAX_LOG_BYTES:
                    self.status = 'full'
            finally:
                os.close(fd)
        except (OSError, ValueError):
            raise DiagnosticLogError('The private diagnostic log could not be opened safely. No test was started.') from None

    def _open(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError('Unsafe log file.')
            return fd
        except BaseException:
            os.close(fd)
            raise

    def record(self, diagnostic, *, scan_number, query_attempt):
        diagnostic = diagnostic if isinstance(diagnostic, dict) else {}
        safe = search_diagnostic(diagnostic.get('category'), diagnostic.get('http_status'))
        counter = lambda value, limit: value if type(value) is int and 1 <= value <= limit else None
        record = {'event': 'serper_request_failed',
                  'time_utc': datetime.now(timezone.utc).isoformat(),
                  'category': safe['category'], 'http_status': safe['http_status'],
                  'scan_number': counter(scan_number, 5), 'query_attempt': counter(query_attempt, 15)}
        raw = (json.dumps(record, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')
        with self.lock:
            if self.status != 'ready':
                return False
            try:
                fd = self._open()
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    if os.fstat(fd).st_size + len(raw) > MAX_LOG_BYTES:
                        self.status = 'full'
                        return False
                    if os.write(fd, raw) != len(raw):
                        self.status = 'unavailable'
                        return False
                finally:
                    os.close(fd)
            except (OSError, ValueError):
                self.status = 'unavailable'
                return False
        return True
