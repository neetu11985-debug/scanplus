import contextlib,io,json,tempfile,time,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_server as journey_module
import server
from storage import Store,digest
from privacy import safe_event
from poynt_contract import PoyntContractHarness,SyntheticPoyntTransport,PaymentBlocked
from test_poynt_contract import txn

class Adversarial(unittest.TestCase):
    setUpClass=classmethod(journey_module.Journey.setUpClass.__func__)
    tearDownClass=classmethod(journey_module.Journey.tearDownClass.__func__)
    setUp=journey_module.Journey.setUp
    req=journey_module.Journey.req
    start=journey_module.Journey.start
    ready=journey_module.Journey.ready
    def session_key(self):return digest(self.cookie.split('=',1)[1])
    def edit_session(self,**changes):
        key=self.session_key()
        with server.STORE.transaction():
            s=server.STORE.get('session',key,key);s.update(changes);server.STORE.put('session',key,key,s['expires'],s)
    def test_two_sessions_report_and_csrf_isolation(self):
        self.ready();first=self.req('report')[1]['report_id'];a_cookie,a_csrf=self.cookie,self.csrf
        self.cookie='';self.csrf='';self.req('start',{'phone':server.FIXTURE_PHONES[1],'consent':True})
        self.assertEqual(self.req('report')[0],403)
        self.assertEqual(self.req('checkout',{'accept':True,'report_id':first})[0],403)
        b_csrf=self.csrf;self.csrf=a_csrf
        self.assertEqual(self.req('verify',{'code':'246810'})[0],403)
        self.csrf=b_csrf;self.req('verify',{'code':'246810'});self.req('checkout',{'accept':True})
        second=self.req('report')[1]['report_id'];self.assertNotEqual(first,second)
        self.cookie,self.csrf=a_cookie,a_csrf;self.assertEqual(self.req('report')[1]['report_id'],first)
    def test_verification_replay_expiry_and_number_binding(self):
        self.start();self.assertEqual(self.req('verify',{'code':'246810','phone':'+12025550148'})[0],400)
        self.req('verify',{'code':'246810'});self.assertEqual(self.req('verify',{'code':'246810'})[0],409)
        self.req('clear',{});self.start();self.edit_session(challenge_expires=0)
        self.assertEqual(self.req('verify',{'code':'246810'})[0],410)
    def test_missing_csrf_and_rotation(self):
        self.start();old=self.csrf;self.csrf=''
        self.assertEqual(self.req('verify',{'code':'246810'})[0],403)
        self.req('session');self.assertNotEqual(self.csrf,old)
        self.assertEqual(self.req('verify',{'code':'246810'})[0],200)
    def test_restart_preserves_checkout_and_session(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'demo.db';server.STORE.close();server.STORE=Store(path)
            self.ready();first=self.req('report')[1];receipt=self.req('checkout',{'accept':True})[1]
            server.STORE.close();server.STORE=Store(path)
            self.assertEqual(self.req('report')[1]['report_id'],first['report_id'])
            self.assertEqual(self.req('checkout',{'accept':True})[1],receipt)
            server.STORE.close();server.STORE=Store()
    def test_retention_and_clear_delete_without_raw_secrets(self):
        self.ready();dump='\n'.join(server.STORE.conn.iterdump())
        for secret in (server.PHONE,'246810',self.csrf,self.cookie.split('=',1)[1]):self.assertNotIn(secret,dump)
        self.edit_session(expires=0)
        self.assertEqual(self.req('report')[0],403)
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='session'").fetchone()[0],0)
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='demo_payment'").fetchone()[0],1)
    def test_rate_limits_and_bounded_request(self):
        for _ in range(10):
            self.cookie='';self.csrf='';self.assertEqual(self.start()[0],200)
        self.cookie='';self.csrf='';self.assertEqual(self.start()[0],429)
        self.assertEqual(self.req('start',{'phone':'x'*3000,'consent':True})[0],413)
    def test_logs_do_not_expose_payload(self):
        out=io.StringIO()
        with contextlib.redirect_stderr(out):self.req('start',{'phone':'+12025550148','code':'987654','token':'SECRET','consent':True})
        self.assertEqual(out.getvalue(),'')
        event=safe_event('provider_unavailable',status=503,phone=server.PHONE,code='987654',token='SECRET',exception='raw secret',reason='timeout')
        self.assertEqual(event,{'event':'provider_unavailable','status':503,'reason':'timeout'})
    def test_payment_restart_nonce_and_transaction_tombstones(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger.db';store=Store(path)
            first=PoyntContractHarness(SyntheticPoyntTransport((200,{'id':'fixture-txn'}),(200,txn())),store)
            order=first.create_order(verified=True,service_available=True,owner='session-a')
            first.charge_fixture(order.id,'fixture-nonce-one',owner='session-a');first.reconcile_fixture(order.id,owner='session-a')
            store.close();store=Store(path);transport=SyntheticPoyntTransport();second=PoyntContractHarness(transport,store)
            self.assertEqual(second.charge_fixture(order.id,'fixture-nonce-one',owner='session-a'),'paid');self.assertEqual(transport.calls,[])
            with self.assertRaises(PaymentBlocked):second.reconcile_fixture(order.id,owner='session-b')
            other=second.create_order(verified=True,service_available=True,owner='session-b')
            with self.assertRaises(PaymentBlocked):second.charge_fixture(other.id,'fixture-nonce-one',owner='session-b')
            dump='\n'.join(store.conn.iterdump());self.assertNotIn('fixture-nonce-one',dump);store.close()
    def test_uncertain_payment_survives_restart_without_recharge(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger.db';store=Store(path);first=PoyntContractHarness(SyntheticPoyntTransport(TimeoutError()),store)
            order=first.create_order(verified=True,service_available=True);first.charge_fixture(order.id,'fixture-nonce-one');store.close()
            store=Store(path);transport=SyntheticPoyntTransport();second=PoyntContractHarness(transport,store)
            self.assertEqual(second.charge_fixture(order.id,'fixture-nonce-one'),'uncertain');self.assertEqual(transport.calls,[]);store.close()
    def test_two_workers_submit_only_once(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger.db';one=Store(path);two=Store(path)
            t1=SyntheticPoyntTransport((200,{'id':'fixture-txn'}));t2=SyntheticPoyntTransport((200,{'id':'fixture-txn'}))
            a=PoyntContractHarness(t1,one);b=PoyntContractHarness(t2,two)
            order=a.create_order(verified=True,service_available=True)
            with ThreadPoolExecutor(2) as workers:
                futures=[workers.submit(h.charge_fixture,order.id,'fixture-nonce-one') for h in (a,b)]
                for future in futures:self.assertIn(future.result(),('pending','uncertain'))
            self.assertEqual(len(t1.calls)+len(t2.calls),1)
            one.close();two.close()
    def test_unknown_host_and_fetch_site_rejected(self):
        import http.client
        for headers in ({'Host':'evil.test','Origin':'http://evil.test'},{'Sec-Fetch-Site':'cross-site'}):
            c=http.client.HTTPConnection('127.0.0.1',self.port)
            c.request('GET','/api/session',headers=headers);r=c.getresponse();r.read();self.assertEqual(r.status,403);c.close()
    def test_paid_report_requires_unexpired_verification(self):
        self.ready();self.edit_session(verified_until=0)
        self.assertEqual(self.req('report')[0],403)
        self.assertEqual(self.req('checkout',{'accept':True})[0],403)
    def test_live_process_fails_closed(self):
        import os,subprocess
        with tempfile.TemporaryDirectory() as root:
            env=dict(os.environ,SCANPLUS_MODE='live',SCANPLUS_DB_PATH=str(Path(root)/'refused.db'))
            result=subprocess.run([sys.executable,str(Path(server.__file__))],env=env,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('http://127.0.0.1',result.stdout)
            self.assertIn('Production unavailable',result.stderr)
    def test_storage_commit_failure_does_not_confirm_action(self):
        import sqlite3
        from contextlib import contextmanager
        class FailingStore(Store):
            @contextmanager
            def transaction(self):
                with super().transaction() as tx:
                    yield tx
                    raise sqlite3.OperationalError('sensitive database detail')
        server.STORE.close();server.STORE=FailingStore()
        status,data=self.start();self.assertEqual(status,503)
        self.assertNotIn('csrf_token',data);self.assertNotIn('sensitive',json.dumps(data))
        self.assertEqual(server.STORE.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
    def test_config_retention_bounds_and_idle_prune(self):
        import os,subprocess
        from unittest.mock import patch
        import maintenance
        result=subprocess.run([sys.executable,'-c','import config'],cwd=str(Path(server.__file__).parent),env=dict(os.environ,SCANPLUS_SESSION_TTL='0'),capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('outside supported bounds',result.stderr)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'prune.db';store=Store(path)
            with store.transaction():store.put('session','expired','owner',0,{'fixture':True})
            store.close();output=io.StringIO()
            with patch.object(maintenance,'DB_PATH',str(path)),contextlib.redirect_stdout(output):maintenance.main()
            self.assertEqual(output.getvalue().strip(),'Expired synthetic records deleted: 1')
            store=Store(path);self.assertEqual(store.conn.execute('SELECT COUNT(*) FROM records').fetchone()[0],0);store.close()
