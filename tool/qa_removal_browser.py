"""Optional Playwright/Chromium QA. Temporary synthetic HTTP server; blocks external requests."""
import asyncio
import json
import os
import shutil
from pathlib import Path
import sys
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
import server
from storage import Store

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence'/'removal-consent'

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    server.STORE.close();server.STORE=Store(':memory:')
    http=server.LocalHTTPServer(('127.0.0.1',0),server.Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{http.server_address[1]}'
    results=[]
    try:
      async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('PLAYWRIGHT_CHROMIUM_PATH') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
        for name,width,height in [('desktop',1440,1000),('mobile',390,844)]:
          context=await browser.new_context(viewport={'width':width,'height':height})
          page=await context.new_page();external=[];requests=[];errors=[]
          async def restrict(route):
            if not route.request.url.startswith(origin+'/'):
              external.append(route.request.url);await route.abort()
            else:await route.continue_()
          await page.route('**/*',restrict)
          page.on('pageerror',lambda e:errors.append(str(e)))
          page.on('request',lambda req:requests.append((req.method,req.url)))
          await page.goto(origin)
          await page.locator('#phone').fill('+1 202 555 0148')
          await page.locator('#start-submit').click()
          assert 'Live lookup is not connected' in await page.locator('#panel').inner_text()
          assert await page.locator('input[type=tel]').count()==0
          assert not any(url==origin+'/api/start' for method,url in requests)
          await page.locator('#availability-example').click()
          await page.locator('#phone').fill('+1 202 555 0147')
          await page.locator('#control').check()
          await page.locator('#start-submit').click()
          await page.locator('#code').fill('246810')
          await page.locator('#verify-form button').click()
          # An earlier viewport's fixture receipt may remain by design.
          await page.wait_for_selector('#terms, #new-checkout')
          if await page.locator('#new-checkout').count():await page.locator('#new-checkout').click()
          await page.locator('#terms').check()
          await page.locator('#complete-checkout').click()
          await page.locator('#review-removal').click()
          await page.wait_for_selector('#removal-consent-form')
          assert await page.locator('#submit-removal').is_disabled()
          await page.locator('#listing-confirm').check()
          assert await page.locator('#submit-removal').is_disabled()
          await page.locator('#removal-authorize').check()
          assert await page.locator('#submit-removal').is_enabled()
          text=await page.locator('#removal-flow').inner_text()
          for snippet in ['no external recipient','+12025550147','This listing only','No charge','cannot be unsent']:
            assert snippet in text,snippet
          assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Horizontal overflow'
          await page.locator('#removal-flow').screenshot(path=str(OUT/(name+'-consent.png')))
          # Cancel is a genuine non-submission and resets both checks.
          await page.locator('#cancel-removal').click()
          await page.wait_for_selector('#review-removal')
          assert not any(method=='POST' and url==origin+'/api/removal' for method,url in requests)
          await page.locator('#review-removal').click()
          await page.wait_for_selector('#removal-consent-form')
          assert not await page.locator('#listing-confirm').is_checked()
          assert not await page.locator('#removal-authorize').is_checked()
          # Reload discards consent, does not submit, and requires fresh review.
          await page.reload();await page.wait_for_selector('#review-removal')
          assert not await page.locator('#removal-consent-form').count()
          await page.locator('#review-removal').click()
          await page.locator('#listing-confirm').check();await page.locator('#removal-authorize').check()
          # Repeated clicks while a request is in flight yield one call.
          await page.locator('#submit-removal').evaluate('(button)=>{button.click();button.click();}')
          await page.wait_for_selector('#review-removal')
          assert sum(method=='POST' and url==origin+'/api/removal' for method,url in requests)==1
          await page.locator('#review-removal').click();await page.locator('#review-removal').click()
          await page.wait_for_timeout(150)
          assert 'removal not verified' in await page.locator('#removal-flow').inner_text()
          assert 'No broker was contacted' in await page.locator('#removal-flow').inner_text()
          await page.locator('#removal-flow').screenshot(path=str(OUT/(name+'-submitted.png')))
          await page.reload();await page.wait_for_selector('#review-removal')
          assert 'removal not verified' in await page.locator('#removal-flow').inner_text()
          # Clear revokes receipt and removes consent from the rendered UI.
          await page.locator('#reset').click();await page.wait_for_selector('#start-form')
          assert not await page.locator('#removal-consent-form').count()
          assert not await page.locator('#removal-flow').count()
          assert not external,external
          assert not errors,errors
          results.append({'viewport':name,'size':[width,height],'result':'PASS','external_requests':len(external),
                          'checks':['exact disclosure','two unchecked confirmations','cancel','fresh review','reload',
                                    'double click','read-only status','receipt reload','clear session','no horizontal overflow','no JavaScript errors']})
          await context.close()
        await browser.close()
    finally:http.shutdown();http.server_close();server.STORE.close()
    print(json.dumps(results,indent=2));(OUT/'browser-results.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':asyncio.run(main())
