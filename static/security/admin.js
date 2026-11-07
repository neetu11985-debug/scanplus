'use strict';
(() => {
  const status = document.getElementById('status');
  const credentials = document.getElementById('credentials');
  const saveReport = document.getElementById('save-report');
  const download = document.getElementById('download');
  let csrf = '';
  let busy = false;
  let generation = 0;
  const buttons = () => [...document.querySelectorAll('button')];
  async function request(path, body) {
    const requestGeneration = generation;
    const response = await fetch(path, {method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? {'Content-Type': 'application/json', 'X-CSRF-Token': csrf} : {},
      body: body ? JSON.stringify(body) : undefined});
    const data = await response.json();
    if (requestGeneration !== generation) throw new Error('Page changed. Reload to check current state.');
    if (!response.ok) throw new Error(data.error || 'Request unavailable.');
    return data;
  }
  async function refresh() {
    const data = await request('/api/admin/status');
    if (data.synthetic_only !== true || data.providers_enabled !== false) throw new Error('Unexpected preview configuration.');
    csrf = data.csrf_token;
    credentials.replaceChildren();
    for (const item of data.credentials) {
      const row = document.createElement('div'); row.className = 'credential';
      const label = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = item.label;
      const detail = document.createElement('small'); detail.textContent = item.configured ? 'Synthetic value saved · never displayed' : 'Not configured';
      label.append(title, detail);
      const button = document.createElement('button'); button.type = 'button'; button.textContent = item.configured ? 'Replace test value' : 'Save test value';
      button.addEventListener('click', () => perform(async () => {
        await request('/api/admin/credential', {name: item.name, confirm_synthetic: true});
        await refresh(); status.textContent = 'Synthetic value encrypted and saved. No provider was contacted.';
      }));
      row.append(label, button); credentials.append(row);
    }
    saveReport.disabled = false;
  }
  async function perform(action) {
    if (busy) return;
    const actionGeneration = generation;
    busy = true; buttons().forEach(button => {button.disabled = true;}); status.textContent = '';
    try { await action(); }
    catch (error) {
      if (actionGeneration === generation) status.textContent = error.message || 'Operation not confirmed. Reload to check saved state.';
      // Never retry a state-changing request automatically.
    } finally { if (actionGeneration === generation) {busy = false; buttons().forEach(button => {button.disabled = !csrf;});} }
  }
  saveReport.addEventListener('click', () => perform(async () => {
    download.hidden = true; download.removeAttribute('href');
    const data = await request('/api/security/demo-record', {confirm_synthetic: true});
    if (data.synthetic_only !== true || !/^\/api\/reports\/[A-Za-z0-9_-]{1,128}\/download$/.test(data.download_url)) throw new Error('Invalid report destination.');
    download.href = data.download_url; download.hidden = false;
    status.textContent = 'Synthetic phone and text report saved encrypted. Download access checks your identity again.';
  }));
  window.addEventListener('pagehide', () => {generation++; busy = false; csrf = ''; buttons().forEach(button => {button.disabled = true;}); download.hidden = true; download.removeAttribute('href');});
  window.addEventListener('pageshow', event => {if (event.persisted) {csrf = ''; perform(refresh);}});
  perform(refresh);
})();
