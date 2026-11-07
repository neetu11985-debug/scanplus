"""Synthetic-only local demo with transactional sessions and explicit request boundaries."""
import json, os, secrets, time, threading, sqlite3, io
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from http.cookies import SimpleCookie, CookieError
from socketserver import TCPServer
from uuid import uuid4
from providers import FixtureDiscovery, FixtureRemoval
from payments import DemoGateway
from stripe_routes import StripeRoutes
from pricing import LookupPricing
from history import DemoHistory
from storage import Store,digest
from config import SESSION_TTL,CHALLENGE_TTL,DB_PATH,require_demo

ROOT=Path(__file__).parent/'static'
TTL=SESSION_TTL
PHONE='+12025550147'
FIXTURE_PHONES=(PHONE,'+12025550148')
STORE=Store(DB_PATH)
PRICING=LookupPricing()  # No active coupons. Inject approved server-owned configuration only.

class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]

class Handler(StripeRoutes, BaseHTTPRequestHandler):
    def setup(self):
        super().setup();self.connection.settimeout(5)
    def log_message(self,*_):pass  # No URL, body, cookie, number, code, nonce or exception logs.
    def reply(self,status,data,cookie=None):
        raw=json.dumps(data).encode();self.send_response(status);self.headers_common()
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        if cookie:self.send_header('Set-Cookie',cookie)
        if status==429:self.send_header('Retry-After','60')
        self.end_headers();self.wfile.write(raw)
    def headers_common(self):
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    def origin(self):return getattr(self,'scheme','http')+'://'+self.headers.get('Host','')
    def valid_host(self):
        origin=self.origin()
        configured=os.environ.get('SCANPLUS_ALLOWED_ORIGINS','')
        if configured:return origin in configured.split(',')
        host=self.headers.get('Host','').split(':')[0]
        return getattr(self,'scheme','http')=='http' and host in ('127.0.0.1','localhost')
    def session(self):
        try:c=SimpleCookie(self.headers.get('Cookie',''))
        except CookieError:return None
        raw=c['sid'].value if 'sid' in c else ''
        if not raw or len(raw)>128:return None
        self.sid=digest(raw)
        s=STORE.get('session',self.sid,self.sid)
        if s and s['verified'] and not STORE.is_current_identity(s['phone_ref'],self.sid):return None
        return s
    def save(self,s):STORE.put('session',self.sid,self.sid,s['expires'],s)
    def do_GET(self):self.dispatch(self.get)
    def do_POST(self):self.dispatch(self.post)
    def dispatch(self,fn):
        output=self.wfile;self.wfile=io.BytesIO()
        try:
            require_demo()
            if not self.valid_host():return self.reply(403,{'error':'Unapproved host or scheme.'})
            if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.reply(403,{'error':'Same-origin request required.'})
            with STORE.transaction():
                STORE.prune();return fn()
        except RuntimeError:
            self.wfile.seek(0);self.wfile.truncate();self.reply(503,{'error':'Live mode is disabled; required production dependencies are absent.'})
        except sqlite3.Error:
            self.wfile.seek(0);self.wfile.truncate();self.reply(503,{'error':'Storage unavailable. No operation has been confirmed; retry later.'})
        except (TimeoutError,OSError):return  # Disconnected/slow client; never echo request details.
        finally:
            payload=self.wfile.getvalue();self.wfile=output
            try:output.write(payload)
            except OSError:pass
    def get(self):
        if self.path in ('/api/stripe/status', '/api/stripe/report', '/api/stripe/report/download'):
            return self.stripe_get(STORE)
        if self.path=='/api/session/status':return self.reply(200,{'active':self.session() is not None})
        if self.path=='/api/session':
            if self.headers.get('Origin') not in (None,self.origin()):return self.reply(403,{'error':'Same-origin request required.'})
            s=self.session()
            if not s:return self.reply(200,{'active':False})
            if not STORE.allow('session:'+self.sid,60):return self.reply(429,{'error':'Too many requests. Wait one minute.'})
            csrf=secrets.token_urlsafe(32);s['csrf_hash']=digest(csrf);self.save(s)
            return self.reply(200,{'active':True,'csrf_token':csrf,'verified':s['verified'] and s['verified_until']>time.time(),'paid':s['paid'],'has_history':bool(DemoHistory(STORE).items(s['phone_ref']))})
        if self.path=='/api/history':
            s=self.session()
            if not s or not s['verified'] or time.time()-s.get('verified_at',0)>CHALLENGE_TTL:return self.reply(403,{'error':'Fresh demo verification required for payment history.'})
            if not STORE.allow('session:'+self.sid,60):return self.reply(429,{'error':'Too many requests. Wait one minute.'})
            return self.reply(200,{'demo':True,'payments':DemoHistory(STORE).items(s['phone_ref'])})
        if self.path in ('/api/report','/api/export'):
            s=self.session()
            if s and not STORE.allow('session:'+self.sid,60):return self.reply(429,{'error':'Too many requests. Wait one minute.'})
            if not s or not s['paid'] or s['verified_until']<=time.time():
                return self.reply(403,{'error':'Complete current test verification and checkout first.'})
            if s.get('receipt',{}).get('payment_id'):DemoHistory(STORE).save(s['phone_ref'],s['receipt'])
            report={'demo':True,'phone':next((p for p in FIXTURE_PHONES if digest(p)==s['phone_ref']),None),'report_id':s['report_id'],'providers':FixtureDiscovery().discover(),'removal':s['removal'],'refund':s.get('refund')}
            if self.path=='/api/export':
                raw=json.dumps(report).encode();self.send_response(200);self.headers_common();self.send_header('Content-Type','application/json');self.send_header('Content-Disposition','attachment; filename=scanplus-demo-report.json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            return self.reply(200,report)
        paths={'/':'index.html','/app.js':'app.js','/style.css':'style.css', '/stripe-test':'stripe-test.html', '/stripe-test.js':'stripe-test.js'}
        if self.path not in paths:return self.reply(404,{'error':'Page not found.'})
        p=ROOT/paths[self.path];raw=p.read_bytes();self.send_response(200);self.headers_common()
        self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[p.suffix[1:]])
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def post(self):
        if self.path == '/api/stripe/webhook':
            return self.stripe_webhook(STORE)
        if self.headers.get('Origin')!=self.origin():return self.reply(403,{'error':'Same-origin request required.'})
        try:
            if self.headers.get('Transfer-Encoding'):return self.reply(400,{'error':'Transfer encoding is unsupported.'})
            n=int(self.headers.get('Content-Length','0'))
            if n<0:return self.reply(400,{'error':'Invalid request size.'})
            if n>2048:return self.reply(413,{'error':'Request too large.'})
            raw=self.rfile.read(n)
            if len(raw)!=n:return self.reply(400,{'error':'Incomplete request.'})
            data=json.loads(raw)
            if not isinstance(data,dict):return self.reply(400,{'error':'Invalid request.'})
        except (ValueError,UnicodeError):return self.reply(400,{'error':'Invalid JSON request.'})
        s=self.session()
        if self.path=='/api/start':
            ip=getattr(self,'client_address',('unknown',))[0]
            if not STORE.allow('start:'+ip,10):return self.reply(429,{'error':'Too many new sessions. Wait one minute.'})
            if data.get('phone') not in FIXTURE_PHONES or data.get('consent') is not True:
                return self.reply(400,{'error':'Only the synthetic demo number is enabled. Confirm the demo declaration.'})
            if s:return self.reply(400,{'error':'Clear this session before starting again.'})
            if STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='session'").fetchone()[0]>=1000:
                return self.reply(503,{'error':'Demo capacity reached. Try later.'})
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);self.sid=digest(token);now=time.time()
            s={'verified':False,'verified_until':0,'paid':False,'expires':now+TTL,'attempts':0,'challenge_expires':now+CHALLENGE_TTL,'consumed':False,'phone_ref':digest(data['phone']),'csrf_hash':digest(csrf),'report_id':str(uuid4()),'removal':'not_requested'}
            self.save(s)
            cookie=f'sid={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={TTL}'+('; Secure' if getattr(self,'scheme','http')=='https' else '')
            return self.reply(200,{'demo':True,'csrf_token':csrf},cookie)
        if not s:return self.reply(401,{'error':'Session expired. Start a new demo.'})
        csrf=self.headers.get('X-CSRF-Token','')
        if not csrf or not secrets.compare_digest(digest(csrf),s['csrf_hash']):
            return self.reply(403,{'error':'Session security token expired. Reload this page and retry.'})
        if not STORE.allow('session:'+self.sid,60):return self.reply(429,{'error':'Too many requests. Wait one minute.'})
        if self.path=='/api/clear':
            STORE.clear_owner(self.sid)
            return self.reply(200,{'cleared':True},'sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
        if self.path=='/api/verify':
            if s['consumed']:return self.reply(409,{'error':'This verification was already used.'})
            if s['challenge_expires']<=time.time():return self.reply(410,{'error':'Test verification expired. Clear the session and restart.'})
            s['attempts']+=1;self.save(s)
            if s['attempts']>5:return self.reply(429,{'error':'Too many verification attempts. Clear the session and restart.'})
            supplied=data.get('phone',next((p for p in FIXTURE_PHONES if digest(p)==s['phone_ref']),''))
            if not isinstance(supplied,str) or digest(supplied)!=s['phone_ref']:return self.reply(400,{'error':'Verification number mismatch.'})
            if data.get('code')!='246810':return self.reply(400,{'error':'That test code is incorrect. Use 246810.'})
            s['verified']=True;s['verified_at']=time.time();s['verified_until']=s['expires'];s['consumed']=True;STORE.bind_identity(s['phone_ref'],self.sid,s['expires']);self.save(s)
            return self.reply(200,{'verified':True,'demo':True,'has_history':bool(DemoHistory(STORE).items(s['phone_ref']))})
        if not s['verified'] or s['verified_until']<=time.time():return self.reply(403,{'error':'Current test verification is required.'})
        if self.path.startswith('/api/stripe/'):
            return self.stripe_post(STORE, s, data)
        if self.path=='/api/quote':
            try:quote=DemoGateway(PRICING).quote(s,data.get('coupon_code',''))
            except ValueError as e:return self.reply(400,{'error':str(e)})
            return self.reply(200,quote)
        if self.path=='/api/checkout':
            if data.get('accept') is not True:return self.reply(400,{'error':'Accept the demo checkout terms.'})
            try:
                receipt=DemoGateway(PRICING).checkout(s,data.get('coupon_code',''))
                DemoHistory(STORE).save(s['phone_ref'],receipt)
            except ValueError as e:return self.reply(400,{'error':str(e)})
            self.save(s);return self.reply(200,receipt)
        if self.path in ('/api/refund','/api/history/delete'):
            if time.time()-s.get('verified_at',0)>CHALLENGE_TTL:return self.reply(403,{'error':'Fresh demo verification required for payment history.'})
            history=DemoHistory(STORE)
            if self.path=='/api/history/delete':
                if data.get('confirm') is not True:return self.reply(400,{'error':'Confirm deletion of your synthetic history.'})
                history.delete(s['phone_ref']);s.pop('receipt',None);s.pop('refund',None);s['paid']=False;self.save(s)
                return self.reply(200,{'deleted':True,'demo':True})
            try:
                result=history.request(s['phone_ref'],data.get('payment_id',s.get('receipt',{}).get('payment_id')),data.get('confirm'),data.get('category','voluntary'))
            except LookupError:return self.reply(404,{'error':'Original payment not available for this verified demo user.'})
            except ValueError as e:return self.reply(409 if data.get('confirm') is True else 400,{'error':str(e)})
            s['refund']=result;self.save(s);return self.reply(200,result)
        if not s['paid']:return self.reply(403,{'error':'Test checkout is required.'})
        if self.path=='/api/removal':
            if data.get('provider')!='fixture':return self.reply(409,{'error':'Live removal is disabled. Follow official instructions.'})
            if s['removal']=='not_requested':
                if data.get('authorize') is not True:return self.reply(400,{'error':'Explicit simulation authorization required.'})
                s['removal']=FixtureRemoval().submit('fixture',True)['status'];self.save(s)
            return self.reply(200,{'status':s['removal'],'demo':True})
        if self.path=='/api/removal/status':
            s['removal']={'request_submitted':'pending','pending':'removal_confirmed'}.get(s['removal'],s['removal']);self.save(s)
            return self.reply(200,{'status':s['removal'],'demo':True})
        return self.reply(404,{'error':'Endpoint not found.'})

if __name__=='__main__':
    require_demo();port=int(os.environ.get('PORT','4173'))
    server=LocalHTTPServer(('127.0.0.1',port),Handler)
    print(f'ScanPlus demo: http://127.0.0.1:{port} — synthetic data only',flush=True)
    def cleanup():
        while True:
            time.sleep(30)
            try:
                with STORE.transaction():STORE.prune()
            except sqlite3.Error:pass
    threading.Thread(target=cleanup,daemon=True).start();server.daemon_threads=True;server.serve_forever(poll_interval=.5)
