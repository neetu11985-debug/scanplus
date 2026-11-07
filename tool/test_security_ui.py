"""Optional offline Chromium QA using intercepted HTTPS and synthetic identities.

Requires Playwright and a locally installed Chromium. No listening server, real
TLS verification, provider call, deployment or authentication-provider test.
"""
import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from encrypted_storage import EncryptedStore
from secure_admin import Principal, PaidStorageGrant, create_preview, REPORT
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence' / 'security-preview'
EVIDENCE.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
    store = EncryptedStore(Path(directory) / 'fixture.sqlite3', {1: b'Q' * 32}, 1)
    current = {'principal': Principal('fixture_owner_a', 'admin', 9999999999, 'c' * 48)}
    app = create_preview(store, lambda env: current['principal'], origin='https://security.example.invalid',
        verify_payment=lambda identity: PaidStorageGrant(identity.owner_id, 'fixture_paid_order_1', 149, 'USD', 9999999999))
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True)
    context = browser.new_context(viewport={'width': 1280, 'height': 1000}, accept_downloads=True)
    errors = []
    def intercept(route):
        request = route.request
        url = urlsplit(request.url)
        if url.netloc != 'security.example.invalid':
            raise AssertionError('Unexpected external request')
        headers = request.all_headers()
        body = (request.post_data or '').encode()
        env = {'REQUEST_METHOD': request.method, 'PATH_INFO': url.path, 'QUERY_STRING': url.query,
               'wsgi.url_scheme': 'https', 'HTTP_HOST': url.netloc,
               'CONTENT_TYPE': headers.get('content-type', ''), 'CONTENT_LENGTH': str(len(body)),
               'wsgi.input': io.BytesIO(body)}
        for name, value in headers.items():
            if name not in ('content-type', 'content-length'):
                env['HTTP_' + name.upper().replace('-', '_')] = value
        result = {}
        def capture(status, response_headers):
            result.update(status=int(status.split()[0]), headers=dict(response_headers))
        raw = b''.join(app(env, capture))
        route.fulfill(status=result['status'], headers=result['headers'], body=raw)
    context.route('**/*', intercept)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('https://security.example.invalid/admin')
    page.get_by_role('button', name='Save test value', exact=True).first.wait_for()
    page.screenshot(path=str(EVIDENCE / 'admin-desktop.png'), full_page=True)
    page.get_by_role('button', name='Save test value', exact=True).first.click()
    page.get_by_role('button', name='Replace test value', exact=True).wait_for()
    page.get_by_role('button', name='Save a paid synthetic phone & report').click()
    page.get_by_role('link', name='Download my test report (.txt)').wait_for()
    first_url = page.locator('#download').get_attribute('href')
    page.get_by_role('button', name='Save a paid synthetic phone & report').dblclick()
    page.wait_for_function("!document.querySelector('#download').hidden")
    assert page.locator('#download').get_attribute('href') == first_url
    with page.expect_download() as download:
        page.get_by_role('link', name='Download my test report (.txt)').click()
    target = Path(directory) / 'download.txt'
    download.value.save_as(target)
    assert target.read_text() == REPORT
    page.reload()
    page.get_by_role('button', name='Replace test value', exact=True).wait_for()
    assert page.locator('#download').is_hidden()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(EVIDENCE / 'admin-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    current['principal'] = None
    denied = page.evaluate('(url) => fetch(url).then(r => r.status)', first_url)
    assert denied == 401
    assert not errors, errors
    browser.close()
    store.close()
print('PASS: desktop/mobile layout, credential status, encrypted paid save, replay, text download, reload; no external services.')
