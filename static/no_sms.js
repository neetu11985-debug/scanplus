'use strict';
function searchDiagnosticMarkup(diagnostic){
  if(!diagnostic||typeof diagnostic!=='object'||Array.isArray(diagnostic))return '';
  const labels={"timeout":"The provider request timed out.","dns_error":"The provider hostname could not be resolved.","tls_certificate_error":"TLS certificate verification failed.","tls_error":"A secure TLS connection could not be completed.","network_permission_denied":"A permission restriction denied the network operation.","connection_refused":"The connection was refused.","connection_closed":"The connection closed before a usable response arrived.","network_error":"A network operation failed.","http_protocol_error":"The HTTP response could not be read correctly.","response_incomplete":"The provider response was incomplete.","response_too_large":"The provider response exceeded the size limit.","invalid_json":"The provider response was not valid JSON.","invalid_response":"The provider response did not have the expected structure.","http_error":"The provider returned an unusable HTTP status.","not_dispatched":"The query was not sent because an allowance or safety gate blocked it.","not_attempted_after_provider_error":"The query was not attempted after an earlier provider failure.","transport_error":"The request failed for an unclassified transport reason."};
  const category=typeof diagnostic.category==='string'&&Object.prototype.hasOwnProperty.call(labels,diagnostic.category)?diagnostic.category:'transport_error';
  const status=Number.isInteger(diagnostic.http_status)&&diagnostic.http_status>=100&&diagnostic.http_status<=599?diagnostic.http_status:'status unavailable';
  return '<p class="fine">Search diagnostic: '+labels[category]+' HTTP '+status+'. No automatic retry occurred.</p>';
}
// End search diagnostics.

const $ = selector => document.querySelector(selector);
// The country selector is US-only. Never trim an overlong entry or infer a country.
function normalizeUsPhone(value){
  return typeof value==='string' && /^[0-9]{10}$/.test(value) ? '+1'+value : null;
}
let csrf = '', busy = false, current = null, generation = 0, expiryTimer = null;
function blankInput() { $('#phone').value = ''; for(const id of ['#own','#ack','#serper-consent','#free-confirm']) $(id).checked = false; }
function controls() {
  $('#start').disabled = busy || !current || current.phase !== 'entry' || current.allowance_used === true;
  $('#scan').disabled = busy || !current || !['ready','blocked'].includes(current.phase) || (current.search_enabled === true && current.allowance_used === true);
  $('#clear').disabled = busy || !current;
}
const escapeText = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function reportMarkup(report) {
  const labels = {match_needs_confirmation:'Potential matches: confirm each listing is yours',not_found_in_checked_sources:'No exact match in the checked indexed results',source_unavailable:'Source unavailable: no absence conclusion'};
  const links = report.sources.map(source => '<article><h3>'+escapeText(source.site)+'</h3><p><strong>'+escapeText(labels[source.status] || 'Unknown outcome: no absence conclusion')+'</strong></p><p class="fine">'+escapeText(source.query_attempted === false ? 'Query not attempted' : 'Checked '+source.checked_at)+(source.reason ? ' · '+escapeText(source.reason.replaceAll('_',' ')) : '')+'</p>'+searchDiagnosticMarkup(source.search_diagnostic)+source.candidates.map(candidate=>'<p><a href="'+escapeText(candidate.source_url)+'" target="_blank" rel="noopener noreferrer">'+escapeText(candidate.source_url)+'</a></p><p>'+escapeText(candidate.evidence)+'</p><p class="fine">Not yet confirmed as your listing. No removal submitted or verified.</p>').join('')+(source.guide ? '<details><summary>Official manual guide: '+escapeText(source.guide.name)+'</summary><p>'+escapeText(source.guide.verification_notice)+'</p><p>Confirm this record belongs to you before taking any action. Phone ownership was not verified in this local self-test.</p><ol>'+source.guide.steps.map(step=>'<li>'+escapeText(step)+'</li>').join('')+'</ol><p><a href="'+escapeText(source.guide.url)+'" target="_blank" rel="noopener noreferrer">Open official privacy / opt-out page</a></p><p>'+escapeText(source.guide.automation_notice)+'</p></details>' : '')+'</article>').join('');
  return '<h2>Your Serper search report</h2><p class="notice">'+escapeText(report.ownership_notice)+'</p><p><strong>'+escapeText(report.sources_checked)+' of '+escapeText(report.sources.length)+'</strong> source queries returned usable responses. '+escapeText(report.queries_attempted)+' queries attempted.</p><p><a href="/api/export.pdf" download>Download PDF report</a> · <a href="/api/export.txt" download>Plain-text alternative</a></p><p>'+escapeText(report.privacy_notice)+'</p>'+links+'<p>'+escapeText(report.coverage)+'</p><p>'+escapeText(report.removal_notice)+'</p><p class="fine">Opening a result or guide contacts that website. Listing URLs may contain personal information. Nothing opens automatically.</p>';
}
function render(state) {
  if (state.phase !== 'entry' && (!Number.isFinite(state.expires_in_ms) || state.expires_in_ms <= 0)) {
    invalidateLocal('This local test expired. Its report and number have been cleared. Reload to continue.');
    return;
  }
  current = state;
  csrf = state.csrf_token;
  const entry = state.phase === 'entry', live = state.search_enabled === true, usage = state.test_usage, exhausted = live && state.allowance_used === true, hasReport = state.phase === 'report' && state.report;
  $('#entry').hidden = !entry || exhausted;
  $('#next').hidden = entry || !!hasReport || state.phase === 'error';
  $('#report').hidden = !hasReport;
  $('#report').innerHTML = hasReport ? reportMarkup(state.report) : '';
  $('#masked').textContent = state.last_four ? 'Number ending ' + state.last_four + '. ' + (live ? 'Held only until the scan or test expiry.' : 'The full number was not retained.') : '';
  $('#mode-description').textContent = live ? 'Real Serper search enabled for bounded local testing after your free-credit confirmation. Maximum three queries per scan. Each new scan requires fresh consent; repeats are limited to the same own number. No query starts automatically.' : state.blocker || 'Real Serper lookup is blocked until free credits and the query allowance are confirmed. No search ran.';
  $('#help').textContent = live ? 'Use only your own number. It stays on this Mac until you separately approve sending it to Serper.' : 'Prefer the reserved example 2025550147 for this offline check. An actual number stays on this Mac and is not used for any lookup.';
  $('#own-label').textContent = live ? 'This is my own number. I am testing only for myself.' : 'This is my own number or the reserved offline test example.';
  $('#start').textContent = live ? 'Continue without SMS' : 'Check input without SMS';
  $('#search-permission').hidden = !live;
  $('#scan').textContent = live ? 'Run one real Serper scan' : 'Check real-search availability';
  $('#status').textContent = hasReport ? 'Scan finished. SMS off. Ownership not verified.' : state.phase === 'error' ? 'Scan could not complete. This scan remains spent; no automatic retry.' : entry ? 'SMS off. Ownership not verified. ' + (state.allowance_used ? 'This process has used its configured test allowance.' : 'No search has started.') : 'Input accepted. SMS off. Ownership not verified.';
  $('#test-usage').hidden = !live || !usage;
  $('#test-usage').textContent = usage ? 'Process test budget: ' + usage.scans_started + ' / ' + usage.scan_limit + ' scans started; ' + usage.queries_attempted + ' / ' + usage.query_limit + ' queries attempted. ' + usage.scans_remaining + ' scan(s) remain. ' + (usage.same_number_locked ? 'Locked to your first scanned number. ' : '') + 'Clear, reload and expiry do not refill this budget. Failed scans count.' + (state.diagnostic_log_status && state.diagnostic_log_status !== 'disabled' ? ' Private diagnostic log: ' + state.diagnostic_log_status + '.' : '') : '';
  $('#clear').textContent = hasReport && !exhausted ? 'Clear report to test the same number again' : 'Clear local entry and report';
  clearTimeout(expiryTimer);
  expiryTimer = state.expires_in_ms > 0 ? setTimeout(() => invalidateLocal('This local test expired. Its report and number have been cleared. Reload to continue.'), state.expires_in_ms) : null;
  controls();
}
function wipeLocal(message) {
  clearTimeout(expiryTimer); expiryTimer = null;
  blankInput(); current = null; csrf = '';
  $('#report').innerHTML = ''; $('#report').hidden = true;
  $('#masked').textContent = ''; $('#next').hidden = true;
  $('#entry').hidden = false; $('#error').hidden = true;
  $('#test-usage').textContent = ''; $('#test-usage').hidden = true;
  $('#status').textContent = message; controls();
}
function invalidateLocal(message) {
  generation++; busy = false; wipeLocal(message);
}
async function refreshSession() {
  invalidateLocal('Checking the current local session. Old report data has been cleared.');
  await run(() => request('session'));
}

async function request(path, data) {
  const requestGeneration = generation;
  const startedAt = performance.now();
  const controller = new AbortController();
  // Three sequential provider requests may each take five seconds. A lost
  // response is reconciled with a read-only session fetch, never a scan retry.
  const timer = setTimeout(() => controller.abort(), path === 'scan' ? 30000 : 10000);
  let parsed = false;
  try {
    const options = {cache:'no-store', credentials:'same-origin', signal:controller.signal};
    if (data !== undefined) Object.assign(options, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(data)});
    const response = await fetch('/api/' + path, options);
    const result = await response.json(); parsed = true;
    if (requestGeneration !== generation) return false;
    // Conservatively account for transit/processing time so a delayed response
    // cannot restart an already-expired display lifetime.
    const state = result.state || result;
    if (Number.isFinite(state.expires_in_ms)) state.expires_in_ms = Math.max(0, state.expires_in_ms - Math.max(0, performance.now() - startedAt));
    if (result.state) render(result.state);
    if (!response.ok) throw Error(result.error || 'The local test could not complete. Reload before retrying.');
    render(result);
    return true;
  } catch(error) {
    error.uncertain = !parsed;
    throw error;
  } finally { clearTimeout(timer); }
}
async function run(work) {
  if (busy) return;
  const operationGeneration = generation;
  busy = true; controls(); $('#error').hidden = true;
  try { await work(); }
  catch(error) {
    if (operationGeneration === generation) {
      $('#error').textContent = error.name === 'AbortError' ? 'The local request timed out. Reload to check its state before retrying.' : error.message;
      $('#error').hidden = false;
    }
  } finally { if (operationGeneration === generation) { busy = false; controls(); } }
}
async function scanOnce() {
  const scanGeneration = generation;
  const consent = {serper_consent:$('#serper-consent').checked, free_allowance_confirmed:$('#free-confirm').checked};
  try { await request('scan', consent); }
  catch(error) {
    if (!error.uncertain || scanGeneration !== generation) throw error;
    wipeLocal('The scan response was uncertain. Checking saved state without repeating the search.');
    try {
      await request('session');
      if (current && current.phase === 'report') return;
      throw Error('The scan did not return a completed report. Current state is shown; no search was automatically retried.');
    } catch(problem) {
      throw Error(problem.message || 'Could not confirm the scan state. Reload before trying again; no search was retried.');
    }
  }
}
$('#entry').addEventListener('submit', event => {
  event.preventDefault();
  if (busy) return;
  const phone = normalizeUsPhone($('#phone').value);
  if (!phone) {
    $('#error').textContent = 'Enter exactly 10 digits without the country code. US (+1) is added automatically.';
    $('#error').hidden = false; $('#phone').focus(); return;
  }
  const data = {phone, own_number:$('#own').checked, no_sms_acknowledged:$('#ack').checked};
  blankInput();
  run(() => request('start', data));
});
$('#scan').addEventListener('click', () => run(scanOnce));
$('#clear').addEventListener('click', () => { blankInput(); run(() => request('clear', {})); });
window.addEventListener('pagehide', () => invalidateLocal('Local data cleared from this page. Return to reload the current session.'));
window.addEventListener('pageshow', event => { if (event.persisted) refreshSession(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) invalidateLocal('Local data cleared while this page is hidden.'); else refreshSession(); });
run(() => request('session'));
