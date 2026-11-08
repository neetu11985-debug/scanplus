'use strict';
// A DOM/state harness, not browser rendering. All numbers are reserved examples.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor() { this.value=''; this.checked=false; this.hidden=false; this.disabled=false; this.textContent=''; this.handlers={}; }
  addEventListener(event, handler) { this.handlers[event]=handler; }
  focus() { this.focused=true; }
}
const elements = new Map();
const $ = id => { if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
const windowHandlers = {}, documentHandlers = {}, calls=[], timers=[];
let state = {phase:'entry',csrf_token:'synthetic-csrf',last_four:null,search_enabled:false,allowance_used:false,expires_in_ms:0};
let pause = null, loseNextScan = false, failNextSession = false;
const context=vm.createContext({
  document:{querySelector:$,hidden:false,addEventListener:(event,handler)=>documentHandlers[event]=handler}, window:{addEventListener:(event,handler)=>windowHandlers[event]=handler},
  fetch:async (url,options) => {
    calls.push({url,options});
    if(pause) await pause;
    if(url==='/api/session' && failNextSession) { failNextSession=false; throw new TypeError('Synthetic connection loss'); }
    if(url==='/api/start') state={...state,phase:'ready',last_four:'0147',expires_in_ms:60000};
    if(url==='/api/clear') state={...state,phase:'entry',last_four:null};
    if(url==='/api/scan') {
      const data = JSON.parse(options.body);
      if(state.search_enabled && data.serper_consent === true && data.free_allowance_confirmed === true) {
        state={...state,phase:'report',allowance_used:true,report:{ownership_notice:'SMS off. Self-attested, not verified.',sources_checked:1,queries_attempted:1,privacy_notice:'Downloads remain on your device.',coverage:'Bounded web-index lookup.',removal_notice:'No removal submitted.',sources:[{site:'spokeo.com',checked_at:'synthetic-time',status:'match_needs_confirmation',query_attempted:true,candidates:[{source_url:'https://spokeo.com/synthetic-record',evidence:'<script>untrusted</script>'}]}]}};
        state.expires_in_ms=60000;
        if(loseNextScan) { loseNextScan=false; throw new TypeError('Synthetic response loss after completion'); }
      } else {
        state={...state,phase:state.search_enabled ? 'ready' : 'blocked'};
        return {ok:false,json:async()=>({error:state.search_enabled ? 'Explicit Serper consent is required.' : 'Real Serper lookup is blocked. No search ran.',state:{...state}})};
      }
    }
    return {ok:true,json:async()=>({...state})};
  }, AbortController,performance:{now:()=>0},setTimeout:(fn,ms)=>{const timer={fn,ms,cancelled:false};timers.push(timer);return timer;},clearTimeout:timer=>{if(timer)timer.cancelled=true;},
  localStorage:{setItem(){throw Error('Storage forbidden');}},sessionStorage:{setItem(){throw Error('Storage forbidden');}}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/no_sms.js'),'utf8'),context);
const tick = () => new Promise(resolve=>setTimeout(resolve,0));
(async()=>{
  await tick(); assert.equal(calls.length,1); assert.equal($('#start').disabled,false);
  const html=fs.readFileSync(path.join(__dirname,'../static/no_sms.html'),'utf8');
  assert.match(html,/<option value="\+1">US \(\+1\)<\/option>/);
  assert.equal((html.match(/<option /g)||[]).length,1);
  assert.match(html,/pattern="\[0-9\]\{10\}"/);
  assert.equal(context.normalizeUsPhone('2025550147'),'+12025550147');
  for(const value of ['', '202555014', '20255501470', '12025550147', '+12025550147', '+442025550147', '202 555 0147', '(202)555-0147', '2025550147 ext 2', '２０２５５５０１４７']){
    assert.equal(context.normalizeUsPhone(value),null,value);
    $('#phone').value=value;$('#entry').handlers.submit({preventDefault(){}});await tick();
    assert.equal(calls.length,1,'Invalid input must never reach the server');
    assert.equal($('#phone').value,value,'Never silently trim or truncate invalid input');
    assert.match($('#error').textContent,/10 digits without the country code/);
  }
  $('#phone').value='2025550147'; $('#own').checked=true; $('#ack').checked=true;
  let unblock; pause=new Promise(resolve=>{unblock=resolve;});
  const submit=()=>$('#entry').handlers.submit({preventDefault(){}});
  submit(); submit(); assert.equal(calls.length,2,'Repeated click must not duplicate request');
  assert.equal($('#phone').value,''); assert.equal($('#start').disabled,true);
  unblock(); pause=null; await tick();
  assert.equal($('#entry').hidden,true); assert.equal($('#next').hidden,false);
  assert.match($('#masked').textContent,/0147/); assert.match($('#status').textContent,/not verified/);
  assert.equal(JSON.parse(calls[1].options.body).no_sms_acknowledged,true);
  assert.equal(JSON.parse(calls[1].options.body).phone,'+12025550147');
  assert.equal($('#error').hidden,true);
  $('#scan').handlers.click(); await tick();
  assert.match($('#error').textContent,/blocked/); assert.equal($('#error').hidden,false);
  assert.equal($('#scan').disabled,false);
  $('#clear').handlers.click(); await tick();
  assert.equal($('#entry').hidden,false); assert.equal($('#next').hidden,true); assert.equal($('#masked').textContent,'');
  $('#phone').value='2025550147'; windowHandlers.pagehide(); assert.equal($('#phone').value,'');
  const before=calls.length; windowHandlers.pageshow({persisted:true}); await tick(); assert.equal(calls.length,before+1);
  state={...state,phase:'entry',search_enabled:true,allowance_used:false,report:null};
  windowHandlers.pageshow({persisted:true}); await tick();
  assert.match($('#mode-description').textContent,/Maximum three queries/);
  assert.equal($('#start').textContent,'Continue without SMS');
  $('#phone').value='2025550147'; $('#own').checked=true; $('#ack').checked=true;
  submit(); await tick();
  assert.equal($('#search-permission').hidden,false);
  $('#scan').handlers.click(); await tick();
  assert.match($('#error').textContent,/consent/);
  assert.equal($('#report').hidden,true);
  $('#serper-consent').checked=true; $('#free-confirm').checked=true;
  $('#scan').handlers.click(); await tick();
  assert.equal($('#report').hidden,false);
  assert.match($('#report').innerHTML,/Download PDF report/);
  assert.ok(!$('#report').innerHTML.includes('export.json'));
  assert.match($('#report').innerHTML,/self-attested, not verified/i);
  assert.ok($('#report').innerHTML.includes('&lt;script&gt;untrusted&lt;/script&gt;'));
  assert.ok(!$('#report').innerHTML.includes('<script>'));
  assert.equal($('#scan').disabled,true);
  const savedReport=state.report;
  vm.runInContext("render({phase:'report',report:{sensitive:'must not render'},expires_in_ms:0})",context);
  assert.equal($('#report').innerHTML,''); assert.equal($('#report').hidden,true);
  assert.match($('#status').textContent,/expired/);
  windowHandlers.pageshow({persisted:true}); await tick();
  assert.equal($('#report').hidden,false);
  assert.ok(timers.some(timer=>timer.ms===30000),'Scan deadline must accommodate three provider requests');
  const expiry=timers.filter(timer=>timer.ms===60000 && !timer.cancelled).at(-1);
  assert.ok(expiry); expiry.fn();
  assert.equal($('#report').innerHTML,''); assert.equal($('#report').hidden,true);
  assert.match($('#status').textContent,/expired/); assert.equal($('#start').disabled,true);
  // Explicit repeat mode displays cumulative use but never starts a scan on Clear/reload.
  state={...state,phase:'report',report:savedReport,allowance_used:false,expires_in_ms:60000,diagnostic_log_status:'full',test_usage:{scan_limit:2,scans_started:1,scans_remaining:1,query_limit:6,queries_attempted:3,same_number_locked:true}};
  windowHandlers.pageshow({persisted:true}); await tick();
  assert.match($('#test-usage').textContent,/1 \/ 2 scans started; 3 \/ 6 queries attempted/);
  assert.match($('#test-usage').textContent,/Locked to your first scanned number/);
  assert.match($('#test-usage').textContent,/Private diagnostic log: full/);
  assert.match($('#clear').textContent,/test the same number again/);
  const repeatedScansBefore=calls.filter(call=>call.url==='/api/scan').length;
  $('#clear').handlers.click(); await tick();
  assert.equal($('#entry').hidden,false); assert.equal($('#start').disabled,false);
  assert.equal($('#serper-consent').checked,false); assert.equal($('#free-confirm').checked,false);
  assert.equal(calls.filter(call=>call.url==='/api/scan').length,repeatedScansBefore);
  state={...state,allowance_used:true,test_usage:{...state.test_usage,scans_started:2,scans_remaining:0,queries_attempted:4}};
  windowHandlers.pageshow({persisted:true}); await tick();
  assert.equal($('#entry').hidden,true); assert.equal($('#start').disabled,true);
  assert.match($('#test-usage').textContent,/2 \/ 2 scans started; 4 \/ 6 queries attempted/);
  assert.equal(calls.filter(call=>call.url==='/api/scan').length,repeatedScansBefore);
  // A lost completion response uses only GET session reconciliation, no repeated POST.
  state={...state,phase:'ready',allowance_used:false,report:null,expires_in_ms:60000};
  windowHandlers.pageshow({persisted:true}); await tick();
  $('#serper-consent').checked=true; $('#free-confirm').checked=true; loseNextScan=true;
  const scansBefore=calls.filter(call=>call.url==='/api/scan').length;
  $('#scan').handlers.click(); await tick();
  assert.equal(calls.filter(call=>call.url==='/api/scan').length,scansBefore+1);
  assert.equal(calls.at(-1).url,'/api/session'); assert.equal($('#report').hidden,false);
  context.document.hidden=true; documentHandlers.visibilitychange();
  assert.equal($('#report').innerHTML,''); assert.equal($('#report').hidden,true);
  failNextSession=true; context.document.hidden=false; documentHandlers.visibilitychange(); await tick();
  assert.equal($('#report').innerHTML,''); assert.equal($('#start').disabled,true);
  assert.match($('#error').textContent,/connection loss/);
  // A late response cannot restore private content after the page becomes hidden.
  let release; pause=new Promise(resolve=>{release=resolve;});
  windowHandlers.pageshow({persisted:true});
  context.document.hidden=true; documentHandlers.visibilitychange();
  release(); pause=null; await tick();
  assert.equal($('#report').innerHTML,''); assert.equal($('#report').hidden,true);
  assert.ok(!calls.some(call=>call.url.includes('verify') || call.url.includes('twilio')));
  assert.ok(calls.every(call=>call.url.startsWith('/api/')));
  console.log('PASS: US-only selector, national-number validation and +1 normalization, bootstrap, no-SMS acknowledgment, repeated-click guard, masking, honest blocked search, clear, page leave/back, same-origin-only requests, separate Serper/allowance consent, real-report rendering and untrusted-text escaping, timed expiry/visibility wiping, stale-response guards and read-only lost-response recovery.');
})().catch(error=>{console.error(error);process.exitCode=1;});
