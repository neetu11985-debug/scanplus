'use strict';
function searchDiagnosticMarkup(diagnostic){
  if(!diagnostic||typeof diagnostic!=='object'||Array.isArray(diagnostic))return '';
  const labels={"timeout":"The provider request timed out.","dns_error":"The provider hostname could not be resolved.","tls_certificate_error":"TLS certificate verification failed.","tls_error":"A secure TLS connection could not be completed.","network_permission_denied":"A permission restriction denied the network operation.","connection_refused":"The connection was refused.","connection_closed":"The connection closed before a usable response arrived.","network_error":"A network operation failed.","http_protocol_error":"The HTTP response could not be read correctly.","response_incomplete":"The provider response was incomplete.","response_too_large":"The provider response exceeded the size limit.","invalid_json":"The provider response was not valid JSON.","invalid_response":"The provider response did not have the expected structure.","http_error":"The provider returned an unusable HTTP status.","not_dispatched":"The query was not sent because an allowance or safety gate blocked it.","not_attempted_after_provider_error":"The query was not attempted after an earlier provider failure.","transport_error":"The request failed for an unclassified transport reason."};
  const category=typeof diagnostic.category==='string'&&Object.prototype.hasOwnProperty.call(labels,diagnostic.category)?diagnostic.category:'transport_error';
  const status=Number.isInteger(diagnostic.http_status)&&diagnostic.http_status>=100&&diagnostic.http_status<=599?diagnostic.http_status:'status unavailable';
  return '<p class="fine">Search diagnostic: '+labels[category]+' HTTP '+status+'. No automatic retry occurred.</p>';
}
// End search diagnostics.

const panel=document.querySelector('#panel'),title=document.querySelector('#stage-title'),error=document.querySelector('#error'),clear=document.querySelector('#clear');
let csrf='',busy=false,generation=0,expiryTimer=null,expiryAt=0;
// The country selector is US-only. Never trim an overlong entry or infer a country.
function normalizeUsPhone(value){
  return typeof value==='string' && /^[0-9]{10}$/.test(value) ? '+1'+value : null;
}
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function verificationDiagnosticMarkup(diagnostic){
  if(!diagnostic || typeof diagnostic!=='object')return '';
  const status=Number.isInteger(diagnostic.http_status) && diagnostic.http_status>=100 && diagnostic.http_status<=599 ? diagnostic.http_status : null;
  const code=status!==null && status>=300 && Number.isInteger(diagnostic.twilio_error_code) && diagnostic.twilio_error_code>=1 && diagnostic.twilio_error_code<=999999 ? diagnostic.twilio_error_code : null;
  return '<p class="fine" role="status">Last verification diagnostic: HTTP '+(status===null?'status unavailable':status)+'; Twilio error code '+(code===null?'unavailable':code)+'. Only these numeric fields are retained for this session. They do not establish whether an SMS was delivered or charged.</p>';
}
function clearExpiry(){if(expiryTimer!==null)clearTimeout(expiryTimer);expiryTimer=null;expiryAt=0;}
function expireView(){
  generation++;clearExpiry();busy=false;
  document.querySelectorAll('input').forEach(input=>{input.value='';if(input.type==='checkbox')input.checked=false;});
  panel.textContent='This self-test expired. Reload to check your current session before another action.';
  title.textContent='Session expired';error.hidden=true;clear.disabled=false;
}
function expiryFor(state){
  clearExpiry();
  if(!Number.isFinite(state.expires_in_ms))return true;
  if(state.phase==='entry')return true;
  if(state.expires_in_ms<=0){expireView();return false;}
  const remaining=Math.min(state.expires_in_ms,300000);
  expiryAt=performance.now()+remaining;expiryTimer=setTimeout(expireView,remaining);return true;
}
async function request(path,data){
  const started=performance.now(),controller=new AbortController(),timer=setTimeout(()=>controller.abort(),path==='scan'?30000:10000);
  try{
    const response=await fetch('/api/'+path,{method:data?'POST':'GET',cache:'no-store',credentials:'same-origin',signal:controller.signal,headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:data?JSON.stringify(data):undefined});
    let result;
    try{
      result=await response.json();
      if(!result||typeof result!=='object'||Array.isArray(result))throw Error();
    }catch(_){
      throw Error('The server returned an unreadable response. The operation may have completed. Reload to check its state; do not repeat it.');
    }
    // Subtract the entire round trip conservatively. A delayed response must not
    // restore a report or challenge after the server's remaining lifetime.
    const elapsed=Math.max(0,performance.now()-started);
    for(const state of [result,result.state])if(state&&Number.isFinite(state.expires_in_ms))state.expires_in_ms=Math.max(0,state.expires_in_ms-elapsed);
    if(!response.ok){const problem=Error(result.error||'Operation was not confirmed. Reload to check before trying again.');problem.state=result.state;throw problem;}
    return result;
  }catch(problem){if(problem.name==='AbortError')throw Error('The response timed out. A provider operation may have completed. Reload to check its state; do not repeat it.');throw problem;}
  finally{clearTimeout(timer);}
}
function revealError(){
  const view=generation,message=error.textContent;
  const reveal=()=>{
    if(view!==generation||error.hidden||error.textContent!==message)return;
    error.tabIndex=-1;error.focus?.({preventScroll:true});
    error.scrollIntoView?.({block:'center',behavior:'auto'});
  };
  reveal();
  // Recheck after the replacement panel has laid out. Never focus a stale alert.
  if(typeof requestAnimationFrame==='function')requestAnimationFrame(()=>requestAnimationFrame(reveal));
}
async function act(operation){
  if(busy)return;
  const view=generation;busy=true;error.hidden=true;clear.disabled=true;panel.querySelectorAll('button').forEach(button=>button.disabled=true);
  try{const state=await operation();if(view!==generation)return;if(state.csrf_token)csrf=state.csrf_token;render(state);
    if(state.checkout_url&&view===generation){
      const target=privateCheckoutUrl(state.checkout_url);
      if(!target||!Number.isFinite(state.expires_in_ms)||state.expires_in_ms<=0)throw Error('Stripe test redirect was not validated. No navigation occurred.');
      location.assign(target);
    }
  }
  catch(problem){if(view!==generation)return;if(problem.state)render(problem.state);if(view!==generation)return;error.textContent=problem.message;error.hidden=false;revealError();}
  finally{if(view===generation){busy=false;clear.disabled=false;panel.querySelectorAll('button').forEach(button=>button.disabled=false);}}
}
function privateCheckoutUrl(value){
  if(typeof value!=='string'||value.length>4096||/[\s\\\x00-\x1f\x7f]/.test(value))return null;
  try{const url=new URL(value);return url.protocol==='https:'&&url.hostname==='checkout.stripe.com'&&!url.port&&!url.username&&!url.password?url.href:null;}catch(_){return null;}
}
function render(state){
  if(!expiryFor(state))return;
  const privateTest=state.test_scope==='private_owner';
  const provider=state.search_provider;
  const providerName={serper:'Serper (Google Search results)',brave:'Brave Search'}[provider];
  title.textContent=({entry:'1. Verify your own number',code:'2. Enter the SMS code',checkout:'3. Complete the Stripe test',verified:state.checkout_test?.enabled?'4. Approve the live search':'3. Approve the live search',report:'Your live search report',start_uncertain:'SMS status needs review',scanning:'Search in progress'})[state.phase]||'Local test';
  if(state.phase==='entry'&&state.test_scope==='private_owner'&&(state.sms_allowance_remaining===0||state.allowance_blocked)){
    panel.textContent='This private test allowance is used or unavailable. Clear, reload or server restart does not authorize another provider request. Ask the operator to review the durable run allowance before any new test.';
    return;
  }
  if(state.phase==='entry'){
    panel.innerHTML='<form id="phone-form" autocomplete="off"><div class="phone-entry"><div><label for="country-code">Country</label><select id="country-code" aria-describedby="phone-help"><option value="+1">US (+1)</option></select></div><div><label for="phone">Your phone number</label><input id="phone" type="tel" autocomplete="off" inputmode="numeric" maxlength="32" pattern="[0-9]{10}" placeholder="2025550147" title="Enter exactly 10 digits without the country code." aria-describedby="phone-help" required></div></div><p id="phone-help" class="fine">Enter 10 digits only. US (+1) is added automatically.</p><label class="check"><input id="own" type="checkbox" required><span>This is my own number, and I can receive its SMS messages.</span></label><label class="check"><input id="twilio" type="checkbox" required><span>I authorize sending this number to Twilio to send one verification SMS and check the code I enter. I have confirmed sufficient no-card trial allowance in this Twilio account. No paid usage or top-up is authorized.</span></label><button class="primary" type="submit">Send real verification SMS</button></form><p class="fine">No search happens at this step. Only proceed after confirming no-card trial eligibility and allowance, and reviewing the setup instructions.</p>';
    document.querySelector('#phone-form').onsubmit=event=>{event.preventDefault();if(busy)return;const input=document.querySelector('#phone');const phone=normalizeUsPhone(input.value);if(!phone){error.textContent='Enter exactly 10 digits without the country code. US (+1) is added automatically.';error.hidden=false;input.focus();return;}const data={phone,own_number:document.querySelector('#own').checked,twilio_consent:document.querySelector('#twilio').checked};input.value='';act(()=>request('start',data));};
  }else if(state.phase==='code'){
    panel.innerHTML=verificationDiagnosticMarkup(state.verification_diagnostic)+'<p>SMS verification started for the number ending '+escape(state.last_four)+'. Enter the code received. The challenge expires after 5 minutes; at most 5 checks are allowed.</p><form id="code-form" autocomplete="off"><label for="code">Verification code</label><input id="code" type="text" inputmode="numeric" autocomplete="off" pattern="[0-9]{4,10}" maxlength="10" required><button class="primary" type="submit">Verify with Twilio</button></form><p class="fine">'+(privateTest?'This run permits one SMS only. Clear ends this test and cannot authorize a resend. Ask the operator to review the allowance before any new test.':'No automatic SMS resend. Clear the test before deliberately trying again.')+'</p>';
    document.querySelector('#code-form').onsubmit=event=>{event.preventDefault();if(busy)return;const input=document.querySelector('#code');const code=input.value;input.value='';act(()=>request('verify',{code}));};
  }else if(state.phase==='checkout'&&state.checkout_test?.enabled){
    const checkout=state.checkout_test;
    const labels={not_started:'Not started',pending:'Awaiting server-confirmed test completion',uncertain:'Previous test request needs review',blocked:'Validation failed; operator review required',expired:'Test checkout expired',cleared:'Test checkout access was cleared',paid_test:'Card test completed',complimentary_test:'No-payment coupon test completed'};
    const chooseCoupon=checkout.coupon_available&&checkout.state==='not_started';
    panel.innerHTML='<p>Twilio verified your number. Complete this private Stripe test before search. <strong>No real charge is possible.</strong></p><p>Test checkout: '+escape(labels[checkout.state]||'Needs review')+'. Base test price before any coupon: $1.49 USD.</p><p class="fine">Stripe receives only the test-order reference, price and return URL, not your phone number or report. Use official test card <strong>4242 4242 4242 4242</strong>, a future expiry and any three-digit test CVC. Never use a real card or real billing details.</p><form id="checkout-form"><label class="check"><input id="accept-test-checkout" type="checkbox" required><span>I approve opening Stripe TEST Checkout using synthetic payment details. This is not a real purchase.</span></label>'+(chooseCoupon?'<label for="test-coupon">Owner-provided 100% test coupon (optional)</label><input id="test-coupon" type="text" autocomplete="off" maxlength="64"><p class="fine">Use the coupon for a separate no-payment test. It does not validate a card payment.</p>':(checkout.state!=='not_started'?'<p class="fine">The reserved test choice is locked: '+(checkout.discount_cents===149?'100% coupon, $0.00 USD':'card test, $1.49 USD')+'. Reopening resumes that same order. A different variant requires a separate approved test run.</p>':'<p class="fine">A test coupon is not configured. Do not invent a code or enter a real card.</p>'))+'<button type="submit" class="primary">Open Stripe test checkout</button></form><button type="button" id="check-test-payment">Check test completion with Stripe</button><p class="fine">After Stripe returns you here, choose Check test completion. Return URLs are not payment proof. There is no automatic check or retry. The original five-minute session still applies; expired or cleared access cannot be recovered by a late checkout.</p>';
    document.querySelector('#checkout-form').onsubmit=event=>{
      event.preventDefault();if(busy)return;
      const data={accept_test:document.querySelector('#accept-test-checkout').checked};
      const coupon=chooseCoupon?document.querySelector('#test-coupon'):null;
      if(coupon&&coupon.value){data.coupon_code=coupon.value;coupon.value='';}
      act(()=>request('checkout/create',data));
    };
    document.querySelector('#check-test-payment').onclick=()=>act(()=>request('checkout/reconcile',{}));
  }else if(state.phase==='verified'){
    if(!providerName){panel.textContent='Search provider is not confirmed. Reload or review setup before proceeding.';return;}
    const planText=provider==='serper'?'I have confirmed active free credits in this Serper account. These queries consume those credits; no paid top-up is authorized.':'I have confirmed sufficient approved free allowance in this Brave account. No paid usage or top-up is authorized.';
    panel.innerHTML='<p>Twilio approved current control of the number ending '+escape(state.last_four)+'.</p>'+(state.checkout_test?.enabled?'<p>Stripe test completion was confirmed by the server. No real payment was collected.</p>':'')+'<p>ScanPlus will make 3 exact-number queries through '+escape(providerName)+', one each for Spokeo, TruePeopleSearch, and Whitepages. It checks up to 10 indexed results per query. It does not directly search those broker databases or visit returned pages.</p><form id="scan-form"><label class="check"><input id="search-consent" type="checkbox" required><span>I authorize sending my phone number to '+escape(providerName)+' for these 3 queries. '+planText+'</span></label><button class="primary" type="submit">Run real self-test scan</button></form><p class="fine">An absent indexed match does not prove your number is absent online. SMS verification is not consent to search; this confirmation is separate. No automatic provider fallback or retries.</p>';
    document.querySelector('#scan-form').onsubmit=event=>{event.preventDefault();if(busy)return;act(()=>request('scan',{[provider+'_consent']:document.querySelector('#search-consent').checked}));};
  }else if(state.phase==='report'){
    const report=state.report;
    const count=report.sources.reduce((total,source)=>total+source.candidates.length,0);
    panel.innerHTML='<div class="report-tools"><a class="button-link" href="/api/export.pdf" download>Download PDF report</a><a href="/api/export.txt" download>Plain-text alternative</a></div><p class="summary"><strong>'+escape(report.sources_checked)+' of '+escape(report.sources.length)+'</strong> source queries returned usable responses.</p><p>'+escape(count)+' potential '+(count===1?'match':'matches')+'. Confirm each listing before using its official removal guide.</p><p class="fine">'+escape(report.privacy_notice||'Downloads may contain personal information in listing URLs and remain on your device after this session expires.')+'</p>'+report.sources.map(source=>'<article><h3>'+escape(source.site)+'</h3><p class="status">'+escape(({match_needs_confirmation:'Potential matches: your confirmation is required',not_found_in_checked_sources:'No exact phone match in the checked indexed results',source_unavailable:'Source unavailable: no absence conclusion'})[source.status]||'Unknown outcome: no absence conclusion')+'</p><p class="fine">'+(source.query_attempted===false?'Query not attempted':'Checked '+escape(source.checked_at))+(source.reason?' · '+escape(source.reason.replaceAll('_',' ')):'')+'</p>'+searchDiagnosticMarkup(source.search_diagnostic)+(source.candidates.length?'<ul class="listing-list">'+source.candidates.map(candidateMarkup).join('')+'</ul>':'')+guideMarkup(source.guide)+'</article>').join('')+'<p>'+escape(report.coverage)+'</p><p class="fine">'+escape(report.removal_notice||'No removal was submitted or verified by ScanPlus.')+'</p><p class="fine">Opening a result contacts that website. A listing URL may itself contain your number; do not open it unless you want to share that request with the site. ScanPlus never opens results automatically.</p>';
    panel.querySelectorAll('[data-review]').forEach(button=>button.onclick=()=>{
      if(busy)return;
      const action=button.dataset.review,id=button.dataset.candidate;
      const confirmed=action!=='record_manual_request'||document.querySelector('#manual-confirm-'+id).checked;
      act(()=>request('listing/review',{candidate_id:id,action,confirmed}));
    });
  }else if(state.phase==='start_uncertain'){
    panel.innerHTML='<p>A verification SMS may have been sent, but its state was not confirmed. No search took place and the number was not retained. '+(privateTest?'Ask the operator to review the Twilio account and durable allowance. Clear, reload or restart cannot authorize another SMS for this run.':'Check your Twilio account before clearing and retrying.')+' There is no automatic retry.</p>'+verificationDiagnosticMarkup(state.verification_diagnostic);
  }else{
    panel.innerHTML='<p>Check the current state by reloading. Do not start another test until the previous operation is resolved.</p>';
  }
}

function candidateMarkup(candidate){
  const review={needs_confirmation:'Not yet confirmed as yours',confirmed_by_user:'You confirmed this is your listing',not_mine:'You marked this as not your listing'}[candidate.match_review]||'Not yet confirmed as yours';
  let actions='';
  if(candidate.id){
    const id=escape(candidate.id);
    const button=(action,label)=>'<button type="button" data-review="'+action+'" data-candidate="'+id+'">'+label+'</button>';
    if(candidate.match_review==='confirmed_by_user'){
      actions=candidate.manual_action==='user_recorded_request'?'<p class="status">You recorded a manual request. Removal has not been verified.</p>':'<label class="check"><input type="checkbox" id="manual-confirm-'+id+'"><span>I submitted a request myself on the official site. This only updates my test checklist.</span></label>'+button('record_manual_request','Record my manual request');
      actions+=button('reset','Reset my checklist');
    }else if(candidate.match_review==='not_mine'){
      actions='<p class="fine">Do not request removal of this record.</p>'+button('reset','Review again');
    }else{
      actions=button('confirm_mine','I confirm this listing is mine')+button('not_mine','This is not my listing');
    }
  }
  return '<li><a href="'+escape(candidate.source_url)+'" target="_blank" rel="noopener noreferrer">'+escape(candidate.source_url)+'</a><p class="fine">'+escape(candidate.evidence)+'</p><p class="status">'+escape(review)+'</p><div class="listing-actions">'+actions+'</div></li>';
}
function guideMarkup(guide){
  if(!guide)return '';
  return '<details class="manual-guide"><summary>Manual removal instructions for '+escape(guide.name)+'</summary><p class="fine">Official destination confirmed from the California registry. Current form steps have not been independently verified.</p><p>'+escape(guide.safety_notice)+'</p><ol>'+guide.steps.map(step=>'<li>'+escape(step)+'</li>').join('')+'</ol><a class="button-link" href="'+escape(guide.url)+'" target="_blank" rel="noopener noreferrer">Open official privacy / opt-out page</a><p class="fine">'+escape(guide.verification_notice)+'</p><p>'+escape(guide.follow_up)+'</p><p class="fine">'+escape(guide.automation_notice)+'</p><p class="fine"><a href="'+escape(guide.source_url)+'" target="_blank" rel="noopener noreferrer">California registry evidence</a> · Registry updated '+escape(guide.registry_updated)+' · Reviewed '+escape(guide.reviewed_at)+'</p></details>';
}

clear.onclick=()=>act(()=>request('clear',{}));
window.addEventListener('pagehide',()=>{generation++;clearExpiry();busy=false;document.querySelectorAll('input').forEach(input=>{input.value='';if(input.type==='checkbox')input.checked=false;});panel.textContent='';csrf='';});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
function checkExpiry(){if(expiryAt&&performance.now()>=expiryAt)expireView();}
window.addEventListener('focus',checkExpiry);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkExpiry();});
act(()=>request('session'));
