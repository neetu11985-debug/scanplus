'use strict';
// Dependency-free DOM contract harness, synthetic data only. Not visual browser QA.
const provider=process.argv[2]||'brave';
if(!['brave','serper'].includes(provider))throw Error('Synthetic test provider must be brave or serper');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element{
 constructor(){this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.innerHTML='';this.type='text';}
 querySelectorAll(){return [];}
 focus(){this.focused=true;}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const events={},requests=[],responses=[];let reloads=0;
const context=vm.createContext({
 document:{querySelector:element,querySelectorAll:()=>[...elements.values()]},
 window:{addEventListener:(type,handler)=>events[type]=handler},location:{reload(){reloads++;}},
 fetch:async(url,options)=>{requests.push({url,options});const next=responses.shift();if(!next)throw Error('Unexpected network request');return{ok:next.ok!==false,json:async()=>next.body};},
 localStorage:{setItem(){throw Error('No browser storage allowed');}},sessionStorage:{setItem(){throw Error('No browser storage allowed');}}
});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const submit=id=>element(id).onsubmit({preventDefault(){}});
(async()=>{
 responses.push({body:{phase:'entry',search_provider:provider,csrf_token:'SYNTHETIC-CSRF'}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/live.js'),'utf8'),context);await tick();
 assert.match(element('#stage-title').textContent,/Verify your own number/);
 assert.match(element('#panel').innerHTML,/<option value="\+1">US \(\+1\)<\/option>/);
 assert.equal((element('#panel').innerHTML.match(/<option /g)||[]).length,1);
 assert.match(element('#panel').innerHTML,/pattern="\[0-9\]\{10\}"/);
 assert.equal(context.normalizeUsPhone('2025550147'),'+12025550147');
 for(const value of ['', '202555014', '20255501470', '12025550147', '+12025550147', '+442025550147', '202 555 0147', '(202)555-0147', '2025550147 ext 2', '２０２５５５０１４７']){
   assert.equal(context.normalizeUsPhone(value),null,value);
   element('#phone').value=value;submit('#phone-form');await tick();
   assert.equal(requests.length,1,'Invalid input must never start SMS');
   assert.equal(element('#phone').value,value,'Never silently trim or truncate invalid input');
   assert.match(element('#error').textContent,/10 digits without the country code/);
 }
 element('#phone').value='2025550147';element('#own').checked=true;element('#twilio').checked=true;
 responses.push({body:{phase:'code',last_four:'0147'}});submit('#phone-form');submit('#phone-form');await tick();
 assert.equal(requests.length,2,'Repeated clicks must not repeat start');assert.equal(element('#error').hidden,true);assert.equal(element('#phone').value,'');
 assert.equal(JSON.parse(requests[1].options.body).phone,'+12025550147');assert.equal(requests[1].options.headers['X-CSRF-Token'],'SYNTHETIC-CSRF');
 assert.match(element('#panel').innerHTML,/ending 0147/);assert.ok(!element('#panel').innerHTML.includes('202555'));
 element('#code').value='000000';responses.push({ok:false,body:{error:'Provider did not approve',state:{phase:'code',last_four:'0147'}}});submit('#code-form');await tick();
 assert.equal(element('#code').value,'');assert.equal(element('#error').hidden,false);
 element('#code').value='123456';responses.push({body:{phase:'verified',search_provider:provider,last_four:'0147'}});submit('#code-form');await tick();
 assert.match(element('#panel').innerHTML,provider==='serper'?/Serper \(Google Search results\)/:/Brave Search/);
 if(provider==='serper'){assert.match(element('#panel').innerHTML,/free credits/);assert.match(element('#panel').innerHTML,/no paid top-up/i);}assert.equal(requests.length,4,'Verification must not auto-scan');
 element('#search-consent').checked=true;responses.push({body:{phase:'report',report:{sources_checked:0,sources:[{site:'spokeo.com',status:'source_unavailable',checked_at:'synthetic',candidates:[],reason:'provider_error'}],coverage:'Synthetic test'}}});submit('#scan-form');submit('#scan-form');await tick();
 assert.equal(requests.length,5);assert.deepEqual(JSON.parse(requests[4].options.body),{[provider+'_consent']:true});assert.match(element('#panel').innerHTML,/no absence conclusion/);assert.match(element('#stage-title').textContent,/report/);
 responses.push({body:{phase:'entry',search_provider:provider}});element('#clear').onclick();await tick();assert.match(element('#stage-title').textContent,/Verify your own number/);
 element('#phone').value='2025550147';events.pagehide();assert.equal(element('#phone').value,'');assert.equal(element('#panel').textContent,'');assert.equal(requests.length,6);
 events.pageshow({persisted:true});assert.equal(reloads,1);
 vm.runInContext("render({phase:'verified',search_provider:'unknown'})",context);assert.match(element('#panel').textContent,/not confirmed/);assert.equal(requests.length,6);
 vm.runInContext("render({phase:'start_uncertain',verification_diagnostic:{http_status:401,twilio_error_code:20003,message:'NEVER SHOW THIS'}})",context);
 assert.match(element('#panel').innerHTML,/HTTP 401; Twilio error code 20003/);
 assert.ok(!element('#panel').innerHTML.includes('NEVER SHOW THIS'));
 assert.equal(requests.length,6,'Showing a diagnostic must never retry');
 vm.runInContext("render({phase:'code',last_four:'0147',verification_diagnostic:{http_status:429,twilio_error_code:60203}})",context);
 assert.match(element('#panel').innerHTML,/HTTP 429; Twilio error code 60203/);
 assert.equal(typeof element('#code-form').onsubmit,'function');
 for(const value of ['20003',true,20003.5,-1,1000000,'<img src=x onerror=alert(1)>']){
   const markup=context.verificationDiagnosticMarkup({http_status:401,twilio_error_code:value});
   assert.match(markup,/Twilio error code unavailable/);assert.ok(!markup.includes('<img'));
 }
 for(const value of ['401',true,401.5,99,600,'<img>']){
   assert.match(context.verificationDiagnosticMarkup({http_status:value,twilio_error_code:20003}),/HTTP status unavailable; Twilio error code unavailable/);
 }
 assert.match(context.verificationDiagnosticMarkup({http_status:201,twilio_error_code:123456}),/Twilio error code unavailable/);
 vm.runInContext("render({phase:'entry',search_provider:'serper'})",context);
 assert.ok(!element('#panel').innerHTML.includes('Last verification diagnostic'));
 console.log('PASS '+provider+': sanitized verification diagnostics, malformed-value rejection, refresh rendering and no automatic retry.');
 console.log('PASS '+provider+': US-only selector, national-number validation and +1 normalization, synthetic UI consent steps, no automatic scan, repeated-click guards, errors, masking, clear, page leave, and back/forward-cache reload. Not visual browser QA.');
})().catch(error=>{console.error(error);process.exitCode=1;});
