const panel=document.querySelector('#panel'), alertBox=document.querySelector('#alert');
let stage=1, currentReport=null, csrfToken='';
const phone='+12025550147';
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function progress(n){stage=n;for(let i=1;i<=3;i++){const el=document.querySelector('#step'+i);el.classList.toggle('active',i===n);el.classList.toggle('done',i<n);if(i===n)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');}}
function error(message){alertBox.textContent=message;alertBox.hidden=false;}
function clearError(){alertBox.hidden=true;}
async function api(path,data){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),10000);try{const response=await fetch('/api/'+path,{method:data?'POST':'GET',signal:controller.signal,headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrfToken}:{},body:data?JSON.stringify(data):undefined});const result=await response.json();if(!response.ok)throw Error(result.error||'Something went wrong. Please try again.');return result;}catch(e){if(e.name==='AbortError')throw Error('Request timed out. Reload to check your session before retrying.');throw e;}finally{clearTimeout(timer);}}
async function run(button,fn){clearError();button.disabled=true;const label=button.textContent;button.textContent='Working…';try{await fn();}catch(e){error(e.message);}finally{if(button.isConnected){button.disabled=false;button.textContent=label;}}}
function start(){document.body.classList.remove('report-mode');progress(1);panel.innerHTML=`<span class="pill">TEST VERIFICATION</span><h3>Start with your number.</h3><p>Try our reserved example. Real phone numbers are disabled.</p><form id="start-form"><label for="phone">Phone number</label><input id="phone" name="phone" type="tel" value="+1 (202) 555-0147" readonly aria-describedby="phone-help"><small id="phone-help">United States · synthetic fixture only</small><label class="check"><input type="checkbox" id="control" required><span>I’m using the synthetic number for this demo. In a live lookup I must control the number.</span></label><button class="primary wide" type="submit">Continue to verification <span>→</span></button></form><p class="fine">No SMS will be sent. No real ownership is verified in this demo.</p>`;document.querySelector('#start-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{const started=await api('start',{phone,consent:document.querySelector('#control').checked});csrfToken=started.csrf_token;verify();});};}
function verify(){progress(1);panel.innerHTML=`<span class="pill">NO SMS SENT</span><h3>A quick test verification.</h3><p>For +1 (202) 555-0147, use the demo code <strong>246810</strong>.</p><form id="verify-form"><label for="code">Six-digit test code</label><input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" placeholder="000000" required><button class="primary wide" type="submit">Verify demo number <span>→</span></button></form><p class="fine">This test does not verify a real phone. Five attempts maximum.</p>`;document.querySelector('#code').focus({preventScroll:true});document.querySelector('#verify-form').onsubmit=e=>{e.preventDefault();run(e.submitter,async()=>{const result=await api('verify',{code:document.querySelector('#code').value});if(result.has_history)await showHistory();else checkout();});};}
function money(cents){return '$'+(cents/100).toFixed(2);}
function checkout(){
  progress(2);
  panel.innerHTML=`<span class="pill">TEST CHECKOUT · NO PAYMENT DETAILS</span><h3>One report. One simple price.</h3><div class="order"><span>Single lookup report<small>Intended one-time launch price</small></span><strong id="lookup-price">Loading…</strong></div><div id="coupon-discount-row" hidden><div class="order"><span>Coupon discount</span><strong id="coupon-discount"></strong></div></div><div class="order"><span>Intended total<small>Not charged in this demo</small></span><strong id="lookup-total">Loading…</strong></div><div class="order total"><span>Charged today</span><strong>$0.00</strong></div><p>Explore supported sources and guided removal. No subscription. No guaranteed removals or spam reduction.</p><p class="fine">Proposed launch policy: request a voluntary refund within 7 days; the verified original processing fee may be retained, subject to applicable legal and provider exceptions. Final terms are pending. This demo charges and refunds $0.</p><form id="checkout-form"><label for="coupon-code">Coupon code (optional)</label><input id="coupon-code" type="text" maxlength="32" autocomplete="off" spellcheck="false" aria-describedby="coupon-help coupon-status"><small id="coupon-help">Only configured codes can apply. No public coupon offer is active.</small><button id="apply-coupon" class="outline" type="button">Apply code</button><button id="remove-coupon" class="text-button" type="button">Clear code</button><p id="coupon-status" role="status">Checking the server price…</p><label class="check"><input type="checkbox" id="terms" required><span>I understand this is a synthetic report with a test payment. Nothing will be charged.</span></label><button id="complete-checkout" class="primary wide" type="submit" disabled>Complete $0 test checkout <span>→</span></button></form>`;
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
  refreshQuote();
}
async function loadReport(){progress(3);panel.innerHTML='<div class="loading"><span class="loader"></span><h3>Preparing your example report</h3><p>Loading synthetic fixtures. No websites are being scanned.</p></div>';try{currentReport=await api('report');renderReport();}catch(e){panel.innerHTML='<h3>Report unavailable</h3><p>No result has been inferred. Please retry or clear the session.</p><button id="retry" class="outline">Retry report</button>';document.querySelector('#retry').onclick=()=>loadReport();error(e.message);}}
function renderReport(){const entering=!document.body.classList.contains('report-mode');document.body.classList.add('report-mode');const report=currentReport;progress(3);panel.innerHTML=`<div class="report-heading"><span class="pill">SYNTHETIC REPORT</span><a class="text-button" id="export" href="/api/export" download>Export JSON ↗</a></div><h3 id="report-title" tabindex="-1">Your next steps, in one place.</h3><p>${escape(report.phone)} · Demo only</p><div class="report-summary"><strong>${report.providers.filter(p=>p.status==='example_listing').length} <small>example listings</small></strong><strong>0 <small>live sources checked</small></strong></div><p class="fine">Illustrations, not findings about a real person. No source listing links are available because no live search occurred.</p><div class="report-list">${report.providers.length===0?'<p>This synthetic fixture has no example listings. No live sources were checked.</p>':''}${report.providers.map(p=>`<details class="result"><summary><span class="provider-icon ${p.id==='whitepages'?'lavender':''}">${escape(p.name[0])}</span><span><b>${escape(p.name)}</b><small>${p.status==='example_listing'?'Example listing · guided action':'Not checked · no discovery access'}</small></span><span class="chevron">+</span></summary><div class="result-body"><p class="fine">Live integration disabled. Official destination confirmed from the California registry; current form steps have not been independently verified.</p><ol>${p.steps.map(s=>`<li>${escape(s)}</li>`).join('')}</ol><a class="outline" target="_blank" rel="noopener noreferrer" href="${escape(p.url)}">Open provider removal page ↗</a><p class="fine">Opens an external site without sending your number. Confirm the destination before sharing personal information. Completing a guide is not a confirmed removal.</p></div></details>`).join('')}</div><details class="simulation" ${report.removal!=='not_requested'?'open':''}><summary>Explore automatic removal · synthetic provider</summary><div class="result-body"><p>This fictional provider demonstrates the authorization and status flow. No real provider receives a request.</p><label class="check"><input type="checkbox" id="authorize" ${report.removal!=='not_requested'?'checked disabled':''}><span>I authorize this simulated request for the synthetic number only.</span></label><div class="status-line" role="status">${statusLabel(report.removal)}</div><button id="simulate" class="outline" ${report.removal==='removal_confirmed'?'disabled':''}>${report.removal==='not_requested'?'Submit simulated request':report.removal==='removal_confirmed'?'Simulation complete':'Check simulated status'}</button></div></details><details class="simulation"><summary>Test a refund request · $0 charged</summary><div class="result-body"><p>Within 7 days of this test checkout, request a $0 demo refund. No provider is contacted. A real refund needs verified original settlement fees and must return through the original payment method.</p><label class="check"><input type="checkbox" id="refund-confirm"><span>I understand this is a test request, not a live refund.</span></label><button class="outline" id="refund-request">Request test refund</button><div id="refund-status" role="status">${report.refund?'Test request received · $0 refundable':'No refund requested'}</div></div></details><button class="outline" id="open-history">View synthetic payment history</button><p class="fine">Only the synthetic provider supports automation in this prototype. Production adapters require verified official support.</p>`;document.querySelector('#open-history').onclick=e=>run(e.target,showHistory);document.querySelector('#refund-request').onclick=e=>run(e.target,async()=>{const r=await api('refund',{confirm:document.querySelector('#refund-confirm').checked});report.refund=r;document.querySelector('#refund-status').textContent='Test request received · $0 refundable';});document.querySelector('#simulate').onclick=e=>run(e.target,async()=>{const first=report.removal==='not_requested';if(first&&!document.querySelector('#authorize').checked)throw Error('Authorize the simulated request first.');const r=await api(first?'removal':'removal/status',first?{provider:'fixture',authorize:true}:{});report.removal=r.status;renderReport();});if(entering){const heading=document.querySelector('#report-title');heading.focus({preventScroll:true});heading.scrollIntoView({block:'start'});}}
function statusLabel(s){return ({not_requested:'Not requested',request_submitted:'Demo: request submitted — not removed',pending:'Demo: pending provider processing — not removed',removal_confirmed:'Simulated completion — nothing submitted or removed'})[s]||'Status unavailable';}
document.querySelector('#reset').onclick=e=>run(e.target,async()=>{try{await api('clear',{});}catch(e){if(!e.message.includes('expired'))throw e;}currentReport=null;csrfToken='';start();const heading=panel.querySelector('h3');heading.tabIndex=-1;heading.focus({preventScroll:true});heading.scrollIntoView({block:'start'});});
document.querySelectorAll('a[href="#workspace"]').forEach(link=>link.addEventListener('click',event=>{if(currentReport&&stage===3){event.preventDefault();renderReport();}}));
document.querySelectorAll('a[href="#how"],a[href="#coverage"]').forEach(link=>link.addEventListener('click',()=>document.body.classList.remove('report-mode')));
async function bootstrap(){try{const session=await api('session');csrfToken=session.csrf_token||'';if(session.active&&session.verified&&session.paid){await loadReport();return;}if(session.active&&session.verified){if(session.has_history)await showHistory();else checkout();return;}if(session.active){verify();return;}}catch(e){error('Session unavailable. Reload to retry.');}start();}
bootstrap();

async function checkCurrentSession(){if(stage===1)return;try{const state=await api('session/status');if(!state.active){currentReport=null;csrfToken='';stage=1;panel.innerHTML='<h3 tabindex="-1">Session ended</h3><p>Your session expired or this demo user verified in another browser. Reload to sign in again.</p>';panel.querySelector('h3').focus();}}catch(e){}}
window.addEventListener('focus',checkCurrentSession);document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkCurrentSession();});setInterval(checkCurrentSession,15000);

async function showHistory(){clearError();const result=await api('history');document.body.classList.add('report-mode');progress(2);currentReport=null;panel.innerHTML=`<span class="pill">SYNTHETIC PAYMENT HISTORY</span><h3 tabindex="-1">Your previous test checkouts</h3><p>Fresh demo verification is required. Receipts persist for 8 days by default so you can return within 7 days after your session expires. Clear session signs out; it does not delete receipts. Real customer authentication is unavailable.</p>${result.payments.length?result.payments.map(p=>`<article class="result result-body"><p>Test checkout · ${escape(new Date(p.created_at*1000).toISOString())} · $0 charged</p><p>${p.eligible?'Within voluntary seven-day window':'Outside voluntary window — exceptions require review'}</p><label class="check"><input type="checkbox" id="confirm-${escape(p.payment_id)}"><span>I understand this is a $0 test refund request.</span></label><button class="outline history-refund" data-payment="${escape(p.payment_id)}">Request test refund</button><p role="status" id="status-${escape(p.payment_id)}">${p.refund?escape(refundLabel(p.refund.status)):'No refund requested'}</p></article>`).join(''):'<p>No retained synthetic checkouts for this verified demo user.</p>'}<button id="new-checkout" class="outline">Start a new test lookup</button><label class="check"><input type="checkbox" id="delete-history-confirm"><span>Delete my synthetic receipts and test refund requests.</span></label><button class="text-button" id="delete-history">Delete synthetic history</button>`;panel.querySelector('h3').focus();panel.querySelector('h3').scrollIntoView({block:'start'});document.querySelectorAll('.history-refund').forEach(button=>button.onclick=()=>run(button,async()=>{const id=button.dataset.payment;const r=await api('refund',{payment_id:id,confirm:document.getElementById('confirm-'+id).checked});document.getElementById('status-'+id).textContent=refundLabel(r.status)+' · $0';}));document.querySelector('#new-checkout').onclick=checkout;document.querySelector('#delete-history').onclick=e=>run(e.target,async()=>{await api('history/delete',{confirm:document.querySelector('#delete-history-confirm').checked});await showHistory();});}

function refundLabel(status){return ({test_request_received:'Test request received',manual_review:'Review required',pending:'Pending',succeeded:'Simulated completion',failed:'Test request failed'})[status]||'Status unavailable';}


// Browser-only input test. Never send personal entries to the fixture API or storage.
function normalizeLocalPhone(value){
    const trimmed=String(value).trim();
    if(!/^\+[0-9\s().-]+$/.test(trimmed))return null;
    const normalized=trimmed.replace(/[\s().-]/g,'');
    return /^\+[1-9][0-9]{7,14}$/.test(normalized)?normalized:null;
}
const localNumberForm=document.querySelector('#local-number-form');
const localPhone=document.querySelector('#local-phone');
const localNumberStatus=document.querySelector('#local-number-status');
const localNumberDetails=document.querySelector('#local-number-test');
function clearLocalPhone(){localPhone.value='';localNumberStatus.textContent='';}
localNumberForm.addEventListener('submit',event=>{
    event.preventDefault();
    const normalized=normalizeLocalPhone(localPhone.value);
    if(!normalized){
        localNumberStatus.textContent='Enter + followed by your country code and 8–15 digits in total. Extensions are not supported. No lookup was performed.';
        return;
    }
    localPhone.value='';
    localNumberStatus.textContent='Format accepted for a number ending '+normalized.slice(-4)+'. Your entry has been cleared. No online lookup or ownership verification was performed.';
});
document.querySelector('#local-number-clear').addEventListener('click',()=>{clearLocalPhone();localPhone.focus();});
localNumberDetails.addEventListener('toggle',()=>{if(!localNumberDetails.open)clearLocalPhone();});
window.addEventListener('pagehide',clearLocalPhone);
