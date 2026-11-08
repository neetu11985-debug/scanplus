# ScanPlus morning release review

Completed 8 November 2026 UTC. No publishing decision is implied. The requested simulator checks used synthetic data only.

## Current recommendation

- **Conditional go: protected synthetic preview.** Demonstrate the sample-number journey, clearly labeled mock results, PDF report and official manual-removal guidance. No real phone search, SMS, charge or automatic removal is part of that preview. Review the exact release commit, CI and deployed smoke test before publication.
- **Separate owner-only live test:** may continue only within its approved provider consent and remaining budget. The local no-SMS tool is not customer verification or a public beta.
- **No-go: public real-number or paid service.** Synthetic tests do not establish live SMS/search quality, customer authentication and abuse protection, provider costs/permissions, selected deployed database security/retention, payment/refund operation or final legal/privacy/support readiness.

A public informational page and a clearly marked sample report would be a different, narrow publishing scope. Do not remove the existing private-access guard merely to expose the testing app.

## Completed automated checks

- 393 Python tests passed.
- All 10 UI contract suites passed.
- Build passed: 84 Python source files, 15 JavaScript files and TypeScript checks.
- `git diff --check` passed.
- Independent review passed 20 in-memory hosted/fixture tests and local cookie/CSRF probes. A second focused review passed 12 in-memory report/expiry tests and the report UI harness after the final labeling fix. No real provider/database operation was used.
- Existing quality probe passed 240 synthetic report reads across 2, 8 and 16 workers, observed rate limits, rejected unsafe Host/Origin/cross-site/traversal requests, and checked the authenticated PDF attachment/signature. This is not a production throughput or capacity measurement.

## Completed simulator evidence

Dedicated iPhone simulator, synthetic fixtures only:

- Six-page PDF opens in native Safari preview. Overview, illustrated manual-removal roadmap and source pages were readable and unclipped. Back returns to the report.
- Clear removes the report; the spent allowance stays spent.
- Unavailable-provider fixture shows 0/3 usable responses, an explicit source-unavailable/no-absence-conclusion label, HTTP 503 and no automatic retry. It makes one mock search attempt and skips the other two.
- The private plain-text link eventually produced Safari's native prompt, but View did not show a text document. The backend remained responsive. Actual native text-file saving is unverified; no backend failure was established. A separate authenticated mock HTTP check returned 200 with a complete 5,441-byte UTF-8 body matching Content-Length, the correct attachment filename, normal connection closure and a 1 ms response.
- Default demo passed required declaration, invalid/valid code, $0 checkout, report, PDF Back, refresh, removal-consent Cancel and Clear. A different reserved number showed live lookup unavailable instead of a synthetic report, with its entry cleared.
- The six-page demo PDF was saved through Safari Share > Save to Files; a second file-picker inspection confirmed a 47 KB ScanPlus PDF in the simulator's local Downloads. This was actual saving, not just preview.
- After more than five minutes, returning to the hosted tab showed Session expired with no report. Reload kept the allowance spent and did not restore a phone form.
- Empty-result mode showed three usable responses and zero potential matches, limited to checked indexed results, without an all-clear claim.
- Final unavailable-mode recheck confirmed the two skipped sources say Query not attempted without a misleading check timestamp.

No external listing/guide was opened and no provider request, payment or removal was made during these checks.

## Fixes completed

Both local no-SMS and local SMS-enabled test runners now use port-specific session-cookie names, preventing accidental overwrites between test servers. Hosted owner testing has its own cookie name. This is not a security boundary against other services on the same host.

Malformed non-ASCII CSRF/session input now rejects cleanly instead of producing an internal error. Regressions reproduced before the fixes and pass afterward. Synthetic browser fixtures now have explicit matched, empty and unavailable scenarios; none can select a live provider. UI and plain-text reports now label skipped queries as Query not attempted rather than Checked; expiry-skipped sources also carry the explicit flag.

The owner's existing real test on port 4178 and the older process on port 4176 were not restarted or reset. Backend fixes apply on a future authorized launch, not retroactively to an already running process.

## Release packaging and remaining gates

The local branch remains `feature/removal-consent-input-test`, based on commit `2dd5d81f50e000026fafc559aef6b7c58840909c`, with accumulated uncommitted changes. No commit, push, merge or deployment was performed. Main is reported to trigger deployment, so a merge is a publishing decision.

The checked source snapshot covered 116 source/config files, with combined SHA-256 `723b72aa9a6e09e76e043a621c8169aeccddf6aa9e2e696a06dc387874a09b13`. This is a local snapshot identifier, not a release commit or CI proof.

Before a protected preview: settle consistent branding/copy, review the full diff, verify CI for the approved commit, complete a final desktop smoke check for the intended audience, then explicitly authorize publication and verify the deployed version. Before a live or paid launch, complete the broader acceptance gates in `FIRST_RELEASE_PLAN.md`.

## Remaining non-blocking observations and limits

- Hosted TXT saving remains unqualified on this simulator; the primary PDF path saved successfully. Do not claim that TXT delivery was verified.
- Simulator automation sometimes dropped the first typed digit when the hosted code input was manually focused; selecting all and retyping worked. No input-trimming handler was found, and this is not established as a physical-device/user defect.
- Coupon helper text flows into the demo Apply/Clear row. Controls remained usable; cosmetic improvement can follow without changing pricing behavior.
- No physical iPhone, Android, screen reader, complete desktop/landscape journey, deployed build or real integration was tested in this pass.

## Evidence and cleanup

Rendered screenshots and the detailed checklist are in `evidence/mobile-first-release-2026-11-08/QA.md`. Key images include `demo-pdf-saved.png`, `hosted-expired.png`, `hosted-empty.png`, `hosted-unavailable.png` and `hosted-skipped-sources-fixed.png`. These are local synthetic test artifacts, not live customer results.

The dedicated simulator and our synthetic servers on ports 4177 and 4180 were stopped after testing. At cleanup, the owner's server on port 4178 was still listening. Port 4176 was not listening; no stop/restart/reset action was taken against either owner test. No secrets were copied or read, and no real provider call, payment, removal, account change or deployment occurred during this pass.
