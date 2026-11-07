'use strict';
// Synthetic DOM contract tests. No browser, provider, real number, or file download.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements=new Map(),events={},requests=[],responses=[];
class Element{
 constructor(){this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.innerHTML='';this.dataset={};}
 querySelectorAll(selector){
  if(selector!=='[data-review]')return [];
  return [...this.innerHTML.matchAll(/data-review="([^"]+)" data-candidate="([^"]+)"/g)].map(match=>{
   const button=element('#action-'+match[1]+'-'+match[2]);button.dataset={review:match[1],candidate:match[2]};return button;
  });
 }
}
const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const candidate={id:'synthetic-id',source_url:'https://spokeo.com/listing?id=123&x=%3Cscript%3E',evidence:'Exact text <script>must be escaped</script>',match_review:'needs_confirmation',manual_action:'not_started',removal_verified:false};
const guide={name:'Spokeo',url:'https://www.spokeo.com/optout',steps:['Open official page','Complete your own verification'],safety_notice:'Confirm your own record',verification_notice:'Current form not independently verified',follow_up:'Check the exact listing again',automation_notice:'No permitted automation configured',source_url:'https://cppa.ca.gov/data_broker_registry/registry.csv',registry_updated:'2026-10-30',reviewed_at:'2026-11-06'};
const report={sources_checked:1,privacy_notice:'Downloads remain on your device',coverage:'Bounded indexed source coverage',removal_notice:'No removal submitted or verified',sources:[{site:'spokeo.com',status:'match_needs_confirmation',checked_at:'synthetic-date',candidates:[candidate],guide}]};
const state=()=>JSON.parse(JSON.stringify({phase:'report',search_provider:'serper',report}));
const context=vm.createContext({document:{querySelector:element,querySelectorAll:()=>[...elements.values()]},window:{addEventListener:(event,fn)=>events[event]=fn},location:{reload(){}},fetch:async(url,options)=>{requests.push({url,options});const response=responses.shift();if(!response)throw Error('Unexpected request');return{ok:response.ok!==false,json:async()=>response.body};},localStorage:{setItem(){throw Error('Unexpected storage');}},sessionStorage:{setItem(){throw Error('Unexpected storage');}}});
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const click=action=>element('#action-'+action+'-synthetic-id').onclick();
(async()=>{
 responses.push({body:{...state(),csrf_token:'synthetic-csrf'}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/live.js'),'utf8'),context);await tick();
 let html=element('#panel').innerHTML;
 assert.match(html,/href="\/api\/export.txt" download/);assert.match(html,/href="\/api\/export.json" download/);
 assert.match(html,/Official destination confirmed/);assert.match(html,/Current form steps have not been independently verified/);
 assert.match(html,/&lt;script&gt;/);assert.ok(!html.includes('<script>'));assert.match(html,/rel="noopener noreferrer"/);
 assert.equal(requests.length,1,'Rendering guides and links must not call sites');
 candidate.match_review='confirmed_by_user';responses.push({body:state()});click('confirm_mine');click('confirm_mine');await tick();
 assert.equal(requests.length,2,'Repeated confirmation must be one local update');assert.deepEqual(JSON.parse(requests[1].options.body),{candidate_id:'synthetic-id',action:'confirm_mine',confirmed:true});
 assert.match(element('#panel').innerHTML,/I submitted a request myself/);
 responses.push({ok:false,body:{error:'Explicit confirmation required',state:state()}});click('record_manual_request');await tick();
 assert.equal(JSON.parse(requests[2].options.body).confirmed,false);assert.equal(element('#error').hidden,false);
 element('#manual-confirm-synthetic-id').checked=true;candidate.manual_action='user_recorded_request';responses.push({body:state()});click('record_manual_request');await tick();
 assert.match(element('#panel').innerHTML,/Removal has not been verified/);assert.equal(JSON.parse(requests[3].options.body).confirmed,true);
 candidate.match_review='needs_confirmation';candidate.manual_action='not_started';responses.push({body:state()});click('reset');await tick();
 candidate.match_review='not_mine';responses.push({body:state()});click('not_mine');await tick();
 assert.match(element('#panel').innerHTML,/Do not request removal of this record/);
 responses.push({body:{phase:'entry',search_provider:'serper'}});element('#clear').onclick();await tick();
 assert.ok(!element('#panel').innerHTML.includes('spokeo.com/listing'));assert.match(element('#stage-title').textContent,/Verify your own number/);
 assert.ok(requests.every(r=>r.url.startsWith('/api/')));assert.ok(!requests.some(r=>/removal|checkout/.test(r.url)));
 events.pagehide();assert.equal(element('#panel').textContent,'');
 console.log('PASS: synthetic report guides, escaped untrusted text, local-only listing review, repeated actions, explicit manual checklist, truthful status, clear, download links. No browser/download validation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
