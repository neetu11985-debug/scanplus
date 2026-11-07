'use strict';
// Offline DOM contract checks, not visual browser QA.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const elements=new Map(),events={},requests=[],pending=[];
class Element{
  constructor(id){this.id=id;this.children=[];this.isConnected=true;this._html='';this.textContent='';this.checked=false;this.disabled=false;this.hidden=false;this.value='';this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x),toggle(){}};}
  detach(){this.isConnected=false;elements.delete(this.id);for(const c of this.children)c.detach();}
  set innerHTML(html){this._html=html;for(const c of this.children)c.detach();this.children=[];for(const m of html.matchAll(/id="([^"]+)"/g)){const c=new Element('#'+m[1]);elements.set(c.id,c);this.children.push(c);}if(html.includes('id="submit-removal"'))el('#submit-removal').disabled=true;}
  get innerHTML(){return this._html;}
  querySelector(selector){return selector.startsWith('#')?elements.get(selector):el(this.id+' '+selector);}
  setAttribute(){}removeAttribute(){}focus(){}scrollIntoView(){}
  addEventListener(){}
}
const el=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const ctx=vm.createContext({document:{querySelector:el,querySelectorAll:()=>[],body:el('body'),addEventListener(){}},window:{addEventListener:(event,fn)=>events[event]=fn},AbortController,setTimeout,clearTimeout,setInterval:()=>0,fetch:async(url,options)=>{requests.push({url,body:options.body?JSON.parse(options.body):null});if(url==='/api/session')return{ok:true,json:async()=>({active:false})};return new Promise(resolve=>pending.push({url,reply(body,status=200){resolve({ok:status===200,json:async()=>body});}}));},localStorage:{setItem(){throw Error('No storage');}},sessionStorage:{setItem(){throw Error('No storage');}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8'),ctx);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const next=url=>{const index=pending.findIndex(x=>x.url===url);assert.notEqual(index,-1,url);return pending.splice(index,1)[0];};
const listing={provider:'fixture',report_id:'report-a',listing_id:'listing-a',label:'Fictional listing',synthetic:true};
const report=()=>({phone:'+12025550147',report_id:'report-a',providers:[],removal:'not_requested',removal_listing:listing,removal_request:null});
const preview=()=>({consent_id:'fixture-consent-token',expires_at:2000000000,disclosure:{...listing,consent_version:'removal-consent-v1',recipient:'Local adapter <script>',purpose:'Simulated removal',data:[{label:'Reserved phone',value:'+12025550147'}],scope:'This listing only',consequences:'No broker contacted; no removal verified',cost:'No charge',retention:'Session only',cancellation:'Cancel before submitting'}});
const receipt={request_id:'fixture-request',listing_id:'listing-a',status:'request_submitted',demo:true,removal_verified:false,message:'No broker was contacted; no removal was verified.'};
function openReport(){ctx.fixture=report();vm.runInContext('currentReport=fixture;renderReport()',ctx);}
async function review(){el('#review-removal').onclick();next('/api/removal/prepare').reply(preview());await settle();}
function checkBoth(){el('#listing-confirm').checked=true;el('#listing-confirm').onchange();el('#removal-authorize').checked=true;el('#removal-authorize').onchange();}
function submit(){return el('#removal-consent-form').onsubmit({preventDefault(){}});}
(async()=>{
  await settle();openReport();
  el('#review-removal').onclick();el('#review-removal').onclick();assert.equal(pending.length,1);
  next('/api/removal/prepare').reply(preview());await settle();
  assert.match(el('#removal-flow').innerHTML,/Local adapter &lt;script&gt;/);assert.ok(!el('#removal-flow').innerHTML.includes('<script>'));
  assert.equal(el('#submit-removal').disabled,true);await submit();assert.equal(pending.length,0);
  el('#listing-confirm').checked=true;el('#listing-confirm').onchange();assert.equal(el('#submit-removal').disabled,true);
  el('#cancel-removal').onclick();next('/api/removal/cancel').reply({cancelled:true});await settle();
  assert.equal(requests.filter(x=>x.url==='/api/removal').length,0);
  await review();assert.equal(el('#listing-confirm').checked,false);assert.equal(el('#removal-authorize').checked,false);
  checkBoth();assert.equal(el('#submit-removal').disabled,false);submit();submit();assert.equal(pending.length,1);
  const body=requests.at(-1).body;assert.equal(body.authorize,true);assert.equal(body.confirm_listing,true);assert.equal(body.consent_id,'fixture-consent-token');assert.equal(body.listing_id,'listing-a');
  next('/api/removal').reply(receipt);await settle();assert.match(el('#panel').innerHTML,/removal not verified/);
  el('#review-removal').onclick();next('/api/removal/status').reply(receipt);await settle();assert.match(el('#panel').innerHTML,/removal not verified/);
  assert.equal(requests.filter(x=>x.url==='/api/removal').length,1);
  openReport();await review();checkBoth();submit();next('/api/removal').reply({error:'Permission expired'},409);await settle();
  assert.equal(el('#listing-confirm').checked,false);assert.equal(el('#removal-authorize').checked,false);assert.equal(el('#submit-removal').disabled,true);assert.match(el('#alert').textContent,/Reload the report/);
  // A late preparation response may not reopen permission after navigation.
  openReport();el('#review-removal').onclick();ctx.start();next('/api/removal/prepare').reply(preview());await settle();assert.match(el('#panel').innerHTML,/Start with your number/);
  openReport();await review();el('#local-phone').value='+1 202 555 0147';events.pagehide();assert.equal(el('#local-phone').value,'');assert.equal(el('#panel').textContent,'');
  events.pageshow({persisted:true});await settle();assert.match(el('#panel').innerHTML,/Start with your number/);
  assert.ok(requests.every(x=>x.url.startsWith('/api/')));
  console.log('PASS: exact escaped disclosure, two unchecked confirmations, cancellation, repeated clicks, idempotent request/status UI, stale-response navigation, failure reset, no external requests/storage, page leave/back. Offline DOM checks only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
