"""Read-only sanitized viewer. Never starts the app or makes network calls."""
import argparse
import os
from pathlib import Path
import stat
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from safe_local_log import MAX_LOG_BYTES, format_safe_line
PATH = ROOT / '.data' / 'scanmydigits-local.log'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--follow', action='store_true')
    args = parser.parse_args()
    position = 0
    identity = None
    waiting = False
    print('ScanMyDigits safe local activity log. Control-C stops this viewer, not the app.', flush=True)
    try:
        while True:
            fd = None
            try:
                fd = os.open(PATH, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_LOG_BYTES):
                    raise OSError()
                with os.fdopen(fd, 'rb') as stream:
                    fd = None
                    initial = identity != info.st_ino or info.st_size < position
                    if initial:
                        position = 0
                        identity = info.st_ino
                    stream.seek(position)
                    raw = stream.read(MAX_LOG_BYTES)
                    # Leave an incomplete final record for the next read.
                    end = raw.rfind(b'\n') + 1
                    lines = raw[:end].splitlines()
                    position += end
                for line in (lines[-50:] if initial else lines):
                    text = format_safe_line(line)
                    if text is not None:
                        print(text, flush=True)
                waiting = False
            except OSError:
                if not waiting:
                    print('No readable private log yet. Logging becomes active after the updated app is restarted.', flush=True)
                waiting = True
            finally:
                if fd is not None:
                    os.close(fd)
            if not args.follow:
                return
            time.sleep(1)
    except KeyboardInterrupt:
        print('Log viewer stopped. App unchanged.')


if __name__ == '__main__': main()
