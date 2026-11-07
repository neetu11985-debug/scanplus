"""Owner-run local properties loader. No shell evaluation or credential output.

Offline --check is the default. --start additionally needs explicit opt-in in
an owner-private file. Neither action contacts providers on its own; live page
operations retain the existing per-provider consent and verification gates.
"""
import argparse
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from live_scan import Settings

DEFAULT_FILE = ROOT / "scanplus.local.properties"
MAX_BYTES = 16 * 1024
NAMES = frozenset(("SCANPLUS_LOCAL_LIVE_TEST", "SCANPLUS_SEARCH_PROVIDER",
                  "SCANPLUS_LOCAL_LIVE_PORT", "TWILIO_ACCOUNT_SID",
                  "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID",
                  "SERPER_API_KEY", "BRAVE_SEARCH_API_KEY"))


class ConfigurationError(ValueError):
    """Messages contain static setting names/line numbers, never file values."""


def read_properties(path):
    # O_NOFOLLOW and descriptor checks avoid following a substituted symlink.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ConfigurationError("Cannot open the private properties file. Check its location and permissions.") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ConfigurationError("Use a regular properties file, not a link or special file.")
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) not in (0o400, 0o600):
            raise ConfigurationError("The properties file must belong to you with owner-only read/write permissions (600 or 400).")
        if info.st_size > MAX_BYTES:
            raise ConfigurationError("The properties file is too large.")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ConfigurationError("The properties file is too large.")
    finally:
        if fd is not None:
            os.close(fd)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ConfigurationError("Save the properties file as UTF-8 plain text.") from None
    if text.lstrip().startswith("{\\rtf"):
        raise ConfigurationError("Save the properties file as plain text, not rich text.")
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if "=" not in line:
            raise ConfigurationError(f"Expected NAME=value on line {number}.")
        name, value = (part.strip() for part in line.split("=", 1))
        if name not in NAMES:
            raise ConfigurationError(f"Unknown setting on line {number}; keep the supplied setting names.")
        if name in values:
            raise ConfigurationError(f"Duplicate setting on line {number}.")
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigurationError(f"Unmatched quotation marks on line {number}.")
            value = value[1:-1]
        if any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise ConfigurationError(f"Use one plain-text value without spaces or smart quotes on line {number}.")
        # Literal values only: no source/eval, escaping, expansion or shell calls.
        values[name] = value
    return values


def validate(values, *, starting=False):
    enabled = values.get("SCANPLUS_LOCAL_LIVE_TEST", "0")
    if enabled not in ("0", "1"):
        raise ConfigurationError("SCANPLUS_LOCAL_LIVE_TEST must be 0 or 1.")
    if starting and enabled != "1":
        raise ConfigurationError("Local live startup is disabled. Leave it disabled until provider setup and live-action approvals are complete; then set SCANPLUS_LOCAL_LIVE_TEST=1 yourself.")
    provider = values.get("SCANPLUS_SEARCH_PROVIDER", "serper")
    if provider not in ("serper", "brave"):
        raise ConfigurationError("SCANPLUS_SEARCH_PROVIDER must be serper or brave.")
    try:
        port = int(values.get("SCANPLUS_LOCAL_LIVE_PORT", "4175"))
    except ValueError:
        raise ConfigurationError("SCANPLUS_LOCAL_LIVE_PORT must be a number from 1024 to 65535.") from None
    if not 1024 <= port <= 65535:
        raise ConfigurationError("SCANPLUS_LOCAL_LIVE_PORT must be a number from 1024 to 65535.")
    selected_key = "SERPER_API_KEY" if provider == "serper" else "BRAVE_SEARCH_API_KEY"
    required = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID", selected_key)
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ConfigurationError("Fill in these settings: " + ", ".join(missing))
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", values["TWILIO_ACCOUNT_SID"]) or not re.fullmatch(r"VA[0-9a-fA-F]{32}", values["TWILIO_VERIFY_SERVICE_SID"]):
        raise ConfigurationError("Check the Twilio Account SID (AC plus 32 hexadecimal characters) and Verify Service SID (VA plus 32 hexadecimal characters).")
    settings = Settings(values["TWILIO_ACCOUNT_SID"], values["TWILIO_AUTH_TOKEN"],
                        values["TWILIO_VERIFY_SERVICE_SID"], search_provider=provider,
                        serper_key=values[selected_key] if provider == "serper" else "",
                        brave_key=values[selected_key] if provider == "brave" else "")
    return settings, port


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check ScanPlus local properties without displaying keys or calling providers.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Offline format check only (default).")
    action.add_argument("--start", action="store_true", help="Start the loopback server only after explicit opt-in.")
    args = parser.parse_args(argv)
    try:
        values = read_properties(DEFAULT_FILE)
        settings, port = validate(values, starting=args.start)
        if not args.start:
            print("Local configuration format checked. No provider request was made; keys, account access, credits and billing are NOT verified.")
            print("Live startup is " + ("enabled in this file." if values.get("SCANPLUS_LOCAL_LIVE_TEST") == "1" else "still disabled."))
            return 0
        from local_live_server import serve
        # Pass directly in memory. Do not export keys to shell/environment/history.
        serve(settings, port)
        return 0
    except ConfigurationError as error:
        print("ScanPlus: " + str(error), file=sys.stderr)
        return 1
    except OSError:
        print("ScanPlus could not read the configuration or start the local server. Check file permissions and whether the local port is already in use.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
