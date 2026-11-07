'use strict';
let csrf = '', busy = false;
const statusBox = document.querySelector('#status');
const errorBox = document.querySelector('#error');
const actions = document.querySelector('#actions');
async function api(path, data) {
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 12000);
  try {
    const r = await fetch('/api/' + path, {method: data ? 'POST' : 'GET', signal: abort.signal,
      headers: data ? {'Content-Type': 'application/json', 'X-CSRF-Token': csrf} : {},
      body: data ? JSON.stringify(data) : undefined});
    const result = await r.json();
    if (!r.ok) throw Error(result.error || 'Request failed.');
    return result;
  } catch (e) {
    if (e.name === 'AbortError') throw Error('Request timed out. Reload to check status before retrying.');
    throw e;
  } finally { clearTimeout(timeout); }
}
function button(label, task) {
  const b = document.createElement('button'); b.className = 'outline'; b.textContent = label;
  b.onclick = async () => {
    if (busy) return;
    busy = true; b.disabled = true; errorBox.textContent = '';
    try { await task(); } catch (e) { errorBox.textContent = e.message; }
    finally { busy = false; b.disabled = false; }
  };
  actions.append(b);
}
async function show() {
  actions.replaceChildren();
  document.querySelector('#download').hidden = true;
  const session = await api('session'); csrf = session.csrf_token || '';
  if (!session.active) {
    statusBox.textContent = 'Start a synthetic session for reserved number +1 202-555-0147. No SMS is sent.';
    button('Start synthetic session', async () => { const s = await api('start', {phone: '+12025550147', consent: true}); csrf = s.csrf_token; await show(); });
    return;
  }
  if (!session.verified) {
    statusBox.textContent = 'Confirm the fixed test verification. This does not verify a real person.';
    button('Verify with synthetic code 246810', async () => { await api('verify', {code: '246810'}); await show(); });
    return;
  }
  const payment = await api('stripe/status');
  statusBox.textContent = 'Stripe sandbox: ' + payment.state + '. Test price $' + (payment.amount_cents / 100).toFixed(2) + ' USD, one time; real charge $0.';
  if (payment.state === 'paid') {
    button('Open server-verified synthetic report', async () => {
      const report = await api('stripe/report');
      const output = document.querySelector('#report'); output.hidden = false;
      output.textContent = JSON.stringify(report, null, 2);
    });
    button('Save synthetic paid report to encrypted storage', async () => {
      await api('stripe/report/save', {confirm_synthetic: true});
      document.querySelector('#download').hidden = false;
      statusBox.textContent = 'Encrypted test report saved. Download while this verified session is active. No new payment was created.';
    });
  } else if (payment.state !== 'expired') {
    button('I agree: continue to Stripe using test data only', async () => {
      const result = await api('stripe/checkout', {accept_test: true});
      if (result.state === 'paid') { await show(); return; }
      const destination = new URL(result.checkout_url);
      if (destination.origin !== 'https://checkout.stripe.com') throw Error('Unsupported checkout destination.');
      window.location.assign(destination.href);
    });
    button('Check payment with Stripe', async () => { await api('stripe/reconcile', {}); await show(); });
  }
  button('Clear synthetic session', async () => { await api('clear', {}); document.querySelector('#report').hidden = true; await show(); });
  if (location.hash === '#cancelled') statusBox.textContent += ' Checkout was cancelled. No success is inferred.';
  if (location.hash === '#returned') statusBox.textContent += ' Return alone proves nothing. Use Check payment with Stripe if confirmation is pending.';
}
show().catch(e => { errorBox.textContent = e.message; statusBox.textContent = 'Sandbox unavailable. Configure test credentials separately, then reload.'; });
