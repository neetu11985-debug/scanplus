'use strict';
// DOM harness for local input behavior. Uses reserved synthetic numbers only.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
class Element {
  constructor(){this.value='';this.textContent='';this.innerHTML='';this.open=false;this.handlers={};this.classList={add(){},remove(){},toggle(){}};}
  addEventListener(type,handler){this.handlers[type]=handler;}
  setAttribute(){} removeAttribute(){} focus(){this.focused=true;} scrollIntoView(){}
}
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const windowHandlers={};let requests=0;
const context=vm.createContext({
  document:{querySelector:element,querySelectorAll:()=>[],body:element('body'),addEventListener(){},hidden:false},
  window:{addEventListener:(type,handler)=>windowHandlers[type]=handler},
  fetch:async()=>{requests++;return {ok:true,json:async()=>({active:false})};},
  AbortController,setTimeout,clearTimeout,setInterval:()=>0,
  localStorage:{setItem(){throw Error('Phone entry must never use browser storage.');}},
  sessionStorage:{setItem(){throw Error('Phone entry must never use browser storage.');}}
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8'),context);
(async()=>{
  // Let the unrelated fixture-session bootstrap settle first.
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(requests,1,'Only the normal empty-session bootstrap may request data.');
  const normalize=value=>context.normalizeLocalPhone(value);
  assert.equal(normalize('+1 (202) 555-0147'),'+12025550147');
  assert.equal(normalize('  +44 7700 900123  '),'+447700900123');
  for(const value of ['2025550147','+012345678','+1234567','+1234567890123456','+12025550147 ext 2','<script>','+1/2025550147',''])assert.equal(normalize(value),null,value);
  const phone=element('#local-phone'),status=element('#local-number-status'),form=element('#local-number-form');
  let prevented=0;const submit=()=>form.handlers.submit({preventDefault(){prevented++;}});
  phone.value='+1 (202) 555-0147';submit();
  assert.equal(phone.value,'');assert.match(status.textContent,/ending 0147/);
  assert.match(status.textContent,/No online lookup or ownership verification/);
  assert.ok(!status.textContent.includes('202555'));
  phone.value='2025550147';submit();assert.match(status.textContent,/Enter \+/);
  element('#local-number-clear').handlers.click();assert.equal(phone.value,'');assert.equal(status.textContent,'');assert.equal(phone.focused,true);
  phone.value='+1 202 555 0148';submit();assert.match(status.textContent,/ending 0148/);
  element('#local-number-test').open=false;element('#local-number-test').handlers.toggle();assert.equal(status.textContent,'');assert.equal(phone.value,'');
  phone.value='+1 202 555 0147';windowHandlers.pagehide();assert.equal(phone.value,'');
  assert.equal(requests,1,'No personal input may make a network call.');
  assert.equal(prevented,3,'Submission must always suppress native form navigation.');
  console.log('PASS: format acceptance/rejection, masking, repeated input, clear, close, page leave, no input network/storage calls.');
})().catch(error=>{console.error(error);process.exitCode=1;});
