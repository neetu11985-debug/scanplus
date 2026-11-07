"""Pure storage-alert decisions. No polling, persistence, credentials or delivery.

Only a trusted server adapter may supply metrics and scope. Browser data and
report/user counts are not authoritative provider storage measurements.
"""
from copy import deepcopy
import re
from urllib.parse import urlsplit

_VERSION = 1
_MAX = 2**63 - 1
_LEVELS = (70, 85, 95)
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def _integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= _MAX:
        raise ValueError("invalid " + name)
    return value


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("invalid " + name)


def _scope(scope):
    _keys(scope, ("provider", "project", "environment", "console_url"), "scope")
    for name in ("provider", "project", "environment"):
        if type(scope[name]) is not str or not _LABEL.fullmatch(scope[name]):
            raise ValueError("invalid " + name)
    url = scope["console_url"]
    if type(url) is not str or not url.isascii() or any(ord(c) <= 32 for c in url):
        raise ValueError("invalid console_url")
    parsed = urlsplit(url)
    if (len(url) > 512 or parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "\\" in url):
        raise ValueError("invalid console_url")
    # Validate malformed ports too. This is validation, never a network request.
    try:
        parsed.port
    except ValueError:
        raise ValueError("invalid console_url") from None
    return dict(scope)


def _sample(sample):
    _keys(sample, ("used_bytes", "quota_bytes", "observed_at"), "metric")
    _integer(sample["used_bytes"], "used_bytes")
    _integer(sample["quota_bytes"], "quota_bytes", 1)
    _integer(sample["observed_at"], "observed_at")
    return dict(sample)


def _state(state, scope):
    if state is None:
        return {"version": _VERSION, "scope": scope, "highest_alert": 0,
                "last_sample": None, "last_checked_at": None,
                "consecutive_failures": 0, "failure_reported": False}
    _keys(state, ("version", "scope", "highest_alert", "last_sample",
                  "last_checked_at", "consecutive_failures", "failure_reported"), "state")
    if type(state["version"]) is not int or state["version"] != _VERSION:
        raise ValueError("unsupported state version")
    if _scope(state["scope"]) != scope:
        raise ValueError("state scope mismatch")
    if type(state["highest_alert"]) is not int or state["highest_alert"] not in (0,) + _LEVELS:
        raise ValueError("invalid highest_alert")
    _integer(state["consecutive_failures"], "consecutive_failures")
    if type(state["failure_reported"]) is not bool:
        raise ValueError("invalid failure_reported")
    if state["last_checked_at"] is not None:
        _integer(state["last_checked_at"], "last_checked_at")
    if state["last_sample"] is not None:
        sample = _sample(state["last_sample"])
        if state["last_checked_at"] is None or sample["observed_at"] > state["last_checked_at"]:
            raise ValueError("invalid sample chronology")
    if state["failure_reported"] and not state["consecutive_failures"]:
        raise ValueError("invalid failure state")
    return deepcopy(state)


def evaluate_usage(scope, sample, *, now, state=None, max_age_seconds=7200,
                   failure_threshold=3):
    """Return JSON-safe {state, status, events} without changing inputs.

    Times are integer Unix seconds. Byte metrics are nonnegative 64-bit integers;
    quota must be positive. None means a failed provider check. Invalid, stale,
    future, conflicting or out-of-order metrics become sanitized check failures.
    Invalid configuration/persisted state raises ValueError (fail closed).

    Persist state and enqueue events atomically in the eventual adapter. Each
    distinct `now` represents one polling attempt. Retries with the same `now`
    produce no events. Serialize checks per scope to avoid concurrent duplicates.
    """
    scope = _scope(scope)
    _integer(now, "now")
    _integer(max_age_seconds, "max_age_seconds", 1)
    _integer(failure_threshold, "failure_threshold", 1)
    current = _state(state, scope)
    previous_check = current["last_checked_at"]
    if previous_check is not None and now < previous_check:
        raise ValueError("clock moved backwards")
    if previous_check == now:
        return {"state": current, "status": "duplicate_check", "events": []}
    current["last_checked_at"] = now
    reason = None
    metric = None
    if sample is None:
        reason = "provider_check_failed"
    else:
        try:
            metric = _sample(sample)
        except ValueError:
            reason = "invalid_metric"
    previous = current["last_sample"]
    if reason is None:
        timestamp = metric["observed_at"]
        if timestamp > now:
            reason = "future_metric"
        elif now - timestamp > max_age_seconds:
            reason = "stale_metric"
        elif previous and timestamp < previous["observed_at"]:
            reason = "out_of_order_metric"
        elif previous and timestamp == previous["observed_at"]:
            if metric != previous:
                reason = "conflicting_metric"
            else:
                return {"state": current, "status": "duplicate_sample", "events": []}
    if reason:
        current["consecutive_failures"] = min(_MAX, current["consecutive_failures"] + 1)
        events = []
        if current["consecutive_failures"] >= failure_threshold and not current["failure_reported"]:
            current["failure_reported"] = True
            events.append({"kind": "usage_check_failure", "scope": dict(scope),
                           "checked_at": now, "reason": reason,
                           "consecutive_failures": current["consecutive_failures"]})
        return {"state": current, "status": reason, "events": events}

    current["consecutive_failures"] = 0
    current["failure_reported"] = False
    current["last_sample"] = metric
    used, quota = metric["used_bytes"], metric["quota_bytes"]
    # Integer comparisons make exact thresholds independent of floating point.
    if used * 100 < quota * 60:
        current["highest_alert"] = 0
    level = max((level for level in _LEVELS if used * 100 >= quota * level), default=0)
    events = []
    if level > current["highest_alert"]:
        current["highest_alert"] = level
        growth = None
        quota_changed = bool(previous and previous["quota_bytes"] != quota)
        if previous and not quota_changed:
            growth = ((used - previous["used_bytes"]) * 3600
                      / (metric["observed_at"] - previous["observed_at"]))
        events.append({"kind": "storage_threshold", "scope": dict(scope),
                       "checked_at": now, "observed_at": metric["observed_at"],
                       "used_bytes": used, "quota_bytes": quota,
                       "threshold_percent": level, "usage_percent": used * 100 / quota,
                       "growth_bytes_per_hour": growth, "quota_changed": quota_changed,
                       "recommendation": "inspect_growth_retention_and_backups"})
    return {"state": current, "status": "ok", "events": events}
