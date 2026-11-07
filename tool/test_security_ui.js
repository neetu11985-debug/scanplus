'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

class Element {
  constructor(tag = 'div') {this.tag = tag; this.children = []; this.events = {}; this.hidden = false; this.disabled = false; this.textContent = ''; this.href = undefined;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children = nodes;}
  addEventListener(name, handler) {this.events[name] = handler;}
  removeAttribute(name) {delete this[name];}
  async click() {if (!this.disabled && this.events.click) await this.events.click();}
}
const ids = Object.fromEntries(['status', 'credentials', 'save-report', 'download'].map(id => [id, new Element()]));
ids['save-report'].tag = 'button'; ids['save-report'].disabled = true; ids.download.hidden = true;
const events = {};
const walk = node => [node, ...node.children.flatMap(walk)];
const document = {getElementById: id => ids[id], createElement: tag => new Element(tag),
  querySelectorAll: tag => Object.values(ids).flatMap(walk).filter(node => node.tag === tag)};
const calls = [];
let configured = false;
let hold;
let failNext = false;
const fetch = async (path, options) => {
  calls.push({path, options});
  assert(!path.startsWith('http'));
  assert.equal(options.credentials, 'same-origin');
  if (hold) await new Promise(resolve => {hold.resolve = resolve;});
  if (failNext) {failNext = false; return {ok: false, json: async () => ({error: 'Current authenticated identity required.'})};}
  if (path === '/api/admin/status') return {ok: true, json: async () => ({synthetic_only: true, providers_enabled: false,
    csrf_token: 'c'.repeat(48), credentials: [{name: 'serper_api_key', label: 'Serper', configured}]})};
  assert.equal(options.headers['X-CSRF-Token'], 'c'.repeat(48));
  const data = JSON.parse(options.body);
  assert.equal(data.confirm_synthetic, true);
  assert(!('value' in data)); assert(!('phone' in data)); assert(!('report' in data)); assert(!('paid' in data));
  if (path === '/api/admin/credential') {configured = true; return {ok: true, json: async () => ({saved: true, synthetic_only: true})};}
  assert.equal(path, '/api/security/demo-record');
  return {ok: true, json: async () => ({report_id: 'fixture-report', synthetic_only: true, download_url: '/api/reports/fixture-report/download'})};
};
const context = {document, window: {addEventListener: (name, handler) => {events[name] = handler;}}, fetch};
const flush = async () => {for (let i = 0; i < 10; i++) await new Promise(resolve => setImmediate(resolve));};
vm.runInNewContext(fs.readFileSync('static/security/admin.js', 'utf8'), context);
(async () => {
  await flush();
  assert.equal(ids.credentials.children[0].children[1].textContent, 'Save test value');
  await ids.credentials.children[0].children[1].click(); await flush();
  assert.equal(ids.credentials.children[0].children[1].textContent, 'Replace test value');
  await ids['save-report'].click(); await flush();
  assert.equal(ids.download.href, '/api/reports/fixture-report/download');
  assert.equal(ids.download.hidden, false);
  hold = {};
  const before = calls.length;
  ids['save-report'].click(); ids['save-report'].click();
  assert.equal(calls.length, before + 1, 'repeated click must not duplicate request');
  events.pagehide();
  const release = hold.resolve; hold = null; release(); await flush();
  assert.equal(ids.download.hidden, true, 'stale response must not restore report link');
  assert.equal(ids.download.href, undefined);
  events.pageshow({persisted: true}); await flush();
  assert.equal(ids['save-report'].disabled, false);
  failNext = true;
  await ids['save-report'].click(); await flush();
  assert.match(ids.status.textContent, /authenticated identity/);
  assert.equal(ids.download.hidden, true);
  console.log('PASS: security preview status-only credentials, fixed synthetic payloads, same-origin requests, duplicate clicks, stale responses, back/forward restore and error state. Not visual browser QA.');
})().catch(error => {console.error(error); process.exitCode = 1;});
