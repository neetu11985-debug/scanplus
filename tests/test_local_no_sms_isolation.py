"""Offline loopback-only local runner isolation. No live keys or providers."""
import http.client
import json
import socket
import threading
import unittest
from unittest.mock import patch

from local_no_sms_server import NoSMSServer, token_matches


class LocalNoSMSIsolationTests(unittest.TestCase):
    def setUp(self):
        original = socket.socket.connect
        def guarded(sock, address):
            self.assertEqual(address[0], '127.0.0.1', 'External network forbidden')
            return original(sock, address)
        guard = patch.object(socket.socket, 'connect', guarded)
        guard.start(); self.addCleanup(guard.stop)
        self.servers = []
        self.addCleanup(self.close_servers)
        for _ in range(2):
            server = NoSMSServer(('127.0.0.1', 0))
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
            thread.start(); self.servers.append((server, thread))

    def close_servers(self):
        for server, thread in self.servers:
            server.shutdown(); server.server_close(); thread.join()

    def call(self, index, path='/api/session', *, cookie='', data=None, csrf=''):
        server = self.servers[index][0]
        headers = {'Cookie': cookie, 'Origin': 'http://127.0.0.1:' + str(server.server_port),
                   'Content-Type': 'application/json', 'X-CSRF-Token': csrf}
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
        try:
            connection.request('GET' if data is None else 'POST', path,
                               body=None if data is None else json.dumps(data), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
        finally:
            connection.close()

    def test_cookies_do_not_collide_across_local_ports(self):
        first = self.call(0); cookie_a = first[2].split(';', 1)[0]
        second = self.call(1, cookie=cookie_a); cookie_b = second[2].split(';', 1)[0]
        self.assertEqual((first[0], second[0]), (200, 200))
        self.assertNotEqual(cookie_a.split('=')[0], cookie_b.split('=')[0])
        self.assertIn('HttpOnly; SameSite=Strict', first[2])
        both = cookie_a + '; ' + cookie_b
        for index, expected in ((0, first), (1, second)):
            response = self.call(index, cookie=both)
            self.assertEqual(response[0], 200)
            self.assertEqual(response[1]['csrf_token'], expected[1]['csrf_token'])
            self.assertFalse(response[1]['search_enabled'])
            self.assertIsNone(response[2])
        self.assertEqual(self.call(0, cookie=cookie_b)[0], 409)
        self.assertEqual(self.call(1, cookie=cookie_a)[0], 409)

    def test_foreign_port_or_legacy_cookie_cannot_authorize_operation(self):
        first = self.call(0); second = self.call(1)
        cookie_a, cookie_b = (result[2].split(';', 1)[0] for result in (first, second))
        data = {'phone': '+12025550147', 'own_number': True, 'no_sms_acknowledged': True}
        self.assertEqual(self.call(0, '/api/start', cookie=cookie_b, data=data, csrf=first[1]['csrf_token'])[0], 401)
        legacy = 'scanplus_no_sms_sid=' + cookie_a.split('=', 1)[1]
        self.assertEqual(self.call(0, '/api/start', cookie=legacy, data=data, csrf=first[1]['csrf_token'])[0], 401)
        self.assertEqual(self.call(0, '/api/start', cookie=cookie_a+'; '+cookie_b, data=data, csrf=first[1]['csrf_token'])[0], 200)
        self.assertEqual(self.call(1, cookie=cookie_a+'; '+cookie_b)[1]['phase'], 'entry')

    def test_malformed_tokens_are_rejected_not_internal_errors(self):
        self.assertFalse(token_matches('é', 'synthetic'))
        self.assertFalse(token_matches(None, 'synthetic'))
        self.assertFalse(token_matches([], 'synthetic'))
        state = self.call(0); cookie = state[2].split(';', 1)[0]
        self.assertEqual(self.call(0, '/api/clear', cookie=cookie, data={}, csrf='é')[0], 403)
        name = cookie.split('=', 1)[0]
        self.assertEqual(self.call(0, '/api/clear', cookie=name+'="é"', data={}, csrf=state[1]['csrf_token'])[0], 401)
        self.assertEqual(self.call(0, cookie=cookie)[0], 200)


if __name__ == '__main__': unittest.main()
