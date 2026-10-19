"""Native policy integration against independent loopback HTTP/TLS/proxy peers.

Every tunnel terminates at a fixture port. No provider, public resolver, system
proxy, private configuration or complete third-party proxy core is involved.
"""
from contextlib import ExitStack
import base64
import copy
import errno
import json
import os
import select
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import threading
from threading import Thread as PairThread
import time
import unittest
from unittest import mock

from loopback_ports import windows_candidates
from test_rust_core import certificates, exact, header, target
from test_shadowsocks import PASSWORD, Reader as SsReader, Writer as SsWriter, cipher_key


class FixtureServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = 64

    def handle_error(self, request, address):
        self.errors.append('independent policy fixture assertion failed')


class HttpOrigin:
    def __init__(self, context=None, mode='normal'):
        self.context, self.mode = context, mode
        self.requests, self.errors = [], []
        self.active = self.peak = 0
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.redirect = None
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream = self.request
                stream.settimeout(4)
                try:
                    if context:
                        stream = context.wrap_socket(stream, server_side=True)
                    request = header(stream)
                    with owner.lock:
                        owner.requests.append(request)
                        owner.active += 1
                        owner.peak = max(owner.peak, owner.active)
                    try:
                        assert request.startswith(b'GET /health HTTP/1.1\r\n'), request[:60]
                        fields = {line.split(b':', 1)[0].lower(): line.split(b':', 1)[1].strip()
                                  for line in request.split(b'\r\n')[1:] if line}
                        assert fields[b'user-agent'] == b'Swirl-Core-Health/1'
                        assert fields[b'connection'] == b'close'
                        assert not ({b'authorization', b'proxy-authorization', b'cookie'} & fields.keys())
                        if owner.mode == 'stall':
                            while not owner.closed.is_set():
                                readable, _, _ = select.select([stream], [], [], 0.05)
                                if readable and not stream.recv(1024):
                                    return
                            return
                        if owner.mode == 'redirect':
                            response = f'HTTP/1.1 302 Found\r\nLocation: {owner.redirect}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'.encode()
                        else:
                            response = b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'
                        stream.sendall(response)
                        if isinstance(stream, ssl.SSLSocket):
                            with stream.unwrap() as plain:
                                plain.shutdown(socket.SHUT_WR)
                                plain.recv(1)
                        else:
                            stream.shutdown(socket.SHUT_WR)
                            stream.recv(1)
                    finally:
                        with owner.lock:
                            owner.active -= 1
                except (EOFError, OSError, ssl.SSLError):
                    pass
                finally:
                    stream.close()

        self.server = FixtureServer(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def close(self):
        self.closed.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.errors, self.errors


class EchoOrigin:
    def __init__(self):
        self.requests, self.errors = [], []
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(4)
                try:
                    while data := self.request.recv(65536):
                        owner.requests.append(data)
                        self.request.sendall(data)
                except OSError:
                    pass

        self.server = FixtureServer(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,
                         kwargs={'poll_interval': 0.02}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        assert not self.errors, self.errors


class ProxyPeer:
    """A separately implemented HTTP CONNECT relay, restricted to fixture ports."""
    def __init__(self, health_port, allowed_ports, delay=0.0, context=None):
        self.health_port, self.allowed_ports = health_port, set(allowed_ports)
        self.delay, self.context = delay, context
        self.healthy, self.fail_application = True, False
        self.health_tunnels = self.application_tunnels = 0
        self.application_payloads, self.errors = [], []
        self.closed = threading.Event()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream = self.request
                stream.settimeout(4)
                try:
                    if context:
                        stream = context.wrap_socket(stream, server_side=True)
                    request = header(stream)
                    method, authority, version = request.split(b'\r\n', 1)[0].split(b' ')
                    assert method == b'CONNECT' and version == b'HTTP/1.1'
                    host, raw_port = authority.decode().rsplit(':', 1)
                    port = int(raw_port)
                    assert host in ('localhost', '127.0.0.1', 'wrong.example.test')
                    assert port in owner.allowed_ports
                    expected = b'Proxy-Authorization: Basic ' + base64.b64encode(b'policy-user:policy-password')
                    assert expected in request
                    is_health = port == owner.health_port
                    if is_health:
                        owner.health_tunnels += 1
                        if not owner.healthy:
                            stream.sendall(b'HTTP/1.1 502 Unavailable\r\n\r\n')
                            return
                        if owner.closed.wait(owner.delay):
                            return
                    else:
                        owner.application_tunnels += 1
                        if owner.fail_application:
                            stream.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                            owner.application_payloads.append(header(stream))
                            # The application request has been consumed. It must
                            # never be replayed through another healthy member.
                            return
                    with socket.create_connection(('127.0.0.1', port), timeout=4) as upstream:
                        stream.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                        readers = [stream, upstream]
                        while readers and not owner.closed.is_set():
                            readable, _, _ = select.select(readers, [], [], 0.05)
                            for source in readable:
                                destination = upstream if source is stream else stream
                                data = source.recv(65536)
                                if data:
                                    destination.sendall(data)
                                else:
                                    readers.remove(source)
                                    try:
                                        destination.shutdown(socket.SHUT_WR)
                                    except OSError:
                                        pass
                except (EOFError, OSError, ssl.SSLError):
                    pass
                finally:
                    stream.close()

        self.server = FixtureServer(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,
                         kwargs={'poll_interval': 0.02}, daemon=True).start()

    def outbound(self, ca=None):
        result = {'type': 'http_connect', 'host': '127.0.0.1', 'port': self.port,
                  'auth': {'username': 'policy-user', 'password': 'policy-password'}}
        if self.context:
            result['tls'] = {'server_name': 'localhost', 'ca_der_base64': ca}
        return result

    def close(self):
        self.closed.set()
        self.server.shutdown()
        self.server.server_close()
        assert not self.errors, self.errors


class PolicyDatagramServer(socketserver.ThreadingUDPServer):
    daemon_threads = True

    def handle_error(self, request, address):
        self.errors.append('independent policy UDP fixture assertion failed')


class UdpPolicyOrigin:
    """An actual UDP destination; its marker proves which target replied."""
    def __init__(self, marker):
        self.marker, self.requests, self.errors = marker, [], []
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                data, stream = self.request
                owner.requests.append(data)
                stream.sendto(owner.marker + data, self.client_address)

        self.server = PolicyDatagramServer(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        assert not self.errors, self.errors


class SsPolicyPeer:
    """Independent SS AEAD TCP health and UDP forwarding on one fixture port.

    A health failure changes only subsequent TCP probe responses. UDP remains
    available so the test can distinguish an existing association's pinned
    policy choice from the automatic group's new choice.
    """
    def __init__(self, method, health_port, udp_ports):
        self.method, self.health_port = method, health_port
        self.udp_ports = set(udp_ports)
        self.healthy, self.health_tunnels = True, 0
        self.health_requests, self.datagrams, self.errors = [], [], []
        owner = self

        class PlaintextReader:
            def __init__(self, stream):
                self.reader, self.buffer = SsReader(stream, owner.method), b''

            def recv(self, size):
                while not self.buffer:
                    self.buffer = self.reader.chunk()
                data, self.buffer = self.buffer[:size], self.buffer[size:]
                return data

        class TcpHandler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                try:
                    plaintext = PlaintextReader(self.request)
                    host, port = target(plaintext)
                    assert host in ('localhost', '127.0.0.1') and port == owner.health_port
                    request = header(plaintext)
                    assert request.startswith(b'GET /health HTTP/1.1\r\n')
                    owner.health_tunnels += 1
                    owner.health_requests.append((host, port, request))
                    if owner.healthy:
                        # Forward the genuine probe to the existing independent
                        # HTTP origin; do not synthesize a successful health mark.
                        with socket.create_connection(('127.0.0.1', port), timeout=3) as upstream:
                            upstream.sendall(request)
                            upstream.shutdown(socket.SHUT_WR)
                            response = b''
                            while data := upstream.recv(4096):
                                response += data
                                assert len(response) < 16384
                    else:
                        response = b'HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                    writer = SsWriter(owner.method)
                    self.request.sendall(writer.salt + writer.chunk(response))
                    self.request.shutdown(socket.SHUT_WR)
                    self.request.recv(1)
                except (EOFError, OSError):
                    pass

        class UdpHandler(socketserver.BaseRequestHandler):
            def handle(self):
                data, stream = self.request
                salt_size = 16 if owner.method == 'aes-128-gcm' else 32
                plain = cipher_key(owner.method, data[:salt_size]).decrypt(bytes(12), data[salt_size:], None)
                assert len(plain) >= 7 and plain[0] == 1
                host, port = socket.inet_ntoa(plain[1:5]), int.from_bytes(plain[5:7], 'big')
                assert host == '127.0.0.1' and port in owner.udp_ports
                payload = plain[7:]
                owner.datagrams.append((host, port, payload))
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
                    upstream.settimeout(2)
                    upstream.connect((host, port))
                    upstream.send(payload)
                    response = upstream.recv(65535)
                salt = os.urandom(salt_size)
                packet = salt + cipher_key(owner.method, salt).encrypt(bytes(12), plain[:7] + response, None)
                stream.sendto(packet, self.client_address)

        # Let the OS reserve an available TCP port; an unexcluded random port
        # can still belong to an exclusive Windows socket and fail with 10013.
        # CPython likewise binds port zero while retaining the actual socket:
        # https://github.com/python/cpython/blob/v3.14.0/Lib/test/support/socket_helper.py
        # TCP and UDP have separate Windows exclusions. Keep rejected TCP
        # reservations until selection ends so the OS cannot return them again.
        # Both serving sockets remain held; unknown access denials still fail.
        candidates = frozenset(windows_candidates(False)) if sys.platform == 'win32' else None
        with ExitStack() as rejected_reservations:
            for attempt in range(8):
                protocol, address = 'TCP', ('127.0.0.1', 0)
                try:
                    with ExitStack() as cleanup:
                        tcp = cleanup.enter_context(FixtureServer(address, TcpHandler))
                        protocol, address = 'UDP', tcp.server_address
                        if candidates is not None and address[1] not in candidates:
                            if attempt == 7:
                                raise RuntimeError('SS policy fixture found no eligible TCP/UDP '
                                                   'port after 8 OS allocations; last reservation '
                                                   f'{address!r} is outside the Windows candidate table')
                            rejected_reservations.enter_context(tcp)
                            cleanup.pop_all()
                            continue
                        udp = cleanup.enter_context(PolicyDatagramServer(address, UdpHandler))
                        cleanup.pop_all()
                    self.tcp, self.udp = tcp, udp
                    break
                except OSError as error:
                    collision = error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) == 10048
                    if not collision or attempt == 7:
                        error.add_note(f'SS policy fixture {protocol} bind on loopback {address!r}; '
                                       f'pair attempt {attempt + 1}/8')
                        raise
        self.port = self.tcp.server_address[1]
        self.threads = []
        for server in (self.tcp, self.udp):
            server.errors = self.errors
            thread = PairThread(target=server.serve_forever,
                                      kwargs={'poll_interval': 0.02}, daemon=True)
            thread.start()
            self.threads.append(thread)

    def outbound(self):
        return {'type': 'shadowsocks', 'host': '127.0.0.1', 'port': self.port,
                'cipher': self.method, 'password': PASSWORD, 'udp': True}

    def close(self):
        for server in (self.tcp, self.udp):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(2)
        assert not self.errors, self.errors


class SsPolicyPeerAllocationTests(unittest.TestCase):
    def setUp(self):
        # These cases exercise allocation error handling, not network traffic.
        # Keep real socket descriptors for the cleanup assertions, but isolate
        # bind/listen/thread effects from Windows reservations and other peers.
        # CPython uses the same scoped-effect approach for bind-error tests:
        # https://github.com/python/cpython/blob/v3.14.0/Lib/test/test_asyncio/test_unix_events.py
        self.candidate_port = 50789

        def bind(server):
            if server.socket_type == socket.SOCK_STREAM:
                self.assertEqual(server.server_address[1], 0)
                server.server_address = (server.server_address[0], self.candidate_port)

        for patcher in (
                mock.patch(__name__ + '.windows_candidates', return_value=(self.candidate_port,)),
                mock.patch.object(socketserver.TCPServer, 'server_bind', autospec=True, side_effect=bind),
                mock.patch.object(socketserver.TCPServer, 'server_activate', autospec=True),
                mock.patch.object(socketserver.BaseServer, 'shutdown', autospec=True),
                mock.patch(__name__ + '.PairThread')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pair_retries_only_collisions_and_releases_failed_sockets(self):
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            for windows in (False, True):
                for fail_count in (1, 7):
                    with self.subTest(failing_kind=failing_kind, windows=windows, fail_count=fail_count):
                        created, requested, rejected = [], [], []
                        failure = OSError(errno.EINVAL if windows else errno.EADDRINUSE,
                                          'controlled bind collision')
                        if windows:
                            failure.winerror = 10048

                        def bind(server):
                            created.append(server)
                            requested.append((server.socket_type, server.server_address[1]))
                            if server.socket_type == failing_kind and len(rejected) < fail_count:
                                rejected.append(server)
                                raise failure
                            original(server)

                        with mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                            peer = SsPolicyPeer('aes-128-gcm', 443, (53,))
                        try:
                            self.assertEqual(len(rejected), fail_count)
                            self.assertEqual(requested[-2:], [(socket.SOCK_STREAM, 0),
                                                             (socket.SOCK_DGRAM, peer.port)])
                            self.assertEqual(peer.tcp.server_address, peer.udp.server_address)
                            self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                            for server in (peer.tcp, peer.udp):
                                self.assertNotEqual(server.socket.fileno(), -1)
                                self.assertFalse(server.allow_reuse_address)
                                self.assertFalse(server.allow_reuse_port)
                        finally:
                            peer.close()
                        self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_stops_after_eight_collisions_with_original_error(self):
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            for windows in (False, True):
                with self.subTest(failing_kind=failing_kind, windows=windows):
                    created, rejected = [], []

                    def bind(server):
                        created.append(server)
                        if server.socket_type == failing_kind:
                            failure = OSError(errno.EINVAL if windows else errno.EADDRINUSE,
                                              f'controlled collision {len(rejected) + 1}')
                            if windows:
                                failure.winerror = 10048
                            rejected.append(failure)
                            raise failure
                        original(server)

                    with mock.patch.object(socketserver.TCPServer, 'server_bind', bind), \
                            mock.patch(__name__ + '.PairThread') as thread:
                        with self.assertRaises(OSError) as caught:
                            SsPolicyPeer('aes-128-gcm', 443, (53,))
                        thread.assert_not_called()
                    self.assertIs(caught.exception, rejected[-1])
                    self.assertEqual(len(rejected), 8)
                    self.assertIn('pair attempt 8/8', caught.exception.__notes__[-1])
                    self.assertEqual(sum(server.socket_type == socket.SOCK_STREAM for server in created), 8)
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_preserves_denials_and_cleans_up_non_socket_errors(self):
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            access_denial = PermissionError(errno.EACCES, 'synthetic socket access denial')
            access_denial.winerror = 10013
            for failure in (access_denial, PermissionError(errno.EACCES, 'controlled bind denial'),
                            OSError(errno.ENOBUFS, 'controlled resource failure'),
                            RuntimeError('controlled non-socket failure')):
                with self.subTest(failing_kind=failing_kind, failure=type(failure).__name__):
                    created, rejected = [], []

                    def bind(server):
                        created.append(server)
                        if server.socket_type == failing_kind:
                            rejected.append(server.server_address)
                            raise failure
                        original(server)

                    try:
                        with mock.patch.object(socketserver.TCPServer, 'server_bind', bind), \
                                mock.patch(__name__ + '.PairThread') as thread:
                            with self.assertRaises(type(failure)) as caught:
                                SsPolicyPeer('aes-128-gcm', 443, (53,))
                            thread.assert_not_called()
                        self.assertIs(caught.exception, failure)
                        self.assertEqual(len(rejected), 1)
                        self.assertEqual(len(created), 1 if failing_kind == socket.SOCK_STREAM else 2)
                        self.assertEqual(rejected[0][1],
                                         0 if failing_kind == socket.SOCK_STREAM else self.candidate_port)
                        if isinstance(failure, OSError):
                            protocol = 'TCP' if failing_kind == socket.SOCK_STREAM else 'UDP'
                            self.assertEqual(failure.__notes__,
                                             [f'SS policy fixture {protocol} bind on loopback {rejected[0]!r}; '
                                              'pair attempt 1/8'])
                        self.assertTrue(all(server.socket.fileno() == -1 for server in created))
                    finally:
                        for server in created:
                            server.server_close()

    def test_windows_rejected_ports_stay_reserved_until_pair_is_owned(self):
        original = socketserver.TCPServer.server_bind
        for rejected_count in (1, 7):
            with self.subTest(rejected_count=rejected_count):
                created, requested = [], []

                def bind(server):
                    self.assertTrue(all(item.socket.fileno() != -1 for item in created))
                    created.append(server)
                    requested.append((server.socket_type, server.server_address[1]))
                    original(server)
                    if server.socket_type == socket.SOCK_STREAM and len(created) <= rejected_count:
                        server.server_address = ('127.0.0.1', self.candidate_port - len(created))

                with mock.patch(__name__ + '.sys.platform', 'win32'), \
                        mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                    peer = SsPolicyPeer('aes-128-gcm', 443, (53,))
                try:
                    self.assertEqual(requested, [(socket.SOCK_STREAM, 0)] * (rejected_count + 1)
                                     + [(socket.SOCK_DGRAM, self.candidate_port)])
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                    self.assertTrue(all(server.socket.fileno() != -1 for server in created[-2:]))
                    self.assertEqual(peer.tcp.server_address, peer.udp.server_address)
                finally:
                    peer.close()
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_windows_rejected_ports_exhaustion_closes_all_eight_reservations(self):
        original = socketserver.TCPServer.server_bind
        created = []

        def bind(server):
            self.assertEqual(server.socket_type, socket.SOCK_STREAM)
            self.assertTrue(all(item.socket.fileno() != -1 for item in created))
            created.append(server)
            original(server)
            server.server_address = ('127.0.0.1', self.candidate_port - len(created))

        with mock.patch(__name__ + '.sys.platform', 'win32'), \
                mock.patch.object(socketserver.TCPServer, 'server_bind', bind), \
                mock.patch(__name__ + '.PairThread') as thread:
            with self.assertRaisesRegex(RuntimeError, 'after 8 OS allocations'):
                SsPolicyPeer('aes-128-gcm', 443, (53,))
            thread.assert_not_called()
        self.assertEqual(len(created), 8)
        self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_windows_exclusion_query_failure_starts_no_sockets_or_threads(self):
        failure = subprocess.CalledProcessError(1, ['netsh', 'controlled-query'])
        with mock.patch(__name__ + '.sys.platform', 'win32'), \
                mock.patch(__name__ + '.windows_candidates', side_effect=failure), \
                mock.patch.object(socketserver.TCPServer, 'server_bind') as bind, \
                mock.patch(__name__ + '.PairThread') as thread:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                SsPolicyPeer('aes-128-gcm', 443, (53,))
            self.assertIs(caught.exception, failure)
            bind.assert_not_called()
            thread.assert_not_called()


class SsPolicyPeerReservationTests(unittest.TestCase):
    def test_os_allocation_avoids_occupied_tcp_and_holds_the_actual_pair(self):
        # Only the platform/table branch is controlled on non-Windows hosts.
        # Every bind/listen/close and the incumbent exclusive socket are real.
        candidates = windows_candidates(False) if sys.platform == 'win32' else range(1, 65536)
        original = socketserver.TCPServer.server_bind
        created, requested = [], []

        def bind(server):
            created.append(server)
            requested.append((server.socket_type, server.server_address[1]))
            if server.socket_type == socket.SOCK_STREAM:
                self.assertEqual(server.server_address[1], 0)
            else:
                tcp = created[-2]
                self.assertNotEqual(tcp.socket.fileno(), -1)
                self.assertEqual(tcp.socket.getsockname(), server.server_address)
            original(server)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as incumbent:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                incumbent.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            incumbent.bind(('127.0.0.1', 0))
            incumbent.listen(1)
            with mock.patch(__name__ + '.sys.platform', 'win32'), \
                    mock.patch(__name__ + '.windows_candidates', return_value=candidates), \
                    mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                peer = SsPolicyPeer('aes-128-gcm', 443, (53,))
            try:
                self.assertNotEqual(peer.port, incumbent.getsockname()[1])
                self.assertEqual(requested[-2:], [(socket.SOCK_STREAM, 0),
                                                 (socket.SOCK_DGRAM, peer.port)])
                self.assertEqual(peer.tcp.socket.getsockname(), peer.udp.socket.getsockname())
                self.assertEqual(peer.tcp.socket.getsockname(), ('127.0.0.1', peer.port))
                for server in (peer.tcp, peer.udp):
                    self.assertFalse(server.allow_reuse_address)
                    self.assertFalse(server.allow_reuse_port)
                    self.assertNotEqual(server.socket.fileno(), -1)
            finally:
                peer.close()
        self.assertTrue(all(server.socket.fileno() == -1 for server in created))


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class PolicyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.tls, cls.ca, _ = certificates(cls.temp.name)
        cls.tls.set_alpn_protocols(['http/1.1'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.fixtures, self.sockets = [], []
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)
        self.origin = self.fixture(EchoOrigin())

    def fixture(self, fixture):
        self.fixtures.append(fixture)
        return fixture

    def close(self):
        for stream in self.sockets:
            stream.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self.fail('policy runtime did not stop with the harness')
        finally:
            for fixture in reversed(self.fixtures):
                fixture.close()
        stderr = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, stderr)
        self.assertNotIn('policy-password', stderr)
        self.assertNotIn(self.ca, stderr)

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def status(self):
        response = self.command(op='snapshot', handle=self.handle)
        self.assertTrue(response['ok'], response)
        return response['status']

    def wait_for(self, condition, seconds=5):
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            last = self.status()
            if condition(last):
                return last
            time.sleep(0.02)
        self.fail(f'policy condition did not settle: {last}')

    def prepare(self, strategy='fallback', delays=(0, 0), https=False, **probe):
        self.health = self.fixture(HttpOrigin(self.tls if https else None))
        self.peers = [self.fixture(ProxyPeer(self.health.port,
                                           [self.health.port, self.origin.port], delay))
                      for delay in delays]
        health_probe = {'url': f'{"https" if https else "http"}://localhost:{self.health.port}/health',
                        'interval_ms': 1000, 'timeout_ms': 700, **probe}
        if https:
            health_probe['tls'] = {'server_name': 'localhost', 'alpn': ['http/1.1'],
                                   'ca_der_base64': self.ca}
        self.config = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'auto',
                       'dns': {'hosts': [{'name': 'localhost', 'address': '127.0.0.1'}]},
                       'nodes': [{'id': chr(97 + i), 'outbound': peer.outbound()}
                                 for i, peer in enumerate(self.peers)],
                       'selectors': [{'id': 'auto', 'members': [chr(97 + i) for i in range(len(self.peers))],
                                      'strategy': strategy, 'probe': health_probe}]}
        return self.config

    def start(self):
        response = self.command(op='start', config=self.config)
        self.assertTrue(response['ok'], response)
        self.handle = response['handle']
        self.port = int(response['status']['address'].rsplit(':', 1)[1])

    def healthy(self):
        return self.wait_for(lambda s: all(m['healthy'] for m in s['policies']['auto']['members']))

    def tunnel(self):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        self.sockets.append(stream)
        stream.sendall(f'CONNECT 127.0.0.1:{self.origin.port} HTTP/1.1\r\nHost: fixture\r\n\r\n'.encode())
        return stream, header(stream)

    def echo(self, stream, payload=b'policy-echo'):
        stream.sendall(payload)
        self.assertEqual(exact(stream, len(payload)), payload)

    def test_fallback_priority_and_failed_request_are_never_replayed(self):
        self.prepare(delays=(0.15, 0))
        self.start()
        self.assertEqual(self.healthy()['policies']['auto']['selected'], 'a')
        self.peers[0].fail_application = True
        stream, response = self.tunnel()
        self.assertIn(b'200', response)
        stream.sendall(b'POST /side-effect HTTP/1.1\r\nHost: fixture\r\nContent-Length: 0\r\n\r\n')
        stream.shutdown(socket.SHUT_WR)
        self.assertEqual(stream.recv(1), b'')
        self.wait_for(lambda s: s['active'] == 0)
        self.assertEqual(len(self.peers[0].application_payloads), 1)
        self.assertEqual(self.peers[1].application_tunnels, 0)
        self.assertEqual(self.origin.requests, [])
        self.assertEqual(self.status()['connections'][0]['node'], 'a')

    def test_url_test_switches_only_new_tcp_sessions(self):
        self.prepare(strategy='url_test', delays=(0.18, 0))
        self.start()
        self.assertEqual(self.healthy()['policies']['auto']['selected'], 'b')
        old, response = self.tunnel()
        self.assertIn(b'200', response)
        self.echo(old, b'old-b')
        self.peers[0].delay, self.peers[1].delay = 0, 0.20
        self.wait_for(lambda s: s['policies']['auto']['selected'] == 'a')
        new, response = self.tunnel()
        self.assertIn(b'200', response)
        self.echo(new, b'new-a')
        self.echo(old, b'still-b')
        connections = self.status()['connections']
        self.assertEqual([c['node'] for c in connections], ['b', 'a'])
        changed = copy.deepcopy(self.config)
        changed['nodes'].append({'id': 'deny', 'outbound': {'type': 'reject'}})
        changed['selected'] = 'deny'
        changed['selectors'] = []
        self.assertTrue(self.command(op='configure', handle=self.handle, config=changed)['ok'])
        self.echo(old, b'old-plan-survives')
        self.echo(new, b'new-plan-survives')
        self.assertIn(b'502', self.tunnel()[1])

    def test_round_robin_consumes_only_new_routed_sessions(self):
        self.prepare(strategy='load_balance', interval_ms=10000)
        self.start()
        self.healthy()
        for _ in range(30):
            self.assertEqual(self.status()['policies']['auto']['selected'], 'a')
        for i in range(4):
            stream, response = self.tunnel()
            self.assertIn(b'200', response)
            self.echo(stream, f'round-{i}'.encode())
            for _ in range(3):
                self.status()
        self.assertEqual([c['node'] for c in self.status()['connections']], ['a', 'b', 'a', 'b'])
        self.assertEqual([p.application_tunnels for p in self.peers], [2, 2])

    def test_all_unhealthy_fails_without_direct_fallback(self):
        self.prepare()
        for peer in self.peers:
            peer.healthy = False
        self.start()
        status = self.wait_for(lambda s: s['policies']['auto']['checks'] >= 2)
        self.assertIsNone(status['policies']['auto']['selected'])
        self.assertIn(b'502', self.tunnel()[1])
        self.assertEqual(self.wait_for(lambda s: s['failed'] == 1)['last_error'], 'NoHealthyPolicyMember')
        self.assertEqual([p.application_tunnels for p in self.peers], [0, 0])
        self.assertEqual(self.origin.requests, [])

    def test_verified_https_runs_inside_native_proxy_tunnel(self):
        self.prepare(https=True)
        self.start()
        status = self.healthy()
        self.assertTrue(all(m['latency_ms'] is not None for m in status['policies']['auto']['members']))
        self.assertGreaterEqual(len(self.health.requests), 2)
        self.assertTrue(all(p.health_tunnels >= 1 for p in self.peers))
        self.assertEqual(status['accepted'], 0)  # probes are not application sessions
        stream, response = self.tunnel()
        self.assertIn(b'200', response)
        self.echo(stream, b'verified-through-proxy')

    def test_https_untrusted_or_wrong_certificate_never_becomes_healthy(self):
        self.prepare(https=True)
        self.start()
        self.healthy()
        baseline = len(self.health.requests)
        for wrong_name in (False, True):
            with self.subTest(wrong_name=wrong_name):
                changed = copy.deepcopy(self.config)
                probe = changed['selectors'][0]['probe']
                if wrong_name:
                    probe['url'] = probe['url'].replace('localhost', 'wrong.example.test')
                    probe['tls']['server_name'] = 'wrong.example.test'
                else:
                    del probe['tls']['ca_der_base64']
                self.assertTrue(self.command(op='configure', handle=self.handle, config=changed)['ok'])
                status = self.wait_for(lambda s: s['policies']['auto']['checks'] >= 2)
                self.assertIsNone(status['policies']['auto']['selected'])
                self.assertTrue(all(m['error'] == 'TlsVerificationOrHandshake'
                                    for m in status['policies']['auto']['members']), status)
        self.assertEqual(len(self.health.requests), baseline)

    def test_https_origin_inside_verified_tls_proxy_uses_two_tls_sessions(self):
        self.prepare(https=True)
        peer = self.fixture(ProxyPeer(self.health.port, [self.health.port, self.origin.port], context=self.tls))
        self.peers = [peer]
        self.config['nodes'] = [{'id': 'a', 'outbound': peer.outbound(self.ca)}]
        self.config['selectors'][0]['members'] = ['a']
        self.start()
        status = self.healthy()
        self.assertEqual(status['policies']['auto']['selected'], 'a')
        self.assertEqual(peer.health_tunnels, 1)
        self.assertEqual(len(self.health.requests), 1)

    def test_redirect_is_unhealthy_and_target_is_never_followed(self):
        self.prepare()
        self.health.mode = 'redirect'
        self.health.redirect = f'http://127.0.0.1:{self.origin.port}/leak'
        self.start()
        status = self.wait_for(lambda s: s['policies']['auto']['checks'] >= 2)
        self.assertTrue(all(m['error'] == 'PolicyProbeStatus' for m in status['policies']['auto']['members']))
        self.assertEqual(self.origin.requests, [])
        self.assertEqual([p.application_tunnels for p in self.peers], [0, 0])

    def test_manual_selection_keeps_health_and_existing_connections(self):
        self.prepare(interval_ms=10000)
        self.config['selectors'].append({'id': 'manual', 'members': ['auto', 'a'], 'selected': 'auto'})
        self.config['selected'] = 'manual'
        self.start()
        before = self.healthy()['policies']['auto']['checks']
        old, response = self.tunnel()
        self.assertIn(b'200', response)
        self.echo(old)
        for chosen in ('a', 'auto', 'a', 'auto'):
            self.assertTrue(self.command(op='select_group', handle=self.handle, id='manual', member=chosen)['ok'])
            self.assertEqual(self.status()['policies']['auto']['checks'], before)
        rejected = self.command(op='select_group', handle=self.handle, id='auto', member='b')
        self.assertEqual(rejected, {'ok': False, 'error': 'AutomaticPolicySelection'})
        self.echo(old, b'manual-did-not-close-session')
        self.assertEqual([p.health_tunnels for p in self.peers], [1, 1])

    def test_invalid_reconfigure_is_atomic_and_does_not_probe(self):
        self.prepare(interval_ms=10000)
        self.start()
        before = self.healthy()
        old, response = self.tunnel()
        self.assertIn(b'200', response)
        for mutation in ('invalid_probe', 'cycle', 'listener', 'unknown_member'):
            changed = copy.deepcopy(self.config)
            if mutation == 'invalid_probe':
                changed['selectors'][0]['probe']['url'] = 'http://username:password@fixture/health'
            elif mutation == 'cycle':
                changed['selectors'].append({'id': 'cycle', 'members': ['cycle'], 'selected': 'cycle'})
            elif mutation == 'listener':
                changed['listen'] = '127.0.0.1:1'
            else:
                changed['selectors'][0]['members'].append('missing')
            result = self.command(op='configure', handle=self.handle, config=changed)
            self.assertFalse(result['ok'], (mutation, result))
            self.assertEqual(self.status()['generation'], before['generation'])
            self.assertEqual(self.status()['policies']['auto']['checks'], before['policies']['auto']['checks'])
            self.echo(old, mutation.encode())
        self.assertEqual([p.health_tunnels for p in self.peers], [1, 1])

    def test_saturated_probe_budget_stops_and_reconfigure_does_not_leak(self):
        self.prepare(delays=(0,) * 12, timeout_ms=700)
        self.health.mode = 'stall'
        self.start()
        deadline = time.monotonic() + 3
        while self.health.active < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.health.active, 4)
        self.assertEqual(self.health.peak, 4)
        # Reconfigure while four old-generation probes are still waiting. The
        # new DIRECT plan has no implicit probes and old tasks must be canceled.
        changed = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'direct',
                   'nodes': [{'id': 'direct', 'outbound': {'type': 'direct'}}]}
        self.assertTrue(self.command(op='configure', handle=self.handle, config=changed)['ok'])
        deadline = time.monotonic() + 2
        while self.health.active and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.health.active, 0)
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])
        count = sum(peer.health_tunnels for peer in self.peers)
        time.sleep(1.05)  # One full configured interval proves there is no worker left.
        self.assertEqual(sum(peer.health_tunnels for peer in self.peers), count)
        self.assertEqual(self.health.active, 0)

    def test_udp_association_pins_distinct_ss_exit_across_health_and_configure(self):
        self.health = self.fixture(HttpOrigin())
        destinations = [self.fixture(UdpPolicyOrigin(marker)) for marker in (b'one:', b'two:', b'three:')]
        self.peers = [self.fixture(SsPolicyPeer(method, self.health.port, [d.port for d in destinations]))
                      for method in ('aes-128-gcm', 'chacha20-ietf-poly1305')]
        self.config = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'auto',
                       'dns': {'hosts': [{'name': 'localhost', 'address': '127.0.0.1'}]},
                       'nodes': [{'id': name, 'outbound': peer.outbound()}
                                 for name, peer in zip(('a', 'b'), self.peers)],
                       'selectors': [{'id': 'auto', 'members': ['a', 'b'], 'strategy': 'fallback',
                                      'probe': {'url': f'http://localhost:{self.health.port}/health',
                                                'interval_ms': 1000, 'timeout_ms': 700}}]}
        self.start()
        self.assertEqual(self.healthy()['policies']['auto']['selected'], 'a')
        self.assertTrue(all(peer.health_tunnels >= 1 for peer in self.peers))
        self.assertGreaterEqual(len(self.health.requests), 2)

        def associate():
            control = socket.create_connection(('127.0.0.1', self.port), timeout=3)
            self.sockets.append(control)
            control.sendall(b'\x05\x01\x00')
            self.assertEqual(exact(control, 2), b'\x05\x00')
            control.sendall(b'\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00')
            response = exact(control, 10)
            self.assertEqual(response[:4], b'\x05\x00\x00\x01')
            relay = (socket.inet_ntoa(response[4:8]), int.from_bytes(response[8:], 'big'))
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sockets.append(client)
            client.bind(('127.0.0.1', 0))
            client.settimeout(2)
            return client, relay

        def exchange(association, destination, payload, chosen):
            client, relay = association
            address = b'\x01\x7f\x00\x00\x01' + destination.port.to_bytes(2, 'big')
            counts = [len(peer.datagrams) for peer in self.peers]
            client.sendto(b'\x00\x00\x00' + address + payload, relay)
            response, sender = client.recvfrom(4096)
            self.assertEqual(sender, relay)
            self.assertEqual(response, b'\x00\x00\x00' + address + destination.marker + payload)
            counts[chosen] += 1
            self.assertEqual([len(peer.datagrams) for peer in self.peers], counts)
            self.assertEqual(self.peers[chosen].datagrams[-1], ('127.0.0.1', destination.port, payload))

        old_a = associate()
        exchange(old_a, destinations[0], b'initial-a', 0)
        self.peers[0].healthy = False
        status = self.wait_for(lambda s: s['policies']['auto']['selected'] == 'b'
                               and not s['policies']['auto']['members'][0]['healthy'])
        self.assertEqual(status['policies']['auto']['members'][0]['error'], 'PolicyProbeStatus')
        exchange(old_a, destinations[0], b'old-a-same-destination', 0)
        # A previously unseen destination rules out merely reusing an existing
        # per-target UDP socket after the live automatic policy has changed.
        exchange(old_a, destinations[1], b'old-a-new-destination', 0)
        old_b = associate()
        exchange(old_b, destinations[0], b'new-b', 1)

        replacement = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'deny',
                       'nodes': [{'id': 'deny', 'outbound': {'type': 'reject'}}]}
        result = self.command(op='configure', handle=self.handle, config=replacement)
        self.assertTrue(result['ok'], result)
        # Both old associations retain their different choices even though the
        # current plan no longer contains either node or the automatic group.
        exchange(old_a, destinations[2], b'old-a-after-configure', 0)
        exchange(old_b, destinations[1], b'old-b-after-configure', 1)
        counts = [len(peer.datagrams) for peer in self.peers]
        seen = [len(destination.requests) for destination in destinations]
        dropped = self.status()['udp_dropped']
        denied, relay = associate()
        denied.settimeout(0.25)
        denied.sendto(b'\x00\x00\x00\x01\x7f\x00\x00\x01'
                      + destinations[0].port.to_bytes(2, 'big') + b'new-association-denied', relay)
        self.wait_for(lambda s: s['udp_dropped'] > dropped)
        with self.assertRaises(socket.timeout):
            denied.recvfrom(4096)
        self.assertEqual([len(peer.datagrams) for peer in self.peers], counts)
        self.assertEqual([len(destination.requests) for destination in destinations], seen)
        self.assertEqual([entry[2] for entry in self.peers[0].datagrams],
                         [b'initial-a', b'old-a-same-destination', b'old-a-new-destination', b'old-a-after-configure'])
        self.assertEqual([entry[2] for entry in self.peers[1].datagrams], [b'new-b', b'old-b-after-configure'])
        self.assertEqual(self.status()['failed'], 0)

    def test_unsupported_udp_member_does_not_retry_a_direct_member(self):
        self.prepare()
        self.config['nodes'].append({'id': 'direct', 'outbound': {'type': 'direct'}})
        self.config['selectors'][0]['members'] = ['a', 'direct']
        self.start()
        self.assertEqual(self.healthy()['policies']['auto']['selected'], 'a')
        control = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        self.sockets.append(control)
        control.sendall(b'\x05\x01\x00')
        self.assertEqual(exact(control, 2), b'\x05\x00')
        control.sendall(b'\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00')
        response = exact(control, 10)
        self.assertEqual(response[:4], b'\x05\x00\x00\x01')
        relay = (socket.inet_ntoa(response[4:8]), int.from_bytes(response[8:], 'big'))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as destination, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            destination.bind(('127.0.0.1', 0))
            destination.settimeout(0.2)
            packet = b'\x00\x00\x00\x01\x7f\x00\x00\x01' + destination.getsockname()[1].to_bytes(2, 'big') + b'never-direct'
            client.sendto(packet, relay)
            self.wait_for(lambda s: s['udp_dropped'] >= 1)
            with self.assertRaises(socket.timeout):
                destination.recvfrom(1024)
        self.assertEqual(self.status()['failed'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
