'use strict';
// Offline private-live UI lifecycle test; fake timers and synthetic responses only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),events={},documentEvents={},pending=[],calls=[],timers=[],frames=[];
let now=0,reloads=0;const redirects=[];
class Element{
  constructor(){this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.innerHTML='';this.type='text';}
  querySelectorAll(){return [];}
  focus(){this.focused=true;}
  scrollIntoView(){this.scrolled=true;}
}
const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const context=vm.createContext({document:{querySelector:el,querySelectorAll:()=>[...elements.values()],hidden:false,addEventListener:(name,fn)=>documentEvents[name]=fn},window:{addEventListener:(name,fn)=>events[name]=fn},location:{reload(){reloads++;},assign(url){redirects.push(url);}},URL,AbortController,requestAnimationFrame:fn=>frames.push(fn),performance:{now:()=>now},setTimeout:(fn,ms)=>{const timer={fn,ms,cancelled:false};timers.push(timer);return timer;},clearTimeout:timer=>{timer.cancelled=true;},fetch:async(url,options)=>{calls.push({url,options});return new Promise((resolve,reject)=>pending.push({url,reply(body,status=200){resolve({ok:status<400,json:async()=>body});},unreadable(){resolve({ok:false,json:async()=>{throw new SyntaxError("SYNTHETIC HTML BODY");}});},reject}));},localStorage:{setItem(){throw Error('No browser storage');}},sessionStorage:{setItem(){throw Error('No browser storage');}}});
const reply=(url,body,status=200)=>{const i=pending.findIndex(x=>x.url===url);assert.notEqual(i,-1,url);pending.splice(i,1)[0].reply(body,status);};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const entry={phase:'entry',search_provider:'serper',test_scope:'private_owner',sms_allowance_remaining:1,expires_in_ms:0,csrf_token:'fixture-csrf'};
const report={phase:'report',search_provider:'serper',test_scope:'private_owner',expires_in_ms:60000,report:{sources_checked:0,sources:[],coverage:'Bounded indexed queries',privacy_notice:'Downloads may retain URLs',removal_notice:'No removal performed'}};
(async()=>{
  vm.runInContext(fs.readFileSync('static/live.js','utf8'),context);reply('/api/session',entry);await tick();
  assert.match(el('#panel').innerHTML,/Send real verification SMS/);
  el('#phone').value='2025550147';el('#own').checked=true;el('#twilio').checked=true;
  el('#phone-form').onsubmit({preventDefault(){}});assert.equal(calls.length,2);
  events.pagehide();reply('/api/start',{phase:'code',last_four:'0147',expires_in_ms:60000});await tick();
  assert.equal(el('#panel').textContent,'','A late provider response must not repopulate a hidden page.');
  events.pageshow({persisted:true});assert.equal(reloads,1);
  const reload=context.act(()=>context.request('session'));reply('/api/session',{phase:'code',last_four:'0147',expires_in_ms:60000,csrf_token:'fresh'});await reload;
  const expiry=timers.filter(x=>x.ms===60000&&!x.cancelled).at(-1);assert.ok(expiry);
  expiry.fn();assert.match(el('#stage-title').textContent,/expired/);assert.ok(!el('#panel').textContent.includes('0147'));assert.equal(calls.length,3,'Expiry never makes a provider request.');
  const restored=context.act(()=>context.request('session'));reply('/api/session',report);await restored;
  assert.match(el('#panel').innerHTML,/Download PDF report/);
  now=60001;events.focus();assert.match(el('#stage-title').textContent,/expired/);assert.ok(!el('#panel').textContent.includes('Download'));
  // Even a successful delayed bootstrap/report response must remain expired.
  const delayed=context.act(()=>context.request('session'));now+=2000;
  reply('/api/session',{...report,expires_in_ms:1000});await delayed;
  assert.match(el('#stage-title').textContent,/expired/);assert.ok(!el('#panel').textContent.includes('Download'));
  const unavailable=context.act(()=>context.request('session'));reply('/api/session',{...entry,sms_allowance_remaining:0});await unavailable;
  assert.match(el('#panel').textContent,/allowance.*used/);
  context.render({phase:'code',test_scope:'private_owner',last_four:'0147',expires_in_ms:60000});
  assert.match(el('#panel').innerHTML,/Clear ends this test and cannot authorize a resend/);
  assert.ok(!el('#panel').innerHTML.includes('deliberately trying again'));
  context.render({phase:'start_uncertain',test_scope:'private_owner',expires_in_ms:60000});
  assert.match(el('#panel').innerHTML,/restart cannot authorize another SMS/);
  assert.ok(!el('#panel').innerHTML.includes('clearing and retrying'));
  const failed=context.act(()=>context.request('scan',{serper_consent:true}));
  assert.ok(timers.some(x=>x.ms===30000),'Three bounded provider requests need a 30-second response deadline.');
  const request=pending.shift();const problem=new Error('fixture timeout');problem.name='AbortError';request.reject(problem);await failed;
  assert.match(el('#error').textContent,/may have completed.*do not repeat/i);assert.equal(el('#error').focused,true);assert.equal(el('#error').scrolled,true);assert.equal(pending.length,0);
  const hiddenFailure=context.act(()=>context.request('session'));events.pagehide();reply('/api/session',{error:'Late failure'},503);await hiddenFailure;
  assert.equal(el('#panel').textContent,'');
  el('#error').focused=false;el('#error').scrolled=false;
  while(frames.length)frames.shift()();
  assert.equal(el('#error').focused,false,'A delayed alert must not steal focus after page leave');
  assert.equal(el('#error').scrolled,false);
  assert.ok(calls.every(call=>call.url.startsWith('/api/')));
  const unreadable=context.act(()=>context.request('session'));pending.shift().unreadable();await unreadable;
  assert.match(el('#error').textContent,/unreadable response.*may have completed.*do not repeat/i);
  assert.ok(!el('#error').textContent.includes('SYNTHETIC HTML BODY'));
  const malformed=context.act(()=>context.request('session'));reply('/api/session',null);await malformed;
  assert.match(el('#error').textContent,/unreadable response/);
  assert.equal(pending.length,0,'Malformed responses must not automatically retry');
  const checkout={phase:'checkout',test_scope:'private_owner',search_provider:'serper',expires_in_ms:60000,checkout_test:{enabled:true,state:'not_started',authorized:false,coupon_available:true,amount_cents:149}};
  const count=calls.length;context.render(checkout);
  assert.match(el('#panel').innerHTML,/4242 4242 4242 4242/);
  assert.match(el('#panel').innerHTML,/separate no-payment test/);
  assert.equal(calls.length,count,'Rendering never creates or reconciles Checkout');
  el('#accept-test-checkout').checked=true;el('#test-coupon').value='OWNER100';
  el('#checkout-form').onsubmit({preventDefault(){}});el('#checkout-form').onsubmit({preventDefault(){}});
  assert.equal(calls.length,count+1,'Repeated checkout click creates one request');
  assert.deepEqual(JSON.parse(calls.at(-1).options.body),{accept_test:true,coupon_code:'OWNER100'});
  assert.equal(el('#test-coupon').value,'');
  reply('/api/checkout/create',{...checkout,checkout_url:'https://checkout.stripe.com/c/pay/cs_test_fixture'});await tick();
  assert.deepEqual(redirects,['https://checkout.stripe.com/c/pay/cs_test_fixture']);
  context.render({...checkout,checkout_test:{...checkout.checkout_test,state:'pending',discount_cents:149,amount_cents:0}});
  assert.match(el('#panel').innerHTML,/100% coupon, \$0.00 USD/);
  assert.ok(!el('#panel').innerHTML.includes('id="test-coupon"'),'Reserved coupon choice cannot change after return');
  context.render(checkout);el('#check-test-payment').onclick();
  reply('/api/checkout/reconcile',{...checkout,phase:'verified',last_four:'0147',checkout_test:{...checkout.checkout_test,state:'complimentary_test',authorized:true,amount_cents:0}});await tick();
  assert.match(el('#panel').innerHTML,/No real payment was collected/);
  assert.match(el('#panel').innerHTML,/search-consent/,'Payment never substitutes for search consent');
  for(const bad of ['http://checkout.stripe.com/c/pay/x','https://checkout.stripe.com.evil.example/x','https://evil.example/x','javascript:alert(1)','https://u:p@checkout.stripe.com/x','\nhttps://checkout.stripe.com/x','https://checkout.stripe.com\\x'])assert.equal(context.privateCheckoutUrl(bad),null);
  const badRedirect=context.act(()=>context.request('checkout/create',{accept_test:true}));
  reply('/api/checkout/create',{...checkout,checkout_url:'https://evil.example/x'});await badRedirect;
  assert.match(el('#error').textContent,/redirect was not validated/);assert.equal(redirects.length,1);
  const staleRedirect=context.act(()=>context.request('checkout/create',{accept_test:true}));events.pagehide();
  reply('/api/checkout/create',{...checkout,checkout_url:'https://checkout.stripe.com/c/pay/cs_test_fixture'});await staleRedirect;
  assert.equal(redirects.length,1,'Page leave suppresses stale Checkout navigation');
  const expiredRedirect=context.act(()=>context.request('checkout/create',{accept_test:true}));now+=2000;
  reply('/api/checkout/create',{...checkout,expires_in_ms:1000,checkout_url:'https://checkout.stripe.com/c/pay/cs_test_fixture'});await expiredRedirect;
  assert.equal(redirects.length,1,'An expired response cannot redirect to Checkout');
  console.log('PASS: private-live expiry, focus expiry, late-response suppression, used-allowance notice, timeout uncertainty and no retries. Mocked UI only.');
})().catch(e=>{console.error(e);process.exitCode=1;});
