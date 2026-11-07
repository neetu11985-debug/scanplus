# Lean launch gate — Friday November 6 target

**November 6 update:** The owner reports the domain is ready; the exact domain and hosting capabilities still need confirmation. The selected no-card search route is now Serper in the separate local self-test. It is disabled and not live-qualified. See `MORNING_READINESS.md` for current test evidence and separate local/public prerequisites. Poynt below applies only if the paid public product proceeds, not to the local no-checkout self-test.

## Foundation implemented and locally tested

- Approved responsive web flow and clear synthetic labels; no native app or AI.
- Transactional SQLite sessions, per-session report/job state, one-use expiring demo challenge, test receipt persistence, deletion and bounded retention.
- CSRF/origin/host checks, request/attempt/session/rate limits, timeouts and redacted diagnostics.
- Offline Brave normalization, Twilio ownership schema boundary, and Poynt order/reconciliation harness. Real transports remain disabled; no secrets or paid setup.
- Durable payment reservations and nonce/transaction replay claims across store reopen and two-worker tests.
- WSGI entry and complete synthetic HTTP/WSGI journeys. Local dev HTTP server remains loopback-only.

## Exact owner/account/hosting gates

1. Confirm GoDaddy product, Python 3.11+ with sqlite3, managed WSGI, reliable local filesystem locking, private writable DB path, HTTPS and scheduler. If SQLite is unavailable or the home is unsuitable for locking, choose the host's supported SQL persistence then adapt the small Store boundary. Do not build another persistence system before that decision. Keep aiclubusa.co untouched.
2. Owner chooses/registers the product domain, legal merchant/support identity, and approves the actual bounded $0.99 service/refund/privacy scope.
3. Configure approved SMS verification service and consent/authentication. Qualify ownership/number/session binding, expiry, resend, decline/throttle/recovery and SMS abuse controls. The offline Twilio class is not an operational integration.
4. Obtain permitted discovery access and terms; approve phone transmission/retention disclosures. Implement the real network transport only after approved setup; qualify coverage, no-match, unavailable and user match-confirmation behavior. A paid report cannot be sold as a synthetic scan.
5. Complete Poynt developer/merchant sandbox configuration. Establish actual OAuth permissions, capture/lookup semantics and webhook authentication contract. Implement and test real sandbox success, decline, cancellation, timeout/reconciliation, duplicate callback, mismatch and refund. No invented callback signature or fake payment success.
6. Manually validate each official removal route. Only enable automated submissions with separate permission/support evidence. CAPTCHA/identity/email checks remain customer actions. No paid PeopleConnect automation absent permission.

## Code/integration work after those gates

Wire qualified transports to the persistent session/order boundaries; preserve hard live-mode refusal until all required adapters and configuration checks exist. Establish production financial retention, host encryption/backup/deletion, trusted proxy/rate/WSGI limits, scheduled prune, no-service/no-charge behavior and operator reconciliation/refund tools. Avoid collecting provider household/address data. Run final staging security/accessibility/cross-browser/mobile checks and obtain the explicit publishing decision. No public deployment or Friday readiness is established by the current fixture tests.
