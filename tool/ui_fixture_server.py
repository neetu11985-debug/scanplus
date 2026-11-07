"""Isolated local QA runner: disposable store, report failure then empty fixture.
Never imported by production/demo entry points. No provider or network client.
"""
import argparse,os,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--port',type=int,default=4174);a=p.parse_args()
output=Path(a.output).resolve();output.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1]
if root not in output.parents:raise SystemExit('QA output must be inside ScanPlus project.')
os.environ.update(SCANPLUS_DB_PATH=str(output/'qa-only.sqlite3'),SCANPLUS_SESSION_TTL='60',SCANPLUS_CHALLENGE_TTL='30',SCANPLUS_MODE='demo')
sys.path.insert(0,str(root))
import server
class EmptyFixture:
    def discover(self):return []
server.FixtureDiscovery=EmptyFixture
class QAHandler(server.Handler):
    report_calls=0
    def get(self):
        if self.path=='/api/report':
            s=self.session()
            if s and s['paid']:
                QAHandler.report_calls+=1
                if QAHandler.report_calls==1:return self.reply(503,{'error':'Synthetic QA report failure. Retry uses an empty synthetic fixture.'})
        return super().get()
http=server.LocalHTTPServer(('127.0.0.1',a.port),QAHandler)
print(f'QA ONLY http://127.0.0.1:{a.port} session TTL60s, challenge30s; separate synthetic store.',flush=True)
try:http.serve_forever(poll_interval=.5)
finally:http.server_close();server.STORE.close()
