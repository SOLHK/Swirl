"""Independent loopback SOCKS4/4a peers and origins for the Rust harness."""
import base64
import json
import os
import select
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from test_rust_core import exact, header


def cstring(stream, limit=255):
    result = b''
    for _ in range(limit + 1):
        byte = exact(stream, 1)
        if byte == b'\0':
            return result
        result += byte
    raise ValueError('unterminated field')


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False
    def handle_error(self, request, address):
        self.errors.append('controlled peer assertion failed')


class Origin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        self.server.accepted += 1
        try:
            while True:
                data = self.request.recv(16384)
                if not data:
                    self.request.sendall(b'EOF-TAIL')
                    return
                self.request.sendall(data)
        except (OSError, EOFError):
            pass


class HttpOrigin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        self.server.accepted += 1
        request = header(self.request)
        self.server.requests.append(request)
        assert request.startswith(b'GET /socks4/')
        body = b'socks4-native-http'
        self.request.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode()
                             + b'\r\nConnection: close\r\n\r\n' + body)


class Peer(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        self.server.accepted += 1
        try:
            request = exact(self.request, 8)
            assert request[:2] == b'\x04\x01'
            user = cstring(self.request)
            host = socket.inet_ntoa(request[4:8])
            if request[4:7] == b'\0\0\0' and request[7] != 0:
                host = cstring(self.request).decode('ascii')
                assert host == 'origin.fixture.invalid'
            port = struct.unpack('!H', request[2:4])[0]
            self.server.requests.append((host, port, user))
            if self.server.mode != 'normal':
                reply = bytes([4 if self.server.mode == 'bad-version' else 0,
                               90 if self.server.mode == 'bad-version' else int(self.server.mode)]) + b'\0' * 6
                self.request.sendall(reply)
                return
            with socket.create_connection(('127.0.0.1' if host == 'origin.fixture.invalid' else host, port), timeout=5) as origin:
                self.server.forwarded += 1
                for byte in b'\0\x5a' + b'\0' * 6:
                    self.request.sendall(bytes([byte]))
                readers = [self.request, origin]
                while readers:
                    ready, _, _ = select.select(readers, [], [], 5)
                    if not ready:
                        return
                    for source in ready:
                        target = origin if source is self.request else self.request
                        data = source.recv(16384)
                        if data:
                            target.sendall(data)
                        else:
                            readers.remove(source)
                            target.shutdown(socket.SHUT_WR)
        except (OSError, EOFError):
            pass


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class Socks4Integration(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self.fail('Rust did not stop')
        finally:
            for server in self.servers:
                server.shutdown()
                server.server_close()
        error = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, error)
        for server in self.servers:
            self.assertEqual(server.errors, [])

    def server(self, handler, mode='normal'):
        server = Server(('127.0.0.1', 0), handler)
        server.accepted, server.forwarded = 0, 0
        server.errors, server.requests, server.mode = [], [], mode
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def config(self, outbound=None, **extra):
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'n',
                'nodes': [{'id': 'n', 'outbound': outbound or {'type': 'direct'}}], **extra}

    def start(self, config):
        result = self.command(op='start', config=config)
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def socket(self):
        return socket.create_connection(('127.0.0.1', self.port), timeout=5)

    def http(self, port, host='127.0.0.1'):
        stream = self.socket()
        try:
            authority = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
            stream.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
            return stream, header(stream)
        except BaseException:
            stream.close()
            raise

    def assert_echo_and_halfclose(self, stream, data=b'four-native' * 8192):
        stream.sendall(data)
        self.assertEqual(exact(stream, len(data)), data)
        stream.shutdown(socket.SHUT_WR)
        self.assertEqual(exact(stream, 8), b'EOF-TAIL')
        self.assertEqual(stream.recv(1), b'')

    def test_inbound_ipv4_and_4a_fragmented_with_coalesced_payload(self):
        origin = self.server(Origin)
        port = origin.server_address[1]
        self.start(self.config(dns={'hosts': [{'name': 'origin.fixture.invalid', 'address': '127.0.0.1'}]}))
        for domain in (False, True):
            with self.subTest(domain=domain), self.socket() as stream:
                request = b'\x04\x01' + struct.pack('!H', port) + (b'\0\0\0\x01' if domain else socket.inet_aton('127.0.0.1'))
                request += b'fixture-user\0' + (b'origin.fixture.invalid\0' if domain else b'')
                for byte in request[:-1]:
                    stream.sendall(bytes([byte]))
                stream.sendall(request[-1:] + b'coalesced')
                self.assertEqual(exact(stream, 8)[:2], b'\0\x5a')
                self.assertEqual(exact(stream, 9), b'coalesced')
                self.assert_echo_and_halfclose(stream)
        self.assertEqual(origin.accepted, 2)

    def test_outbound_v4_local_dns_and_4a_remote_dns(self):
        origin, peer = self.server(Origin), self.server(Peer)
        for remote in (False, True):
            with self.subTest(remote=remote):
                outbound = {'type': 'socks4', 'host': '127.0.0.1', 'port': peer.server_address[1],
                            'user_id': 'USERID-not-password', 'remote_dns': remote}
                self.start(self.config(outbound, dns={'hosts': [{'name': 'origin.fixture.invalid', 'address': '127.0.0.1'}]}))
                stream, response = self.http(origin.server_address[1], 'origin.fixture.invalid')
                with stream:
                    self.assertIn(b' 200 ', response)
                    self.assert_echo_and_halfclose(stream)
                self.assertEqual(peer.requests[-1][0], 'origin.fixture.invalid' if remote else '127.0.0.1')
                self.assertEqual(peer.requests[-1][2], b'USERID-not-password')
                self.stop()
        self.assertEqual(peer.forwarded, 2)
        self.assertEqual(origin.accepted, 2)

    @unittest.skipUnless(os.environ.get('SWIRL_RUST_INSPECTOR'), 'set SWIRL_RUST_INSPECTOR')
    def test_subscription_candidates_forward_through_independent_peer(self):
        origin, peer = self.server(Origin), self.server(Peer)
        port, expected = peer.server_address[1], 0
        for version, remote in (('4', False), ('4a', True)):
            kind = 'socks' + version
            uri = f'{kind}://import%3Afixture@127.0.0.1:{port}#synthetic'
            sing = json.dumps({'outbounds': [{'type': 'socks', 'version': version, 'tag': 'synthetic',
                              'server': '127.0.0.1', 'server_port': port, 'username': 'import:fixture', 'network': 'tcp'}]})
            yaml = f"proxies: [{{name: synthetic, type: {kind}, server: 127.0.0.1, port: {port}, username: 'import:fixture'}}]"
            documents = (uri, base64.b64encode(uri.encode()).decode(), yaml, sing,
                         base64.b64encode(sing.encode()).decode())
            for index, document in enumerate(documents):
                with self.subTest(version=version, source=index):
                    result = subprocess.run([os.environ['SWIRL_RUST_INSPECTOR'], '--private-json'],
                                            input=document, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    inspected = json.loads(result.stdout)
                    self.assertTrue(inspected['report']['nodes'][0]['native_tcp_candidate'])
                    self.assertFalse(inspected['report']['nodes'][0]['real_network_verified'])
                    candidate = inspected['tcpCandidates'][0]
                    self.assertEqual(candidate['type'], 'socks4')
                    self.assertEqual(candidate['remote_dns'], remote)
                    self.start(self.config(candidate, dns={'hosts': [{'name': 'origin.fixture.invalid', 'address': '127.0.0.1'}]}))
                    try:
                        stream, response = self.http(origin.server_address[1], 'origin.fixture.invalid')
                        with stream:
                            self.assertIn(b' 200 ', response)
                            self.assert_echo_and_halfclose(stream, b'native-import-roundtrip')
                        expected += 1
                        self.assertEqual(peer.requests[-1], ('origin.fixture.invalid' if remote else '127.0.0.1',
                                                             origin.server_address[1], b'import:fixture'))
                        deadline = time.monotonic() + 2
                        while True:
                            status = self.command(op='snapshot', handle=self.handle)['status']
                            if status['active'] == 0 or time.monotonic() >= deadline:
                                break
                            time.sleep(0.01)
                        self.assertEqual(status['accepted'], 1)
                        self.assertEqual(status['active'], 0)
                        self.assertEqual(status['failed'], 0)
                        self.assertEqual(status['last_error'], '')
                        self.assertGreater(status['upload'], 0)
                        self.assertGreater(status['download'], 0)
                    finally:
                        self.stop()
        self.assertEqual(peer.forwarded, expected)
        self.assertEqual(origin.accepted, expected)

    @unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'), 'Qt integration executable required')
    def test_qt_imported_socks4_and_4a_data_path(self):
        origin, peer = self.server(HttpOrigin), self.server(Peer)
        env = {**os.environ, 'SWIRL_SOCKS4_REFERENCE_PORT': str(peer.server_address[1]),
               'SWIRL_SOCKS4_ORIGIN_PORT': str(origin.server_address[1])}
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'qt.txt'
            result = subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'], 'socks4ThroughIndependentPeer',
                                     '-o', str(log) + ',txt'], env=env, capture_output=True, text=True, timeout=40)
            output = log.read_text(encoding='utf-8') if log.exists() else 'Qt log unavailable'
            self.assertEqual(result.returncode, 0, output + result.stdout + result.stderr)
        self.assertEqual(peer.requests, [('127.0.0.1', origin.server_address[1], b'qt-user:fixture')] * 3
                         + [('origin.fixture.invalid', origin.server_address[1], b'qt-user:fixture')] * 3)
        self.assertEqual(peer.forwarded, 6)
        self.assertEqual(origin.accepted, 6)
        self.assertEqual(len(origin.requests), 6)

    def test_rejected_or_wrong_version_upstream_never_falls_back(self):
        origin = self.server(Origin)
        for mode in ('91', '92', '93', 'bad-version'):
            peer = self.server(Peer, mode)
            self.start(self.config({'type': 'socks4', 'host': '127.0.0.1', 'port': peer.server_address[1]}))
            stream, response = self.http(origin.server_address[1])
            with stream:
                self.assertIn(b' 502 ', response)
            self.assertEqual(peer.forwarded, 0)
            self.stop()
        self.assertEqual(origin.accepted, 0)

    def test_password_protected_inbound_rejects_socks4(self):
        origin = self.server(Origin)
        self.start(self.config(inbound_auth={'username': 'user', 'password': 'password'}))
        with self.socket() as stream:
            stream.sendall(b'\x04\x01' + struct.pack('!H', origin.server_address[1]) + socket.inet_aton('127.0.0.1') + b'user\0')
            # Early password-policy rejection leaves the request unread. TCP
            # may deliver EOF/RST before all denial bytes, notably on Windows.
            reply = b''
            try:
                while len(reply) < 8:
                    part = stream.recv(8 - len(reply))
                    if not part:
                        break
                    reply += part
            except ConnectionResetError:
                pass
            self.assertEqual(reply, (b'\0\x5b' + b'\0' * 6)[:len(reply)])
        # A transport close alone cannot prove authentication was enforced.
        deadline = time.monotonic() + 2
        while True:
            status = self.command(op='snapshot', handle=self.handle)['status']
            if status['active'] == 0 or time.monotonic() >= deadline:
                break
        self.assertEqual(status['accepted'], 1)
        self.assertEqual(status['active'], 0)
        self.assertEqual(status['failed'], 1)
        self.assertEqual(status['last_error'], 'InboundAuthentication')
        self.assertEqual(status['connections'], [])
        self.assertEqual(origin.accepted, 0)

    def test_invalid_command_userid_domain_and_zero_port_are_rejected(self):
        self.start(self.config())
        prefix = b'\x04\x01\x01\xbb'
        cases = [b'\x04\x02', prefix + socket.inet_aton('127.0.0.1') + b'x' * 256,
                 prefix + b'\0\0\0\x01\0bad..domain\0',
                 prefix + b'\0\0\0\x01\0' + b'x' * 254,
                 b'\x04\x01\0\0' + socket.inet_aton('127.0.0.1') + b'\0']
        for request in cases:
            with self.subTest(size=len(request)), self.socket() as stream:
                stream.sendall(request)
                self.assertEqual(exact(stream, 8)[:2], b'\0\x5b')

    def test_ipv6_destination_rejected_before_proxy_connection(self):
        peer = self.server(Peer)
        self.start(self.config({'type': 'socks4', 'host': '127.0.0.1', 'port': peer.server_address[1]}))
        stream, response = self.http(443, '::1')
        with stream:
            self.assertIn(b' 502 ', response)
        self.assertEqual(peer.accepted, 0)

    def test_existing_socks4_session_survives_atomic_update(self):
        origin, peer = self.server(Origin), self.server(Peer)
        self.start(self.config({'type': 'socks4', 'host': '127.0.0.1', 'port': peer.server_address[1]}))
        stream, response = self.http(origin.server_address[1])
        with stream:
            self.assertIn(b' 200 ', response)
            self.assertTrue(self.command(op='configure', handle=self.handle,
                                         config=self.config({'type': 'reject'}))['ok'])
            self.assert_echo_and_halfclose(stream, b'old-config-alive')
        denied, response = self.http(origin.server_address[1])
        with denied:
            self.assertIn(b' 502 ', response)
        self.assertEqual(peer.forwarded, 1)

    def test_invalid_configuration_rejected_without_activation(self):
        for mutation in ({'user_id': 'x\0y'}, {'user_id': 'x' * 256}, {'remote_dns': 'true'},
                         {'host': ''}, {'port': 0}, {'password': 'not-supported'}):
            outbound = {'type': 'socks4', 'host': '127.0.0.1', 'port': 1080, **mutation}
            self.assertFalse(self.command(op='start', config=self.config(outbound))['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
