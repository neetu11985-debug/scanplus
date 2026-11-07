# Tonight's five-minute ScanPlus test

This is a local synthetic demo, not a real lookup. No card, real number or SMS is needed.

1. Open http://127.0.0.1:4173 on this Mac. If the server stopped, run:
   ```sh
   cd '/Users/rajeshkumar/dev/ScanPlus codes'
   python3 server.py
   ```
2. Click **Try the demo**. Confirm the fixed demo number +1 (202) 555-0147 and check the declaration.
3. Continue. Enter **000000** first: expect a clear incorrect-code error. Enter **246810** to continue.
4. Check that checkout displays a $1.49 intended launch price and **$0 charged today**. Accept the demo declaration and complete checkout. No payment details are collected.
5. Confirm the report shows **2 example listings**, **0 live sources checked**, and TruePeopleSearch as **not checked**. No result is a finding about a real person.
6. Expand a provider guide. Confirm instructions and the unverified candidate-link notice are readable. Opening a guide leaves ScanPlus and shares no phone number automatically; do not submit real personal data during this demo.
7. Expand **Explore automatic removal · synthetic provider**. Try submitting without authorization: expect an error. Check the authorization, submit, and observe **request submitted**. Check status once for **pending**, then again for **Simulated completion — nothing submitted or removed**. None of these actions contacts a real broker.
8. Optionally export JSON; it should contain only synthetic data and no real listing links. A downloaded file stays on your Mac until you delete it.
9. Click **Clear session**. Expect the starting form. On a phone-sized browser window, repeat the main path and check readable text, no horizontal scroll and easy controls. This loopback server is intentionally unavailable to a separate physical phone.

Discuss after the test: Is the value of the report clear? Which step feels confusing? Are the mock/live distinctions obvious? Is $1.49 worth a bounded report and helpful removal guidance? Keep feedback focused on the one web product.

## Current verification

The service/contract/adversarial suite passed, plus Python compilation and JavaScript syntax checks. Desktop and 390 × 844 browser journeys passed. See evidence/QA.md for exact results, resolved failures and unrun checks. JSON export, fault-injected empty/network-error screens, formal accessibility, cross-browser and physical-phone checks remain unrun.

## Before accepting real payments

Confirm the existing GoDaddy plan/runtime and separate deployment location, legal merchant/support identity, domain, real ownership verification, permitted discovery provider, current official removal flows, gateway sandbox and signed callback verification, refunds and privacy/retention policies. No live integration is enabled by this prototype.
