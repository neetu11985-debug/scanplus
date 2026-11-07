"""Small local SQLite store; synthetic data only. No external service or encryption claims."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
import time


def digest(value): return sha256(value.encode()).hexdigest()

class Store:
    def __init__(self,path=':memory:'):
        self.path=str(path); self.lock=RLock()
        if self.path!=':memory:':
            path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        self.conn=sqlite3.connect(self.path,timeout=2,check_same_thread=False)
        self.conn.execute('PRAGMA foreign_keys=ON');self.conn.execute('PRAGMA secure_delete=ON')
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,owner TEXT NOT NULL,expires REAL NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS claims(kind TEXT NOT NULL,key TEXT NOT NULL,owner TEXT NOT NULL,expires REAL NOT NULL,PRIMARY KEY(kind,key));
            CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY,expires REAL NOT NULL,count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS active_identities(identity TEXT PRIMARY KEY,sid TEXT NOT NULL,expires REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS record_expiry ON records(expires);
        ''');self.conn.commit()
    @contextmanager
    def transaction(self):
        with self.lock:
            self.conn.execute('BEGIN IMMEDIATE')
            try:yield self
            except BaseException:self.conn.rollback();raise
            else:
                try:self.conn.commit()
                except BaseException:self.conn.rollback();raise
    def prune(self,now=None):
        now=time.time() if now is None else now
        for table in ('records','claims','limits','active_identities'):self.conn.execute(f'DELETE FROM {table} WHERE expires<=?',(now,))
    def get(self,kind,key,owner=None):
        row=self.conn.execute('SELECT owner,expires,data FROM records WHERE kind=? AND id=?',(kind,key)).fetchone()
        if not row or row[1]<=time.time() or (owner is not None and row[0]!=owner):return None
        return json.loads(row[2])
    def put(self,kind,key,owner,expires,data):
        self.conn.execute('INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET owner=excluded.owner,expires=excluded.expires,data=excluded.data',(kind,key,owner,expires,json.dumps(data,separators=(',',':'))))
    def delete(self,kind,key):self.conn.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,key))
    def clear_owner(self,owner):
        self.conn.execute('DELETE FROM records WHERE owner=?',(owner,))
        self.conn.execute('DELETE FROM claims WHERE owner=?',(owner,))
        self.conn.execute('DELETE FROM active_identities WHERE sid=?',(owner,))
    def bind_identity(self,identity,sid,expires):
        self.conn.execute('INSERT INTO active_identities VALUES(?,?,?) ON CONFLICT(identity) DO UPDATE SET sid=excluded.sid,expires=excluded.expires',(identity,sid,expires))
    def is_current_identity(self,identity,sid):
        row=self.conn.execute('SELECT sid,expires FROM active_identities WHERE identity=?',(identity,)).fetchone()
        return bool(row and row[0]==sid and row[1]>time.time())
    def claim(self,kind,key,owner,expires):
        hashed=digest(key)
        row=self.conn.execute('SELECT owner FROM claims WHERE kind=? AND key=?',(kind,hashed)).fetchone()
        if row:return row[0]==owner
        self.conn.execute('INSERT INTO claims VALUES(?,?,?,?)',(kind,hashed,owner,expires));return True
    def allow(self,key,limit,window=60):
        hashed=digest(key);now=time.time()
        row=self.conn.execute('SELECT expires,count FROM limits WHERE key=?',(hashed,)).fetchone()
        if not row or row[0]<=now:
            if not row and self.conn.execute('SELECT COUNT(*) FROM limits').fetchone()[0]>=4096:return False
            self.conn.execute('INSERT OR REPLACE INTO limits VALUES(?,?,1)',(hashed,now+window));return True
        self.conn.execute('UPDATE limits SET count=count+1 WHERE key=?',(hashed,))
        return row[1]<limit
    def clear_all(self):
        with self.transaction():
            for table in ('records','claims','limits','active_identities'):self.conn.execute(f'DELETE FROM {table}')
    def close(self):self.conn.close()
