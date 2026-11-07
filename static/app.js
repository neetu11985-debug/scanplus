const panel=document.querySelector('#panel'), alertBox=document.querySelector('#alert');
let stage=1, currentReport=null, csrfToken='', viewVersion=0, sessionActive=false, clearing=false;
const pendingMutations=new Set();
const phone='+12025550147';
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function progress(n){viewVersion++;stage=n;for(let i=1;i<=3;i++){const el=document.querySelector('#step'+i);el.classList.toggle('active',i===n);el.classList.toggle('done',i<n);if(i===n)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');}}
function error(message){alertBox.textContent=message;alertBox.hidden=false;}
function clearError(){alertBox.hidden=true;}
async function api(path,data){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  const request=(async()=>{
    try{
      const response=await fetch('/api/'+path,{method:data?'POST':'GET',signal:controller.signal,headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrfToken}:{},body:data?JSON.stringify(data):undefined});
      const result=await response.json();
      if(!response.ok){const failure=Error(result.error||'Something went wrong. Please try again.');failure.status=response.status;throw failure;}
      return result;
    }catch(e){if(e.name==='AbortError')throw Error('Request timed out. Reload to check your session before retrying.');throw e;}
    finally{clearTimeout(timer);}
  })();
  if(data)pendingMutations.add(request);
  try{return await request;}finally{pendingMutations.delete(request);}
}
async function run(button,fn){
  if(button.disabled)return;
  clearError();button.disabled=true;const label=button.textContent;button.textContent='Working…';
  try{await fn();}catch(e){if(button.isConnected)error(e.message);}
  finally{if(button.isConnected){button.disabled=false;button.textContent=label;}}
}
function focusAndReveal(target){
  if(!target)return;
  if(target.tagName==='H3'||target.tagName==='H4')target.tabIndex=-1;
  target.focus({preventScroll:true});
  const view=viewVersion,reveal=()=>{if(target.isConnected&&view===viewVersion)target.scrollIntoView({block:'start',behavior:'instant'});};
  reveal();
  // Safari can settle a shortened panel after focus. Recheck after layout without smooth-scroll races.
  if(typeof requestAnimationFrame==='function')requestAnimationFrame(reveal);
}
function focusPanel(){focusAndReveal(panel.querySelector('h3'));}
function start(useExample=true){
  document.body.classList.remove('report-mode');progress(1);
  panel.innerHTML=`<span class="pill">SYNTHETIC DEMO · LIVE LOOKUP NOT CONNECTED</span><h3>Start with your number.</h3><p>Use the reserved example to try verification, $0 checkout and a synthetic report. Entering a personal number shows current availability only. It cannot start a real lookup here.</p><form id="start-form" autocomplete="off"><label for="phone">Phone number, including country code</label><input id="phone" type="tel" inputmode="tel" autocomplete="off" maxlength="32" value="${useExample?'+1 (202) 555-0147':''}" aria-describedby="phone-help entry-status" required><small id="phone-help">Reserved example · synthetic fixture only</small><label class="check" id="demo-declaration"><input type="checkbox" id="control" required><span>I’m using the synthetic number for this demo. In a live lookup I must control the number.</span></label><button id="start-submit" class="primary wide" type="submit">Continue <span>&gt;</span></button><div class="entry-actions"><button id="use-example" class="text-button" type="button" hidden>Use example number instead</button><button id="entry-clear" class="text-button" type="button">Clear my entry</button></div></form><p id="entry-status" role="status"></p><p class="fine">No SMS will be sent. Personal entries are not sent to the backend or saved by ScanPlus. This does not verify a real phone or scan the web.</p>`;
  const form=document.querySelector('#start-form'),input=document.querySelector('#phone'),declaration=document.querySelector('#demo-declaration'),control=document.querySelector('#control'),submit=document.querySelector('#start-submit'),status=document.querySelector('#entry-status'),example=document.querySelector('#use-example');
  function controls(){
    const isDemo=normalizeLocalPhone(input.value)===phone;
    declaration.hidden=!isDemo;control.required=isDemo;example.hidden=isDemo;
    if(!isDemo)control.checked=false;
    document.querySelector('#phone-help').textContent=isDemo?'Reserved example · Continue opens test verification':'Continue to see availability · real lookup is not connected';
  }
  input.oninput=()=>{status.textContent='';controls();};
  example.onclick=()=>{input.value='+1 (202) 555-0147';status.textContent='';controls();control.focus();};
  document.querySelector('#entry-clear').onclick=()=>{input.value='';status.textContent='';controls();input.focus();};
  controls();
  form.onsubmit=e=>{
    e.preventDefault();if(submit.disabled||clearing)return;
    const normalized=normalizeLocalPhone(input.value);
    if(!normalized){clearError();status.textContent='Enter + followed by your country code and 8–15 digits in total. No lookup was performed.';return;}
    if(normalized!==phone){clearError();input.value='';showLookupAvailability();return;}
    run(submit,async()=>{const started=await api('start',{phone,consent:control.checked});if(!form.isConnected)return;csrfToken=started.csrf_token;sessionActive=true;verify();});
  };
}
function showLookupAvailability(){
  progress(1);
  panel.innerHTML='<span class="pill">LIVE LOOKUP UNAVAILABLE</span><h3>Live lookup is not connected.</h3><p>Your entry had an accepted format and has been cleared. It was not sent or saved. No ownership verification, online search or payment was performed.</p><p>This site currently supports the synthetic demo only. A real lookup needs a connected ownership-verification service, an approved search provider and your consent to send your number.</p><button id="availability-example" class="primary wide" type="button">Try the example demo &gt;</button><button id="availability-back" class="text-button" type="button">Change number</button><p class="fine">The example report is not a result about your number. No provider will be contacted.</p>';
  document.querySelector('#availability-example').onclick=()=>{start();focusPanel();};
  document.querySelector('#availability-back').onclick=()=>{start(false);document.querySelector('#phone').focus();};
  focusPanel();
}
function verify(){
  progress(1);
  panel.innerHTML=`<span class="pill">NO SMS SENT</span><h3>A quick test verification.</h3><p>For +1 (202) 555-0147, use the demo code <strong>246810</strong>.</p><form id="verify-form"><label for="code">Six-digit test code</label><input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" placeholder="000000" required><button class="primary wide" type="submit">Verify demo number <span>&gt;</span></button></form><p class="fine">This test does not verify a real phone. Five attempts maximum.</p>`;
  const form=document.querySelector('#verify-form');
  document.querySelector('#code').focus({preventScroll:true});
  form.onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{const result=await api('verify',{code:document.querySelector('#code').value});if(!form.isConnected)return;if(result.has_history)await showHistory();else checkout();});};
}
function money(cents){return '$'+(cents/100).toFixed(2);}
function checkout(){
  progress(2);
  panel.innerHTML=`<span class="pill">TEST CHECKOUT · NO PAYMENT DETAILS</span><h3>One report. One simple price.</h3><div class="order"><span>Single lookup report<small>Intended one-time launch price</small></span><strong id="lookup-price">Loading…</strong></div><div id="coupon-discount-row" hidden><div class="order"><span>Coupon discount</span><strong id="coupon-discount"></strong></div></div><div class="order"><span>Intended total<small>Not charged in this demo</small></span><strong id="lookup-total">Loading…</strong></div><div class="order total"><span>Charged today</span><strong>$0.00</strong></div><p>Explore supported sources and guided removal. No subscription. No guaranteed removals or spam reduction.</p><p class="fine">Proposed launch policy: request a voluntary refund within 7 days; the verified original processing fee may be retained, subject to applicable legal and provider exceptions. Final terms are pending. This demo charges and refunds $0.</p><form id="checkout-form"><label for="coupon-code">Coupon code (optional)</label><input id="coupon-code" type="text" maxlength="32" autocomplete="off" spellcheck="false" aria-describedby="coupon-help coupon-status"><small id="coupon-help">Only configured codes can apply. No public coupon offer is active.</small><button id="apply-coupon" class="outline" type="button">Apply code</button><button id="remove-coupon" class="text-button" type="button">Clear code</button><p id="coupon-status" role="status">Checking the server price…</p><label class="check"><input type="checkbox" id="terms" required><span>I understand this is a synthetic report with a test payment. Nothing will be charged.</span></label><button id="complete-checkout" class="primary wide" type="submit" disabled>Complete $0 test checkout <span>&gt;</span></button></form>`;
  const form=document.querySelector('#checkout-form');
  const coupon=document.querySelector('#coupon-code');
  const apply=document.querySelector('#apply-coupon');
  const remove=document.querySelector('#remove-coupon');
  const submit=document.querySelector('#complete-checkout');
  const status=document.querySelector('#coupon-status');
  let quote=null, busy=false, appliedInput='';
  function controls(){
    coupon.disabled=busy||Boolean(quote?.locked);
    apply.disabled=busy||Boolean(quote?.locked);
    remove.disabled=busy||Boolean(quote?.locked);
    submit.disabled=busy||!quote||coupon.value!==appliedInput;
  }
  async function refreshQuote(){
    if(busy)return;
    clearError();busy=true;quote=null;controls();
    const requested=coupon.value;
    status.textContent='Checking the server price…';
    try{
      const result=await api('quote',{coupon_code:requested});
      if(!form.isConnected)return;
      quote=result;appliedInput=requested;
      document.querySelector('#lookup-price').textContent=money(result.list_price_cents);
      document.querySelector('#lookup-total').textContent=money(result.amount_cents);
      document.querySelector('#coupon-discount-row').hidden=result.discount_cents===0;
      document.querySelector('#coupon-discount').textContent='−'+money(result.discount_cents);
      if(result.locked){
        coupon.value=result.coupon_code||'';appliedInput=coupon.value;
        status.textContent='This session already has a test receipt. Its original price is unchanged; continue to reopen that report.';
      }else status.textContent=result.coupon_code?'Code applied: '+result.coupon_code+'. Demo charge remains $0.00.':'No coupon applied. Demo charge remains $0.00.';
    }catch(e){
      if(!form.isConnected)return;
      document.querySelector('#lookup-price').textContent='Unavailable';
      document.querySelector('#lookup-total').textContent='Unavailable';
      document.querySelector('#coupon-discount-row').hidden=true;
      status.textContent=e.message+' Clear the code or try again before checkout.';
    }finally{busy=false;if(form.isConnected)controls();}
  }
  coupon.oninput=()=>{quote=null;document.querySelector('#lookup-total').textContent='Apply or clear code';document.querySelector('#coupon-discount-row').hidden=true;status.textContent='Apply this code or clear it to continue.';controls();};
  apply.onclick=refreshQuote;
  remove.onclick=()=>{coupon.value='';refreshQuote();};
  form.onsubmit=async event=>{
    event.preventDefault();
    if(busy||!quote||coupon.value!==appliedInput)return;
    busy=true;controls();clearError();
    try{
      await api('checkout',{accept:document.querySelector('#terms').checked,coupon_code:quote.coupon_code||''});
      if(form.isConnected)await loadReport();
    }catch(e){if(form.isConnected)error(e.message);}
    finally{busy=false;if(form.isConnected)controls();}
  };
  focusPanel();refreshQuote();
}
async function loadReport(){
  progress(3);const view=viewVersion;
  panel.innerHTML='<div class="loading"><span class="loader"></span><h3>Preparing your example report</h3><p>Loading synthetic fixtures. No websites are being scanned.</p></div>';
  try{const report=await api('report');if(view!==viewVersion)return;currentReport=report;renderReport();}
  catch(e){if(view!==viewVersion)return;panel.innerHTML='<h3>Report unavailable</h3><p>No result has been inferred. Please retry or clear the session.</p><button id="retry" class="outline">Retry report</button>';document.querySelector('#retry').onclick=()=>loadReport();error(e.message);}
}
function renderReport(focusTarget='report'){document.body.classList.add('report-mode');const report=currentReport;progress(3);panel.innerHTML=`<div class="report-heading"><span class="pill">SYNTHETIC REPORT</span><a class="text-button" id="export" href="/api/export" download>Export JSON</a></div><h3 id="report-title" tabindex="-1">Your next steps, in one place.</h3><p>${escape(report.phone)} · Demo only</p><div class="report-summary"><strong>${report.providers.filter(p=>p.status==='example_listing').length} <small>example listings</small></strong><strong>0 <small>live sources checked</small></strong></div><p class="fine">Illustrations, not findings about a real person. No source listing links are available because no live search occurred.</p><div class="report-list">${report.providers.length===0?'<p>This synthetic fixture has no example listings. No live sources were checked.</p>':''}${report.providers.map(p=>`<details class="result"><summary><span class="provider-icon ${p.id==='whitepages'?'lavender':''}">${escape(p.name[0])}</span><span><b>${escape(p.name)}</b><small>${p.status==='example_listing'?'Example listing · guided action':'Not checked · no discovery access'}</small></span><span class="chevron">+</span></summary><div class="result-body"><p class="fine">Live integration disabled. Official destination confirmed from the California registry; current form steps have not been independently verified.</p><ol>${p.steps.map(s=>`<li>${escape(s)}</li>`).join('')}</ol><a class="outline" target="_blank" rel="noopener noreferrer" href="${escape(p.url)}">Open provider removal page (external)</a><p class="fine">Opens an external site without sending your number. Confirm the destination before sharing personal information. Completing a guide is not a confirmed removal.</p></div></details>`).join('')}</div>${removalMarkup(report)}<details class="simulation"><summary>Test a refund request · $0 charged</summary><div class="result-body"><p>Within 7 days of this test checkout, request a $0 demo refund. No provider is contacted. A real refund needs verified original settlement fees and must return through the original payment method.</p><label class="check"><input type="checkbox" id="refund-confirm"><span>I understand this is a test request, not a live refund.</span></label><button class="outline" id="refund-request">Request test refund</button><div id="refund-status" role="status">${report.refund?'Test request received · $0 refundable':'No refund requested'}</div></div></details><button class="outline" id="open-history">View synthetic payment history</button><p class="fine">Only the synthetic provider supports automation in this prototype. Production adapters require verified official support.</p>`;document.querySelector('#open-history').onclick=e=>run(e.target,showHistory);document.querySelector('#refund-request').onclick=e=>run(e.target,async()=>{const r=await api('refund',{confirm:document.querySelector('#refund-confirm').checked});report.refund=r;document.querySelector('#refund-status').textContent='Test request received · $0 refundable';});bindRemoval(report);focusAndReveal(document.querySelector(focusTarget==='removal'?'#review-removal':'#report-title'));}
function statusLabel(s){return ({not_requested:'Not requested',request_submitted:'Synthetic request submitted; removal not verified',outcome_unknown:'Outcome uncertain; do not resubmit'})[s]||'Status unavailable; no removal verified';}
function removalMarkup(report){
  const request=report.removal_request;
  return `<details class="simulation" open><summary>Review removal permission · synthetic listing</summary><div class="result-body" id="removal-flow"><p>This is one fictional listing. No broker API is connected and no external recipient receives data.</p><p class="status-line" role="status">${escape(statusLabel(request?.status||'not_requested'))}</p>${request?`<p>${escape(request.message)}</p><p class="fine">Request: ${escape(request.request_id)}</p>`:''}<button id="review-removal" class="outline">${request?'Check request status':'Review this listing and permission'}</button></div></details>`;
}
function bindRemoval(report){
  const button=document.querySelector('#review-removal');
  let busy=false;
  button.onclick=async()=>{
    if(busy)return;busy=true;
    await run(button,async()=>{
      if(report.removal_request){
        const result=await api('removal/status',{request_id:report.removal_request.request_id});
        if(!button.isConnected||currentReport!==report)return;
        report.removal_request=result;report.removal=result.status;renderReport('removal');return;
      }
      const result=await api('removal/prepare',{provider:report.removal_listing.provider,report_id:report.removal_listing.report_id,listing_id:report.removal_listing.listing_id});
      if(!button.isConnected||currentReport!==report)return;
      if(result.request){report.removal_request=result.request;report.removal=result.request.status;renderReport('removal');return;}
      renderRemovalConsent(report,result);
    });
    busy=false;
  };
}
function renderRemovalConsent(report,preview){
  const flow=document.querySelector('#removal-flow'),d=preview.disclosure;
  flow.innerHTML=`<h4 tabindex="-1">Permission for this listing only</h4><p><strong>${escape(d.label)}</strong><br>Listing: ${escape(d.listing_id)}</p><p><strong>Recipient:</strong> ${escape(d.recipient)}</p><p><strong>Purpose:</strong> ${escape(d.purpose)}</p><p><strong>Exact data used by the local adapter:</strong></p><ul>${d.data.map(field=>`<li>${escape(field.label)}: ${escape(field.value)}</li>`).join('')}</ul><p>${escape(d.scope)}</p><p>${escape(d.consequences)}</p><p>${escape(d.cost)}</p><p class="fine">${escape(d.retention)}</p><p class="fine">${escape(d.cancellation)}</p><p class="fine">Permission screen expires at ${escape(new Date(preview.expires_at*1000).toLocaleTimeString())}. Version: ${escape(d.consent_version)}.</p><form id="removal-consent-form"><label class="check"><input type="checkbox" id="listing-confirm" required><span>I reviewed this exact fictional listing. For a real request, phone control alone would not prove the listing is mine.</span></label><label class="check"><input type="checkbox" id="removal-authorize" required><span>I authorize this one simulated request using only the displayed data, recipient and purpose.</span></label><button type="submit" id="submit-removal" class="outline" disabled>Authorize and submit synthetic request</button><button type="button" id="cancel-removal" class="text-button">Cancel without submitting</button></form>`;
  const form=document.querySelector('#removal-consent-form'),mine=document.querySelector('#listing-confirm'),allow=document.querySelector('#removal-authorize'),submit=document.querySelector('#submit-removal'),cancel=document.querySelector('#cancel-removal');
  let busy=false;
  const controls=()=>{submit.disabled=busy||!mine.checked||!allow.checked;cancel.disabled=busy;mine.disabled=busy;allow.disabled=busy;};
  mine.onchange=controls;allow.onchange=controls;
  focusAndReveal(flow.querySelector('h4'));
  form.onsubmit=async event=>{
    event.preventDefault();if(busy||!mine.checked||!allow.checked)return;
    busy=true;controls();clearError();
    try{
      const result=await api('removal',{provider:d.provider,report_id:d.report_id,listing_id:d.listing_id,consent_id:preview.consent_id,consent_version:d.consent_version,confirm_listing:true,authorize:true});
      if(!form.isConnected||currentReport!==report)return;
      report.removal_request=result;report.removal=result.status;renderReport('removal');
    }catch(e){if(form.isConnected){mine.checked=false;allow.checked=false;error(e.message+' Reload the report to check whether a request exists before retrying.');}}
    finally{busy=false;if(form.isConnected)controls();}
  };
  cancel.onclick=async()=>{
    if(busy)return;busy=true;controls();clearError();
    try{
      await api('removal/cancel',{consent_id:preview.consent_id});
      if(form.isConnected&&currentReport===report)renderReport('removal');
    }catch(e){if(form.isConnected){mine.checked=false;allow.checked=false;error(e.message+' Cancellation could not be confirmed. Clear the session to discard the permission.');}}
    finally{busy=false;if(form.isConnected)controls();}
  };
}
async function clearSession(){
  if(clearing)return;clearing=true;viewVersion++;currentReport=null;clearError();
  const reset=document.querySelector('#reset');reset.disabled=true;
  panel.innerHTML='<h3>Clearing your session…</h3><p>Waiting for any current request to finish before signing out.</p>';
  try{
    await Promise.allSettled([...pendingMutations]);
    // Another tab may have rotated the CSRF token. Refresh it before clearing.
    const session=await api('session');csrfToken=session.csrf_token||'';
    if(session.active)await api('clear',{});
    sessionActive=false;csrfToken='';start();focusPanel();
  }catch(e){
    panel.innerHTML='<h3>Session could not be cleared.</h3><p>The server has not confirmed sign-out. Retry before assuming the session is closed.</p><button id="retry-clear" class="outline" type="button">Retry clear session</button>';
    document.querySelector('#retry-clear').onclick=clearSession;error(e.message);
  }finally{clearing=false;reset.disabled=false;}
}
document.querySelector('#reset').onclick=clearSession;
document.querySelectorAll('a[href="#workspace"]').forEach(link=>link.addEventListener('click',event=>{if(currentReport&&stage===3){event.preventDefault();renderReport();}}));
document.querySelectorAll('a[href="#how"],a[href="#coverage"]').forEach(link=>link.addEventListener('click',()=>document.body.classList.remove('report-mode')));
async function bootstrap(){
  const view=++viewVersion;
  try{
    const session=await api('session');if(view!==viewVersion)return;
    csrfToken=session.csrf_token||'';sessionActive=Boolean(session.active);
    if(session.active&&session.verified&&session.paid){await loadReport();return;}
    if(session.active&&session.verified){if(session.has_history)await showHistory();else checkout();return;}
    if(session.active){verify();return;}
    start();
  }catch(e){if(view!==viewVersion)return;start();error('Session unavailable. Reload to retry.');}
}
bootstrap();

async function checkCurrentSession(){
  if(!sessionActive||clearing)return;const view=viewVersion;
  try{
    const state=await api('session/status');if(view!==viewVersion)return;
    if(!state.active){currentReport=null;csrfToken='';sessionActive=false;progress(1);panel.innerHTML='<h3 tabindex="-1">Session ended</h3><p>Your session expired or this demo user verified in another browser.</p><button id="restart-session" class="outline" type="button">Start again</button>';document.querySelector('#restart-session').onclick=()=>{start();focusPanel();};focusPanel();}
  }catch(e){}
}
window.addEventListener('focus',checkCurrentSession);document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkCurrentSession();});setInterval(checkCurrentSession,15000);

async function showHistory(){clearError();const view=++viewVersion;const result=await api('history');if(view!==viewVersion)return;document.body.classList.add('report-mode');progress(2);currentReport=null;panel.innerHTML=`<span class="pill">SYNTHETIC PAYMENT HISTORY</span><h3 tabindex="-1">Your previous test checkouts</h3><p>Fresh demo verification is required. Receipts persist for 8 days by default so you can return within 7 days after your session expires. Clear session signs out; it does not delete receipts. Real customer authentication is unavailable.</p>${result.payments.length?result.payments.map(p=>`<article class="result result-body"><p>Test checkout · ${escape(new Date(p.created_at*1000).toISOString())} · $0 charged</p><p>${p.eligible?'Within voluntary seven-day window':'Outside voluntary window — exceptions require review'}</p><label class="check"><input type="checkbox" id="confirm-${escape(p.payment_id)}"><span>I understand this is a $0 test refund request.</span></label><button class="outline history-refund" data-payment="${escape(p.payment_id)}">Request test refund</button><p role="status" id="status-${escape(p.payment_id)}">${p.refund?escape(refundLabel(p.refund.status)):'No refund requested'}</p></article>`).join(''):'<p>No retained synthetic checkouts for this verified demo user.</p>'}<button id="new-checkout" class="outline">Start a new test lookup</button><label class="check"><input type="checkbox" id="delete-history-confirm"><span>Delete my synthetic receipts and test refund requests.</span></label><button class="text-button" id="delete-history">Delete synthetic history</button>`;focusPanel();document.querySelectorAll('.history-refund').forEach(button=>button.onclick=()=>run(button,async()=>{const id=button.dataset.payment;const r=await api('refund',{payment_id:id,confirm:document.getElementById('confirm-'+id).checked});document.getElementById('status-'+id).textContent=refundLabel(r.status)+' · $0';}));document.querySelector('#new-checkout').onclick=checkout;document.querySelector('#delete-history').onclick=e=>run(e.target,async()=>{await api('history/delete',{confirm:document.querySelector('#delete-history-confirm').checked});await showHistory();});}

function refundLabel(status){return ({test_request_received:'Test request received',manual_review:'Review required',pending:'Pending',succeeded:'Simulated completion',failed:'Test request failed'})[status]||'Status unavailable';}


// Browser-only input test. Never send personal entries to the fixture API or storage.
function normalizeLocalPhone(value){
    const trimmed=String(value).trim();
    if(!/^\+[0-9\s().-]+$/.test(trimmed))return null;
    const normalized=trimmed.replace(/[\s().-]/g,'');
    return /^\+[1-9][0-9]{7,14}$/.test(normalized)?normalized:null;
}
// Clear personal input and all report/permission content before back/forward caching.
window.addEventListener('pagehide',()=>{viewVersion++;currentReport=null;const entry=document.querySelector('#phone');if(entry)entry.value='';panel.textContent='';});
window.addEventListener('pageshow',event=>{if(event.persisted){currentReport=null;bootstrap();}});
