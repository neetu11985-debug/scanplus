import os
from pathlib import Path

def bounded_int(name,default,low,high):
    value=int(os.environ.get(name,default))
    if not low<=value<=high:raise ValueError(f'{name} outside supported bounds.')
    return value

def require_demo():
    if os.environ.get('SCANPLUS_MODE','demo')!='demo':
        raise RuntimeError('Production unavailable: approved hosting, real ownership/search/payment transports and merchant configuration are not installed. Fixtures cannot run in live mode.')

SESSION_TTL=bounded_int('SCANPLUS_SESSION_TTL',900,60,86400)
CHALLENGE_TTL=bounded_int('SCANPLUS_CHALLENGE_TTL',300,30,600)
PAYMENT_TTL=bounded_int('SCANPLUS_PAYMENT_TTL',86400,300,604800)
DEMO_HISTORY_TTL=bounded_int('SCANPLUS_DEMO_HISTORY_TTL',8*86400,7*86400+1,30*86400)
DB_PATH=os.environ.get('SCANPLUS_DB_PATH',str(Path(__file__).parent/'.data'/'scanplus-demo.sqlite3'))
