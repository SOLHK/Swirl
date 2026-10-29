"""Independent RFC6455 peers with actual VLESS/Trojan destination forwarding.

All listeners/certificates are synthetic loopback fixtures. No private account,
subscription, public proxy or complete proxy core is used.
"""
import base64
import concurrent.futures
import hashlib
import json
import os
import select
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from test_rust_core import certificates, exact, header, target

UUID = '00112233-4455-6677-8899-aabbccddeeff'


def frame(opcode, data=b'', fin=True):
    first = bytes([opcode | (128 if fin else 0)])
    if len(data) < 126:
        return first + bytes([len(data)]) + data
    if len(data) <= 65535:
        return first + b'\x7e' + struct.pack('!H', len(data)) + data
    return first + b'\x7f' + struct.pack('!Q', len(data)) + data


class Framed:
    def __init__(self, stream, server):
        self.stream, self.server, self.buffer = stream, server, b''

    def recv(self, size):
        # Protocol handshakes need application bytes and may wait across control
        # frames. The bidirectional forwarding loop must use recv_frame instead:
        # a readable socket may contain only a Pong, with no more upload coming.
        while True:
            data = self.recv_frame(size)
            if data is not None:
                return data

    def recv_frame(self, size):
        """Consume at most one frame; None means control/empty data, not EOF."""
        if not self.buffer:
            h = exact(self.stream, 2)
            assert h[0] & 0x70 == 0 and h[1] & 0x80
            opcode = h[0] & 15
            length = h[1] & 127
            if length == 126:
                length = struct.unpack('!H', exact(self.stream, 2))[0]
                assert length >= 126
            elif length == 127:
                length = struct.unpack('!Q', exact(self.stream, 8))[0]
                assert length >= 65536
            assert length <= 1048576
            mask = exact(self.stream, 4)
            payload = exact(self.stream, length)
            payload = bytes(x ^ mask[i % 4] for i, x in enumerate(payload))
            self.server.masks.append(mask)
            if opcode == 10:
                self.server.pongs.append(payload)
                if payload == b'tail-gate':
                    self.server.pong_seen.set()
                return None
            if opcode == 8:
                self.stream.sendall(frame(8, payload))
                return b''
            assert opcode == 2 and h[0] & 128
            self.buffer = payload
            if not payload:
                return None
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def sendall(self, data):
        if self.server.mode == 'fragmented' and len(data) > 1:
            middle = len(data) // 2
            packet = frame(2, data[:middle], False) + frame(9, b'interleaved') + frame(0, data[middle:])
        else:
            packet = frame(2, data)
        if self.server.mode == 'pong-gated' and self.server.destinations and not self.server.gate_sent:
            packet += frame(9, b'tail-gate')
            self.server.gate_sent = True
        self.stream.sendall(packet)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True
    def handle_error(self, request, address):
        self.errors.append('controlled WebSocket peer assertion failed')


class Origin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(6)
        self.server.accepted += 1
        try:
            while True:
                data = self.request.recv(16384)
                if not data:
                    return
                self.server.received += len(data)
                self.request.sendall(data)
        except (OSError, EOFError):
            pass


class GatedOrigin(socketserver.BaseRequestHandler):
    """Release a response tail only after the peer consumes a control-only Pong."""
    def handle(self):
        self.request.settimeout(6)
        self.server.accepted += 1
        assert exact(self.request, 7) == b'request'
        self.server.received += 7
        self.request.sendall(b'prefix')
        assert self.server.pong_seen.wait(3), 'client did not answer the tail-gate Ping'
        self.request.sendall(b'tail-without-another-upload')
        # Keep the origin open while the client reads the tail, so EOF is not
        # needed to make progress in either forwarding direction.
        self.request.recv(1)


class HttpOrigin(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        self.server.accepted += 1
        request = header(self.request)
        self.server.requests.append(request)
        assert request.startswith(b'GET /websocket HTTP/1.1\r\n')
        body = b'w' * 131073
        self.request.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode()
                             + b'\r\nConnection: close\r\n\r\n' + body)


class Peer(socketserver.BaseRequestHandler):
    def handle(self):
        stream = self.request
        stream.settimeout(6)
        stream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server.active += 1
        try:
            if self.server.context:
                stream = self.server.context.wrap_socket(stream, server_side=True)
            with stream:
                request = header(stream)
                self.server.requests.append(request)
                assert request.startswith(b'GET /ws?fixture=1 HTTP/1.1\r\n')
                assert b'Host: ws.fixture.invalid\r\n' in request
                fields = {}
                for row in request.split(b'\r\n')[1:]:
                    if row:
                        key, value = row.split(b':', 1)
                        fields[key.lower()] = value.strip()
                assert fields[b'sec-websocket-version'] == b'13'
                assert len(base64.b64decode(fields[b'sec-websocket-key'])) == 16
                assert b'sec-websocket-extensions' not in fields
                digest = hashlib.sha1(fields[b'sec-websocket-key'] + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest()
                accept = base64.b64encode(digest)
                if self.server.mode == 'bad-accept':
                    accept = b'WRONG'
                response = b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + b'\r\n'
                if self.server.mode == 'extension':
                    response += b'Sec-WebSocket-Extensions: permessage-deflate\r\n'
                if self.server.mode == 'duplicate':
                    response += b'Sec-WebSocket-Accept: ' + accept + b'\r\n'
                if self.server.mode == 'status':
                    response = b'HTTP/1.1 302 Redirect\r\nLocation: http://127.0.0.1:9/\r\n'
                pings = [b'coalesced']
                if self.server.mode == 'ping-burst':
                    pings.extend(i.to_bytes(2, 'big') for i in range(32))
                stream.sendall(response + b'\r\n' + b''.join(frame(9, ping) for ping in pings))
                if self.server.mode in ('bad-accept', 'extension', 'duplicate', 'status'):
                    self.server.unexpected += len(stream.recv(1024))
                    return
                bad = {'masked': b'\x82\x84MASKNEVER', 'rsv': b'\xc2\x05NEVER',
                       'continuation': b'\x80\x05NEVER', 'text': b'\x81\x05NEVER',
                       'length': b'\x82\x7e\x00\x05NEVER', 'oversize': b'\x82\x7f' + struct.pack('!Q', 1048577),
                       'close-code': frame(8, b'\x03\xed'), 'close-utf8': frame(8, b'\x03\xe8\xff')}
                if self.server.mode in bad:
                    stream.sendall(bad[self.server.mode])
                    time.sleep(0.1)
                    return
                framed = Framed(stream, self.server)
                if self.server.protocol == 'vless':
                    assert exact(framed, 1) == b'\0'
                    if exact(framed, 16) != bytes.fromhex(UUID.replace('-', '')):
                        return
                    assert exact(framed, 2) == b'\0\x01'
                    port = int.from_bytes(exact(framed, 2), 'big')
                    kind = exact(framed, 1)[0]
                    if kind == 1:
                        host = socket.inet_ntop(socket.AF_INET, exact(framed, 4))
                    elif kind == 3:
                        host = socket.inet_ntop(socket.AF_INET6, exact(framed, 16))
                    else:
                        assert kind == 2
                        host = exact(framed, exact(framed, 1)[0]).decode('ascii')
                    framed.sendall(b'\0\0')
                else:
                    if exact(framed, 56) != hashlib.sha224(b'fixture-password').hexdigest().encode():
                        return
                    assert exact(framed, 3) == b'\r\n\x01'
                    host, port = target(framed)
                    assert exact(framed, 2) == b'\r\n'
                self.server.destinations.append((host, port))
                assert host in ('127.0.0.1', 'origin.fixture.invalid')
                with socket.create_connection(('127.0.0.1', port), timeout=6) as origin:
                    self.server.forwarded += 1
                    while True:
                        buffered = bool(framed.buffer) or isinstance(stream, ssl.SSLSocket) and stream.pending() > 0
                        ready = select.select([stream, origin], [], [], 0 if buffered else 6)[0]
                        if buffered and stream not in ready:
                            ready.append(stream)
                        if not ready:
                            return
                        for source in ready:
                            if source is stream:
                                data = framed.recv_frame(16384)
                                if data is None:
                                    continue
                                if not data:
                                    return
                                origin.sendall(data)
                                self.server.upstream_bytes += len(data)
                            else:
                                data = origin.recv(16384)
                                if not data:
                                    stream.sendall(frame(8, b'\x03\xe8'))
                                    return
                                framed.sendall(data)
                                self.server.downstream_bytes += len(data)
        except (EOFError, OSError, ssl.SSLError) as exc:
            self.server.peer_diagnostics.append(f'{type(exc).__name__}: {exc}')
        finally:
            self.server.active -= 1


class WebSocketPeerTests(unittest.TestCase):
    def test_control_only_and_empty_frames_return_to_the_forwarding_loop(self):
        for opcode, payload in ((10, b'only-pong'), (2, b'')):
            with self.subTest(opcode=opcode):
                peer, client = socket.socketpair()
                with peer, client:
                    peer.settimeout(0.25)
                    state = SimpleNamespace(masks=[], pongs=[])
                    masked = bytes(x ^ b'MASK'[i % 4] for i, x in enumerate(payload))
                    client.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + b'MASK' + masked)
                    self.assertIsNone(Framed(peer, state).recv_frame(16384))
                    self.assertEqual(state.pongs, [payload] if opcode == 10 else [])


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class WebSocketTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.context, cls.ca, _ = certificates(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

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
        stderr = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, stderr)
        for server in self.servers:
            self.assertEqual(server.errors, [])

    def server(self, handler, protocol='vless', tls=False, mode='normal'):
        server = Server(('127.0.0.1', 0), handler)
        server.protocol, server.context, server.mode = protocol, self.context if tls else None, mode
        server.requests, server.destinations, server.errors, server.masks, server.pongs = [], [], [], [], []
        server.active = server.forwarded = server.accepted = server.received = server.unexpected = 0
        server.upstream_bytes = server.downstream_bytes = 0
        server.peer_diagnostics = []
        server.pong_seen = threading.Event()
        server.gate_sent = False
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def config(self, peer, **tls):
        outbound = {'type': peer.protocol, 'host': '127.0.0.1', 'port': peer.server_address[1],
                    'websocket': {'host': 'ws.fixture.invalid', 'path': '/ws?fixture=1'}}
        if peer.protocol == 'vless':
            outbound['uuid'] = UUID
        else:
            outbound['password'] = 'fixture-password'
        if peer.context:
            outbound['tls'] = {'server_name': 'localhost', 'alpn': ['http/1.1'], 'ca_der_base64': self.ca, **tls}
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'n', 'nodes': [{'id': 'n', 'outbound': outbound}]}

    def start(self, config):
        result = self.command(op='start', config=config)
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def tunnel(self, origin, host='127.0.0.1'):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=6)
        try:
            stream.sendall(f'CONNECT {host}:{origin.server_address[1]} HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode())
            return stream, header(stream)
        except BaseException:
            stream.close()
            raise

    def echo(self, stream, size=65537):
        data = bytes(range(256)) * (size // 256) + b'z' * (size % 256)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            sent = pool.submit(stream.sendall, data)
            self.assertEqual(exact(stream, len(data)), data)
            sent.result(timeout=6)

    def test_vless_ws_wss_trojan_wss_forward_actual_origin_and_mask_frames(self):
        for protocol, tls in [('vless', False), ('vless', True), ('trojan', True)]:
            with self.subTest(protocol=protocol, tls=tls):
                origin = self.server(Origin)
                peer = self.server(Peer, protocol, tls)
                self.start(self.config(peer))
                stream, response = self.tunnel(origin, 'origin.fixture.invalid')
                with stream:
                    self.assertIn(b' 200 ', response)
                    self.echo(stream, 262145)
                self.assertEqual(peer.forwarded, 1)
                self.assertEqual(origin.accepted, 1)
                self.assertEqual(origin.received, 262145)
                self.assertIn(b'coalesced', peer.pongs)
                self.assertGreater(len(set(peer.masks)), 1)
                self.stop()

    @unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'), 'Qt integration executable required')
    def test_qt_vless_websocket_data_path(self):
        origin, peer = self.server(HttpOrigin), self.server(Peer)
        env = {**os.environ, 'SWIRL_WS_REFERENCE_PORT': str(peer.server_address[1]),
               'SWIRL_WS_ORIGIN_PORT': str(origin.server_address[1])}
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'qt.txt'
            result = subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'], 'webSocketThroughIndependentPeer',
                                     '-o', str(log) + ',txt'], env=env, capture_output=True, text=True, timeout=15)
            output = log.read_text(encoding='utf-8') if log.exists() else 'Qt log unavailable'
            self.assertEqual(result.returncode, 0, output + result.stdout + result.stderr)
        self.assertEqual(peer.destinations, [('origin.fixture.invalid', origin.server_address[1])])
        self.assertEqual(peer.forwarded, 1)
        self.assertEqual(origin.accepted, 1)
        self.assertEqual(len(origin.requests), 1)
        self.assertGreater(peer.upstream_bytes, 0)
        self.assertGreaterEqual(peer.downstream_bytes, 131073)
        self.assertGreater(len(peer.masks), 0)

    def test_fragmented_binary_messages_and_interleaved_ping_are_not_payload(self):
        origin, peer = self.server(Origin), self.server(Peer, mode='fragmented')
        self.start(self.config(peer))
        stream, response = self.tunnel(origin)
        with stream:
            self.assertIn(b' 200 ', response)
            try:
                self.echo(stream)
            except (EOFError, TimeoutError, ConnectionError) as exc:
                self.fail(f'fragmented WebSocket echo failed: {type(exc).__name__}: {exc}; '
                          f'origin.accepted={origin.accepted}, origin.received={origin.received}, '
                          f'peer.forwarded={peer.forwarded}, peer.active={peer.active}, '
                          f'upstream_bytes={peer.upstream_bytes}, downstream_bytes={peer.downstream_bytes}, '
                          f'pongs={len(peer.pongs)}, masks={len(peer.masks)}, '
                          f'peer_diagnostics={peer.peer_diagnostics!r}, peer_errors={peer.errors!r}')
            stream.sendall(b'after-ping')
            self.assertEqual(exact(stream, 10), b'after-ping')
        self.assertIn(b'interleaved', peer.pongs)

    def test_control_only_pong_does_not_block_the_origin_response_tail(self):
        for tls in (False, True):
            with self.subTest(tls=tls):
                origin, peer = self.server(GatedOrigin), self.server(Peer, tls=tls, mode='pong-gated')
                origin.pong_seen = peer.pong_seen
                self.start(self.config(peer))
                stream, response = self.tunnel(origin)
                with stream:
                    self.assertIn(b' 200 ', response)
                    stream.sendall(b'request')
                    expected = b'prefixtail-without-another-upload'
                    self.assertEqual(exact(stream, len(expected)), expected)
                    self.assertIn(b'tail-gate', peer.pongs)
                    self.assertEqual(origin.received, 7)
                self.stop()

    def test_coalesced_ping_burst_preserves_the_connection_and_all_pongs(self):
        for tls in (False, True):
            with self.subTest(tls=tls):
                origin, peer = self.server(Origin), self.server(Peer, tls=tls, mode='ping-burst')
                self.start(self.config(peer))
                stream, response = self.tunnel(origin)
                with stream:
                    self.assertIn(b' 200 ', response)
                    self.echo(stream, 32769)
                    self.assertEqual(peer.pongs, [b'coalesced'] + [i.to_bytes(2, 'big') for i in range(32)])
                self.assertEqual(origin.received, 32769)
                self.stop()

    def test_bad_upgrades_fail_without_sending_credentials_or_origin_traffic(self):
        origin = self.server(Origin)
        for mode in ('bad-accept', 'extension', 'duplicate', 'status'):
            peer = self.server(Peer, mode=mode)
            self.start(self.config(peer))
            stream, response = self.tunnel(origin)
            with stream:
                self.assertIn(b' 502 ', response)
            self.assertEqual(peer.forwarded, 0)
            self.assertEqual(peer.unexpected, 0)
            self.stop()
        self.assertEqual(origin.accepted, 0)

    def test_malformed_frames_never_release_invalid_payload(self):
        origin = self.server(Origin)
        for mode in ('masked', 'rsv', 'continuation', 'text', 'length', 'oversize', 'close-code', 'close-utf8'):
            peer = self.server(Peer, mode=mode)
            self.start(self.config(peer))
            stream, response = self.tunnel(origin)
            with stream:
                if b' 200 ' in response:
                    try:
                        stream.sendall(b'probe')
                        data = stream.recv(65536)
                    except ConnectionError:
                        data = b''
                    self.assertEqual(data, b'')
                else:
                    self.assertIn(b' 502 ', response)
            self.assertEqual(peer.forwarded, 0)
            self.stop()
        self.assertEqual(origin.accepted, 0)

    def test_wss_verifies_name_and_trust_before_http_upgrade(self):
        origin = self.server(Origin)
        for tls in ({'server_name': 'wrong.invalid'}, {'ca_der_base64': None}):
            peer = self.server(Peer, tls=True)
            self.start(self.config(peer, **tls))
            stream, response = self.tunnel(origin)
            with stream:
                self.assertIn(b' 502 ', response)
            self.assertEqual(peer.requests, [])
            self.stop()

    def test_configuration_generation_preserves_existing_ws_stream(self):
        origin, peer = self.server(Origin), self.server(Peer)
        config = self.config(peer)
        self.start(config)
        stream, response = self.tunnel(origin)
        with stream:
            self.assertIn(b' 200 ', response)
            self.echo(stream, 4096)
            config['nodes'][0]['outbound'] = {'type': 'reject'}
            self.assertTrue(self.command(op='configure', handle=self.handle, config=config)['ok'])
            self.echo(stream, 8192)
            denied, response = self.tunnel(origin)
            with denied:
                self.assertIn(b' 502 ', response)
        self.assertEqual(peer.forwarded, 1)

    def test_stop_cancels_owned_ws_driver_and_releases_network(self):
        origin, peer = self.server(Origin), self.server(Peer)
        self.start(self.config(peer))
        stream, response = self.tunnel(origin)
        with stream:
            self.assertIn(b' 200 ', response)
            self.echo(stream, 1024)
            self.stop()
            deadline = time.monotonic() + 3
            while peer.active and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(peer.active, 0)
            self.assertEqual(stream.recv(1), b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
