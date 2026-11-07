'use strict';
// Offline DOM harness. No browser, packages, external requests or real checkout.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const elements=new Map();
let panelChildren=[];
class Element {
  constructor(id){
    this.id=id;this.value='';this.textContent='';this._html='';this.hidden=false;
    this.disabled=false;this.checked=false;this.isConnected=true;this.handlers={};
    this.classList={add(){},remove(){},toggle(){}};
  }
  get innerHTML(){return this._html;}
  set innerHTML(html){
    this._html=html;
    if(this.id==='#panel'){
      for(const element of panelChildren){element.isConnected=false;elements.delete(element.id);}
      panelChildren=[];
      for(const match of html.matchAll(/id="([^"]+)"/g)){
        const element=new Element('#'+match[1]);elements.set(element.id,element);panelChildren.push(element);
      }
    }
  }
  addEventListener(type,fn){this.handlers[type]=fn;}
  setAttribute(){} removeAttribute(){} focus(){} scrollIntoView(){}
}
function el(id){if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);}
const pending=[], requests=[];
let reportLoads=0;
const context=vm.createContext({
  document:{querySelector:el,querySelectorAll:()=>[],body:el('body'),addEventListener(){}},
  window:{addEventListener(){}},AbortController,setTimeout,clearTimeout,setInterval:()=>0,
  fetch:async(url,options)=>{
    requests.push({url,body:options.body?JSON.parse(options.body):null});
    if(url==='/api/session')return {ok:true,json:async()=>({active:false})};
    assert.ok(['/api/quote','/api/checkout'].includes(url),'Unexpected network request '+url);
    return new Promise(resolve=>pending.push({url,body:JSON.parse(options.body),reply(body,status=200){resolve({ok:status===200,json:async()=>body});}}));
  },
  reportReady(){reportLoads++;el('#panel').innerHTML='<h3>Report ready</h3>';}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8'),context);
vm.runInContext('loadReport=async()=>reportReady()',context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const next=url=>{
  const index=pending.findIndex(request=>request.url===url);
  assert.notEqual(index,-1,'Expected request '+url);
  return pending.splice(index,1)[0];
};
const quote=(discount=0,code=null,locked=false)=>({list_price_cents:149,discount_cents:discount,amount_cents:149-discount,
  currency:'USD',billing:'one_time',coupon_code:code,charged_cents:0,mode:'test',locked});
function submit(){return el('#checkout-form').onsubmit({preventDefault(){}});}
function edit(code){el('#coupon-code').value=code;el('#coupon-code').oninput();}
async function openCheckout(){
  context.checkout();assert.equal(el('#complete-checkout').disabled,true);
  next('/api/quote').reply(quote());await settle();
}
(async()=>{
  await settle();
  await openCheckout();
  assert.equal(el('#lookup-price').textContent,'$1.49');
  assert.equal(el('#lookup-total').textContent,'$1.49');
  assert.equal(el('#coupon-discount-row').hidden,true);
  assert.equal(el('#complete-checkout').disabled,false);

  edit('fixture');
  assert.equal(el('#complete-checkout').disabled,true,'Editing invalidates the old quote.');
  el('#apply-coupon').onclick();el('#apply-coupon').onclick();
  assert.equal(pending.length,1,'Repeated apply cannot create overlapping quotes.');
  assert.equal(el('#coupon-code').disabled,true);
  const applied=next('/api/quote');assert.equal(applied.body.coupon_code,'fixture');
  applied.reply(quote(24,'FIXTURE'));await settle();
  assert.equal(el('#lookup-total').textContent,'$1.25');
  assert.equal(el('#coupon-discount').textContent,'−$0.24');
  assert.equal(el('#coupon-discount-row').hidden,false);
  assert.match(el('#coupon-status').textContent,/Code applied: FIXTURE/);
  assert.equal(el('#complete-checkout').disabled,false);

  edit('invalid');el('#apply-coupon').onclick();
  next('/api/quote').reply({error:'Coupon code is invalid or unavailable.'},400);await settle();
  assert.equal(el('#complete-checkout').disabled,true);
  assert.equal(el('#lookup-total').textContent,'Unavailable');
  assert.equal(el('#coupon-discount-row').hidden,true);
  assert.match(el('#coupon-status').textContent,/Clear the code or try again/);
  await submit();assert.equal(pending.length,0,'Invalid quote must not submit.');

  el('#remove-coupon').onclick();
  const cleared=next('/api/quote');assert.equal(cleared.body.coupon_code,'');
  cleared.reply(quote());await settle();
  assert.equal(el('#coupon-code').value,'');
  assert.equal(el('#lookup-total').textContent,'$1.49');
  el('#terms').checked=true;
  const completion=submit();await submit();
  assert.equal(pending.length,1,'Double submission must not create a second checkout request.');
  assert.equal(el('#coupon-code').disabled,true,'Code cannot change during checkout.');
  const payment=next('/api/checkout');
  assert.deepEqual(payment.body,{accept:true,coupon_code:''},'Only consent and optional code may be submitted.');
  payment.reply({charged_cents:0});await completion;
  assert.equal(reportLoads,1);

  context.checkout();
  const abandoned=next('/api/quote');
  el('#panel').innerHTML='<h3>Cleared session</h3>';
  abandoned.reply(quote(149,'FIXTURE'));await settle();
  assert.equal(el('#panel').innerHTML,'<h3>Cleared session</h3>','Late quote must not replace a new screen.');

  await openCheckout();el('#terms').checked=true;
  const abandonedCheckout=submit();
  const delayed=next('/api/checkout');
  el('#panel').innerHTML='<h3>Other screen</h3>';
  delayed.reply({charged_cents:0});await abandonedCheckout;
  assert.equal(reportLoads,1,'Late checkout must not navigate away from a new screen.');
  assert.equal(el('#panel').innerHTML,'<h3>Other screen</h3>');

  context.checkout();
  next('/api/quote').reply({...quote(0,null,true),list_price_cents:100,amount_cents:100});await settle();
  assert.equal(el('#lookup-total').textContent,'$1.00','A legacy receipt keeps its original intended amount.');
  assert.equal(el('#coupon-code').disabled,true);
  assert.equal(el('#apply-coupon').disabled,true);
  assert.equal(el('#remove-coupon').disabled,true);
  assert.match(el('#coupon-status').textContent,/original price is unchanged/);

  await openCheckout();el('#terms').checked=true;
  const failedCheckout=submit();
  next('/api/checkout').reply({error:'Coupon code is invalid or unavailable.'},400);await failedCheckout;
  assert.equal(el('#alert').hidden,false);
  assert.match(el('#alert').textContent,/invalid or unavailable/);
  assert.equal(el('#coupon-code').disabled,false,'A failed checkout allows recovery.');
  assert.equal(pending.length,0);
  console.log('PASS: server price, optional apply/clear, invalid code, quote invalidation, duplicate actions, stale-response navigation, legacy receipt, checkout recovery.');
})().catch(error=>{console.error(error);process.exitCode=1;});
