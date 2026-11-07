// Offline DOM harness. No browser, network, credentials or actual Stripe Checkout.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/stripe-test.js', 'utf8');
function node() { return {textContent:'', hidden:true, disabled:false, children:[], append(n){this.children.push(n);}, replaceChildren(){this.children=[];}}; }
function harness({verified=true, state='pending', amount=149, hash='', failed=false, url='https://checkout.stripe.com/c/pay/cs_test_fixture'}={}) {
  const nodes = Object.fromEntries(['#status','#error','#actions','#report'].map(id=>[id,node()]));
  const calls=[], redirects=[];
  const context={URL,AbortController,setTimeout,clearTimeout,
    document:{querySelector:id=>nodes[id],createElement:()=>node()},
    location:{hash},window:{location:{assign:value=>redirects.push(value)}},
    fetch:async (path,options)=>{
      calls.push({path,options});
      let data={};let ok=true;
      if(path==='/api/session')data={active:true,verified,csrf_token:'fixture-csrf'};
      if(path==='/api/stripe/status') {data={state,amount_cents:amount};if(failed){ok=false;data={error:'Sandbox disabled.'};}}
      if(path==='/api/stripe/checkout')data={state:'pending',checkout_url:url};
      if(path==='/api/stripe/reconcile'){state='paid';data={state,amount_cents:amount};}
      if(path==='/api/stripe/report')data={demo:true,text:'<script>untrusted</script>'};
      return {ok,json:async()=>data};
    }};
  vm.createContext(context);vm.runInContext(source,context);
  return {nodes,calls,redirects,context,buttons:()=>nodes['#actions'].children};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  let h=harness();await tick();assert.match(h.nodes['#status'].textContent,/Test price \$1\.49 USD/);
  h=harness({amount:99});await tick();assert.match(h.nodes['#status'].textContent,/Test price \$0\.99 USD/);
  h=harness({hash:'#returned'});await tick();
  assert.match(h.nodes['#status'].textContent,/Return alone proves nothing/);
  assert.equal(h.calls.filter(c=>c.path.includes('reconcile')||c.path.includes('report')||c.path.includes('checkout')).length,0);
  const checkout=h.buttons()[0];const one=checkout.onclick();const two=checkout.onclick();await Promise.all([one,two]);
  assert.equal(h.calls.filter(c=>c.path==='/api/stripe/checkout').length,1);
  assert.equal(h.redirects.length,1);assert.match(h.redirects[0],/^https:\/\/checkout.stripe.com\//);
  const request=h.calls.find(c=>c.path==='/api/stripe/checkout');assert.deepEqual(JSON.parse(request.options.body),{accept_test:true});assert.equal(request.options.headers['X-CSRF-Token'],'fixture-csrf');
  h=harness({hash:'#cancelled'});await tick();assert.match(h.nodes['#status'].textContent,/cancelled/);assert.equal(h.redirects.length,0);
  await h.buttons()[1].onclick();assert.match(h.nodes['#status'].textContent,/paid/);
  await h.buttons()[0].onclick();assert.equal(h.nodes['#report'].hidden,false);assert.match(h.nodes['#report'].textContent,/<script>untrusted/);assert.equal(h.nodes['#report'].innerHTML,undefined);
  h=harness({state:'expired'});await tick();assert.equal(h.buttons().length,1);assert.match(h.buttons()[0].textContent,/Clear/);
  h=harness({url:'https://evil.example/pay'});await tick();await h.buttons()[0].onclick();assert.equal(h.redirects.length,0);assert.match(h.nodes['#error'].textContent,/Unsupported/);
  h=harness({failed:true});await tick();assert.match(h.nodes['#error'].textContent,/Sandbox disabled/);assert.equal(h.buttons().length,0);
  h=harness({verified:false});await tick();assert.match(h.buttons()[0].textContent,/synthetic code/);assert.equal(h.calls.some(c=>c.path.startsWith('/api/stripe/')),false);
  console.log('PASS: Stripe sandbox UI explicit redirect, duplicate-click guard, fixed request/CSRF, pending/cancel/expired/disabled states, server reconciliation, safe report text and untrusted destination rejection. Offline DOM harness only, not rendered browser QA.');
})().catch(e=>{console.error(e);process.exitCode=1;});
