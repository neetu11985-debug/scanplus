"""PEP 3333 entry point sharing the existing demo handler. No socket server on import."""
import io
import os
from email.message import Message
from http import HTTPStatus
from threading import RLock
from server import Handler

LOCK=RLock()

class WSGIHandler(Handler):
    def __init__(self, environ):
        self.path=environ.get('PATH_INFO','/')
        self.scheme=environ.get('wsgi.url_scheme','http')
        self.client_address=(environ.get('REMOTE_ADDR','unknown'),0)
        self.headers=Message()
        for key,value in environ.items():
            if key.startswith('HTTP_'): self.headers[key[5:].replace('_','-')]=value
        for key in ('CONTENT_LENGTH','CONTENT_TYPE'):
            if environ.get(key): self.headers[key.replace('_','-')]=environ[key]
        if not self.headers.get('Host'):
            self.headers['Host']=environ.get('SERVER_NAME','localhost')+':'+environ.get('SERVER_PORT','80')
        self.rfile=environ['wsgi.input']; self.wfile=io.BytesIO(); self.response_headers=[]; self.status=500
    def send_response(self, status, message=None): self.status=status; self.response_headers=[]
    def send_header(self, name, value): self.response_headers.append((name,str(value)))
    def end_headers(self): pass

def application(environ,start_response):
    if os.environ.get('SCANPLUS_MODE','demo')!='demo':
        start_response('503 Service Unavailable',[('Content-Type','text/plain'),('Cache-Control','no-store')])
        return [b'Live mode is disabled.']
    if environ.get('SCRIPT_NAME',''):
        start_response('503 Service Unavailable',[('Content-Type','text/plain')])
        return [b'Configure a separate domain root; subpath mounting is not configured.']
    with LOCK:  # Consistent single-process in-memory demo state; not a durable production store.
        handler=WSGIHandler(environ)
        method=environ.get('REQUEST_METHOD','GET')
        if method=='GET': handler.do_GET()
        elif method=='POST': handler.do_POST()
        else: handler.reply(405,{'error':'Method not allowed.'})
        body=handler.wfile.getvalue()
        if not any(k.lower()=='content-length' for k,v in handler.response_headers):
            handler.response_headers.append(('Content-Length',str(len(body))))
        start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}',handler.response_headers)
        return [body]
