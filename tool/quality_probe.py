"""Controlled synthetic WSGI workload. Temporary DB, no external calls or user data."""
import os,sys,tempfile,time,json,io,resource,statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory() as temp:
    os.environ['SCANPLUS_DB_PATH']=str(Path(temp)/'probe.sqlite3')
    os.environ['SCANPLUS_ALLOWED_ORIGINS']='https://scanplus.test'
    import server
    from storage import Store
    from wsgi import application
    def request(path,data=None,cookie='',csrf='',extra=None):
        body=json.dumps(data).encode() if data is not None else b''
        env={'PATH_INFO':'/api/'+path,'REQUEST_METHOD':'POST' if data is not None else 'GET','CONTENT_LENGTH':str(len(body)),'HTTP_HOST':'scanplus.test','HTTP_ORIGIN':'https://scanplus.test','HTTP_COOKIE':cookie,'HTTP_X_CSRF_TOKEN':csrf,'wsgi.url_scheme':'https','wsgi.input':io.BytesIO(body),'REMOTE_ADDR':'127.0.0.1','SCRIPT_NAME':''}
        if extra:env.update(extra)
        receipt={}
        def start(status,headers):receipt.update(status=int(status.split()[0]),headers=dict(headers))
        raw=b''.join(application(env,start));return receipt,json.loads(raw)
    results=[]
    for workers in (2,8,16):
        server.STORE.close();server.STORE=Store(Path(temp)/f'{workers}.sqlite3')
        clients=[]
        for phone in server.FIXTURE_PHONES:
            receipt,data=request('start',{'phone':phone,'consent':True})
            cookie=receipt['headers']['Set-Cookie'].split(';')[0];csrf=data['csrf_token']
            assert request('verify',{'code':'246810'},cookie,csrf)[0]['status']==200
            assert request('checkout',{'accept':True},cookie,csrf)[0]['status']==200
            clients.append((cookie,csrf))
        def read(i):
            begin=time.perf_counter();reply,_=request('report',cookie=clients[i%2][0]);return reply['status'],(time.perf_counter()-begin)*1000
        begin=time.perf_counter();cpu=time.process_time()
        with ThreadPoolExecutor(workers) as pool:out=list(pool.map(read,range(80)))
        wall=time.perf_counter()-begin;cpu=time.process_time()-cpu
        latency=sorted(v for _,v in out)
        assert all(s==200 for s,_ in out)
        results.append(dict(workers=workers,verified_synthetic_users=2,requests=80,status_200=sum(s==200 for s,_ in out),wall_seconds=round(wall,4),requests_per_second=round(80/wall,1),latency_p50_ms=round(statistics.median(latency),2),latency_p95_ms=round(latency[int(len(latency)*.95)-1],2),cpu_seconds=round(cpu,4),peak_process_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)))
        # Verify per-session read limit; only controlled fixture requests.
        statuses=[request('report',cookie=clients[0][0])[0]['status'] for _ in range(25)]
        assert 429 in statuses
    receipt,payload=request('export',cookie=clients[1][0]);assert receipt['status']==200
    assert 'attachment' in receipt['headers']['Content-Disposition'];assert payload['demo'] and payload['phone']==server.FIXTURE_PHONES[1]
    checks={}
    for name,path,extra,expected in [('host','session',{'HTTP_HOST':'evil.test'},403),('origin','start',{'HTTP_ORIGIN':'https://evil.test'},403),('traversal','../server.py',{},404),('cross_site','session',{'HTTP_SEC_FETCH_SITE':'cross-site'},403)]:
        receipt,_=request(path,{} if path=='start' else None,extra=extra);assert receipt['status']==expected;checks[name]=receipt['status']
    server.STORE.close()
    print(json.dumps({'conditions':'Temporary SQLite, in-process WSGI application and global LOCK, two synthetic identities only; no browser rendering/network/provider latency. Not production capacity.','workloads':results,'limits':'429 observed at per-session 60/minute limit in each workload','local_security_checks':checks,'export':'Authenticated attachment schema/headers verified; OS browser save not inspected.','bottleneck':'WSGI global lock and SQLite serialize operations. Runtime/host and real integrations not qualified.'},indent=2))
