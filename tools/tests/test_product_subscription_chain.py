"""Subscription-to-origin evidence with independent, bounded Python relays.

The portable menu uses the real Rust inspector and control executable. Its JSON
persistence is a test host, not Qt/DPAPI. The separate Windows menu calls the
actual Qt importer, encrypted NodeStore, controller and Rust adapter. Neither
menu talks to a provider or implements a replacement product configuration path.

Protocol primitives reuse the independent Python peers in this test directory;
all positive tunnels MUST reach a separately listening HTTP/HTTPS/echo origin.
"""
import base64
import concurrent.futures
import copy
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import random
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from test_rust_core import certificates, exact, header, target
from test_shadowsocks import PASSWORD, Reader, Writer, cipher_key


USER = 'product-user'
UUID = '00112233-4455-6677-8899-aabbccddeeff'
BODY = b'product-origin-ok'
TAIL = b'origin-after-halfclose'


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = 64

    def handle_error(self, request, address):
        _, error, trace = sys.exc_info()
        frames = []
        while trace:
            frames.append({'file': Path(trace.tb_frame.f_code.co_filename).name,
                           'function': trace.tb_frame.f_code.co_name, 'line': trace.tb_lineno})
            trace = trace.tb_next
        # Keep the exact failing source boundary and system error without
        # copying request bytes, credentials or exception messages to CI.
        self.errors.append({'category': 'IndependentFixtureAssertion',
                            'fixture': self.fixture_kind, 'type': type(error).__name__,
                            'errno': getattr(error, 'errno', None),
                            'winerror': getattr(error, 'winerror', None), 'frames': frames[-8:]})


class Origin:
    def __init__(self, context=None, echo=False, client_closes_tls=False):
        self.requests, self.errors, self.payloads, self.sni = [], [], [], []
        self.context, self.echo = context, echo
        self.tls_closed = 0
        self.stopped = threading.Event()
        if context:
            context.set_servername_callback(lambda stream, name, ctx: self.sni.append(name))
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream = self.request
                stream.settimeout(8)
                try:
                    if context:
                        try:
                            stream = context.wrap_socket(stream, server_side=True, suppress_ragged_eofs=False)
                        except ssl.SSLError:
                            return  # The explicit wrong-name client is a negative test.
                    if echo:
                        while data := stream.recv(8191):
                            owner.payloads.append(data)
                            stream.sendall(data)
                        stream.sendall(TAIL)
                    else:
                        request = header(stream)
                        owner.requests.append(request)
                        first = request.split(b'\r\n', 1)[0]
                        assert first.startswith(b'GET /'), first
                        assert first.endswith(b' HTTP/1.1'), first
                        # This secret-free payload belongs to the independent
                        # origin, never to the relay serving as the proxy.
                        body = BODY + b':' + first.split(b' ')[1]
                        stream.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: ' +
                                       str(len(body)).encode() +
                                       b'\r\nConnection: close\r\n\r\n' + body)
                    tls_closed = isinstance(stream, ssl.SSLSocket)
                    if tls_closed:
                        if client_closes_tls:
                            # The Qt test client explicitly owns shutdown after
                            # its full response. Require its authenticated TLS
                            # EOF first; a bare TCP EOF raises SSLEOFError.
                            assert stream.recv(1) == b''
                        stream = stream.unwrap()
                    try:
                        stream.shutdown(socket.SHUT_WR)
                    except OSError as error:
                        # unwrap already proved both TLS close_notify alerts.
                        # Some clients have also completed TCP close by now;
                        # still require raw EOF below, and accept no other error.
                        if not tls_closed or (error.errno != errno.ENOTCONN and
                                              getattr(error, 'winerror', None) != 10057):
                            raise
                    assert stream.recv(1) == b''
                    if tls_closed:
                        # Count normal completion only after authenticated TLS
                        # closure AND raw EOF; cancellation cannot count as it.
                        owner.tls_closed += 1
                except (EOFError, ConnectionError, socket.timeout):
                    # Cancellation is explicitly exercised by the caller.
                    pass
                finally:
                    stream.close()

        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.server.fixture_kind = 'tls-origin' if context else 'echo-origin' if echo else 'http-origin'
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def close(self):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.errors, self.errors


class SsStream:
    """Independent SIP004 stream adapter; no Rust framing code is shared."""
    def __init__(self, stream, method, password):
        self.stream = stream
        self.reader = Reader(stream, method)
        self.reader.cipher = cipher_key(method, self.reader.salt, password)
        self.writer = Writer(method)
        self.writer.cipher = cipher_key(method, self.writer.salt, password)
        self.pending = bytearray()
        self.sent_salt = False

    def recv(self, count):
        while not self.pending:
            chunk = self.reader.chunk(allow_boundary_eof=True)
            if chunk is None:
                return b''
            self.pending.extend(chunk)
        value = bytes(self.pending[:count])
        del self.pending[:count]
        return value

    def sendall(self, data):
        if not self.sent_salt:
            self.stream.sendall(self.writer.salt)
            self.sent_salt = True
        for start in range(0, len(data), 8191):
            record = self.writer.chunk(data[start:start + 8191])
            # Exercise length/tag fragmentation on the actual wire.
            self.stream.sendall(record[:1])
            self.stream.sendall(record[1:17])
            self.stream.sendall(record[17:])


def terminated(stream):
    result = bytearray()
    while True:
        byte = exact(stream, 1)
        if byte == b'\0':
            return bytes(result)
        result.extend(byte)
        assert len(result) <= 255


class Relay:
    """Authenticate first, then relay ONLY to this fixture's explicit origins."""
    def __init__(self, protocol, identity, ports, password=PASSWORD, cipher='aes-128-gcm'):
        self.protocol, self.identity = protocol, identity
        self.password, self.cipher = password, cipher
        self.ports = set(ports)
        self.connections, self.denied, self.errors = [], [], []
        self.upload, self.download = 0, 0
        self.lock = threading.Lock()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                wire = self.request
                wire.settimeout(8)
                stream = wire
                upstream = None
                try:
                    if protocol == 'http':
                        request = header(stream)
                        line, *fields = request.split(b'\r\n')
                        method, authority, version = line.split(b' ')
                        assert method == b'CONNECT' and version == b'HTTP/1.1'
                        expected = b'Proxy-Authorization: Basic ' + base64.b64encode(
                            (USER + ':' + password).encode())
                        if expected not in fields:
                            owner.denied.append('Authentication')
                            wire.sendall(b'HTTP/1.1 407 Denied\r\nContent-Length: 0\r\n\r\n')
                            return
                        host, port = authority.decode().rsplit(':', 1)
                        destination = (host.strip('[]'), int(port))
                    elif protocol == 'socks5':
                        assert exact(stream, 3) == b'\x05\x01\x02'
                        wire.sendall(b'\x05\x02')
                        assert exact(stream, 1) == b'\x01'
                        user = exact(stream, exact(stream, 1)[0]).decode()
                        secret = exact(stream, exact(stream, 1)[0]).decode()
                        if (user, secret) != (USER, password):
                            owner.denied.append('Authentication')
                            wire.sendall(b'\x01\x01')
                            return
                        wire.sendall(b'\x01\x00')
                        assert exact(stream, 3) == b'\x05\x01\x00'
                        destination = target(stream)
                    elif protocol in ('socks4', 'socks4a'):
                        assert exact(stream, 2) == b'\x04\x01'
                        port = int.from_bytes(exact(stream, 2), 'big')
                        address = exact(stream, 4)
                        assert terminated(stream) == USER.encode()
                        host = (terminated(stream).decode() if address[:3] == bytes(3)
                                and address[3] else socket.inet_ntoa(address))
                        destination = (host, port)
                    elif protocol == 'ss':
                        stream = SsStream(wire, cipher, password)
                        destination = target(stream)
                    elif protocol == 'vless':
                        assert exact(stream, 1) == b'\0'
                        if exact(stream, 16) != bytes.fromhex(UUID.replace('-', '')):
                            owner.denied.append('Authentication')
                            return
                        assert exact(stream, 2) == b'\0\x01'
                        port = int.from_bytes(exact(stream, 2), 'big')
                        kind = exact(stream, 1)[0]
                        if kind == 1:
                            host = socket.inet_ntop(socket.AF_INET, exact(stream, 4))
                        elif kind == 3:
                            host = socket.inet_ntop(socket.AF_INET6, exact(stream, 16))
                        else:
                            assert kind == 2
                            host = exact(stream, exact(stream, 1)[0]).decode()
                        destination = (host, port)
                    else:
                        raise AssertionError('UnsupportedIndependentPeer')
                    host, port = destination
                    assert host in ('localhost', '127.0.0.1', '::1', 'a.fixture.invalid',
                                    'b.fixture.invalid', 'denied.fixture.invalid',
                                    'nested.suffix.fixture.invalid', 'keyword.fixture.invalid',
                                    'final.fixture.invalid', 'wrong.fixture.invalid',
                                    'a.product.invalid', 'b.product.invalid',
                                    'choice.product.invalid', 'denied.product.invalid',
                                    'stream.product.invalid', 'nested.suffix.product.invalid',
                                    'keyword.product.invalid', 'port.product.invalid')
                    assert port in owner.ports
                    upstream = socket.create_connection(('127.0.0.1', port), timeout=8)
                    event = {'peer': identity, 'host': host, 'port': port, 'upload': 0,
                             'download': 0, 'prefix': b'', 'upload_eof': False,
                             'download_eof': False, 'write_shutdown': None,
                             'upload_truncated': False}
                    owner.connections.append(event)
                    if protocol == 'http':
                        wire.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                    elif protocol == 'socks5':
                        wire.sendall(b'\x05\0\0\x01\x7f\0\0\x01\0\0')
                    elif protocol in ('socks4', 'socks4a'):
                        wire.sendall(b'\0\x5a\0\0\0\0\0\0')
                    elif protocol == 'vless':
                        wire.sendall(b'\0\0')

                    def upload():
                        try:
                            while data := stream.recv(4093):
                                upstream.sendall(data)
                                with owner.lock:
                                    owner.upload += len(data)
                                    event['upload'] += len(data)
                                    event['prefix'] = (event['prefix'] + data)[:4096]
                            event['upload_eof'] = True
                        except EOFError:
                            # SsStream returns empty only between complete
                            # authenticated records; partial records fail.
                            event['upload_truncated'] = True
                        except (OSError, InvalidTag):
                            pass
                        finally:
                            try:
                                upstream.shutdown(socket.SHUT_WR)
                            except OSError:
                                pass

                    uploader = threading.Thread(target=upload, daemon=True)
                    uploader.start()
                    try:
                        while data := upstream.recv(8191):
                            stream.sendall(data)
                            with owner.lock:
                                owner.download += len(data)
                                event['download'] += len(data)
                        event['download_eof'] = True
                        try:
                            wire.shutdown(socket.SHUT_WR)
                            event['write_shutdown'] = 'sent'
                        except OSError as error:
                            # Darwin can finish TCP close before this final
                            # half-close after the origin EOF. Accept only that
                            # state, and verify the upload's EOF after joining.
                            if (error.errno != errno.ENOTCONN and
                                    getattr(error, 'winerror', None) != 10057):
                                raise
                            event['write_shutdown'] = 'already_closed'
                    finally:
                        uploader.join(8)
                        assert not uploader.is_alive(), 'RelayUploadDidNotFinish'
                        assert not event['upload_truncated'], 'RelayUploadRecordTruncated'
                    if event['write_shutdown'] == 'already_closed':
                        assert event['upload_eof'], 'RelayClosedBeforeUploadEof'
                except InvalidTag:
                    owner.denied.append('Authentication')
                except (EOFError, ConnectionError, socket.timeout):
                    pass
                finally:
                    if upstream:
                        upstream.close()
                    wire.close()

        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.server.fixture_kind = 'relay-' + protocol + '-' + identity
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def node(self):
        node = {'name': self.identity, 'type': self.protocol, 'server': '127.0.0.1', 'port': self.port}
        if self.protocol in ('http', 'socks5'):
            node.update(username=USER, password=self.password)
        elif self.protocol in ('socks4', 'socks4a'):
            node['username'] = USER
        elif self.protocol == 'ss':
            node.update(cipher=self.cipher, password=self.password, udp=False)
        elif self.protocol == 'vless':
            node.update(uuid=UUID, tls=False, network='tcp')
        return node

    def document(self, fmt='json'):
        if fmt == 'json':
            return json.dumps({'proxies': [self.node()]})
        assert self.protocol == 'ss'
        authority = base64.urlsafe_b64encode((self.cipher + ':' + self.password).encode()).decode().rstrip('=')
        uri = f'ss://{authority}@127.0.0.1:{self.port}#{quote(self.identity)}'
        return base64.b64encode(uri.encode()).decode() if fmt == 'base64' else uri

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.errors, self.errors


class RelayHalfCloseChecks(unittest.TestCase):
    """Exercise the independent fixture over real sockets with OS close races."""

    def exchange(self, shutdown_errno=None, upload_error=False, protocol='http',
                 cipher='chacha20-ietf-poly1305', truncated_tail=None):
        from unittest import mock
        origin = Origin(echo=True)
        relay = Relay(protocol, 'halfclose-check', [origin.port], cipher=cipher)
        finished = threading.Event()
        original_process = relay.server.process_request_thread
        original_shutdown = socket.socket.shutdown
        original_recv = socket.socket.recv
        injected = False

        def process(request, address):
            try:
                original_process(request, address)
            finally:
                finished.set()

        relay.server.process_request_thread = process

        def shutdown(stream, how):
            nonlocal injected
            selected = (stream.getsockname()[1] == relay.port and
                        how == socket.SHUT_WR and not injected and
                        shutdown_errno is not None)
            try:
                result = original_shutdown(stream, how)
            except OSError as error:
                if (not selected or (error.errno != errno.ENOTCONN and
                                     getattr(error, 'winerror', None) != 10057)):
                    raise
                result = None
            if selected:
                injected = True
                # Actual FIN/data delivery happens first; Darwin can report
                # ENOTCONN when the peer has already completed its close.
                raise OSError(shutdown_errno, 'synthetic fixture shutdown state')
            return result

        def recv(stream, count, *args):
            data = original_recv(stream, count, *args)
            if upload_error and not data and stream.getsockname()[1] == relay.port:
                raise OSError(errno.EIO, 'synthetic fixture receive failure')
            return data

        payload = b'independent-relay-halfclose' * 257
        close_failed = False
        try:
            with mock.patch.object(socket.socket, 'shutdown', shutdown), \
                    mock.patch.object(socket.socket, 'recv', recv):
                with socket.create_connection(('127.0.0.1', relay.port), timeout=3) as stream:
                    if protocol == 'http':
                        auth = base64.b64encode((USER + ':' + PASSWORD).encode())
                        stream.sendall(f'CONNECT localhost:{origin.port} HTTP/1.1\r\n'.encode() +
                                       b'Proxy-Authorization: Basic ' + auth + b'\r\n\r\n')
                        self.assertIn(b'200 Connection Established', header(stream))
                        stream.sendall(payload)
                        response = stream
                    else:
                        self.assertEqual(protocol, 'ss')
                        writer = Writer(cipher)
                        address = b'\x03\x09localhost' + origin.port.to_bytes(2, 'big')
                        stream.sendall(writer.salt + writer.chunk(b'') +
                                       writer.chunk(address + payload) + writer.chunk(b''))
                        response = SsStream(stream, cipher, PASSWORD)
                    self.assertEqual(exact(response, len(payload)), payload)
                    if truncated_tail is not None:
                        stream.sendall(writer.chunk(b'must-not-reach-origin')[:truncated_tail])
                    stream.shutdown(socket.SHUT_WR)
                    self.assertEqual(exact(response, len(TAIL)), TAIL)
                    self.assertEqual(response.recv(1), b'')
                self.assertTrue(finished.wait(3), 'independent relay did not finish')
            self.assertEqual(relay.upload, len(payload))
            self.assertEqual(relay.download, len(payload) + len(TAIL))
            self.assertEqual(b''.join(origin.payloads), payload)
        finally:
            try:
                relay.close()
            except AssertionError:
                close_failed = True
            origin.close()
        return relay, injected, close_failed

    def test_normal_halfclose_delivers_payload_tail_and_eof(self):
        relay, injected, failed = self.exchange()
        self.assertFalse(injected)
        self.assertFalse(failed)
        self.assertEqual(relay.errors, [])

    def test_not_connected_after_both_eofs_is_a_completed_close(self):
        relay, injected, failed = self.exchange(errno.ENOTCONN)
        self.assertTrue(injected)
        self.assertFalse(failed, relay.errors)
        self.assertEqual(relay.errors, [])
        self.assertEqual(relay.connections[0]['write_shutdown'], 'already_closed')
        self.assertTrue(relay.connections[0]['upload_eof'])
        self.assertTrue(relay.connections[0]['download_eof'])

    def test_other_shutdown_errors_still_fail_the_fixture(self):
        for code in (errno.EBADF, errno.EIO):
            with self.subTest(errno=code):
                relay, injected, failed = self.exchange(code)
                self.assertTrue(injected)
                self.assertTrue(failed)
                self.assertEqual([error['errno'] for error in relay.errors], [code])

    def test_not_connected_without_verified_upload_eof_still_fails(self):
        relay, injected, failed = self.exchange(errno.ENOTCONN, upload_error=True)
        self.assertTrue(injected)
        self.assertTrue(failed)
        self.assertEqual([error['type'] for error in relay.errors], ['AssertionError'])


    def test_ss_record_boundary_eof_and_close_for_all_aead_ciphers(self):
        for cipher in ('aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305'):
            with self.subTest(cipher=cipher):
                relay, injected, failed = self.exchange(errno.ENOTCONN, protocol='ss', cipher=cipher)
                self.assertTrue(injected)
                self.assertFalse(failed, relay.errors)
                self.assertEqual(relay.errors, [])
                self.assertTrue(relay.connections[0]['upload_eof'])
                self.assertEqual(relay.connections[0]['write_shutdown'], 'already_closed')

    def test_ss_partial_encrypted_header_is_not_record_boundary_eof(self):
        for count in (1, 17):
            with self.subTest(bytes=count):
                relay, _, failed = self.exchange(protocol='ss', truncated_tail=count)
                self.assertTrue(failed, 'truncated SS header must fail the fixture')
                self.assertFalse(relay.connections[0]['upload_eof'])
                self.assertEqual([error['type'] for error in relay.errors], ['AssertionError'])

    def test_ss_partial_encrypted_payload_is_not_record_boundary_eof(self):
        for count in (18, 19, 18 + len(b'must-not-reach-origin') + 15):
            with self.subTest(bytes=count):
                relay, _, failed = self.exchange(protocol='ss', truncated_tail=count)
                self.assertTrue(failed, 'truncated SS payload or tag must fail the fixture')
                self.assertFalse(relay.connections[0]['upload_eof'])
                self.assertEqual([error['type'] for error in relay.errors], ['AssertionError'])


class Harness:
    def __init__(self):
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        assert line, 'RustControlExited'
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(8)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(2)
            raise AssertionError('RustShutdownTimeout')
        finally:
            error = self.process.stderr.read()
            self.process.stdout.close()
            self.process.stderr.close()
        assert self.process.returncode == 0, error
        assert PASSWORD not in error and UUID not in error


class ChainBase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='swirl-synthetic-chain-')
        self.addCleanup(self.folder.cleanup)
        self.context, self.ca_der, self.ca_pem = certificates(self.folder.name)
        self.http = self.keep(Origin())
        self.https = self.keep(Origin(context=self.context,
                                      client_closes_tls=getattr(self, 'client_closes_tls', False)))
        self.echo = self.keep(Origin(echo=True))

    def keep(self, resource):
        self.addCleanup(resource.close)
        return resource

    def relay(self, protocol='http', identity='A', **kwargs):
        return self.keep(Relay(protocol, identity,
                               [self.http.port, self.https.port, self.echo.port], **kwargs))


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS') and os.environ.get('SWIRL_RUST_INSPECTOR'),
                     'compiled Rust control and inspector required')
class ProductChainIntegration(ChainBase):
    def setUp(self):
        super().setUp()
        self.core = self.keep(Harness())

    def inspect(self, document):
        result = subprocess.run([os.environ['SWIRL_RUST_INSPECTOR'], '--private-json'],
                                input=document, text=True, capture_output=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def imported(self, peers, fmt='json'):
        nodes = []
        for peer in peers:
            document = peer.document(fmt)
            parsed = self.inspect(document)
            self.assertTrue(parsed['report']['parsed'])
            self.assertTrue(parsed['report']['original_preserved'])
            self.assertEqual(len(parsed['tcpCandidates']), 1)
            candidate = parsed['tcpCandidates'][0]
            self.assertIsNotNone(candidate, parsed['report'])
            self.assertEqual(candidate['host'], '127.0.0.1')
            self.assertEqual(candidate['port'], peer.port)
            # Persist/reload both source and IR using this portable test host.
            # DPAPI and actual product-object reconstruction are tested below.
            path = Path(self.folder.name) / (peer.identity + '.json')
            path.write_text(json.dumps({'source': document, 'parsed': parsed}), encoding='utf-8')
            loaded = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(loaded['source'], document)
            self.assertEqual(loaded['parsed'], parsed)
            nodes.append({'id': peer.identity, 'outbound': loaded['parsed']['tcpCandidates'][0]})
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': peers[0].identity, 'nodes': nodes}

    def start(self, config):
        result = self.core.command(op='start', config=config)
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])
        return self.handle

    def tunnel(self, host, port):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=8)
        stream.settimeout(8)
        authority = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
        stream.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
        response = header(stream)
        if not response.startswith(b'HTTP/1.1 200 '):
            stream.close()
            raise ConnectionError('TunnelRejected')
        return stream

    def fetch(self, host='localhost', path='/chain', tls=False, server_name='localhost'):
        stream = self.tunnel(host, self.https.port if tls else self.http.port)
        try:
            if tls:
                context = ssl.create_default_context(cadata=self.ca_pem)
                context.set_alpn_protocols(['http/1.1'])
                stream = context.wrap_socket(stream, server_hostname=server_name)
                self.assertEqual(stream.selected_alpn_protocol(), 'http/1.1')
            stream.sendall(f'GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'.encode())
            response = header(stream)
            self.assertTrue(response.startswith(b'HTTP/1.1 200 OK\r\n'))
            length = next(int(line.split(b':', 1)[1]) for line in response.split(b'\r\n')
                          if line.lower().startswith(b'content-length:'))
            self.assertEqual(exact(stream, length), BODY + b':' + path.encode())
            if tls:
                stream = stream.unwrap()
            stream.shutdown(socket.SHUT_WR)
            self.assertEqual(stream.recv(1), b'')
        finally:
            stream.close()

    def idle(self, failures=0):
        deadline = time.monotonic() + 5
        while True:
            result = self.core.command(op='snapshot', handle=self.handle)['status']
            if result['active'] == 0 or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        self.assertEqual(result['active'], 0, result)
        self.assertEqual(result['failed'], failures, result)
        return result

    def test_imported_six_protocols_reach_independent_http_and_verified_https(self):
        for protocol in ('http', 'socks4', 'socks4a', 'socks5', 'ss', 'vless'):
            with self.subTest(protocol=protocol):
                peer = self.relay(protocol, protocol)
                self.start(self.imported([peer]))
                host = '127.0.0.1' if protocol == 'socks4' else 'localhost'
                self.fetch(host, '/' + protocol)
                self.fetch(host, '/' + protocol + '-tls', tls=True)
                self.assertEqual(len(peer.connections), 2)
                self.assertEqual([c['port'] for c in peer.connections], [self.http.port, self.https.port])
                self.assertTrue(all(c['upload'] and c['download'] for c in peer.connections))
                status = self.idle()
                self.assertGreater(status['upload'], 0)
                self.assertGreater(status['download'], 0)
                self.assertTrue(self.core.command(op='stop', handle=self.handle)['ok'])
        self.assertEqual(len(self.http.requests), 6)
        self.assertEqual(len(self.https.requests), 6)
        self.assertEqual(self.https.sni, ['localhost'] * 6)
        self.assertEqual(self.https.tls_closed, 6)

    def test_ss_uri_and_base64_all_aead_ciphers(self):
        for cipher in ('aes-128-gcm', 'aes-256-gcm', 'chacha20-ietf-poly1305'):
            peer = self.relay('ss', cipher, cipher=cipher)
            for fmt in ('uri', 'base64'):
                with self.subTest(cipher=cipher, format=fmt):
                    self.start(self.imported([peer], fmt))
                    self.fetch(path='/' + cipher + '-' + fmt)
                    self.idle()
                    self.assertTrue(self.core.command(op='stop', handle=self.handle)['ok'])
            self.assertEqual(len(peer.connections), 2)
        self.assertEqual(len(self.http.requests), 6)

    def test_switch_uses_b_for_new_sessions_and_keeps_existing_a(self):
        a, b = self.relay('ss', 'A'), self.relay('socks5', 'B')
        config = self.imported([a, b])
        self.start(config)
        with self.tunnel('localhost', self.echo.port) as old:
            old.sendall(b'before-switch')
            self.assertEqual(exact(old, 13), b'before-switch')
            self.assertEqual(len(a.connections), 1)
            self.assertEqual(len(b.connections), 0)
            self.assertTrue(self.core.command(op='select', handle=self.handle, id='B')['ok'])
            self.fetch(path='/new-b')
            old.sendall(b'after-switch')
            self.assertEqual(exact(old, 12), b'after-switch')
            old.shutdown(socket.SHUT_WR)
            self.assertEqual(exact(old, len(TAIL)), TAIL)
            self.assertEqual(old.recv(1), b'')
        self.assertEqual(len(a.connections), 1)
        self.assertEqual(len(b.connections), 1)
        self.assertEqual(a.connections[0]['upload'], 25)
        self.assertFalse(self.core.command(op='select', handle=self.handle, id='missing')['ok'])
        changed = copy.deepcopy(config)
        changed['selected'] = 'missing'
        self.assertFalse(self.core.command(op='configure', handle=self.handle, config=changed)['ok'])
        self.fetch(path='/still-b')
        self.assertEqual(len(a.connections), 1)
        self.assertEqual(len(b.connections), 2)
        self.assertEqual(self.idle()['selected'], 'B')

    def test_ordered_runtime_routes_use_imported_nodes_direct_reject_and_group(self):
        a, b = self.relay('http', 'A'), self.relay('ss', 'B')
        config = self.imported([a, b])
        config['nodes'] += [{'id': 'direct', 'outbound': {'type': 'direct'}},
                            {'id': 'reject', 'outbound': {'type': 'reject'}}]
        config['selectors'] = [{'id': 'manual', 'members': ['A', 'B'], 'selected': 'B'}]
        config['rules'] = [
            {'matcher': {'type': 'domain', 'value': 'denied.fixture.invalid'}, 'outbound': 'reject'},
            {'matcher': {'type': 'domain', 'value': 'a.fixture.invalid'}, 'outbound': 'A'},
            {'matcher': {'type': 'domain_suffix', 'value': 'suffix.fixture.invalid'}, 'outbound': 'B'},
            {'matcher': {'type': 'domain_keyword', 'value': 'keyword'}, 'outbound': 'A'},
            {'matcher': {'type': 'cidr', 'value': '127.0.0.0/8'}, 'outbound': 'direct'},
            {'matcher': {'type': 'cidr', 'value': '::1/128'}, 'outbound': 'reject'},
            {'matcher': {'type': 'destination_port', 'value': self.https.port}, 'outbound': 'B'},
            {'matcher': {'type': 'match'}, 'outbound': 'manual'},
        ]
        self.start(config)
        for host, identity in [('a.fixture.invalid', 'A'), ('nested.suffix.fixture.invalid', 'B'),
                               ('keyword.fixture.invalid', 'A'), ('final.fixture.invalid', 'B')]:
            before = (len(a.connections), len(b.connections))
            self.fetch(host=host, path='/' + identity)
            self.assertEqual((len(a.connections), len(b.connections)),
                             (before[0] + (identity == 'A'), before[1] + (identity == 'B')))
        before = (len(a.connections), len(b.connections))
        self.fetch(host='127.0.0.1', path='/direct')
        self.assertEqual((len(a.connections), len(b.connections)), before)
        origin_before = len(self.http.requests)
        for host in ('denied.fixture.invalid', '::1'):
            with self.assertRaises((ConnectionError, EOFError)):
                self.fetch(host=host)
        self.assertEqual(len(self.http.requests), origin_before)
        self.assertEqual((len(a.connections), len(b.connections)), before)
        self.fetch(path='/port-rule', tls=True)
        self.assertEqual(len(b.connections), before[1] + 1)
        self.assertTrue(self.core.command(op='select_group', handle=self.handle, id='manual', member='A')['ok'])
        self.fetch(host='final.fixture.invalid', path='/group-a')
        self.assertEqual(len(a.connections), before[0] + 1)
        # Source rules run through the same immutable runtime plan. Imported
        # document rule/name translation is separately covered by the Qt menu.
        config['rules'] = [{'matcher': {'type': 'source_cidr', 'value': '127.0.0.0/8'}, 'outbound': 'B'},
                           {'matcher': {'type': 'match'}, 'outbound': 'reject'}]
        self.assertTrue(self.core.command(op='configure', handle=self.handle, config=config)['ok'])
        self.fetch(path='/source-b')
        self.assertEqual(len(b.connections), before[1] + 2)
        self.idle(failures=2)

    def test_wrong_authentication_never_reaches_origin_or_another_exit(self):
        spare = self.relay('http', 'spare')
        for protocol in ('http', 'socks5', 'ss', 'vless'):
            with self.subTest(protocol=protocol):
                bad = self.relay(protocol, 'bad')
                node = bad.node()
                if protocol == 'vless':
                    node['uuid'] = '11112233-4455-6677-8899-aabbccddeeff'
                else:
                    node['password'] = 'incorrect-synthetic-password'
                parsed = self.inspect(json.dumps({'proxies': [node]}))
                self.assertIsNotNone(parsed['tcpCandidates'][0])
                config = self.imported([spare])
                config['nodes'].append({'id': 'bad', 'outbound': parsed['tcpCandidates'][0]})
                config['selected'] = 'bad'
                self.start(config)
                with self.assertRaises((ConnectionError, EOFError, OSError)):
                    self.fetch(path='/must-not-arrive')
                self.idle(failures=1)
                self.assertEqual(len(self.http.requests), 0)
                self.assertEqual(spare.connections, [])
                self.assertEqual(bad.connections, [])
                self.assertEqual(bad.denied, ['Authentication'])
                self.assertTrue(self.core.command(op='stop', handle=self.handle)['ok'])

    def test_verified_origin_tls_rejects_wrong_name_without_http_request(self):
        peer = self.relay('ss', 'A')
        self.start(self.imported([peer]))
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.fetch(tls=True, server_name='wrong.fixture.invalid')
        self.assertEqual(self.https.requests, [])
        self.assertEqual(self.https.sni, ['wrong.fixture.invalid'])
        self.assertEqual(len(peer.connections), 1)

    def test_unsupported_security_and_transports_are_retained_and_cannot_start(self):
        peer = self.relay('vless', 'A')
        for extra in ({'reality-opts': {'public-key': 'synthetic-public-key', 'short-id': 'ab'}},
                      {'tls': True, 'flow': 'xtls-rprx-vision'},
                      {'network': 'grpc', 'grpc-opts': {'grpc-service-name': 'synthetic'}},
                      {'network': 'xhttp', 'xhttp-opts': {'path': '/preserve'}},
                      {'network': None}, {'future-security': {'enabled': False, 'key': None}}):
            with self.subTest(fields=list(extra)):
                node = {**peer.node(), **extra}
                raw = json.dumps({'proxies': [node]})
                result = self.inspect(raw)
                self.assertTrue(result['report']['parsed'])
                self.assertEqual(result['nodes'][0], node)
                self.assertEqual(result['tcpCandidates'], [None])
                self.assertFalse(result['report']['nodes'][0]['real_network_verified'])
                # Passing the unrepresentable conversion through the real ABI
                # must not replace it with a default outbound or a listener.
                rejected = self.core.command(op='start', config={
                    'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'A',
                    'nodes': [{'id': 'A', 'outbound': result['tcpCandidates'][0]}]})
                self.assertFalse(rejected['ok'])
        self.assertEqual(peer.connections, [])
        self.assertEqual(self.http.requests, [])
        self.assertEqual(self.https.requests, [])

    def test_large_fragmented_concurrent_halfclose_and_cancel(self):
        peer = self.relay('ss', 'A', cipher='chacha20-ietf-poly1305')
        self.start(self.imported([peer], 'base64'))

        def exchange(index):
            payload = random.Random(index).randbytes(256 * 1024 + 17)
            with self.tunnel('localhost', self.echo.port) as stream:
                offset = 0
                randomizer = random.Random(index + 51)
                while offset < len(payload):
                    size = min(randomizer.randint(1, 7919), len(payload) - offset)
                    part = payload[offset:offset + size]
                    stream.sendall(part)
                    self.assertEqual(exact(stream, len(part)), part)
                    offset += size
                stream.shutdown(socket.SHUT_WR)
                self.assertEqual(exact(stream, len(TAIL)), TAIL)
                self.assertEqual(stream.recv(1), b'')

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(exchange, range(6)))
        status = self.idle()
        self.assertEqual(status['accepted'], 6)
        self.assertEqual(peer.upload, 6 * (256 * 1024 + 17))
        self.assertEqual(sum(map(len, self.echo.payloads)), peer.upload)
        self.assertEqual(status['upload'], peer.upload)
        self.assertEqual(status['download'], peer.download)
        with self.tunnel('localhost', self.echo.port) as stream:
            stream.sendall(b'cancel-after-authenticated-response')
            self.assertEqual(exact(stream, 35), b'cancel-after-authenticated-response')
            self.assertTrue(self.core.command(op='stop', handle=self.handle)['ok'])
            self.assertEqual(stream.recv(1), b'')


@unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'),
                     'Windows Qt/DPAPI integration executable required')
class ProductQtIntegration(ChainBase):
    client_closes_tls = True

    def test_actual_product_import_persist_select_route_and_recreate(self):
        for protocol in ('http', 'socks5', 'ss', 'vless'):
            with self.subTest(protocol=protocol):
                a, b = self.relay(protocol, 'A'), self.relay(protocol, 'B')
                document = {'proxies': [a.node(), b.node()],
                            'proxy-groups': [{'name': 'choice', 'type': 'select', 'proxies': ['A', 'B']}],
                            'rules': ['DOMAIN,a.product.invalid,A',
                                      'DOMAIN,b.product.invalid,B',
                                      'DOMAIN,choice.product.invalid,choice',
                                      'DOMAIN,denied.product.invalid,REJECT',
                                      'IP-CIDR,127.0.0.1/32,DIRECT,no-resolve',
                                      'DOMAIN-SUFFIX,suffix.product.invalid,B',
                                      'DOMAIN-KEYWORD,keyword,A',
                                      f'DST-PORT,{self.http.port},B', 'MATCH,REJECT']}
                case = Path(self.folder.name) / protocol
                case.mkdir()
                fixture = {'subscription': json.dumps(document), 'http_port': self.http.port,
                           'https_port': self.https.port, 'stream_port': self.echo.port,
                           'ca_pem': self.ca_pem, 'expected_body': BODY.decode()}
                path = case / 'fixture.json'
                path.write_text(json.dumps(fixture), encoding='utf-8')
                log = case / 'qt.log'
                env = {**os.environ, 'SWIRL_PRODUCT_FIXTURE': str(path)}
                before = (len(self.http.requests), len(self.https.requests), len(self.https.sni),
                          self.https.tls_closed)
                result = subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'],
                                         'subscriptionProductChainAgainstIndependentPeer',
                                         '-o', str(log) + ',txt'], env=env, text=True,
                                        capture_output=True, timeout=90)
                output = log.read_text(encoding='utf-8') if log.exists() else ''
                evidence = os.environ.get('SWIRL_PRODUCT_EVIDENCE')
                if evidence:
                    folder = Path(evidence)
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / ('qt-' + protocol + '.log')).write_text(
                        output + result.stdout + result.stderr, encoding='utf-8')
                self.assertEqual(result.returncode, 0, output + result.stdout + result.stderr)
                self.assertNotIn('SKIP', output)
                expected_paths = {'/selected-a', '/selected-b', '/restored-b',
                                  '/rule-a', '/rule-b', '/rule-choice', '/rule-direct',
                                  '/rule-suffix', '/rule-keyword', '/rule-port'}
                actual_paths = [request.split(b' ')[1].decode() for request in self.http.requests[before[0]:]]
                self.assertCountEqual(actual_paths, expected_paths)
                self.assertEqual([request.split(b' ')[1] for request in self.https.requests[before[1]:]],
                                 [b'/selected-a-tls'])
                self.assertEqual(self.https.sni[before[2]:], ['localhost', 'wrong.fixture.invalid'])
                deadline = time.monotonic() + 2
                while self.https.tls_closed == before[3] and not self.https.errors and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertEqual(self.https.tls_closed - before[3], 1)
                for peer, paths in [(a, ['/selected-a', '/rule-a', '/rule-choice', '/rule-keyword']),
                                    (b, ['/selected-b', '/restored-b', '/rule-b',
                                         '/rule-suffix', '/rule-port'])]:
                    observed = [event['prefix'].split(b' ')[1].decode() for event in peer.connections
                                if event['prefix'].startswith(b'GET ')]
                    self.assertCountEqual(observed, paths)
                    self.assertTrue(all(event['host'] != 'denied.product.invalid' for event in peer.connections))
                self.assertEqual([event['port'] for event in a.connections].count(self.echo.port), 1)
                self.assertEqual([event['port'] for event in b.connections].count(self.echo.port), 0)
                self.assertEqual(len(a.connections), 6)
                self.assertEqual(len(b.connections), 6)
                if evidence:
                    report = {'protocol': protocol, 'origin_http_paths': actual_paths,
                              'origin_https_sni': self.https.sni[before[2]:],
                              'origin_https_tls_closed': self.https.tls_closed - before[3],
                              'origin_errors': {'http': self.http.errors, 'https': self.https.errors,
                                                'echo': self.echo.errors},
                              'peers': [{key: value for key, value in event.items() if key != 'prefix'}
                                        for peer in (a, b) for event in peer.connections]}
                    (Path(evidence) / ('peers-' + protocol + '.json')).write_text(
                        json.dumps(report, indent=2) + '\n', encoding='utf-8')


class EvidenceStream:
    def __init__(self, primary, record):
        self.primary, self.record = primary, record

    def write(self, data):
        self.primary.write(data)
        self.record.write(data)

    def flush(self):
        self.primary.flush()
        self.record.flush()


if __name__ == '__main__':
    import sys
    evidence = os.environ.get('SWIRL_PRODUCT_EVIDENCE')
    log = io.StringIO()
    runner = unittest.TextTestRunner(stream=EvidenceStream(sys.stderr, log), verbosity=2)
    program = unittest.main(testRunner=runner, exit=False)
    result = program.result
    if evidence:
        folder = Path(evidence)
        folder.mkdir(parents=True, exist_ok=True)
        # Keep the actual traceback even if a required executable vanished or
        # source-identity collection fails after the test runner has finished.
        (folder / 'tests.log').write_text(log.getvalue(), encoding='utf-8')
        root = Path(__file__).resolve().parents[2]
        source = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                                text=True, capture_output=True, check=True).stdout.strip()
        changes = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'],
                                 cwd=root, text=True, capture_output=True,
                                 check=True).stdout.splitlines()
        binaries = {}
        for key in ('SWIRL_RUST_HARNESS', 'SWIRL_RUST_INSPECTOR', 'SWIRL_RUST_QT_TESTS'):
            if os.environ.get(key):
                path = Path(os.environ[key])
                binaries[key] = {'filename': path.name, 'available': path.is_file()}
                if path.is_file():
                    binaries[key]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        report = {'source_sha': source, 'platform': sys.platform, 'binaries': binaries,
                  'tracked_worktree_changes': changes,
                  'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                  'skipped': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
                  'success': result.wasSuccessful(),
                  'scope': 'Rust test-host JSON persistence; only ProductQtIntegration uses product Qt/DPAPI'}
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
