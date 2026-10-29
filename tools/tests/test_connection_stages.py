"""Independent loopback evidence for native address dialing and failure stages.

Resolved-address retries must stop before TLS/authentication/application bytes.
The deterministic stalled-connect timing/cancellation cases live in Rust tests;
these peers validate actual DNS, sockets, framed SS traffic and control reports.
"""
from contextlib import contextmanager
import errno
import json
import os
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from dns_peer import DnsPeer
from loopback_ports import windows_exclusions
from test_rust_core import Reference, Handler, certificates, exact, header
from test_shadowsocks import Peer as SsPeer, Handler as SsHandler, PASSWORD


class ObservedReference(Reference):
    def process_request(self, request, address):
        self.tcp_connections += 1
        super().process_request(request, address)


class IPv6Reference(ObservedReference):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


class IPv6SsPeer(SsPeer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def reserve_dual_loopback():
    """Own both address families before starting either half of a DNS fixture."""
    excluded = (windows_exclusions(False) | windows_exclusions(True)
                if sys.platform == 'win32' else frozenset())
    if len(excluded) == 65535:
        raise RuntimeError('No unexcluded dual-family loopback fixture port')
    held, filtered, attempt = [], set(), 0
    try:
        while attempt < 8:
            ipv4 = socket.socket()
            try:
                ipv6 = socket.socket(socket.AF_INET6)
            except BaseException:
                ipv4.close()
                raise
            try:
                ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                if sys.platform == 'win32' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    for stream in (ipv4, ipv6):
                        stream.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                # Let the OS allocate and retain a free IPv4 TCP endpoint.
                ipv4.bind(('127.0.0.1', 0))
                port = ipv4.getsockname()[1]
                if port in excluded:
                    if port in filtered:
                        raise RuntimeError('OS reused a still-held excluded dual-family fixture port')
                    filtered.add(port)
                    held.append(ipv4)
                    ipv6.close()
                    # A configured reservation is not a live bind collision.
                    # Keep each rejected endpoint until the whole selection
                    # finishes; the finite exclusion set bounds these probes.
                    continue
                ipv6.bind(('::1', port))
                return ipv4, ipv6
            except OSError as error:
                ipv4.close()
                ipv6.close()
                # Retry setup collisions only. Access denial, including an
                # unknown WSAEACCES, remains the original test failure.
                if (error.errno != errno.EADDRINUSE and
                        getattr(error, 'winerror', None) != 10048) or attempt == 7:
                    raise
                attempt += 1
            except BaseException:
                ipv4.close()
                ipv6.close()
                raise
    finally:
        for stream in held:
            stream.close()


def adopt_server(server_type, handler, stream):
    """Transfer a reservation directly; never release and rebind its port."""
    try:
        server = server_type(stream.getsockname(), handler, bind_and_activate=False)
        server.socket.close()
        server.socket = stream
        server.server_address = stream.getsockname()
        server.server_activate()
        return server
    except BaseException:
        stream.close()
        raise


class DualLoopbackAllocationTests(unittest.TestCase):
    def assert_socket_roundtrip(self, stream, marker):
        stream.listen(1)
        stream.settimeout(2)
        with socket.create_connection(stream.getsockname()[:2], timeout=2) as client:
            accepted, _ = stream.accept()
            with accepted:
                accepted.settimeout(2)
                client.sendall(marker)
                self.assertEqual(exact(accepted, len(marker)), marker)
                accepted.sendall(marker[::-1])
                self.assertEqual(exact(client, len(marker)), marker[::-1])

    @contextmanager
    def controlled_ports(self, ports, exclusions, before_bind=None):
        # Retain real descriptors for ownership assertions, but control bind
        # results to exercise long reservation blocks on every CI platform.
        native, created, requested, addresses = socket.socket, [], [], {}
        ports = iter(ports)

        def allocate(*args, **kwargs):
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        def bind(stream, address):
            requested.append((stream.family, address))
            if before_bind is not None:
                before_bind(stream, address, created)
            if stream.family == socket.AF_INET:
                self.assertEqual(address, ('127.0.0.1', 0))
                addresses[stream] = ('127.0.0.1', next(ports))
            else:
                addresses[stream] = (*address, 0, 0)

        with mock.patch(__name__ + '.sys.platform', 'win32'), \
                mock.patch(__name__ + '.windows_exclusions',
                           side_effect=lambda ipv6: exclusions[ipv6]), \
                mock.patch.object(native, 'bind', new=bind), \
                mock.patch.object(native, 'getsockname', new=lambda stream: addresses[stream]), \
                mock.patch(__name__ + '.socket.socket', side_effect=allocate):
            yield created, requested

    def allocate_with_collision(self, repeat):
        native, created = socket.socket, []
        bind = native.bind
        rejected = []

        def track(*args, **kwargs):
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        def collide(stream, address):
            if stream.family == socket.AF_INET6 and (repeat or not rejected):
                # A real exclusive incumbent may correctly produce Windows
                # 10013. Inject only a known retryable collision here; access
                # denial is covered separately and must never be reclassified.
                failure = OSError(errno.EADDRINUSE, 'controlled second-family collision')
                failure.winerror = 10048
                rejected.append(failure)
                raise failure
            return bind(stream, address)

        with mock.patch.object(native, 'bind', new=collide), \
                mock.patch(__name__ + '.socket.socket', side_effect=track):
            if repeat:
                with self.assertRaises(OSError) as caught:
                    reserve_dual_loopback()
                self.assertIs(caught.exception, rejected[-1])
                self.assertEqual(len(rejected), 8)
                self.assertTrue(all(stream.fileno() == -1 for stream in created))
            else:
                ipv4, ipv6 = reserve_dual_loopback()
                self.addCleanup(ipv4.close)
                self.addCleanup(ipv6.close)
                self.assertEqual(ipv4.getsockname()[1], ipv6.getsockname()[1])
                self.assertTrue(all(stream.fileno() == -1 for stream in created[:-2]))
                self.assertGreaterEqual(len(created), 4)

    def test_second_family_collision_releases_both_sockets_before_retry(self):
        self.allocate_with_collision(False)

    def test_collision_budget_remains_eight_and_releases_every_attempt(self):
        self.allocate_with_collision(True)

    def test_two_hundred_reservations_keep_ownership_and_leave_eight_collision_attempts(self):
        blocked = list(range(32000, 32200))
        ports = blocked + list(range(40000, 40008))
        rejected = []

        def collide(stream, address, created):
            # Each prior rejected IPv4 owner must remain live while the OS
            # allocates later ports, including all seven collision retries.
            for owner in created[:min(400, len(created) - 2):2]:
                self.assertNotEqual(owner.fileno(), -1)
            if stream.family == socket.AF_INET6 and len(rejected) < 7:
                failure = OSError(errno.EINVAL, 'controlled Windows collision')
                failure.winerror = 10048
                rejected.append(failure)
                raise failure

        excluded = (frozenset(blocked[:100]), frozenset(blocked[100:]))
        with self.controlled_ports(ports, excluded, collide) as (created, requested):
            ipv4, ipv6 = reserve_dual_loopback()
            self.addCleanup(ipv4.close)
            self.addCleanup(ipv6.close)
            self.assertEqual(ipv4.getsockname()[1], 40007)
            self.assertEqual(ipv6.getsockname()[1], 40007)
            # The configured OS dynamic range may lie outside 49152..65535.
            self.assertLess(ipv4.getsockname()[1], 49152)
        self.assertEqual(len(rejected), 7)
        self.assertEqual(sum(family == socket.AF_INET for family, _ in requested), 208)
        self.assertEqual(sum(family == socket.AF_INET6 for family, _ in requested), 8)
        self.assertTrue(all(stream.fileno() == -1 for stream in created[:-2]))
        self.assertTrue(all(stream.fileno() != -1 for stream in created[-2:]))

    def test_failure_after_reservations_closes_held_and_current_sockets(self):
        for failing_family in (socket.AF_INET, socket.AF_INET6):
            denied = PermissionError(errno.EACCES, 'controlled access denial')
            denied.winerror = 10013
            for failure in (denied, OSError(errno.ENOBUFS, 'controlled resource exhaustion'),
                            RuntimeError('controlled non-socket failure')):
                with self.subTest(family=failing_family, failure=type(failure).__name__):
                    rejected = []

                    def fail(stream, address, created):
                        if len(created) == 8 and stream.family == failing_family:
                            self.assertTrue(all(owner.fileno() != -1 for owner in created[:6:2]))
                            rejected.append(address)
                            raise failure

                    excluded = (frozenset(range(32000, 32003)), frozenset())
                    with self.controlled_ports([32000, 32001, 32002, 40000], excluded, fail) as (created, _):
                        with self.assertRaises(type(failure)) as caught:
                            reserve_dual_loopback()
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(len(rejected), 1)
                    self.assertEqual(len(created), 8)
                    self.assertTrue(all(stream.fileno() == -1 for stream in created))

    def test_repeated_held_excluded_port_fails_and_closes_every_socket(self):
        excluded = (frozenset({32000}), frozenset())
        with self.controlled_ports([32000, 32000], excluded) as (created, requested):
            with self.assertRaisesRegex(RuntimeError, 'still-held excluded'):
                reserve_dual_loopback()
        self.assertEqual(len(created), 4)
        self.assertEqual(len(requested), 2)
        self.assertTrue(all(stream.fileno() == -1 for stream in created))

    def test_windows_exclusive_and_ipv6_only_options_precede_binds(self):
        ipv4, ipv6, calls = mock.Mock(), mock.Mock(), []
        ipv4.getsockname.return_value = ('127.0.0.1', 40000)
        for label, stream in (('ipv4', ipv4), ('ipv6', ipv6)):
            stream.setsockopt.side_effect = lambda level, name, value, label=label: calls.append(
                (label, level, name, value))
            stream.bind.side_effect = lambda address, label=label: calls.append((label, address))
        with mock.patch(__name__ + '.sys.platform', 'win32'), \
                mock.patch.object(socket, 'SO_EXCLUSIVEADDRUSE', 12345, create=True), \
                mock.patch(__name__ + '.windows_exclusions', return_value=frozenset()), \
                mock.patch(__name__ + '.socket.socket', side_effect=(ipv4, ipv6)):
            self.assertEqual(reserve_dual_loopback(), (ipv4, ipv6))
        self.assertEqual(calls, [
            ('ipv6', socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1),
            ('ipv4', socket.SOL_SOCKET, 12345, 1),
            ('ipv6', socket.SOL_SOCKET, 12345, 1),
            ('ipv4', ('127.0.0.1', 0)),
            ('ipv6', ('::1', 40000)),
        ])
        ipv4.close.assert_not_called()
        ipv6.close.assert_not_called()

    def test_windows_exclusion_query_failure_allocates_no_sockets(self):
        failure = subprocess.CalledProcessError(1, ['netsh', 'controlled-query'])
        with mock.patch(__name__ + '.sys.platform', 'win32'), \
                mock.patch(__name__ + '.windows_exclusions', side_effect=failure), \
                mock.patch(__name__ + '.socket.socket') as factory:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                reserve_dual_loopback()
        self.assertIs(caught.exception, failure)
        factory.assert_not_called()

    def test_real_allocations_keep_both_families_and_avoid_existing_owner(self):
        pairs = []
        for _ in range(2):
            pair = reserve_dual_loopback()
            for stream in pair:
                self.addCleanup(stream.close)
            pairs.append(pair)
            self.assertEqual(pair[0].getsockname()[0], '127.0.0.1')
            self.assertEqual(pair[1].getsockname()[0], '::1')
            self.assertEqual(pair[0].getsockname()[1], pair[1].getsockname()[1])
            self.assertEqual(pair[1].getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY), 1)
            self.assert_socket_roundtrip(pair[0], b'owned-ipv4')
            self.assert_socket_roundtrip(pair[1], b'owned-ipv6')
        self.assertNotEqual(pairs[0][0].getsockname()[1], pairs[1][0].getsockname()[1])

    def test_real_ipv6_incumbent_preserves_access_denial_or_retries_only_collision(self):
        released, incumbent = reserve_dual_loopback()
        port = released.getsockname()[1]
        released.close()
        self.addCleanup(incumbent.close)
        incumbent.listen(1)
        native, created, observed = socket.socket, [], []
        bind, forced = native.bind, False

        def allocate(*args, **kwargs):
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        def force_second_family_collision(stream, address):
            nonlocal forced
            if stream.family == socket.AF_INET and not forced:
                self.assertEqual(address, ('127.0.0.1', 0))
                address, forced = ('127.0.0.1', port), True
            try:
                return bind(stream, address)
            except OSError as error:
                # Record the actual kernel result; never translate an exclusive
                # owner's access denial into the retryable address-in-use code.
                self.assertEqual(stream.family, socket.AF_INET6)
                self.assertEqual(address, ('::1', port))
                observed.append(error)
                raise

        with mock.patch.object(native, 'bind', new=force_second_family_collision), \
                mock.patch(__name__ + '.socket.socket', side_effect=allocate):
            try:
                pair = reserve_dual_loopback()
            except OSError as error:
                self.assertEqual(observed, [error])
                self.assertEqual(getattr(error, 'winerror', None), 10013)
                self.assertEqual(len(created), 2)
                self.assertTrue(all(stream.fileno() == -1 for stream in created))
                outcome = 'access-denied-failed-closed'
            else:
                for stream in pair:
                    self.addCleanup(stream.close)
                self.assertEqual(len(observed), 1)
                error = observed[0]
                self.assertTrue(error.errno == errno.EADDRINUSE or
                                getattr(error, 'winerror', None) == 10048)
                self.assertNotEqual(pair[0].getsockname()[1], port)
                self.assertEqual(pair[0].getsockname()[1], pair[1].getsockname()[1])
                self.assertTrue(all(stream.fileno() == -1 for stream in created[:-2]))
                outcome = 'address-in-use-retried'
        print(f'Dual-family incumbent: errno={observed[0].errno} '
              f'winerror={getattr(observed[0], "winerror", None)} outcome={outcome}')
        self.assert_socket_roundtrip(incumbent, b'original-ipv6-owner')

    def test_unknown_access_denial_is_not_retried(self):
        native, created = socket.socket, []
        denied = OSError(errno.EACCES, 'synthetic access denial')
        denied.winerror = 10013

        def track(*args, **kwargs):
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        with mock.patch.object(native, 'bind', side_effect=denied) as bind, \
                mock.patch(__name__ + '.socket.socket', side_effect=track):
            with self.assertRaises(OSError) as caught:
                reserve_dual_loopback()
        self.assertIs(caught.exception, denied)
        self.assertEqual(bind.call_count, 1)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(stream.fileno() == -1 for stream in created))

    def test_second_socket_creation_failure_releases_first(self):
        native, created = socket.socket, []
        failure = OSError(errno.EMFILE, 'synthetic descriptor exhaustion')

        def allocate(*args, **kwargs):
            if created:
                raise failure
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        with mock.patch(__name__ + '.socket.socket', side_effect=allocate) as factory:
            with self.assertRaises(OSError) as caught:
                reserve_dual_loopback()
        self.assertIs(caught.exception, failure)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(created[0].fileno(), -1)


class StallHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            if self.request.recv(16384):
                self.server.received.set()
                self.server.release.wait(3)
        except OSError:
            pass


def address_response(peer, data, tcp):
    assert len(data) <= 512
    assert data[2:12] == b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
    cursor, labels = 12, []
    while data[cursor]:
        size = data[cursor]
        labels.append(data[cursor + 1:cursor + 1 + size].decode('ascii'))
        cursor += size + 1
    host = '.'.join(labels).lower()
    kind, qclass = struct.unpack('!HH', data[cursor + 1:])
    assert kind in (1, 28) and qclass == 1
    peer.queries.append((host, kind, tcp))
    records = []
    for address in peer.answers:
        family = socket.AF_INET6 if ':' in address else socket.AF_INET
        if kind == (28 if family == socket.AF_INET6 else 1):
            packed = socket.inet_pton(family, address)
            records.append(b'\xc0\x0c' + struct.pack('!HHIH', kind, 1, 30, len(packed)) + packed)
    return data[:2] + struct.pack('!HHHHH', 0x8180, 1, len(records), 0, 0) + data[12:] + b''.join(records)


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'compiled Rust harness required')
class ConnectionStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trusted = tempfile.TemporaryDirectory()
        cls.untrusted = tempfile.TemporaryDirectory()
        cls.context, cls.ca, _ = certificates(cls.trusted.name)
        cls.other_context, _, _ = certificates(cls.untrusted.name)

    @classmethod
    def tearDownClass(cls):
        cls.trusted.cleanup()
        cls.untrusted.cleanup()

    def setUp(self):
        self.peers, self.servers = [], []
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)

    def close(self):
        for server in self.servers:
            if hasattr(server, 'release'):
                server.release.set()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self.fail('Native harness did not terminate')
        finally:
            for peer in self.peers:
                peer.close()
            for server in self.servers:
                server.shutdown()
                server.server_close()
        errors = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, errors)
        self.assertNotIn(PASSWORD, errors)
        for server in self.servers:
            self.assertEqual(server.errors, [])

    def command(self, **value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def dns(self, answers=('127.0.0.1', '::1'), silent=False):
        peer = DnsPeer(mode='silent' if silent else 'normal')
        if not silent:
            peer.answers = answers
            peer.respond = types.MethodType(address_response, peer)
        self.peers.append(peer)
        return peer

    def server(self, protocol='echo', host='127.0.0.1', port=0, tls=None, stall=False,
               reserved=None):
        server_type = IPv6Reference if ':' in host else ObservedReference
        handler = StallHandler if stall else Handler
        server = (adopt_server(server_type, handler, reserved) if reserved is not None
                  else server_type((host, port), handler))
        server.protocol, server.tls = protocol, tls
        server.requests, server.errors, server.accepted = [], [], 0
        server.tcp_connections = 0
        server.received, server.release = threading.Event(), threading.Event()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def ipv6_with_refused_ipv4(self):
        ipv4, ipv6 = reserve_dual_loopback()
        port = ipv4.getsockname()[1]
        try:
            server = self.server(host='::1', reserved=ipv6)
        finally:
            # A held non-listening socket can blackhole Windows SYNs. Release
            # only the refusal endpoint and still require actual OS refusal.
            ipv4.close()
        self.assert_refused('127.0.0.1', port)
        return server

    def dual_servers(self, first_options, second_options):
        ipv4, ipv6 = reserve_dual_loopback()
        try:
            first = self.server(reserved=ipv4, **first_options)
            second = self.server(host='::1', reserved=ipv6, **second_options)
            return first, second
        except BaseException:
            ipv4.close()
            ipv6.close()
            raise

    def refuse(self, port=0, host='127.0.0.1'):
        # A bound non-listening socket blackholes SYNs on some platforms.
        # Close the reservation, then require an actual OS refusal. The other
        # live endpoint is IPv6-only, not an unconfigured 127.0.0.2 alias.
        with socket.socket() as guard:
            guard.bind((host, port))
            port = guard.getsockname()[1]
        self.assert_refused(host, port)
        return port

    def assert_refused(self, host, port):
        # Allow OS rejection delivery, not a TLS/protocol timeout or test skip.
        # The two native refusal cases use the same 3s fixture-only budget.
        with socket.socket() as check:
            check.settimeout(3)
            with self.assertRaises(ConnectionRefusedError):
                check.connect((host, port))

    def start(self, outbound, peer=None, rules=None, timeout_ms=1200):
        config = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'node',
                  'nodes': [{'id': 'node', 'outbound': outbound},
                            {'id': 'deny', 'outbound': {'type': 'reject'}}],
                  'limits': {'max_connections': 4, 'handshake_timeout_ms': timeout_ms}}
        if peer:
            config['dns'] = {'use_system_hosts': False, 'servers': [peer.address]}
        if rules is not None:
            config['rules'] = rules
        result = self.command(op='start', config=config)
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def tunnel(self, host='target.fixture.invalid', port=443, success=True):
        stream = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        self.addCleanup(stream.close)
        stream.settimeout(5)
        stream.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode())
        self.assertIn(b' 200 ' if success else b' 502 ', header(stream))
        return stream

    def settled(self, *, failed=0, error='', stage='', accepted=1):
        deadline = time.monotonic() + 2
        while True:
            state = self.command(op='snapshot', handle=self.handle)['status']
            if state['active'] == 0 and all(x['ended'] for x in state['connections']):
                break
            self.assertLess(time.monotonic(), deadline, state)
            time.sleep(0.01)
        self.assertEqual((state['accepted'], state['failed']), (accepted, failed))
        self.assertEqual(state['last_error'], error)
        self.assertEqual(state['last_error_stage'], stage)
        self.assertEqual(len(state['connections']), accepted)
        for record in state['connections']:
            self.assertEqual(record['error'], error)
            self.assertEqual(record['failure_stage'], stage)
        return state

    def test_direct_tries_next_resolved_address_and_reuses_host_cache(self):
        origin = self.ipv6_with_refused_ipv4()
        port = origin.server_address[1]
        peer = self.dns()
        self.start({'type': 'direct'}, peer)
        for host in ('target.fixture.invalid', 'TARGET.FIXTURE.INVALID'):
            with self.tunnel(host, port) as stream:
                stream.sendall(b'native-multi-address')
                self.assertEqual(exact(stream, 20), b'native-multi-address')
                stream.shutdown(socket.SHUT_WR)
                self.assertEqual(stream.recv(1), b'')
        state = self.settled(accepted=2)
        self.assertGreater(state['upload'], 0)
        self.assertGreater(state['download'], 0)
        self.assertEqual(origin.tcp_connections, 2)
        self.assertEqual(len(peer.queries), 2)

    def test_http_obfs_ss_uses_resolved_proxy_addresses_without_resolving_target(self):
        ipv4, ipv6 = reserve_dual_loopback()
        try:
            server = adopt_server(IPv6SsPeer, SsHandler, ipv6)
        finally:
            ipv4.close()
        server.method, server.obfs, server.mode, server.fixed_salt = 'aes-128-gcm', True, 'echo', None
        server.targets, server.headers, server.errors, server.received = [], [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        port = server.server_address[1]
        self.assert_refused('127.0.0.1', port)
        peer = self.dns()
        self.start({'type': 'shadowsocks', 'host': 'proxy.fixture.invalid', 'port': port,
                    'password': PASSWORD, 'cipher': 'aes-128-gcm',
                    'obfs_http': {'host': 'obfs.example'}}, peer)
        with self.tunnel() as stream:
            stream.sendall(b'private-free-ss')
            self.assertEqual(exact(stream, 15), b'private-free-ss')
            stream.shutdown(socket.SHUT_WR)
            self.assertEqual(exact(stream, 20), b'tail-after-halfclose')
            self.assertEqual(stream.recv(1), b'')
        self.settled()
        self.assertEqual(server.targets, [('target.fixture.invalid', 443)])
        self.assertEqual(len(server.headers), 1)
        self.assertEqual({q[0] for q in peer.queries}, {'proxy.fixture.invalid'})

    def test_resolving_cidr_rule_pins_failed_address_without_trying_other_answer(self):
        origin = self.ipv6_with_refused_ipv4()
        port = origin.server_address[1]
        peer = self.dns()
        self.start({'type': 'direct'}, peer, rules=[
            {'matcher': {'type': 'cidr', 'value': '127.0.0.1/32', 'resolve': True}, 'outbound': 'node'},
            {'matcher': {'type': 'match'}, 'outbound': 'deny'}], timeout_ms=3000)
        self.tunnel(port=port, success=False).close()
        self.settled(failed=1, error='UpstreamConnectionRefused', stage='tcp_connect')
        self.assertEqual(origin.tcp_connections, 0)
        self.assertEqual(len(peer.queries), 2)
        self.assert_refused('127.0.0.1', port)

    def test_dns_timeout_is_not_misreported_as_tcp_or_protocol_timeout(self):
        peer = self.dns(silent=True)
        self.start({'type': 'shadowsocks', 'host': 'proxy.fixture.invalid', 'port': 443,
                    'password': PASSWORD, 'cipher': 'aes-128-gcm'}, peer, timeout_ms=200)
        self.tunnel(success=False).close()
        state = self.settled(failed=1, error='UpstreamDnsTimeout', stage='dns')
        self.assertEqual((state['upload'], state['download']), (0, 0))
        self.assertTrue(peer.queries)

    def test_refused_tcp_is_distinct_from_dns_and_has_no_protocol_traffic(self):
        port = self.refuse(host='127.0.0.1')
        self.start({'type': 'shadowsocks', 'host': '127.0.0.1', 'port': port,
                    'password': PASSWORD, 'cipher': 'aes-128-gcm'}, timeout_ms=3000)
        self.tunnel(success=False).close()
        state = self.settled(failed=1, error='UpstreamConnectionRefused', stage='tcp_connect')
        self.assertEqual((state['upload'], state['download']), (0, 0))
        self.assert_refused('127.0.0.1', port)

    def test_tls_timeout_does_not_restart_on_another_resolved_address(self):
        first, second = self.dual_servers({'stall': True}, {})
        port = first.server_address[1]
        self.start({'type': 'trojan', 'host': 'proxy.fixture.invalid', 'port': port,
                    'password': 'synthetic-trojan',
                    'tls': {'server_name': 'localhost', 'ca_der_base64': self.ca}},
                   self.dns(), timeout_ms=400)
        self.tunnel(success=False).close()
        self.settled(failed=1, error='UpstreamTlsTimeout', stage='tls_handshake')
        self.assertTrue(first.received.is_set())
        self.assertEqual(second.tcp_connections, 0)

    def test_protocol_timeout_after_tcp_success_has_its_own_stage(self):
        first, second = self.dual_servers({'stall': True}, {})
        port = first.server_address[1]
        self.start({'type': 'socks5', 'host': 'proxy.fixture.invalid', 'port': port},
                   self.dns(), timeout_ms=400)
        self.tunnel(success=False).close()
        self.settled(failed=1, error='UpstreamProtocolTimeout', stage='protocol_handshake')
        self.assertTrue(first.received.is_set())
        self.assertEqual(second.tcp_connections, 0)

    def test_untrusted_certificate_cannot_select_an_alternate_trusted_peer(self):
        first, second = self.dual_servers(
            {'protocol': 'http_connect', 'tls': self.other_context},
            {'protocol': 'http_connect', 'tls': self.context})
        port = first.server_address[1]
        self.start({'type': 'http_connect', 'host': 'proxy.fixture.invalid', 'port': port,
                    'auth': {'username': 'fixture-user', 'password': 'fixture-password'},
                    'tls': {'server_name': 'localhost', 'ca_der_base64': self.ca}},
                   self.dns())
        self.tunnel(success=False).close()
        # Both synthetic CAs have the same issuer DN but different keys. This
        # is a rejected certificate chain, not an absent matching issuer.
        self.settled(failed=1, error='TlsCertificateInvalid', stage='tls_handshake')
        self.assertEqual(first.tcp_connections, 1)
        self.assertEqual(second.tcp_connections, 0)
        self.assertEqual(first.requests, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
