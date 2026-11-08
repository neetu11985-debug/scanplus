'use strict';
// Exercise the exact pure formatter embedded in each UI, without any network.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
for(const name of ['static/live.js','static/no_sms.js']){
  const source=fs.readFileSync(name,'utf8'),start=source.indexOf('function searchDiagnosticMarkup('),end=source.indexOf('// End search diagnostics.');
  assert.ok(start>=0&&end>start);
  const context=vm.createContext({});vm.runInContext(source.slice(start,end),context);
  const format=context.searchDiagnosticMarkup;
  assert.match(format({category:'timeout',http_status:200}),/timed out.*HTTP 200.*No automatic retry/);
  assert.match(format({category:'dns_error'}),/could not be resolved.*status unavailable/);
  assert.match(format({category:'network_permission_denied'}),/permission restriction/);
  for(const category of ['<img src=x onerror=alert(1)>','PRIVATE-EXCEPTION-BODY','__proto__',{},null]){
    const result=format({category,http_status:'PRIVATE-STATUS',message:'PRIVATE-KEY'});
    assert.match(result,/unclassified transport reason.*status unavailable/);
    assert.ok(!/PRIVATE|<img|__proto__/.test(result));
  }
  for(const http_status of [true,99,600,200.5,'200',{},null])assert.match(format({category:'http_error',http_status}),/HTTP status unavailable/);
  for(const value of [null,undefined,[],true,'PRIVATE'])assert.equal(format(value),'');
  assert.ok(source.includes('searchDiagnosticMarkup(source.search_diagnostic)'));
}
console.log('PASS: both search UIs render only allowlisted categories and numeric HTTP status; unknown/raw data is discarded. No network.');
