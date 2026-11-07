"""Render ingress only; do not reuse this proxy trust on another host."""
import os
if os.environ.get('RENDER') != 'true':
    raise RuntimeError('This server configuration is only for Render ingress.')
port = int(os.environ.get('PORT', '10000'))
if not 1 <= port <= 65535:
    raise RuntimeError('Invalid service port.')
bind = '0.0.0.0:' + str(port)
workers = 1
threads = 1
worker_class = 'sync'
preload_app = False
forwarded_allow_ips = '*'
secure_scheme_headers = {'X-FORWARDED-PROTO': 'https'}
accesslog = None
# Gunicorn parser errors can include attacker-controlled request text. Suppress them.
errorlog = '/dev/null'
capture_output = False
timeout = 30
limit_request_line = 2048
limit_request_fields = 32
limit_request_field_size = 4096
