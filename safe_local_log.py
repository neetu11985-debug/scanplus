"""Owner-private, bounded local activity log with a fixed schema only."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import threading

MAX_LOG_BYTES = 1024 * 1024
EVENTS = frozenset(('server_started', 'server_stopped', 'session_read', 'sms_start',
                   'code_check', 'search', 'session_clear', 'listing_review',
                   'report_read', 'report_export', 'page_read', 'unknown_route'))
PHASES = frozenset(('entry', 'code', 'verified', 'report', 'start_uncertain', 'scanning'))


def safe_record(event, *, local_status=None, provider_status=None, twilio_error_code=None, phase=None):
    if not isinstance(event, str) or event not in EVENTS:
        return None
    result = {'time_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'event': event}
    for name, value in (('local_http_status', local_status), ('provider_http_status', provider_status)):
        if type(value) is int and 100 <= value <= 599:
            result[name] = value
    if (type(provider_status) is int and 300 <= provider_status <= 599
            and type(twilio_error_code) is int and 1 <= twilio_error_code <= 999999):
        result['twilio_error_code'] = twilio_error_code
    if isinstance(phase, str) and phase in PHASES:
        result['phase'] = phase
    return result


class SafeLocalLog:
    """No payloads, request paths, phone, codes, credentials or exception text."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def write(self, event, **fields):
        fd = None
        try:
            record = safe_record(event, **fields)
            if record is None:
                return False
            raw = (json.dumps(record, separators=(',', ':')) + '\n').encode('utf-8')
            with self.lock:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                parent = self.path.parent.lstat()
                if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid():
                    return False
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size + len(raw) > MAX_LOG_BYTES):
                    return False
                return os.write(fd, raw) == len(raw)
        except Exception:
            # Logging failure must not disclose the exception or alter app behavior.
            return False
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


def format_safe_line(line):
    """The viewer also validates every field, never prints raw file content."""
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return None
        stamp = datetime.fromisoformat(data.get('time_utc', ''))
        if stamp.tzinfo is None:
            return None
        record = safe_record(data.get('event'), local_status=data.get('local_http_status'),
                             provider_status=data.get('provider_http_status'),
                             twilio_error_code=data.get('twilio_error_code'), phase=data.get('phase'))
        if record is None:
            return None
        record['time_utc'] = stamp.astimezone(timezone.utc).isoformat(timespec='seconds')
        return ' | '.join(str(record[key]) if key in ('time_utc', 'event') else key + '=' + str(record[key])
                          for key in record)
    except Exception:
        return None
