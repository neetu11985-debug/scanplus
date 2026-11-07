'use strict';
// Offline DOM regression. Reserved fixtures only; deliberately no network or storage.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');
const css=fs.readFileSync(path.join(__dirname,'../static/style.css'),'utf8');
assert.ok(!html.includes('local-number-form'),'Only one number-entry flow may exist.');
assert.ok(!/[↗◈◎]/.test(html+source),'Decorative glyphs must not depend on missing mobile fonts.');
assert.ok(!source.includes('Check number format only'),'Continue must not silently become a format-only dead end.');
assert.match(css,/\[hidden\]\s*\{\s*display:\s*none\s*!important/,'Flex styles must not override hidden declarations.');
function harness(){
  const elements=new Map(),events={},requests=[],pending=[];
  class Element{
    constructor(id){this.id=id;this.children=[];this.value='';this.checked=false;this.required=false;this.disabled=false;this.hidden=false;this.isConnected=true;this._html='';this.textContent='';this.classes=new Set();this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x),toggle(){}};}
    detach(){this.isConnected=false;elements.delete(this.id);for(const c of this.children)c.detach();}
    set innerHTML(value){this._html=value;for(const c of this.children)c.detach();this.children=[];for(const match of value.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)){const child=new Element('#'+match[1]),tag=match[0];child.value=(tag.match(/\bvalue="([^"]*)"/)||[])[1]||'';child.disabled=/\bdisabled(?:\s|>)/.test(tag);child.hidden=/\bhidden(?:\s|>)/.test(tag);child.required=/\brequired(?:\s|>)/.test(tag);elements.set(child.id,child);this.children.push(child);}}
    get innerHTML(){return this._html;}
    querySelector(selector){if(selector.startsWith('#'))return elements.get(selector)||null;return new Element(this.id+' '+selector);}
    addEventListener(){}setAttribute(){}removeAttribute(){}focus(){this.focused=true;}scrollIntoView(options){this.lastScroll=options;}
  }
  for(const id of ['#panel','#alert','#reset','#step1','#step2','#step3','body'])elements.set(id,new Element(id));
  const get=id=>elements.get(id)||null;
  const ctx=vm.createContext({document:{querySelector:get,querySelectorAll:()=>[],body:get('body'),addEventListener(){}},window:{addEventListener:(name,fn)=>events[name]=fn},AbortController,setTimeout,clearTimeout,setInterval:()=>0,fetch:async(url,options)=>{requests.push({url,body:options.body?JSON.parse(options.body):null,headers:options.headers});return new Promise(resolve=>pending.push({url,reply(body,status=200){resolve({ok:status<400,status,json:async()=>body});}}));},localStorage:{setItem(){throw Error('No browser storage');}},sessionStorage:{setItem(){throw Error('No browser storage');}}});
  vm.runInContext(source,ctx);
  const reply=(url,body,status=200)=>{const index=pending.findIndex(p=>p.url===url);assert.notEqual(index,-1,'Expected '+url);pending.splice(index,1)[0].reply(body,status);};
  return {ctx,get,events,requests,pending,reply};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const submit=(form,button)=>form.onsubmit({preventDefault(){},submitter:button});
(async()=>{
  const h=harness();h.reply('/api/session',{active:false});await settle();
  const {ctx,get,requests}=h;
  assert.match(get('#panel').innerHTML,/Continue <span>/);
  assert.equal(get('#phone').value,'+1 (202) 555-0147');
  assert.match(get('#panel').innerHTML,/class="entry-actions"/);
  ctx.focusAndReveal(get('#entry-clear'));assert.equal(get('#entry-clear').lastScroll.behavior,'instant');
  assert.equal(get('#demo-declaration').hidden,false);
  get('#phone').value='+1 202 555 0148';get('#phone').oninput();
  assert.equal(get('#demo-declaration').hidden,true);assert.equal(get('#control').required,false);
  assert.equal(get('#use-example').hidden,false);
  const personal=get('#phone');submit(get('#start-form'),get('#start-submit'));
  assert.equal(personal.value,'');assert.equal(get('#phone'),null);
  assert.match(get('#panel').innerHTML,/Live lookup is not connected/);
  assert.ok(!get('#panel').innerHTML.includes('0148'),'Do not retain even the personal-number suffix after navigation.');
  assert.equal(requests.length,1,'No personal-number request allowed.');
  get('#availability-back').onclick();assert.equal(get('#phone').value,'');assert.equal(get('#phone').focused,true);
  get('#phone').value='2025550148';get('#phone').oninput();submit(get('#start-form'),get('#start-submit'));
  assert.match(get('#entry-status').textContent,/Enter \+/);assert.equal(requests.length,1);
  get('#entry-clear').onclick();assert.equal(get('#phone').value,'');assert.equal(get('#entry-status').textContent,'');
  get('#use-example').onclick();assert.equal(get('#phone').value,'+1 (202) 555-0147');assert.equal(get('#control').required,true);assert.equal(get('#control').checked,false);
  const normalize=value=>ctx.normalizeLocalPhone(value);
  assert.equal(normalize('+1 (202) 555-0147'),'+12025550147');assert.equal(normalize(' +44 7700 900123 '),'+447700900123');
  for(const value of ['2025550147','+012345678','+1234567','+1234567890123456','+12025550147 ext 2','<script>','+1/2025550147',''])assert.equal(normalize(value),null,value);
  get('#control').checked=true;
  const form=get('#start-form'),button=get('#start-submit');submit(form,button);submit(form,button);
  assert.equal(h.pending.length,1,'Repeated start makes only one request.');assert.deepEqual(requests.at(-1).body,{phone:'+12025550147',consent:true});
  h.reply('/api/start',{csrf_token:'fixture-csrf'});await settle();assert.ok(get('#verify-form'));
  // Verification-stage expiry must not be skipped just because stage is 1.
  ctx.checkCurrentSession();h.reply('/api/session/status',{active:false});await settle();assert.ok(get('#restart-session'));
  get('#restart-session').onclick();assert.ok(get('#start-form'));
  // Late report/history/verification responses cannot overwrite newer navigation.
  ctx.loadReport();ctx.start();h.reply('/api/report',{phone:'+12025550147',providers:[]});await settle();assert.ok(get('#start-form'));
  ctx.showHistory();ctx.start();h.reply('/api/history',{payments:[]});await settle();assert.ok(get('#start-form'));
  ctx.verify();get('#code').value='246810';submit(get('#verify-form'),new (get('#phone')?.constructor||button.constructor)('verify-submit'));ctx.start();h.reply('/api/verify',{has_history:false});await settle();assert.ok(get('#start-form'));assert.equal(h.pending.length,0);
  // History reserves a new view before fetching; a live initiating button must still show errors.
  const historyButton=get('#entry-clear'),historyFailure=ctx.run(historyButton,ctx.showHistory);
  h.reply('/api/history',{error:'Fresh demo verification required for payment history.'},403);await historyFailure;
  assert.equal(get('#alert').hidden,false);assert.match(get('#alert').textContent,/Fresh demo verification/);assert.equal(historyButton.disabled,false);
  // Navigation detaches the initiating control, so late failures must not contaminate the new view.
  const staleFailure=ctx.run(get('#entry-clear'),ctx.showHistory);ctx.start();
  h.reply('/api/history',{error:'Old history error'},503);await staleFailure;assert.equal(get('#alert').hidden,true);
  // Clear waits for a pending mutation and refreshes stale CSRF before sign-out.
  get('#control').checked=true;submit(get('#start-form'),get('#start-submit'));
  const clear=ctx.clearSession();assert.equal(h.pending.length,1,'Clear must wait for outstanding start.');
  h.reply('/api/start',{csrf_token:'old-token'});await settle();
  h.reply('/api/session',{active:true,csrf_token:'fresh-token'});await settle();
  assert.equal(requests.at(-1).url,'/api/clear');assert.equal(requests.at(-1).headers['X-CSRF-Token'],'fresh-token');
  h.reply('/api/clear',{cleared:true});await clear;assert.ok(get('#start-form'));
  // Failed clear must not falsely claim server-side sign-out.
  const failClear=ctx.clearSession();await settle();h.reply('/api/session',{active:true,csrf_token:'token'});await settle();h.reply('/api/clear',{error:'Session security token expired.'},403);await failClear;
  assert.ok(get('#retry-clear'));assert.match(get('#panel').innerHTML,/has not confirmed sign-out/);
  ctx.start();get('#phone').value='+1 202 555 0148';const entry=get('#phone');ctx.loadReport();h.events.pagehide();h.reply('/api/report',{phone:'+12025550147',providers:[]});await settle();assert.equal(get('#panel').textContent,'');
  h.events.pageshow({persisted:true});h.reply('/api/session',{active:false});await settle();assert.ok(get('#start-form'));
  assert.equal(h.pending.length,0);
  console.log('PASS: one entry, stable Continue, unavailable next screen, fixture-only requests, hidden declaration, format validation, no storage, double submit, verification expiry, stale navigation, clear during request, failed clear, pagehide/back. Offline DOM checks only.');
})().catch(e=>{console.error(e);process.exitCode=1;});
