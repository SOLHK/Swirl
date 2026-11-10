"""Portable network regressions for the production V2 system-proxy data path.

Client -> compiled swirl-api/start_v2 -> authenticated independent HTTP/SOCKS5
node -> separately listening origin. No DIRECT route or external proxy core is
used. TLS certificates are verified; h2 is an independent test-only HTTP/2
implementation. These tests do not modify Windows proxy settings and do not
establish Codex Desktop, private-provider, or Windows 11 hardware acceptance.

Run with SWIRL_RUST_HARNESS pointing to the source-identical swirl-api binary.
Missing binaries/dependencies fail rather than silently skipping the gate.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest

import h2.config
import h2.connection
import h2.events

from test_product_subscription_chain import Relay, Server, USER
from test_rust_core import certificates, exact, header
from test_shadowsocks import PASSWORD


NODE = '10000000-0000-4000-8000-000000000001'
STORE = '40000000-0000-4000-8000-000000000001'
REQUEST = '50000000-0000-4000-8000-000000000001'
# A reserved synthetic name reaches the configured proxy node. localhost and
# loopback literals intentionally select V2's builtin local DIRECT policy.
# The independent node alone maps this name to its explicit loopback origins.
TARGET = 'stream.product.invalid'
HANDSHAKE_MS = 1000
LATE_DELAY = 1.3
WS_GUID = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
TAIL = bytes(range(251)) * 1021
HTTP_BODY = b'v2-independent-tls-origin'
SSE_EVENTS = [f'id: {i}\nevent: token\ndata: value-{i}\n\n'.encode() for i in range(8)]


class V2Host:
    """Bounded JSON caller of the same control entry used by the Qt bridge."""
    def __init__(self):
        binary = Path(os.environ['SWIRL_RUST_HARNESS']).resolve(strict=True)
        self.process = subprocess.Popen([str(binary)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)
        self.responses = queue.Queue()

        def read():
            for line in self.process.stdout:
                self.responses.put(line)
            self.responses.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def command(self, **value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()
        try:
            line = self.responses.get(timeout=8)
        except queue.Empty:
            raise AssertionError('V2ControlResponseTimeout') from None
        if line is None:
            raise AssertionError('V2ControlExited')
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
            raise AssertionError('V2ControlShutdownTimeout') from None
        finally:
            self.reader.join(2)
            stderr = self.process.stderr.read()
            self.process.stdout.close()
            self.process.stderr.close()
        assert self.process.returncode == 0, 'V2ControlNonzeroExit'
        assert PASSWORD not in stderr, 'V2ControlLoggedCredential'


class BioTLS:
    """A real OpenSSL client whose ClientHello can share the CONNECT write."""
    def __init__(self, raw, context):
        self.raw = raw
        self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.tls = context.wrap_bio(self.incoming, self.outgoing,
                                    server_side=False, server_hostname='localhost')
        self.eof = False

    def client_hello(self):
        try:
            self.tls.do_handshake()
        except ssl.SSLWantReadError:
            pass
        data = self.outgoing.read()
        assert data and data[0] == 22, 'RealClientHelloMissing'
        return data

    def flush(self):
        data = self.outgoing.read()
        if data:
            self.raw.sendall(data)

    def receive(self):
        self.flush()
        data = self.raw.recv(16384)
        if data:
            self.incoming.write(data)
        else:
            assert not self.eof, 'RepeatedTransportEof'
            self.eof = True
            self.incoming.write_eof()

    def operation(self, callback):
        while True:
            try:
                result = callback()
                self.flush()
                return result
            except ssl.SSLWantReadError:
                self.receive()
            except ssl.SSLWantWriteError:
                self.flush()

    def handshake(self):
        self.operation(self.tls.do_handshake)

    def sendall(self, data):
        view = memoryview(data)
        while view:
            count = self.operation(lambda: self.tls.write(view))
            view = view[count:]

    def recv(self, count):
        return self.operation(lambda: self.tls.read(count))

    def unwrap(self):
        self.operation(self.tls.unwrap)
        return self.raw

    def close(self):
        self.raw.close()


def ws_frame(opcode, payload, *, masked=False, final=True):
    """RFC 6455 framing for fixed synthetic messages, without extensions."""
    first = opcode | (0x80 if final else 0)
    length = len(payload)
    flag = 0x80 if masked else 0
    if length < 126:
        prefix = bytes([first, flag | length])
    elif length < 65536:
        prefix = bytes([first, flag | 126]) + struct.pack('!H', length)
    else:
        raise AssertionError('FixtureFrameTooLarge')
    if masked:
        mask = b'\x11\x22\x33\x44'
        return prefix + mask + bytes(byte ^ mask[index % 4]
                                    for index, byte in enumerate(payload))
    return prefix + payload


def ws_read(stream, *, masked):
    first, second = exact(stream, 2)
    assert first & 0x70 == 0, 'UnexpectedWebSocketExtension'
    assert bool(second & 0x80) == masked, 'WebSocketMaskDirection'
    length = second & 0x7f
    if length == 126:
        length = struct.unpack('!H', exact(stream, 2))[0]
        assert length >= 126, 'WebSocketNonminimalLength'
    assert length <= 32768 and second & 0x7f != 127, 'FixtureFrameTooLarge'
    mask = exact(stream, 4) if masked else None
    payload = exact(stream, length)
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bool(first & 0x80), first & 0x0f, payload


class CompatOrigin:
    """Independent peers terminate TLS and validate the actual inner protocol."""
    def __init__(self, mode, context=None):
        self.mode, self.context = mode, context
        self.errors, self.requests, self.payloads = [], [], []
        self.clean_tls, self.finished = 0, 0
        self.lock = threading.Lock()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream = self.request
                stream.settimeout(8)
                try:
                    if context:
                        stream = context.wrap_socket(stream, server_side=True,
                                                     suppress_ragged_eofs=False)
                        expected = 'h2' if mode == 'h2' else 'http/1.1'
                        assert stream.selected_alpn_protocol() == expected, 'OriginAlpnMismatch'
                    if mode == 'h2':
                        owner.serve_h2(stream)
                    elif mode == 'halfclose':
                        data = bytearray()
                        while chunk := stream.recv(8191):
                            data.extend(chunk)
                            assert len(data) <= 32768, 'FixtureUploadTooLarge'
                        owner.payloads.append(bytes(data))
                        # Require the complete upload EOF before producing the
                        # delayed response, so truncating the reverse copy fails.
                        time.sleep(LATE_DELAY)
                        stream.sendall(TAIL)
                    elif mode == 'hold':
                        assert exact(stream, 4) == b'hold'
                        stream.sendall(b'held')
                        assert stream.recv(1) == b'', 'CancelledStreamSentData'
                        return
                    else:
                        request = header(stream)
                        owner.requests.append(request)
                        assert request.startswith(b'GET /compat HTTP/1.1\r\n'), 'OriginRequestMismatch'
                        if mode == 'sse':
                            owner.serve_sse(stream)
                        elif mode == 'websocket':
                            owner.serve_websocket(stream, request)
                        else:
                            assert mode == 'http'
                            stream.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '
                                           + str(len(HTTP_BODY)).encode()
                                           + b'\r\nConnection: close\r\n\r\n' + HTTP_BODY)
                    if context:
                        # No bare TCP EOF is accepted as a successful TLS close.
                        stream = stream.unwrap()
                        with owner.lock:
                            owner.clean_tls += 1
                    stream.shutdown(socket.SHUT_WR)
                    assert stream.recv(1) == b'', 'OriginMissingClientEof'
                finally:
                    stream.close()
                    with owner.lock:
                        owner.finished += 1

        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.errors, self.server.fixture_kind = self.errors, 'v2-compat-' + mode
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.worker.start()

    def serve_h2(self, stream):
        conn = h2.connection.H2Connection(config=h2.config.H2Configuration(
            client_side=False, header_encoding='utf-8'))
        conn.initiate_connection()
        stream.sendall(conn.data_to_send())
        ended, paths = set(), {}
        # Wait until all three requests have arrived before returning any body.
        # Three serialized connections cannot satisfy this multiplexing test.
        while len(ended) != 3:
            data = stream.recv(16384)
            assert data, 'H2RequestTruncated'
            for event in conn.receive_data(data):
                if isinstance(event, h2.events.RequestReceived):
                    fields = dict(event.headers)
                    assert fields[':method'] == 'GET' and fields[':scheme'] == 'https'
                    assert fields[':authority'] == 'localhost'
                    paths[event.stream_id] = fields[':path']
                elif isinstance(event, h2.events.StreamEnded):
                    ended.add(event.stream_id)
            data = conn.data_to_send()
            if data:
                stream.sendall(data)
        assert ended == {1, 3, 5} and set(paths.values()) == {'/one', '/two', '/three'}
        self.requests.append(paths)
        # Complete in reverse order with interleaved data frames.
        for stream_id in (5, 3, 1):
            conn.send_headers(stream_id, [(':status', '200'), ('content-type', 'text/plain')])
            conn.send_data(stream_id, paths[stream_id].encode() + b':')
        for stream_id in (3, 1, 5):
            conn.send_data(stream_id, b'complete', end_stream=True)
        stream.sendall(conn.data_to_send())
        # Require the client's GOAWAY before initiating authenticated TLS close.
        while True:
            data = stream.recv(16384)
            assert data, 'H2ClientMissingGoaway'
            events = conn.receive_data(data)
            if any(isinstance(event, h2.events.ConnectionTerminated) for event in events):
                return
            outgoing = conn.data_to_send()
            if outgoing:
                stream.sendall(outgoing)

    @staticmethod
    def serve_sse(stream):
        stream.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                       b'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n')
        for index, event in enumerate(SSE_EVENTS):
            if index == 1:
                time.sleep(LATE_DELAY)
            # Split each event between HTTP chunks and split each chunk on the
            # wire. SSE parsing must survive both independent boundaries.
            for part in (event[:7], event[7:]):
                chunk = f'{len(part):x}\r\n'.encode() + part + b'\r\n'
                stream.sendall(chunk[:1])
                stream.sendall(chunk[1:])
        stream.sendall(b'0\r\n\r\n')

    @staticmethod
    def serve_websocket(stream, request):
        fields = dict(line.split(b': ', 1) for line in request.split(b'\r\n')[1:] if b': ' in line)
        assert fields[b'Upgrade'].lower() == b'websocket'
        assert fields[b'Connection'].lower() == b'upgrade'
        assert fields[b'Sec-WebSocket-Version'] == b'13'
        key = fields[b'Sec-WebSocket-Key']
        assert len(base64.b64decode(key, validate=True)) == 16
        accept = base64.b64encode(hashlib.sha1(key + WS_GUID).digest())
        stream.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                       b'Connection: Upgrade\r\nSec-WebSocket-Accept: ' + accept
                       + b'\r\n\r\n' + ws_frame(1, b'first-frame-with-101'))
        final, opcode, first = ws_read(stream, masked=True)
        assert not final and opcode == 2
        assert ws_read(stream, masked=True) == (True, 9, b'ping')
        stream.sendall(ws_frame(10, b'ping'))
        final, opcode, second = ws_read(stream, masked=True)
        assert final and opcode == 0
        stream.sendall(ws_frame(2, first + second))
        close = ws_read(stream, masked=True)
        assert close == (True, 8, b'\x03\xe8')
        stream.sendall(ws_frame(8, close[2]))

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        assert not self.errors, self.errors


class WindowsProxyCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('SWIRL_RUST_HARNESS'):
            raise RuntimeError('SWIRL_RUST_HARNESS must name the compiled production control binary')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='swirl-v2-compat-')
        self.addCleanup(self.folder.cleanup)
        self.context, _, self.ca = certificates(self.folder.name)
        self.context.set_alpn_protocols(['h2', 'http/1.1'])
        self.host = V2Host()
        self.addCleanup(self.host.close)
        self.handle = None

    def keep(self, resource):
        self.addCleanup(resource.close)
        return resource

    def start(self, origin, protocol):
        self.peer = self.keep(Relay(protocol, 'compat-node', [origin.port]))
        outbound = {'type': 'http_connect' if protocol == 'http' else 'socks5',
                    'host': '127.0.0.1', 'port': self.peer.port,
                    'auth': {'username': USER, 'password': PASSWORD}}
        self.candidate = {'schema': 2, 'listen': '127.0.0.1:0',
                          'nodes': [{'id': NODE, 'outbound': outbound}],
                          'policy': {'schema': 2, 'mode': 'global',
                                     'default_policy': {'id': 'policy:default',
                                                        'target': {'kind': 'node', 'id': NODE}}},
                          'limits': {'max_connections': 32, 'handshake_timeout_ms': HANDSHAKE_MS}}
        result = self.host.command(control_schema=2, op='start_v2', request_id=REQUEST,
                                   store_id=STORE, saved_revision='1', candidate=self.candidate)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status']['schema'], 2)
        self.assertEqual(result['status']['configuration']['applied_mode'], 'global')
        self.handle = int(result['handle'])
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def connect_response(self, stream):
        response = header(stream)
        status, *fields = response.split(b'\r\n')
        version, code, _ = status.split(b' ', 2)
        self.assertIn(version, (b'HTTP/1.0', b'HTTP/1.1'))
        self.assertEqual(code, b'200')
        names = {field.split(b':', 1)[0].lower() for field in fields if field}
        self.assertFalse(names & {b'content-length', b'transfer-encoding'})

    def tunnel(self, origin, version='1.1', initial=b''):
        raw = socket.create_connection(('127.0.0.1', self.port), timeout=8)
        raw.settimeout(8)
        request = f'CONNECT {TARGET}:{origin.port} HTTP/{version}\r\nHost: {TARGET}:{origin.port}\r\n\r\n'.encode()
        raw.sendall(request + initial)
        self.connect_response(raw)
        return raw

    def tls(self, origin, alpn='http/1.1'):
        context = ssl.create_default_context(cadata=self.ca)
        context.set_alpn_protocols([alpn])
        raw = self.tunnel(origin)
        try:
            stream = context.wrap_socket(raw, server_hostname='localhost', suppress_ragged_eofs=False)
        except BaseException:
            raw.close()
            raise
        self.assertEqual(stream.selected_alpn_protocol(), alpn)
        return stream

    def close_tls(self, stream):
        raw = stream.unwrap()
        raw.shutdown(socket.SHUT_WR)
        self.assertEqual(raw.recv(1), b'')
        raw.close()

    def idle(self, origin, *, tls=True):
        deadline = time.monotonic() + 5
        while True:
            result = self.host.command(op='snapshot', handle=self.handle)['status']
            peer_finished = (self.peer.connections and self.peer.connections[0]['upload_eof']
                             and self.peer.connections[0]['download_eof'])
            # SessionGuard publishes active and record.ended separately.
            # Wait for both completion fields without weakening either check.
            records = result['connections']
            record_finished = len(records) == 1 and records[0]['ended']
            if result['active'] == 0 and record_finished and origin.finished and peer_finished:
                break
            if time.monotonic() > deadline:
                self.fail('V2SessionDidNotFinish: ' + json.dumps(result))
            time.sleep(0.01)
        self.assertEqual(result['failed'], 0, result)
        self.assertEqual(len(result['connections']), 1, result)
        record = result['connections'][0]
        self.assertEqual((record['node'], record['category'], record['ended']), (NODE, 'proxy', True))
        self.assertEqual(record['error'], '')
        self.assertEqual(len(self.peer.connections), 1)
        event = self.peer.connections[0]
        self.assertEqual((event['host'], event['port']), (TARGET, origin.port))
        self.assertTrue(event['upload'] and event['download'])
        self.assertTrue(event['upload_eof'] and event['download_eof'], event)
        self.assertFalse(origin.errors, origin.errors)
        if tls:
            self.assertEqual(origin.clean_tls, 1)
        self.assertTrue(self.host.command(op='stop', handle=self.handle)['ok'])
        self.handle = None

    def test_v2_connect_versions_preserve_coalesced_real_clienthello(self):
        for protocol in ('http', 'socks5'):
            for version in ('1.0', '1.1'):
                with self.subTest(upstream=protocol, http=version):
                    origin = self.keep(CompatOrigin('http', self.context))
                    self.start(origin, protocol)
                    raw = socket.create_connection(('127.0.0.1', self.port), timeout=8)
                    self.addCleanup(raw.close)
                    context = ssl.create_default_context(cadata=self.ca)
                    context.set_alpn_protocols(['http/1.1'])
                    stream = BioTLS(raw, context)
                    hello = stream.client_hello()
                    request = f'CONNECT {TARGET}:{origin.port} HTTP/{version}\r\nHost: {TARGET}:{origin.port}\r\n\r\n'.encode()
                    raw.sendall(request + hello)
                    self.connect_response(raw)
                    stream.handshake()
                    stream.sendall(b'GET /compat HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                    self.assertIn(b'200 OK', header(stream))
                    self.assertEqual(exact(stream, len(HTTP_BODY)), HTTP_BODY)
                    self.close_tls(stream)
                    self.idle(origin)
                    self.assertEqual(self.peer.connections[0]['prefix'][:len(hello)], hello)

    def test_v2_verified_tls_h2_multiplexes_three_real_requests(self):
        for protocol in ('http', 'socks5'):
            with self.subTest(upstream=protocol):
                origin = self.keep(CompatOrigin('h2', self.context))
                self.start(origin, protocol)
                stream = self.tls(origin, 'h2')
                self.addCleanup(stream.close)
                conn = h2.connection.H2Connection(config=h2.config.H2Configuration(
                    client_side=True, header_encoding='utf-8'))
                conn.initiate_connection()
                paths = {1: '/one', 3: '/two', 5: '/three'}
                for stream_id, path in paths.items():
                    conn.send_headers(stream_id, [(':method', 'GET'), (':scheme', 'https'),
                                                  (':authority', 'localhost'), (':path', path)], end_stream=True)
                stream.sendall(conn.data_to_send())
                bodies, statuses, ended = {i: b'' for i in paths}, {}, []
                while len(ended) != 3:
                    data = stream.recv(16384)
                    self.assertTrue(data, 'H2ResponseTruncated')
                    for event in conn.receive_data(data):
                        if isinstance(event, h2.events.ResponseReceived):
                            statuses[event.stream_id] = dict(event.headers)[':status']
                        elif isinstance(event, h2.events.DataReceived):
                            bodies[event.stream_id] += event.data
                            conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
                        elif isinstance(event, h2.events.StreamEnded):
                            ended.append(event.stream_id)
                        elif isinstance(event, (h2.events.StreamReset, h2.events.ConnectionTerminated)):
                            self.fail('UnexpectedH2Termination')
                    outgoing = conn.data_to_send()
                    if outgoing:
                        stream.sendall(outgoing)
                self.assertEqual(statuses, {1: '200', 3: '200', 5: '200'})
                self.assertEqual(bodies, {i: path.encode() + b':complete' for i, path in paths.items()})
                self.assertEqual(ended, [3, 1, 5])
                conn.close_connection()
                stream.sendall(conn.data_to_send())
                self.close_tls(stream)
                self.idle(origin)
                self.assertEqual(origin.requests, [paths])

    def test_v2_tls_sse_chunking_and_idle_exceed_handshake_deadline(self):
        for protocol in ('http', 'socks5'):
            with self.subTest(upstream=protocol):
                origin = self.keep(CompatOrigin('sse', self.context))
                self.start(origin, protocol)
                stream = self.tls(origin)
                self.addCleanup(stream.close)
                # The origin starts its idle interval after sending headers.
                # Include time spent waiting to read them on a busy runner.
                start = time.monotonic()
                stream.sendall(b'GET /compat HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\n\r\n')
                response = header(stream)
                self.assertIn(b'Content-Type: text/event-stream\r\n', response)
                self.assertIn(b'Transfer-Encoding: chunked\r\n', response)
                events, pending = [], b''
                while True:
                    line = b''
                    while not line.endswith(b'\r\n'):
                        line += exact(stream, 1)
                        self.assertLess(len(line), 16)
                    length = int(line[:-2], 16)
                    if not length:
                        self.assertEqual(exact(stream, 2), b'\r\n')
                        break
                    pending += exact(stream, length)
                    self.assertEqual(exact(stream, 2), b'\r\n')
                    while b'\n\n' in pending:
                        event, pending = pending.split(b'\n\n', 1)
                        events.append(event + b'\n\n')
                self.assertEqual(events, SSE_EVENTS)
                self.assertEqual(pending, b'')
                self.assertGreater(time.monotonic() - start, HANDSHAKE_MS / 1000)
                self.close_tls(stream)
                self.idle(origin)

    def test_v2_wss_upgrade_first_frame_fragmentation_ping_and_clean_close(self):
        for protocol in ('http', 'socks5'):
            with self.subTest(upstream=protocol):
                origin = self.keep(CompatOrigin('websocket', self.context))
                self.start(origin, protocol)
                stream = self.tls(origin)
                self.addCleanup(stream.close)
                key = base64.b64encode(b'swirl-fixture-v2')
                stream.sendall(b'GET /compat HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
                               b'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '
                               + key + b'\r\n\r\n')
                response = header(stream)
                self.assertTrue(response.startswith(b'HTTP/1.1 101 Switching Protocols\r\n'))
                self.assertIn(b'Sec-WebSocket-Accept: ' + base64.b64encode(hashlib.sha1(key + WS_GUID).digest()), response)
                self.assertEqual(ws_read(stream, masked=False), (True, 1, b'first-frame-with-101'))
                first, second = bytes(range(256)) * 17, b'end-of-fragmented-message'
                stream.sendall(ws_frame(2, first, masked=True, final=False)
                               + ws_frame(9, b'ping', masked=True)
                               + ws_frame(0, second, masked=True))
                self.assertEqual(ws_read(stream, masked=False), (True, 10, b'ping'))
                self.assertEqual(ws_read(stream, masked=False), (True, 2, first + second))
                stream.sendall(ws_frame(8, b'\x03\xe8', masked=True))
                self.assertEqual(ws_read(stream, masked=False), (True, 8, b'\x03\xe8'))
                self.close_tls(stream)
                self.idle(origin)

    def test_v2_halfclose_delivers_delayed_large_tail_without_task_leak(self):
        for protocol in ('http', 'socks5'):
            with self.subTest(upstream=protocol):
                origin = self.keep(CompatOrigin('halfclose'))
                self.start(origin, protocol)
                stream = self.tunnel(origin)
                self.addCleanup(stream.close)
                payload = bytes(range(256)) * 101
                stream.sendall(payload)
                stream.shutdown(socket.SHUT_WR)
                received = bytearray()
                while data := stream.recv(997):
                    received.extend(data)
                    self.assertLessEqual(len(received), len(TAIL))
                self.assertEqual(bytes(received), TAIL)
                self.assertEqual(origin.payloads, [payload])
                stream.close()
                self.idle(origin, tls=False)

    def test_v2_client_cancellation_and_core_stop_release_proxy_sessions(self):
        for protocol in ('http', 'socks5'):
            with self.subTest(upstream=protocol):
                origin = self.keep(CompatOrigin('hold'))
                self.start(origin, protocol)
                with self.tunnel(origin) as stream:
                    stream.sendall(b'hold')
                    self.assertEqual(exact(stream, 4), b'held')
                self.idle(origin, tls=False)

                origin = self.keep(CompatOrigin('hold'))
                self.start(origin, protocol)
                with self.tunnel(origin) as stream:
                    stream.sendall(b'hold')
                    self.assertEqual(exact(stream, 4), b'held')
                    state = self.host.command(op='snapshot', handle=self.handle)['status']
                    self.assertEqual(state['active'], 1)
                    self.assertTrue(self.host.command(op='stop', handle=self.handle)['ok'])
                    self.assertEqual(stream.recv(1), b'')
                self.assertFalse(self.host.command(op='snapshot', handle=self.handle)['ok'])
                with self.assertRaises(OSError):
                    socket.create_connection(('127.0.0.1', self.port), timeout=0.5)
                deadline = time.monotonic() + 5
                while not origin.finished or not self.peer.connections[0]['upload_eof']:
                    self.assertLess(time.monotonic(), deadline, 'StoppedProxySessionDidNotClose')
                    time.sleep(0.01)
                self.assertEqual(len(self.peer.connections), 1)
                self.assertFalse(origin.errors, origin.errors)
                self.handle = None


if __name__ == '__main__':
    unittest.main(verbosity=2)
