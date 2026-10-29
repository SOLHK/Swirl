"""Independent SOA/NXDOMAIN/NODATA peers for the native Rust resolver.

All DNS and origin traffic stays on loopback. No private subscription, system
DNS, certificate store or external proxy core is used. Existing UDP/DoT/DoH
fixtures supply transport framing only; this file independently encodes denials.
"""
import errno
import json
import os
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from loopback_ports import parse_exclusions, reserve_tcp_udp, windows_exclusions
from dns_peer import DnsPeer, name
from test_dns_tls import DotPeer
from test_dns_https import DohPeer
from test_rust_core import Reference, Handler, certificates, exact, header


class LoopbackPortSelectionTests(unittest.TestCase):
    def setUp(self):
        windows_exclusions.cache_clear()
        self.addCleanup(windows_exclusions.cache_clear)

    @staticmethod
    def table(rows=b''):
        return b'Localized column labels\n----------    --------\n' + rows + b'\n* - Exclusions.\n'

    def test_netsh_numeric_rows_and_empty_table(self):
        # Actual ranges from the failed Windows job, with a localized heading
        # and an administered reservation. No English labels are required.
        data = b'\xe7\xab\xaf\xe5\x8f\xa3\n----------    --------\n'
        data += b'60437 60536\n60537 60636\n63203 63302\n63303 63402 *\n'
        self.assertEqual(parse_exclusions(data),
                         [(60437, 60536), (60537, 60636), (63203, 63302), (63303, 63402)])
        self.assertEqual(parse_exclusions(self.table()), [])

    def test_missing_or_malformed_exclusion_table_fails(self):
        for output in (b'', b'netsh failed', b'49152 65535\n',
                       self.table(b'65536 65537'), self.table(b'0 5'),
                       self.table(b'60000 59999'), self.table(b'49152 broken'),
                       self.table(b'49152 65535 unexpected'), self.table(b'* 49152 65535')):
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    parse_exclusions(output)

    def test_windows_exclusions_preserve_both_protocols_and_cache_each_family(self):
        commands = []

        def query(command, **options):
            commands.append(command)
            self.assertEqual(options, {'check': True, 'stdout': subprocess.PIPE,
                                       'stderr': subprocess.PIPE, 'timeout': 10})
            # Preserve all numeric reservations, not only a default dynamic range.
            rows = b'80 80\n49152 50788' if command[-1] == 'protocol=tcp' else b'50790 65535'
            return types.SimpleNamespace(stdout=self.table(rows))

        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.subprocess.run', side_effect=query):
            for ipv6 in (False, True):
                expected = (frozenset(range(49152, 65536)) - {50789}) | {80}
                self.assertEqual(windows_exclusions(ipv6), expected)
                self.assertEqual(windows_exclusions(ipv6), expected)
        self.assertEqual(commands, [
            ['netsh', 'interface', family, 'show', 'excludedportrange', f'protocol={protocol}']
            for family in ('ipv4', 'ipv6') for protocol in ('tcp', 'udp')])

    def test_query_failures_never_bind_or_start_servers(self):
        for failure in (FileNotFoundError('netsh unavailable'),
                        subprocess.CalledProcessError(1, ['netsh']),
                        subprocess.TimeoutExpired(['netsh'], 10)):
            with self.subTest(failure=type(failure).__name__):
                windows_exclusions.cache_clear()
                with mock.patch('loopback_ports.sys.platform', 'win32'), \
                        mock.patch('loopback_ports.subprocess.run', side_effect=failure), \
                        mock.patch.object(socketserver.TCPServer, 'server_bind') as bind, \
                        mock.patch('dns_peer.Thread') as thread:
                    with self.assertRaises(type(failure)) as caught:
                        DnsPeer()
                    self.assertIs(caught.exception, failure)
                    bind.assert_not_called()
                    thread.assert_not_called()

    def test_all_ports_excluded_fails_before_allocating_an_endpoint(self):
        result = types.SimpleNamespace(stdout=self.table(b'1 65535'))
        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.subprocess.run', return_value=result), \
                mock.patch.object(socketserver.TCPServer, 'server_bind') as bind, \
                mock.patch('dns_peer.Thread') as thread:
            with self.assertRaisesRegex(RuntimeError, 'No unexcluded TCP/UDP fixture port'):
                DnsPeer()
            bind.assert_not_called()
            thread.assert_not_called()

    def test_portable_pairs_use_os_allocation_without_querying_netsh(self):
        for platform in ('linux', 'darwin'):
            for ipv6 in (False, True):
                with self.subTest(platform=platform, ipv6=ipv6):
                    family = socket.AF_INET6 if ipv6 else socket.AF_INET
                    requested = []

                    class TCP(socketserver.TCPServer):
                        address_family = family

                    class UDP(socketserver.UDPServer):
                        address_family = family

                    def tcp_factory(address):
                        requested.append(address)
                        return TCP(address, socketserver.BaseRequestHandler)

                    with mock.patch('loopback_ports.sys.platform', platform), \
                            mock.patch('loopback_ports.subprocess.run') as query:
                        tcp, udp = reserve_tcp_udp(
                            tcp_factory, lambda address: UDP(address, socketserver.BaseRequestHandler),
                            ipv6=ipv6)
                    try:
                        self.assertEqual(requested, [('::1' if ipv6 else '127.0.0.1', 0)])
                        self.assertGreater(tcp.server_address[1], 0)
                        self.assertEqual(tcp.socket.getsockname(), udp.socket.getsockname())
                        query.assert_not_called()
                    finally:
                        tcp.server_close()
                        udp.server_close()


class LoopbackPairOwnershipTests(unittest.TestCase):
    def factories(self, excluded, *, collisions=0, tcp_error=None, udp_error=None,
                  repeated=False, selected=58000):
        # Model a deterministic OS allocation sequence without binding chosen
        # host ports. Every returned SocketServer owns a real descriptor; the
        # actual bind/forwarding contract is tested separately below.
        sequence = iter(([55000, 55000] if repeated else sorted(excluded)) + [selected] * 8)
        trace = {'created': [], 'held': [], 'tcp': [], 'udp': [], 'collisions': []}

        def held_are_open():
            self.assertTrue(all(server.socket.fileno() != -1 for server in trace['held']))

        def tcp_factory(address):
            trace['tcp'].append(address)
            self.assertEqual(address, ('127.0.0.1', 0))
            held_are_open()
            if tcp_error is not None and len(trace['tcp']) > len(excluded):
                raise tcp_error
            server = socketserver.TCPServer(address, socketserver.BaseRequestHandler,
                                            bind_and_activate=False)
            server.server_address = (address[0], next(sequence))
            trace['created'].append(server)
            if server.server_address[1] in excluded:
                trace['held'].append(server)
            return server

        def udp_factory(address):
            trace['udp'].append(address)
            self.assertNotIn(address[1], excluded)
            self.assertEqual(len(trace['held']), len(excluded))
            held_are_open()
            tcp = trace['created'][-1]
            self.assertEqual(tcp.server_address, address)
            self.assertNotEqual(tcp.socket.fileno(), -1)
            if udp_error is not None:
                raise udp_error
            if len(trace['collisions']) < collisions:
                error = OSError(errno.EINVAL, 'controlled UDP address collision')
                error.winerror = 10048
                trace['collisions'].append(error)
                raise error
            server = socketserver.UDPServer(address, socketserver.BaseRequestHandler,
                                            bind_and_activate=False)
            trace['created'].append(server)
            return server

        return tcp_factory, udp_factory, trace

    def test_two_hundred_excluded_owners_are_held_without_using_collision_budget(self):
        excluded = frozenset(range(55000, 55200))
        tcp_factory, udp_factory, trace = self.factories(excluded, collisions=7)
        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.windows_exclusions', return_value=excluded):
            tcp, udp = reserve_tcp_udp(tcp_factory, udp_factory)
        try:
            self.assertEqual(len(trace['held']), 200)
            self.assertEqual(len(trace['tcp']), 208)
            self.assertEqual(len(trace['udp']), 8)
            self.assertEqual(len(trace['collisions']), 7)
            self.assertEqual((tcp, udp), tuple(trace['created'][-2:]))
            self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created'][:-2]))
            self.assertNotEqual(tcp.socket.fileno(), -1)
            self.assertNotEqual(udp.socket.fileno(), -1)
        finally:
            tcp.server_close()
            udp.server_close()
        self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created']))

    def test_held_exclusions_release_when_eight_real_collisions_are_exhausted(self):
        excluded = frozenset(range(55000, 55200))
        tcp_factory, udp_factory, trace = self.factories(excluded, collisions=8)
        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.windows_exclusions', return_value=excluded):
            with self.assertRaises(OSError) as caught:
                reserve_tcp_udp(tcp_factory, udp_factory)
        self.assertEqual(len(trace['tcp']), 208)
        self.assertEqual(len(trace['udp']), 8)
        self.assertIs(caught.exception, trace['collisions'][-1])
        self.assertIn('pair attempt 8/8', caught.exception.__notes__[-1])
        self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created']))

    def test_held_exclusions_release_on_tcp_or_udp_errors_without_retry(self):
        excluded = frozenset(range(55000, 55200))
        for protocol in ('tcp', 'udp'):
            denied = PermissionError(errno.EACCES, 'controlled unknown access denial')
            denied.winerror = 10013
            for error in (denied, OSError(errno.ENOBUFS, 'controlled resource failure'),
                          RuntimeError('controlled constructor failure')):
                with self.subTest(protocol=protocol, error=type(error).__name__):
                    tcp_factory, udp_factory, trace = self.factories(
                        excluded, **{protocol + '_error': error})
                    with mock.patch('loopback_ports.sys.platform', 'win32'), \
                            mock.patch('loopback_ports.windows_exclusions', return_value=excluded):
                        with self.assertRaises(type(error)) as caught:
                            reserve_tcp_udp(tcp_factory, udp_factory)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(len(trace['tcp']), 201)
                    self.assertEqual(len(trace['udp']), int(protocol == 'udp'))
                    self.assertEqual(len(trace['held']), 200)
                    self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created']))
                    if isinstance(error, OSError):
                        self.assertIn('pair attempt 1/8', error.__notes__[-1])

    def test_repeated_os_result_cannot_reuse_a_still_held_excluded_owner(self):
        excluded = frozenset({55000})
        tcp_factory, udp_factory, trace = self.factories(excluded, repeated=True)
        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.windows_exclusions', return_value=excluded):
            with self.assertRaisesRegex(RuntimeError, 'still-held excluded TCP fixture port'):
                reserve_tcp_udp(tcp_factory, udp_factory)
        self.assertEqual(len(trace['tcp']), 2)
        self.assertEqual(trace['udp'], [])
        self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created']))

    def test_os_dynamic_port_range_is_not_assumed_to_start_at_49152(self):
        tcp_factory, udp_factory, trace = self.factories(frozenset(), selected=32000)
        with mock.patch('loopback_ports.sys.platform', 'win32'), \
                mock.patch('loopback_ports.windows_exclusions', return_value=frozenset()):
            tcp, udp = reserve_tcp_udp(tcp_factory, udp_factory)
        try:
            self.assertEqual(trace['tcp'], [('127.0.0.1', 0)])
            self.assertEqual(trace['udp'], [('127.0.0.1', 32000)])
            self.assertEqual(tcp.server_address, udp.server_address)
        finally:
            tcp.server_close()
            udp.server_close()
        self.assertTrue(all(server.socket.fileno() == -1 for server in trace['created']))


class DnsPeerAllocationTests(unittest.TestCase):
    def isolate_bind_effects(self):
        # Error-only unit cases must not bind arbitrary host ports. Retain real
        # unbound descriptors so constructor/ExitStack cleanup is still checked.
        # The forwarding cases below continue to reserve and use actual sockets.
        def bind(server):
            if server.socket_type == socket.SOCK_STREAM:
                self.assertEqual(server.server_address[1], 0)
                server.server_address = (server.server_address[0], 50789)

        for patcher in (
                mock.patch('loopback_ports.windows_exclusions', return_value=frozenset()),
                mock.patch.object(socketserver.TCPServer, 'server_bind', autospec=True, side_effect=bind),
                mock.patch.object(socketserver.TCPServer, 'server_activate', autospec=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_pair_forwards(self, peer):
        # A maximum-length DNS name still crosses both actual socket types.
        host = '.'.join(('a' * 63, 'b' * 63, 'c' * 63, 'd' * 61))
        question = name(host) + struct.pack('!HH', 1, 1)
        query = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + question
        answer = (b'\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00' + question
                  + b'\xc0\x0c' + struct.pack('!HHIH', 1, 1, 30, 4) + b'\x7f\x00\x00\x01')
        with socket.socket(peer.udp.address_family, socket.SOCK_DGRAM) as stream:
            stream.settimeout(3)
            stream.connect(peer.udp.server_address)
            stream.send(query)
            self.assertEqual(stream.recv(4096), answer)
        with socket.create_connection((peer.tcp.server_address[0], peer.port), timeout=3) as stream:
            frame = struct.pack('!H', len(query)) + query
            for at in range(0, len(frame), 3):
                stream.sendall(frame[at:at + 3])
            size = struct.unpack('!H', exact(stream, 2))[0]
            self.assertEqual(exact(stream, size), answer)
        self.assertEqual(peer.queries, [(host, 1, False), (host, 1, True)])

    def test_tcp_reserves_port_before_udp_and_forwards_both_families(self):
        original = socketserver.TCPServer.server_bind
        for ipv6, first_collision in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(ipv6=ipv6, first_collision=first_collision):
                created, requested = [], []

                def bind(server):
                    created.append(server)
                    requested.append((server.socket_type, server.server_address[1]))
                    if server.socket_type == socket.SOCK_STREAM:
                        self.assertEqual(server.server_address[1], 0)
                    if first_collision and len(created) == 1:
                        raise OSError(errno.EADDRINUSE, 'controlled first TCP collision')
                    # UDP must use the already-held TCP port, never select a
                    # port and close a probe socket before the real TCP bind.
                    if server.socket_type == socket.SOCK_DGRAM:
                        self.assertEqual(created[-2].socket_type, socket.SOCK_STREAM)
                        self.assertNotEqual(created[-2].socket.fileno(), -1)
                        self.assertEqual(server.server_address[1], created[-2].server_address[1])
                        self.assertEqual(created[-2].socket.getsockname()[:2], server.server_address[:2])
                    original(server)

                with mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                    peer = DnsPeer(ipv6=ipv6)
                try:
                    self.assertEqual(requested[-2:], [(socket.SOCK_STREAM, 0),
                                                      (socket.SOCK_DGRAM, peer.port)])
                    self.assertGreaterEqual(len(requested), 2 + int(first_collision))
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                    self.assertEqual(peer.udp.server_address[1], peer.tcp.server_address[1])
                    self.assert_pair_forwards(peer)
                finally:
                    peer.close()
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_windows_access_denial_is_not_retried_on_either_endpoint(self):
        self.isolate_bind_effects()
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with self.subTest(failing_kind=failing_kind):
                created, rejected = [], []
                failure = PermissionError(errno.EACCES, 'synthetic socket access denial')
                failure.winerror = 10013

                def bind(server):
                    created.append(server)
                    if server.socket_type == failing_kind:
                        rejected.append(server.server_address)
                        raise failure
                    original(server)

                with mock.patch.object(socketserver.TCPServer, 'server_bind', bind), \
                        mock.patch('dns_peer.Thread') as thread:
                    with self.assertRaises(PermissionError) as caught:
                        DnsPeer()
                    thread.assert_not_called()
                self.assertIs(caught.exception, failure)
                self.assertEqual(len(rejected), 1)
                self.assertEqual(len(created), 1 if failing_kind == socket.SOCK_STREAM else 2)
                self.assertEqual(rejected[0][1], 0 if failing_kind == socket.SOCK_STREAM else 50789)
                protocol = 'TCP' if failing_kind == socket.SOCK_STREAM else 'UDP'
                self.assertEqual(failure.__notes__,
                                 [f'DNS fixture {protocol} bind on loopback {rejected[0]!r}; pair attempt 1/8'])
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_os_allocation_avoids_wildcard_and_dual_stack_incumbents(self):
        original = socketserver.TCPServer.server_bind
        for family, host in ((socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')):
            with self.subTest(family=family), socket.socket(family, socket.SOCK_STREAM) as incumbent:
                if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                    incumbent.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                if family == socket.AF_INET6:
                    incumbent.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                incumbent.bind((host, 0))
                incumbent.listen(1)
                incumbent_port = incumbent.getsockname()[1]
                # This is a known, still-held owner, not a reason to recover
                # from an unknown 10013 in the allocator. Capture the actual
                # platform protection before requesting a fresh OS endpoint.
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    with self.assertRaises(OSError) as caught:
                        probe.bind(('127.0.0.1', incumbent_port))
                protected = caught.exception
                self.assertTrue(protected.errno == errno.EADDRINUSE or
                                getattr(protected, 'winerror', None) in (10013, 10048))
                print(f'Known held wildcard owner family={family.name}: '
                      f'errno={protected.errno}, winerror={getattr(protected, "winerror", None)}')
                created, requested = [], []

                def bind(server):
                    created.append(server)
                    requested.append((server.socket_type, server.server_address[1]))
                    self.assertNotEqual(incumbent.fileno(), -1)
                    if server.socket_type == socket.SOCK_STREAM:
                        self.assertEqual(server.server_address[1], 0)
                    else:
                        tcp = created[-2]
                        self.assertNotEqual(tcp.socket.fileno(), -1)
                        self.assertEqual(tcp.socket.getsockname(), server.server_address)
                    original(server)

                with mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                    peer = DnsPeer()
                try:
                    self.assertNotEqual(peer.port, incumbent_port)
                    self.assertEqual(requested[-2:], [(socket.SOCK_STREAM, 0),
                                                      (socket.SOCK_DGRAM, peer.port)])
                    self.assertIs(peer.tcp, created[-2])
                    self.assertIs(peer.udp, created[-1])
                    self.assert_pair_forwards(peer)
                finally:
                    peer.close()
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_retries_collision_and_releases_failed_sockets(self):
        original = socketserver.TCPServer.server_bind
        for collision_kind in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
            for windows in (False, True):
                for fail_count in (1, 7):
                    with self.subTest(collision_kind=collision_kind, windows=windows, fail_count=fail_count):
                        created, rejected = [], []
                        failure = OSError(errno.EINVAL if windows else errno.EADDRINUSE,
                                          'controlled bind collision')
                        if windows:
                            failure.winerror = 10048

                        def collide(server):
                            created.append(server)
                            if server.socket_type == collision_kind and len(rejected) < fail_count:
                                rejected.append(server)
                                raise failure
                            original(server)

                        with mock.patch.object(socketserver.TCPServer, 'server_bind', collide):
                            peer = DnsPeer()
                        try:
                            self.assertEqual(len(rejected), fail_count)
                            self.assertEqual(peer.udp.server_address[1], peer.tcp.server_address[1])
                            self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                            for server in (peer.udp, peer.tcp):
                                self.assertFalse(server.allow_reuse_address)
                                self.assertFalse(server.allow_reuse_port)
                            self.assert_pair_forwards(peer)
                        finally:
                            peer.close()
                        self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_stops_after_bounded_collisions(self):
        self.isolate_bind_effects()
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            for windows in (False, True):
                with self.subTest(failing_kind=failing_kind, windows=windows):
                    created, rejected = [], []

                    def always_collide(server):
                        created.append(server)
                        if server.socket_type == failing_kind:
                            failure = OSError(errno.EINVAL if windows else errno.EADDRINUSE,
                                              f'controlled collision {len(rejected) + 1}')
                            if windows:
                                failure.winerror = 10048
                            rejected.append(failure)
                            raise failure
                        original(server)

                    with mock.patch.object(socketserver.TCPServer, 'server_bind', always_collide), \
                            mock.patch('dns_peer.Thread') as thread:
                        with self.assertRaises(OSError) as caught:
                            DnsPeer()
                        thread.assert_not_called()
                    self.assertIs(caught.exception, rejected[-1])
                    self.assertEqual(len(rejected), 8)
                    self.assertIn('pair attempt 8/8', caught.exception.__notes__[-1])
                    self.assertEqual(sum(server.socket_type == socket.SOCK_STREAM for server in created), 8)
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_cleans_up_other_errors_without_retry(self):
        self.isolate_bind_effects()
        original = socketserver.TCPServer.server_bind
        for failing_kind in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
            for failure in (PermissionError(errno.EACCES, 'controlled bind denial'),
                            RuntimeError('controlled non-socket failure')):
                with self.subTest(failing_kind=failing_kind, failure=type(failure).__name__):
                    created = []

                    def fail(server):
                        created.append(server)
                        if server.socket_type == failing_kind:
                            raise failure
                        original(server)

                    with mock.patch.object(socketserver.TCPServer, 'server_bind', fail):
                        with self.assertRaises(type(failure)) as caught:
                            DnsPeer()
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(len(created), 1 if failing_kind == socket.SOCK_STREAM else 2)
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created))


def record(owner, kind, body, ttl, qclass=1):
    return name(owner) + struct.pack('!HHIH', kind, qclass, ttl, len(body)) + body


def respond(peer, data, tcp):
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
    plan = peer.plan.copy()
    state = plan.get('families', {}).get(kind, plan.get('state', 'nx'))
    if state == 'silent':
        return None
    flags = 0x8180 | {'nx': 3, 'fail': 2, 'refused': 5}.get(state, 0)
    answers, authority, additional = [], [], []
    alias = plan.get('alias')
    if alias and host != alias:
        answers.append(record(host, 5, name(alias), plan.get('alias_ttl', 30)))
        host = alias
        if plan.get('followup'):
            flags, state = 0x8180, 'alias'
    if state == 'positive':
        body = socket.inet_pton(socket.AF_INET if kind == 1 else socket.AF_INET6,
                                '127.0.0.1' if kind == 1 else '::1')
        answers.append(record(host, kind, body, plan.get('ttl', 30)))
    if state in ('nx', 'nodata') and kind in plan.get('soa_types', (1, 28)):
        mailbox = plan.get('mailbox_label', b'hostmaster')
        body = name('ns.fixture.invalid') + bytes([len(mailbox)]) + mailbox + name('fixture.invalid')
        body += struct.pack('!IIIII', 1, 60, 60, 3600, plan.get('minimum', 30))
        if plan.get('damage') == 'soa-length':
            body = body[:-1]
        rr = record(plan.get('zone', 'fixture.invalid'), 6, body,
                    plan.get('ttl', 30), plan.get('soa_class', 1))
        (additional if plan.get('additional_soa') else authority).append(rr)
    if state == 'referral':
        authority.append(record('fixture.invalid', 2, name('ns.fixture.invalid'), 30))
    damage = plan.get('damage')
    if damage == 'tc' or damage == 'udp-tc' and not tcp:
        flags |= 0x0200
    result = (data[:2] + struct.pack('!HHHHH', flags, 1, len(answers), len(authority), len(additional))
              + data[12:] + b''.join(answers + authority + additional))
    if damage == 'wrong-id':
        result = bytes([result[0] ^ 1]) + result[1:]
    elif damage == 'wrong-question':
        result = result[:13] + bytes([result[13] ^ 1]) + result[14:]
    elif damage == 'trailing':
        result += b'unexpected'
    return result


@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'), 'set SWIRL_RUST_HARNESS')
class DnsNegativeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.context, cls.ca, _ = certificates(cls.temp.name)
        cls.context.set_alpn_protocols(['dot', 'http/1.1'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.peers, self.origins = [], []
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
            self.fail('Rust harness did not terminate')
        finally:
            for peer in self.peers:
                peer.close()
            for server in self.origins:
                server.shutdown()
                server.server_close()
        stderr = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        self.assertEqual(self.process.returncode, 0, stderr)
        self.assertNotIn(self.ca, stderr)
        for server in self.origins:
            self.assertEqual(server.errors, [])

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def peer(self, transport='udp', cache='', age=0, ipv6=False, **plan):
        if transport == 'doh':
            peer = DohPeer(self.context, cache=cache, age=age, ipv6=ipv6)
        elif transport == 'dot':
            peer = DotPeer(self.context, ipv6=ipv6)
        else:
            peer = DnsPeer(ipv6=ipv6)
        peer.transport, peer.plan = transport, plan
        peer.respond = types.MethodType(respond, peer)
        self.peers.append(peer)
        return peer

    def config(self, peers, query_family=None):
        peers = peers if isinstance(peers, list) else [peers]
        dns = {'use_system_hosts': False}
        if query_family is not None:
            dns['query_family'] = query_family
        if peers[0].transport == 'udp':
            dns['servers'] = [peer.address for peer in peers]
        else:
            endpoints = []
            for peer in peers:
                endpoint = {'address': peer.address, 'tls': {'server_name': 'localhost',
                            'ca_der_base64': self.ca,
                            'alpn': ['http/1.1' if peer.transport == 'doh' else 'dot']}}
                if peer.transport == 'doh':
                    endpoint['https_path'] = '/dns-query'
                endpoints.append(endpoint)
            dns['tls_servers'] = endpoints
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'direct',
                'nodes': [{'id': 'direct', 'outbound': {'type': 'direct'}}], 'dns': dns}

    def start(self, peers, query_family=None):
        result = self.command(op='start', config=self.config(peers, query_family))
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def origin(self):
        server = Reference(('127.0.0.1', 0), Handler)
        server.protocol, server.tls = 'echo', None
        server.requests, server.errors, server.accepted = [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.origins.append(server)
        return server.server_address[1]

    def connect(self, port=443, host='negative.fixture.invalid', expected=None):
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as stream:
            stream.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode())
            response = header(stream)
            if expected is None:
                self.assertIn(b' 200 ', response)
                stream.sendall(b'native-dns')
                self.assertEqual(exact(stream, 10), b'native-dns')
            else:
                self.assertIn(b' 502 ', response)
        if expected:
            deadline = time.monotonic() + 1
            while True:
                status = self.command(op='snapshot', handle=self.handle)['status']
                if status['active'] == 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.005)
            self.assertEqual(status['last_error'], expected)

    def make_positive(self, peer):
        peer.plan = {'families': {1: 'positive', 28: 'nodata'}}

    def test_nxdomain_cache_shares_ports_and_case_on_every_transport(self):
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport)
                self.start(peer)
                self.connect(expected='DnsNameError')
                self.connect(8443, 'NEGATIVE.FIXTURE.INVALID', expected='DnsNameError')
                self.assertEqual(len(peer.queries), 2)
                self.stop()

    def test_resolution_failure_cache_expires_and_recovers_real_forwarding(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            for state in ('fail', 'refused'):
                with self.subTest(transport=transport, state=state):
                    peer = self.peer(transport, state=state)
                    self.start(peer)
                    self.connect(expected='DnsServerError')
                    before = len(peer.queries)
                    self.make_positive(peer)
                    self.connect(8443, 'NEGATIVE.FIXTURE.INVALID', expected='DnsServerError')
                    self.assertEqual(len(peer.queries), before)
                    time.sleep(1.1)
                    self.connect(port)
                    self.assertEqual(len(peer.queries), before + 2)
                    self.stop()

    def test_failure_is_cached_only_after_all_configured_servers_fail(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                failed = self.peer(transport, state='fail')
                good = self.peer(transport, families={1: 'positive', 28: 'nodata'})
                self.start([failed, good])
                self.connect(port)
                counts = len(failed.queries), len(good.queries)
                self.assertGreater(counts[0], 0)
                self.assertEqual(counts[1], 2)
                self.connect(port)
                self.assertEqual((len(failed.queries), len(good.queries)), counts)
                self.stop()

    def test_timeout_failure_cache_starts_after_resolution_finishes(self):
        peer = self.peer(state='silent')
        self.start(peer)
        self.connect(expected='DnsTimeout')
        self.assertEqual(len(peer.queries), 2)
        self.make_positive(peer)
        self.connect(expected='DnsTimeout')
        self.assertEqual(len(peer.queries), 2)
        time.sleep(1.1)
        self.connect(self.origin())
        self.assertEqual(len(peer.queries), 4)

    def test_configuration_replacement_clears_failure_cache(self):
        peer = self.peer(state='fail')
        self.start(peer)
        self.connect(expected='DnsServerError')
        self.make_positive(peer)
        self.assertTrue(self.command(op='configure', handle=self.handle, config=self.config(peer))['ok'])
        self.connect(self.origin())
        self.assertEqual(len(peer.queries), 4)

    def test_nodata_is_separate_from_name_error_and_requires_both_families(self):
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport, state='nodata')
                self.start(peer)
                self.connect(expected='DnsEmpty')
                self.connect(8443, expected='DnsEmpty')
                self.assertEqual(len(peer.queries), 2)
                self.stop()

    def test_positive_addresses_share_hostname_but_use_each_real_destination_port(self):
        first, second = self.origin(), self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport, families={1: 'positive', 28: 'nodata'})
                self.start(peer)
                self.connect(first)
                self.connect(second, 'NEGATIVE.FIXTURE.INVALID')
                self.assertEqual(len(peer.queries), 2)
                self.stop()
        self.assertEqual([server.accepted for server in self.origins], [3, 3])

    def test_soa_record_ttl_and_minimum_both_expire_denials(self):
        port = self.origin()
        for ttl, minimum in ((1, 30), (30, 1)):
            with self.subTest(ttl=ttl, minimum=minimum):
                peer = self.peer(ttl=ttl, minimum=minimum)
                self.start(peer)
                self.connect(expected='DnsNameError')
                self.make_positive(peer)
                self.connect(8443, expected='DnsNameError')
                self.assertEqual(len(peer.queries), 2)
                time.sleep(1.1)
                self.connect(port)
                self.assertEqual(len(peer.queries), 4)
                self.stop()

    def test_cname_followup_denial_never_outlives_earliest_alias(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport, alias='gone.fixture.invalid', alias_ttl=1,
                                 followup=True, minimum=20)
                self.start(peer)
                self.connect(expected='DnsNameError')
                self.connect(8443, expected='DnsNameError')
                self.assertEqual(len(peer.queries), 4)
                peer.plan['families'] = {1: 'positive', 28: 'nodata'}
                time.sleep(1.1)
                self.connect(port)
                self.assertEqual(len(peer.queries), 8)
                self.stop()

    def test_inline_cname_uses_terminal_soa_and_preserves_mailbox_label_bytes(self):
        peer = self.peer(alias='gone.fixture.invalid', mailbox_label=b'host.master')
        self.start(peer)
        self.connect(expected='DnsNameError')
        self.connect(8443, expected='DnsNameError')
        self.assertEqual(len(peer.queries), 2, 'inline SOA must avoid unnecessary CNAME followups')

    def test_missing_foreign_additional_or_wrong_class_soa_is_never_cached(self):
        port = self.origin()
        for options in ({'soa_types': ()}, {'soa_types': (1,)}, {'zone': 'ture.invalid'},
                        {'soa_class': 3}, {'additional_soa': True}):
            with self.subTest(options=options):
                peer = self.peer(**options)
                self.start(peer)
                self.connect(expected='DnsNameError')
                self.make_positive(peer)
                self.connect(port)
                self.assertEqual(len(peer.queries), 4)
                self.stop()

    def test_zero_negative_ttls_are_not_cached_on_any_transport(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            for options in ({'ttl': 0}, {'minimum': 0}):
                with self.subTest(transport=transport, options=options):
                    peer = self.peer(transport, **options)
                    self.start(peer)
                    self.connect(expected='DnsNameError')
                    self.make_positive(peer)
                    self.connect(port)
                    self.assertEqual(len(peer.queries), 4)
                    self.stop()

    def test_doh_age_and_cache_control_also_limit_negative_ttl(self):
        for options in ({'cache': 'no-store'}, {'cache': 'no-cache'},
                        {'cache': 'max-age=0'}, {'minimum': 5, 'age': 5},
                        {'cache': 'max-age=3', 'age': 3}):
            with self.subTest(options=options):
                peer = self.peer('doh', **options)
                self.start(peer)
                self.connect(expected='DnsNameError')
                self.connect(8443, expected='DnsNameError')
                self.assertEqual(len(peer.queries), 4)
                self.stop()

    def test_inconsistent_families_and_failed_families_never_create_negative_cache(self):
        port = self.origin()
        for families, expected in (({1: 'positive', 28: 'nx'}, 'DnsInconsistentAnswer'),
                                   ({1: 'nx', 28: 'positive'}, 'DnsInconsistentAnswer'),
                                   ({1: 'nodata', 28: 'nx'}, 'DnsInconsistentAnswer'),
                                   ({1: 'fail', 28: 'nx'}, 'DnsNameError'),
                                   ({1: 'fail', 28: 'positive'}, 'DnsServerError'),
                                   ({1: 'positive', 28: 'fail'}, 'DnsServerError')):
            with self.subTest(families=families):
                peer = self.peer(families=families)
                self.start(peer)
                self.connect(expected=expected)
                self.make_positive(peer)
                if expected == 'DnsServerError':
                    # Resolution failures are cached separately from SOA
                    # denials; retain the exact failure, then retry on expiry.
                    self.connect(port, expected='DnsServerError')
                    self.assertEqual(len(peer.queries), 2)
                    time.sleep(1.1)
                self.connect(port)
                self.assertEqual(len(peer.queries), 4)
                self.stop()

    def test_invalid_negative_packets_are_rejected_and_never_cached(self):
        port = self.origin()
        for damage, expected in (('wrong-id', 'DnsIdentity'), ('wrong-question', 'DnsQuestion'),
                                 ('trailing', 'DnsTrailingData'), ('soa-length', 'DnsSoaLength'),
                                 ('tc', 'DnsTcpTruncated')):
            with self.subTest(damage=damage):
                peer = self.peer(damage=damage)
                self.start(peer)
                self.connect(expected=expected)
                before = len(peer.queries)
                self.make_positive(peer)
                self.connect(port)
                self.assertEqual(len(peer.queries), before + 2)
                self.stop()

    def test_validated_tcp_retry_can_cache_the_complete_negative_answer(self):
        peer = self.peer(damage='udp-tc')
        self.start(peer)
        self.connect(expected='DnsNameError')
        self.connect(8443, expected='DnsNameError')
        self.assertEqual(len(peer.queries), 4)
        self.assertEqual(sum(tcp for _, _, tcp in peer.queries), 2)

    def test_unproven_empty_answers_fail_over_but_valid_zero_ttl_denials_are_terminal(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                empty = self.peer(transport, state='nodata', soa_types=())
                good = self.peer(transport, families={1: 'positive', 28: 'nodata'})
                self.start([empty, good])
                self.connect(port)
                self.assertEqual(len(good.queries), 2)
                self.stop()
                for state, expected in (('nodata', 'DnsEmpty'), ('nx', 'DnsNameError')):
                    terminal = self.peer(transport, state=state, minimum=0)
                    unused = self.peer(transport, families={1: 'positive', 28: 'nodata'})
                    self.start([terminal, unused])
                    self.connect(expected=expected)
                    self.assertEqual(unused.queries, [])
                    self.stop()

    def test_config_generation_drops_old_negative_cache(self):
        peer = self.peer()
        self.start(peer)
        self.connect(expected='DnsNameError')
        before = self.command(op='snapshot', handle=self.handle)['status']['generation']
        self.make_positive(peer)
        result = self.command(op='configure', handle=self.handle, config=self.config(peer))
        self.assertTrue(result['ok'], result)
        self.assertGreater(self.command(op='snapshot', handle=self.handle)['status']['generation'], before)
        self.connect(self.origin())
        self.assertEqual(len(peer.queries), 4)

    def test_negative_cache_capacity_does_not_grow_beyond_existing_bound(self):
        peer = self.peer()
        self.start(peer)
        for index in range(257):
            self.connect(host=f'negative-{index}.fixture.invalid', expected='DnsNameError')
        self.assertEqual(len(peer.queries), 514)
        self.connect(host='negative-0.fixture.invalid', expected='DnsNameError')
        self.assertEqual(len(peer.queries), 516, 'oldest retained denial must have been evicted')


    def test_ipv4_only_omits_aaaa_and_preserves_tcp_retry_and_cname(self):
        port = self.origin()
        for transport, damage in (('udp', None), ('udp', 'udp-tc'), ('dot', None), ('doh', None)):
            with self.subTest(transport=transport, damage=damage):
                peer = self.peer(transport, families={1: 'positive', 28: 'silent'},
                                 alias='alias.fixture.invalid', followup=True, damage=damage)
                self.start(peer, 'ipv4_only')
                self.connect(port)
                expected = [('negative.fixture.invalid', 1, transport != 'udp'),
                            ('alias.fixture.invalid', 1, transport != 'udp')]
                if damage:
                    expected = [(host, kind, tcp) for host, kind, _ in expected for tcp in (False, True)]
                self.assertEqual(peer.queries, expected)
                self.connect(port)
                self.assertEqual(peer.queries, expected, 'A-only positive response must be cached')
                self.stop()

    def test_ipv4_only_negative_soa_cache_expires_without_querying_aaaa(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            for state, error in (('nx', 'DnsNameError'), ('nodata', 'DnsEmpty')):
                with self.subTest(transport=transport, state=state):
                    peer = self.peer(transport, families={1: state, 28: 'silent'}, minimum=1)
                    self.start(peer, 'ipv4_only')
                    self.connect(expected=error)
                    self.connect(8443, 'NEGATIVE.FIXTURE.INVALID', expected=error)
                    self.assertEqual(peer.queries, [('negative.fixture.invalid', 1, transport != 'udp')])
                    self.make_positive(peer)
                    time.sleep(1.1)
                    self.connect(port)
                    self.assertEqual([kind for _, kind, _ in peer.queries], [1, 1])
                    self.stop()

    def test_ipv4_only_unproven_empty_failover_and_zero_ttl_denial(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                empty = self.peer(transport, state='nodata', soa_types=())
                good = self.peer(transport, families={1: 'positive', 28: 'silent'})
                self.start([empty, good], 'ipv4_only')
                self.connect(port)
                self.assertEqual([kind for _, kind, _ in empty.queries], [1])
                self.assertEqual([kind for _, kind, _ in good.queries], [1])
                self.stop()
                for state, error in (('nx', 'DnsNameError'), ('nodata', 'DnsEmpty')):
                    terminal = self.peer(transport, state=state, minimum=0)
                    unused = self.peer(transport, state='positive')
                    self.start([terminal, unused], 'ipv4_only')
                    self.connect(expected=error)
                    self.connect(expected=error)
                    self.assertEqual([kind for _, kind, _ in terminal.queries], [1, 1])
                    self.assertEqual(unused.queries, [])
                    self.stop()

    def test_ipv4_only_can_query_an_ipv6_upstream_on_all_transports(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport, ipv6=True, families={1: 'positive', 28: 'silent'})
                self.assertTrue(peer.address.startswith('[::1]:'), peer.address)
                self.assertEqual(peer.tcp.server_address[0], '::1')
                self.start(peer, 'ipv4_only')
                self.connect(port)
                self.assertEqual(peer.queries, [('negative.fixture.invalid', 1, transport != 'udp')])
                self.stop()

    def test_ipv4_only_nxdomain_without_soa_is_terminal_but_never_cached(self):
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                negative = self.peer(transport, state='nx', soa_types=())
                unused = self.peer(transport, state='positive')
                self.start([negative, unused], 'ipv4_only')
                self.connect(expected='DnsNameError')
                self.connect(8443, expected='DnsNameError')
                self.assertEqual([kind for _, kind, _ in negative.queries], [1, 1])
                self.assertEqual(unused.queries, [])
                self.stop()

    def test_ipv4_only_doh_age_and_no_store_bound_single_family_cache(self):
        for cache, age in (('no-store', 0), ('max-age=2', 2)):
            with self.subTest(cache=cache, age=age):
                peer = self.peer('doh', state='nodata', cache=cache, age=age)
                self.start(peer, 'ipv4_only')
                self.connect(expected='DnsEmpty')
                self.connect(8443, expected='DnsEmpty')
                self.assertEqual([kind for _, kind, _ in peer.queries], [1, 1])
                self.stop()

    def test_query_family_reconfiguration_discards_the_previous_cache(self):
        port = self.origin()
        for transport in ('udp', 'dot', 'doh'):
            with self.subTest(transport=transport):
                peer = self.peer(transport, families={1: 'positive', 28: 'nodata'})
                self.start(peer)
                self.connect(port)
                self.assertEqual(sorted(kind for _, kind, _ in peer.queries), [1, 28])
                self.assertTrue(self.command(op='configure', handle=self.handle,
                                            config=self.config(peer, 'ipv4_only'))['ok'])
                peer.plan = {'families': {1: 'nodata', 28: 'silent'}}
                self.connect(expected='DnsEmpty')
                self.assertEqual([kind for _, kind, _ in peer.queries[2:]], [1])
                self.make_positive(peer)
                self.assertTrue(self.command(op='configure', handle=self.handle,
                                            config=self.config(peer))['ok'])
                self.connect(port)
                self.assertEqual(sorted(kind for _, kind, _ in peer.queries[3:]), [1, 28])
                self.stop()



if __name__ == '__main__':
    unittest.main(verbosity=2)
