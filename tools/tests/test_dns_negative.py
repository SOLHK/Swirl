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

from dns_peer import DnsPeer, name
from test_dns_tls import DotPeer
from test_dns_https import DohPeer
from test_rust_core import Reference, Handler, certificates, exact, header


class DnsPeerAllocationTests(unittest.TestCase):
    def test_windows_reserved_tcp_port_retry_is_bounded_and_does_not_mask_udp_denial(self):
        original = socketserver.TCPServer.server_bind
        for failing_kind, fail_count in ((socket.SOCK_STREAM, 1),
                                         (socket.SOCK_STREAM, 8),
                                         (socket.SOCK_DGRAM, 1)):
            with self.subTest(failing_kind=failing_kind, fail_count=fail_count):
                created, rejected = [], []
                failure = PermissionError(errno.EACCES, 'synthetic reserved port')
                failure.winerror = 10013

                def bind(server):
                    created.append(server)
                    if server.socket_type == failing_kind and len(rejected) < fail_count:
                        rejected.append(server)
                        raise failure
                    original(server)

                with mock.patch.object(socketserver.TCPServer, 'server_bind', bind):
                    if failing_kind == socket.SOCK_STREAM and fail_count == 1:
                        peer = DnsPeer()
                        try:
                            self.assertEqual(peer.udp.server_address[1], peer.tcp.server_address[1])
                            self.assertFalse(peer.tcp.allow_reuse_address)
                            self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                        finally:
                            peer.close()
                    else:
                        with self.assertRaises(PermissionError) as caught:
                            DnsPeer()
                        self.assertIs(caught.exception, failure)
                self.assertEqual(len(rejected), fail_count)
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_retries_collision_and_releases_failed_sockets(self):
        original = socketserver.TCPServer.server_bind
        for collision_kind in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
            with self.subTest(collision_kind=collision_kind):
                created, rejected = [], []

                def collide_once(server):
                    created.append(server)
                    if server.socket_type == collision_kind and not rejected:
                        rejected.append(server)
                        raise OSError(errno.EADDRINUSE, 'controlled bind collision')
                    original(server)

                with mock.patch.object(socketserver.TCPServer, 'server_bind', collide_once):
                    peer = DnsPeer()
                try:
                    self.assertEqual(len(rejected), 1)
                    self.assertEqual(peer.udp.server_address[1], peer.tcp.server_address[1])
                    self.assertTrue(all(server.socket.fileno() == -1 for server in created[:-2]))
                    for server in (peer.udp, peer.tcp):
                        self.assertFalse(server.allow_reuse_address)
                        self.assertFalse(server.allow_reuse_port)
                    self.assertEqual(peer.queries, [])
                finally:
                    peer.close()
                self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_stops_after_bounded_collisions(self):
        original = socketserver.TCPServer.server_bind
        created = []

        def always_collide(server):
            created.append(server)
            if server.socket_type == socket.SOCK_STREAM:
                raise OSError(errno.EADDRINUSE, 'controlled bind collision')
            original(server)

        with mock.patch.object(socketserver.TCPServer, 'server_bind', always_collide):
            with self.assertRaises(OSError) as caught:
                DnsPeer()
        self.assertEqual(caught.exception.errno, errno.EADDRINUSE)
        self.assertEqual(sum(server.socket_type == socket.SOCK_STREAM for server in created), 8)
        self.assertTrue(all(server.socket.fileno() == -1 for server in created))

    def test_pair_allocation_cleans_up_other_errors_without_retry(self):
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
                    self.assertEqual(len(created), 1 if failing_kind == socket.SOCK_DGRAM else 2)
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
