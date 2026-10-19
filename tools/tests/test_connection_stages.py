"""Independent loopback evidence for native address dialing and failure stages.

Resolved-address retries must stop before TLS/authentication/application bytes.
The deterministic stalled-connect timing/cancellation cases live in Rust tests;
these peers validate actual DNS, sockets, framed SS traffic and control reports.
"""
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
from loopback_ports import windows_candidates
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
    held = []
    try:
        for attempt in range(8):
            ipv4 = socket.socket()
            try:
                ipv6 = socket.socket(socket.AF_INET6)
            except BaseException:
                ipv4.close()
                raise
            try:
                ipv6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                # Let the OS allocate and retain a free IPv4 TCP endpoint.
                ipv4.bind(('127.0.0.1', 0))
                port = ipv4.getsockname()[1]
                if sys.platform == 'win32' and any(
                        port not in windows_candidates(family) for family in (False, True)):
                    held.append(ipv4)
                    ipv6.close()
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
            except BaseException:
                ipv4.close()
                ipv6.close()
                raise
        raise RuntimeError('No eligible dual-family loopback fixture port in eight attempts')
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
    def held_ipv6(self):
        ipv4, ipv6 = reserve_dual_loopback()
        port = ipv4.getsockname()[1]
        ipv4.close()
        self.addCleanup(ipv6.close)
        return port

    def allocate_with_collision(self, repeat):
        port = self.held_ipv6()
        native, created = socket.socket, []
        bind = native.bind
        forced = 0

        def track(*args, **kwargs):
            stream = native(*args, **kwargs)
            created.append(stream)
            return stream

        def collide(stream, address):
            nonlocal forced
            if stream.family == socket.AF_INET and (repeat or forced == 0):
                forced += 1
                address = ('127.0.0.1', port)
            return bind(stream, address)

        with mock.patch.object(native, 'bind', new=collide), \
                mock.patch(__name__ + '.socket.socket', side_effect=track):
            if repeat:
                with self.assertRaises(OSError) as caught:
                    reserve_dual_loopback()
                self.assertTrue(caught.exception.errno == errno.EADDRINUSE or
                                getattr(caught.exception, 'winerror', None) == 10048)
                self.assertEqual(forced, 8)
                self.assertTrue(all(stream.fileno() == -1 for stream in created))
            else:
                ipv4, ipv6 = reserve_dual_loopback()
                self.addCleanup(ipv4.close)
                self.addCleanup(ipv6.close)
                self.assertNotEqual(ipv4.getsockname()[1], port)
                self.assertEqual(ipv4.getsockname()[1], ipv6.getsockname()[1])
                self.assertTrue(all(stream.fileno() == -1 for stream in created[:-2]))
                self.assertGreaterEqual(len(created), 4)

    def test_second_family_collision_releases_both_sockets_before_retry(self):
        self.allocate_with_collision(False)

    def test_collision_budget_remains_eight_and_releases_every_attempt(self):
        self.allocate_with_collision(True)

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
        self.settled(failed=1, error='UpstreamConnectFailed', stage='tcp_connect')
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
        state = self.settled(failed=1, error='UpstreamConnectFailed', stage='tcp_connect')
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
        self.settled(failed=1, error='TlsVerificationOrHandshake', stage='tls_handshake')
        self.assertEqual(first.tcp_connections, 1)
        self.assertEqual(second.tcp_connections, 0)
        self.assertEqual(first.requests, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
