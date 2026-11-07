# Storage usage alert evaluator

## Implemented locally

`storage_usage.evaluate_usage` is a pure, dependency-free decision function. It
accepts externally supplied provider metrics and returns JSON-compatible state
and event candidates. It does not fetch metrics, verify provider authenticity,
persist state, schedule checks, send messages, or change database capacity/data.
Nothing imports this into the live server. Passing tests prove synthetic decision
behavior only, not live monitoring, working delivery, or deployment readiness.

## Trusted adapter contract

Call `evaluate_usage(scope, sample, now=unix_seconds, state=previous_state)`.
Only a trusted backend adapter may populate these values, never a browser form.

- `scope` has exactly `provider`, `project`, `environment`, `console_url`.
  Labels must be 1–80 ASCII letters/digits/dots/underscores/hyphens, starting with
  a letter/digit. The console URL must be HTTPS with no credentials, whitespace,
  query, or fragment. Use a verified public provider-console link, without secrets
  in its path. URL validation does not verify the host or the user's access.
- `sample` has exactly `used_bytes`, `quota_bytes`, `observed_at`, or is `None`
  when a provider check fails. Supply the provider's total storage consumption,
  including whatever indexes/metadata it counts, and actual plan quota in the
  same byte units. Do not estimate from customer count or report text length.
- Bytes and timestamps must be integers from 0 through 2^63−1. Quota must be
  positive. Used bytes may exceed quota. Booleans, floats (including NaN/infinity),
  strings, extra fields and missing fields are rejected as invalid metrics.
- `now` and `observed_at` are Unix seconds. Default maximum sample age is 7,200
  seconds inclusive. Future, older, and conflicting same-time measurements fail.
  A different valid observation needs a later `observed_at`. A provider adapter
  must preserve the provider's observation timestamp, not re-stamp cached data.
- Use an hourly polling cadence initially. One distinct `now` is one attempt.
  An identical check timestamp returns `duplicate_check` without processing it;
  backward check time raises `ValueError`. Coalesce or serialize same-second calls.
- Persist the returned state, not the input state. State schema version is 1 and
  is bound to the entire scope, including console URL. A scope change requires
  explicit state migration or a new independent stream. Unknown versions,
  malformed state/configuration and scope mismatches raise `ValueError`; never
  silently reset corrupt state, which could generate duplicate alerts.

## Threshold and failure behavior

A first sample at or above 70% alerts. New crossings of 85% and 95% escalate.
A jump straight to 95% emits one 95% event, not three messages. The highest level
already emitted remains suppressed until usage falls strictly below 60%.
Exactly 60% does not re-arm. A quota change uses the new actual quota immediately
but does not by itself reset suppression. A quota increase can cause below-60%
re-arming; a quota reduction can cause a new higher-level alert.

Failure samples do not overwrite the last good metric or re-arm usage alerts.
Three consecutive failed checks emit one failure event by default. Further
failures are suppressed until a fresh valid metric resets failure state.
An identical still-fresh observation returns `duplicate_sample` and does not
claim recovery or increment the failure counter; once stale, it counts as failure.
Failure reasons are fixed codes, never raw provider errors or response bodies.

## Exact output schema

The top-level result contains `state`, `status`, and `events` (zero or one event).

State fields: `version`, `scope`, `highest_alert` (0/70/85/95), `last_sample`
(null or the three metric fields), `last_checked_at`, `consecutive_failures`,
and `failure_reported`. Inputs are not modified. JSON round-tripping is supported.

A storage event contains only:

- `kind`: `storage_threshold`
- `scope`: the four validated configuration fields
- `checked_at`, `observed_at`, `used_bytes`, `quota_bytes`
- `threshold_percent`: 70, 85, or 95; `usage_percent`: numeric, possibly over 100
- `growth_bytes_per_hour`: signed average between two accepted observations, or
  null for the first observation or changed quota. This is descriptive, not a
  forecast. Negative growth represents storage reduction.
- `quota_changed`: boolean compared with the previous accepted observation
- `recommendation`: `inspect_growth_retention_and_backups`

A failure event contains only `kind` (`usage_check_failure`), `scope`, `checked_at`,
`reason`, and `consecutive_failures`. Reasons are `provider_check_failed`,
`invalid_metric`, `future_metric`, `stale_metric`, `out_of_order_metric`, or
`conflicting_metric`. `status` uses those codes or `ok`, `duplicate_check`, or
`duplicate_sample`.

No customer identifiers, phones, report content, credentials, raw error details,
or arbitrary provider metadata are copied into reports. Scope values are trusted
operator configuration, not a general-purpose secret-redaction boundary. Render
reports as escaped text and deliver only to the authorized operator destination.

## Remaining activation work (not performed)

1. Choose the actual provider, project, environment, plan quota and verified
   metrics endpoint. Configure approved least-privilege credentials separately.
2. Implement and test a backend-only adapter that validates provider responses and
   handles provider units, freshness, pagination and rate limits correctly.
3. Store state durably per scope and serialize evaluation. Atomically commit the
   new state with an outbox event; otherwise a crash can lose or duplicate alerts.
   A delivery worker needs retry and idempotency semantics of its own. This pure
   evaluator does not guarantee exactly-once external delivery.
4. Configure the hourly scheduler and authorized recipient/channel, then verify
   actual metrics and alert delivery under controlled operational tests.
5. Choose a project-specific rapid-growth policy if wanted. Growth is reported
   on threshold events, but unexpected-fast-growth standalone alerts are not yet
   implemented because no meaningful rate threshold has been selected.
6. Inspect legitimate growth, retention/pruning and backup sizes before proposing
   capacity changes. Do not purchase capacity or delete customer data automatically.
   Storage metrics do not monitor compute, connection, egress or plan-expiry limits.

## Verification

Local synthetic checks (2026-11-07), no live provider or delivery calls:

- `python -m unittest discover -s tests -p test_storage_usage.py -v`: 10 passed.
- `python -m py_compile storage_usage.py tests/test_storage_usage.py`: passed.

Browser/JavaScript checks are not applicable to this isolated Python module.
Actual provider integration, scheduler persistence/concurrency, recipient access,
and end-to-end external alert delivery remain untested and unconfigured.
