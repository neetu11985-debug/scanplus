'use strict';
const panel=document.querySelector('#panel'),title=document.querySelector('#stage-title'),error=document.querySelector('#error'),clear=document.querySelector('#clear');
let csrf='',busy=false;
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
async function request(path,data){
  const response=await fetch('/api/'+path,{method:data?'POST':'GET',cache:'no-store',credentials:'same-origin',headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:data?JSON.stringify(data):undefined});
  const result=await response.json();
  if(!response.ok){if(result.state)render(result.state);throw Error(result.error||'Operation was not confirmed. Reload to check before trying again.');}
  if(result.csrf_token)csrf=result.csrf_token;
  return result;
}
async function act(operation){
  if(busy)return;
  busy=true;error.hidden=true;clear.disabled=true;panel.querySelectorAll('button').forEach(button=>button.disabled=true);
  try{render(await operation());}
  catch(problem){error.textContent=problem.message;error.hidden=false;}
  finally{busy=false;clear.disabled=false;panel.querySelectorAll('button').forEach(button=>button.disabled=false);}
}
function render(state){
  const provider=state.search_provider;
  const providerName={serper:'Serper (Google Search results)',brave:'Brave Search'}[provider];
  title.textContent=({entry:'1. Verify your own number',code:'2. Enter the SMS code',verified:'3. Approve the live search',report:'Your live search report',start_uncertain:'SMS status needs review',scanning:'Search in progress'})[state.phase]||'Local test';
  if(state.phase==='entry'){
    panel.innerHTML='<form id="phone-form" autocomplete="off"><div class="phone-entry"><div><label for="country-code">Country</label><select id="country-code" aria-describedby="phone-help"><option value="+1">US (+1)</option></select></div><div><label for="phone">Your phone number</label><input id="phone" type="tel" autocomplete="off" inputmode="numeric" maxlength="32" pattern="[0-9]{10}" placeholder="2025550147" title="Enter exactly 10 digits without the country code." aria-describedby="phone-help" required></div></div><p id="phone-help" class="fine">Enter 10 digits only. US (+1) is added automatically.</p><label class="check"><input id="own" type="checkbox" required><span>This is my own number, and I can receive its SMS messages.</span></label><label class="check"><input id="twilio" type="checkbox" required><span>I authorize sending this number to Twilio to send one verification SMS and check the code I enter. I have confirmed sufficient no-card trial allowance in this Twilio account. No paid usage or top-up is authorized.</span></label><button class="primary" type="submit">Send real verification SMS</button></form><p class="fine">No search happens at this step. Only proceed after confirming no-card trial eligibility and allowance, and reviewing the setup instructions.</p>';
    document.querySelector('#phone-form').onsubmit=event=>{event.preventDefault();if(busy)return;const input=document.querySelector('#phone');const phone=normalizeUsPhone(input.value);if(!phone){error.textContent='Enter exactly 10 digits without the country code. US (+1) is added automatically.';error.hidden=false;input.focus();return;}const data={phone,own_number:document.querySelector('#own').checked,twilio_consent:document.querySelector('#twilio').checked};input.value='';act(()=>request('start',data));};
  }else if(state.phase==='code'){
    panel.innerHTML=verificationDiagnosticMarkup(state.verification_diagnostic)+'<p>SMS verification started for the number ending '+escape(state.last_four)+'. Enter the code received. The challenge expires after 5 minutes; at most 5 checks are allowed.</p><form id="code-form" autocomplete="off"><label for="code">Verification code</label><input id="code" type="text" inputmode="numeric" autocomplete="off" pattern="[0-9]{4,10}" maxlength="10" required><button class="primary" type="submit">Verify with Twilio</button></form><p class="fine">No automatic SMS resend. Clear the test before deliberately trying again.</p>';
    document.querySelector('#code-form').onsubmit=event=>{event.preventDefault();if(busy)return;const input=document.querySelector('#code');const code=input.value;input.value='';act(()=>request('verify',{code}));};
  }else if(state.phase==='verified'){
    if(!providerName){panel.textContent='Search provider is not confirmed. Reload or review setup before proceeding.';return;}
    const planText=provider==='serper'?'I have confirmed active free credits in this Serper account. These queries consume those credits; no paid top-up is authorized.':'I have confirmed sufficient approved free allowance in this Brave account. No paid usage or top-up is authorized.';
    panel.innerHTML='<p>Twilio approved current control of the number ending '+escape(state.last_four)+'.</p><p>ScanPlus will make 3 exact-number queries through '+escape(providerName)+', one each for Spokeo, TruePeopleSearch, and Whitepages. It checks up to 10 indexed results per query. It does not directly search those broker databases or visit returned pages.</p><form id="scan-form"><label class="check"><input id="search-consent" type="checkbox" required><span>I authorize sending my phone number to '+escape(providerName)+' for these 3 queries. '+planText+'</span></label><button class="primary" type="submit">Run real local scan</button></form><p class="fine">An absent indexed match does not prove your number is absent online. SMS verification is not consent to search; this confirmation is separate. No automatic provider fallback or retries.</p>';
    document.querySelector('#scan-form').onsubmit=event=>{event.preventDefault();if(busy)return;act(()=>request('scan',{[provider+'_consent']:document.querySelector('#search-consent').checked}));};
  }else if(state.phase==='report'){
    const report=state.report;
    const count=report.sources.reduce((total,source)=>total+source.candidates.length,0);
    panel.innerHTML='<div class="report-tools"><a class="button-link" href="/api/export.txt" download>Download readable report</a><a href="/api/export.json" download>Download JSON</a></div><p class="summary"><strong>'+escape(report.sources_checked)+' of '+escape(report.sources.length)+'</strong> source queries returned usable responses.</p><p>'+escape(count)+' potential '+(count===1?'match':'matches')+'. Confirm each listing before using its official removal guide.</p><p class="fine">'+escape(report.privacy_notice||'Downloads may contain personal information in listing URLs and remain on your device after this session expires.')+'</p>'+report.sources.map(source=>'<article><h3>'+escape(source.site)+'</h3><p class="status">'+escape(({match_needs_confirmation:'Potential matches: your confirmation is required',not_found_in_checked_sources:'No exact phone match in the checked indexed results',source_unavailable:'Source unavailable: no absence conclusion'})[source.status]||'Unknown outcome: no absence conclusion')+'</p><p class="fine">Checked '+escape(source.checked_at)+(source.reason?' · '+escape(source.reason.replaceAll('_',' ')):'')+'</p>'+(source.candidates.length?'<ul class="listing-list">'+source.candidates.map(candidateMarkup).join('')+'</ul>':'')+guideMarkup(source.guide)+'</article>').join('')+'<p>'+escape(report.coverage)+'</p><p class="fine">'+escape(report.removal_notice||'No removal was submitted or verified by ScanPlus.')+'</p><p class="fine">Opening a result contacts that website. A listing URL may itself contain your number; do not open it unless you want to share that request with the site. ScanPlus never opens results automatically.</p>';
    panel.querySelectorAll('[data-review]').forEach(button=>button.onclick=()=>{
      if(busy)return;
      const action=button.dataset.review,id=button.dataset.candidate;
      const confirmed=action!=='record_manual_request'||document.querySelector('#manual-confirm-'+id).checked;
      act(()=>request('listing/review',{candidate_id:id,action,confirmed}));
    });
  }else if(state.phase==='start_uncertain'){
    panel.innerHTML='<p>A verification SMS may have been sent, but its state was not confirmed. No search took place and the number was not retained. Check your Twilio account before clearing and retrying. There is no automatic retry.</p>'+verificationDiagnosticMarkup(state.verification_diagnostic);
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
      actions=candidate.manual_action==='user_recorded_request'?'<p class="status">You recorded a manual request. Removal has not been verified.</p>':'<label class="check"><input type="checkbox" id="manual-confirm-'+id+'"><span>I submitted a request myself on the official site. This only updates my local checklist.</span></label>'+button('record_manual_request','Record my manual request');
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
window.addEventListener('pagehide',()=>{document.querySelectorAll('input').forEach(input=>{input.value='';if(input.type==='checkbox')input.checked=false;});panel.textContent='';csrf='';});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
act(()=>request('session'));
