"""Independent RFC 1928/1929 SOCKS5 UDP peers for the compiled native core.

Wire fields below use Python sockets, struct and ipaddress, never Swirl codecs
or another proxy core. Every destination is a loopback fixture; credentials are
synthetic. The peer's forwarding counts, the origin's received payloads and exact
prefixed replies together verify the relay path and exclude local echoes or an
accidental DIRECT bypass.

Primary references reviewed before implementation:
https://www.rfc-editor.org/rfc/rfc1928#section-6
https://www.rfc-editor.org/rfc/rfc1928#section-7
https://www.rfc-editor.org/rfc/rfc1929
https://github.com/Anorov/PySocks/blob/master/socks.py
The PySocks control-socket lifetime provides a comparison, not copied code.
Swirl's strict configured-auth and explicit-relay-address rules remain intact.
"""

import ipaddress
import json
import os
from pathlib import Path
import queue
import select
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import traceback
import unittest
import xml.etree.ElementTree as ET


USER = 'synthetic-socks5-user'
PASSWORD = 'synthetic-socks5-password'
PREFIX = b'socks5-udp-native:'
QT_PAYLOAD = b'qt-socks5-udp'
UDP_BUFFER_MINIMUM = 65_536


def udp_socket(family=socket.AF_INET):
    # Darwin's default UDP SO_SNDBUF is smaller than a legal 65,507-byte
    # datagram. Configure every real forwarding hop independently of the Core,
    # keeping larger OS defaults and the original wire-size acceptance limit.
    result = socket.socket(family, socket.SOCK_DGRAM)
    try:
        for option in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            if result.getsockopt(socket.SOL_SOCKET, option) < UDP_BUFFER_MINIMUM:
                result.setsockopt(socket.SOL_SOCKET, option, UDP_BUFFER_MINIMUM)
            actual = result.getsockopt(socket.SOL_SOCKET, option)
            if actual < UDP_BUFFER_MINIMUM:
                raise RuntimeError(f'UDP buffer option {option} was clamped to {actual}')
        return result
    except BaseException:
        result.close()
        raise


def exact(stream, length):
    result = bytearray()
    while len(result) < length:
        part = stream.recv(length - len(result))
        if not part:
            raise EOFError('SOCKS fixture stream ended')
        result.extend(part)
    return bytes(result)


def address(host, port):
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        name = host.encode('ascii')
        if not 1 <= len(name) <= 255:
            raise ValueError('SOCKS domain length')
        encoded = b'\x03' + bytes([len(name)]) + name
    else:
        encoded = bytes([1 if parsed.version == 4 else 4]) + parsed.packed
    return encoded + struct.pack('!H', port)


def read_address(read):
    kind = read(1)[0]
    if kind == 1:
        host = str(ipaddress.IPv4Address(read(4)))
    elif kind == 4:
        host = str(ipaddress.IPv6Address(read(16)))
    elif kind == 3:
        length = read(1)[0]
        if not length:
            raise ValueError('Empty SOCKS domain')
        host = read(length).decode('ascii')
    else:
        raise ValueError('Unknown SOCKS address type')
    return kind, host, struct.unpack('!H', read(2))[0]


def packet(host, port, payload):
    return b'\x00\x00\x00' + address(host, port) + payload


def unpack_packet(data):
    if data[:3] != b'\x00\x00\x00':
        raise ValueError('Nonzero reserved/fragment field')
    offset = 3

    def read(length):
        nonlocal offset
        end = offset + length
        if end > len(data):
            raise ValueError('Truncated SOCKS datagram')
        result = data[offset:end]
        offset = end
        return result

    kind, host, port = read_address(read)
    return kind, host, port, data[offset:]


class UdpOrigin:
    """An actual UDP application, with no knowledge of SOCKS framing."""

    def __init__(self):
        self.socket = udp_socket()
        self.socket.bind(('127.0.0.1', 0))
        self.socket.settimeout(0.05)
        self.address = self.socket.getsockname()
        self.received = []
        self.errors = []
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.closed.is_set():
                try:
                    data, sender = self.socket.recvfrom(65535)
                except socket.timeout:
                    continue
                self.received.append(data)
                self.socket.sendto(PREFIX + data, sender)
        except OSError:
            if not self.closed.is_set():
                self.errors.append(traceback.format_exc())

    def close(self):
        self.closed.set()
        self.thread.join(2)
        self.socket.close()
        if self.thread.is_alive() or self.errors:
            raise AssertionError(f'UDP origin did not close cleanly: {self.errors}')


class ReferenceServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    request_queue_size = 64

    def handle_error(self, request, client_address):
        self.owner.errors.append(traceback.format_exc())


class PeerSession:
    def __init__(self, control):
        self.control = control
        self.relay = None
        self.client = None
        self.closed = threading.Event()
        self.close_requested = threading.Event()
        self.datagrams = []
        self.rejection = None


class Socks5Peer:
    """Per-control UDP relays with independently parsed requests and replies."""

    def __init__(self, origin, auth=False, mode='normal', bound='ipv4'):
        self.origin, self.auth, self.mode, self.bound = origin, auth, mode, bound
        self.sessions, self.greetings, self.credentials, self.requests = [], [], [], []
        self.errors, self.datagrams = [], []
        self.forwarded = 0
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.release = threading.Event()
        if mode != 'hold-method':
            self.release.set()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                owner.handle(self.request)

        self.server = ReferenceServer(('127.0.0.1', 0), Handler)
        self.server.owner = self
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    @property
    def accepted(self):
        return len(self.sessions)

    def send(self, control, data):
        # Fragmenting the TCP reply checks read-exact behavior independently of
        # how the operating system happens to coalesce loopback writes.
        for byte in data:
            control.sendall(bytes([byte]))

    def relay_socket(self, family):
        for _ in range(8):
            relay = udp_socket(family)
            relay.bind(('::1' if family == socket.AF_INET6 else '127.0.0.1', 0))
            if relay.getsockname()[1] != self.port:
                return relay
            relay.close()
        raise RuntimeError('Could not allocate a UDP port different from the TCP fixture')

    def expect_rejection(self, session, response):
        # The peer remains open. An ignored invalid field must not pass merely
        # because the fixture closed the connection before forwarding could run.
        control, relay = session.control, session.relay
        control.sendall(response)
        watched = [control] + ([relay] if relay is not None else [])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            readable, _, _ = select.select(watched, [], [], 0.02)
            if relay is not None and relay in readable:
                wire, _ = relay.recvfrom(65535)
                raise AssertionError(f'UDP continued after {self.mode}: {wire[:32].hex()}')
            if control not in readable:
                continue
            try:
                continued = control.recv(4096)
                closure = 'eof'
            except ConnectionResetError:
                # Rejecting a header while unread address bytes remain can
                # produce a TCP reset; this is still an active remote close.
                continued, closure = b'', 'reset'
            if continued:
                raise AssertionError(f'TCP continued after {self.mode}: {continued[:32].hex()}')
            if relay is not None and select.select([relay], [], [], 0.05)[0]:
                raise AssertionError(f'UDP arrived while rejecting {self.mode}')
            session.rejection = closure
            return
        raise AssertionError(f'Core did not actively reject {self.mode} while the peer stayed open')

    def handle(self, control):
        session = PeerSession(control)
        with self.lock:
            self.sessions.append(session)
        control.settimeout(3)
        try:
            greeting = exact(control, 2)
            methods = exact(control, greeting[1])
            self.greetings.append(greeting + methods)
            expected = b'\x02' if self.auth else b'\x00'
            if greeting != b'\x05\x01' or methods != expected:
                raise AssertionError('Swirl must offer only its configured authentication method')
            while not self.release.is_set():
                readable, _, _ = select.select([control], [], [], 0.02)
                if self.closed.is_set() or session.close_requested.is_set():
                    return
                if readable:
                    if control.recv(1):
                        raise AssertionError('Application bytes before method selection')
                    return
            if self.mode == 'method-version':
                self.expect_rejection(session, b'\x04' + expected)
                return
            if self.mode == 'method-rejected':
                self.expect_rejection(session, b'\x05\xff')
                return
            if self.mode == 'method-downgrade':
                self.expect_rejection(session, b'\x05\x00')
                return
            self.send(control, b'\x05' + expected)
            if self.auth:
                version, length = exact(control, 2)
                user = exact(control, length)
                password = exact(control, exact(control, 1)[0])
                self.credentials.append((user, password))
                if version != 1 or (user, password) != (USER.encode(), PASSWORD.encode()):
                    raise AssertionError('RFC 1929 credentials were changed')
                if self.mode == 'auth-version':
                    self.expect_rejection(session, b'\x05\x00')
                    return
                if self.mode == 'auth-denied':
                    self.expect_rejection(session, b'\x01\x01')
                    return
                self.send(control, b'\x01\x00')
            request = exact(control, 3)
            source = read_address(lambda size: exact(control, size))
            if request != b'\x05\x03\x00' or source[1:] != ('0.0.0.0', 0):
                raise AssertionError('Expected UDP ASSOCIATE with unknown, zero source endpoint')
            self.requests.append(source)
            family = socket.AF_INET6 if self.bound in ('ipv6', 'domain') else socket.AF_INET
            with self.relay_socket(family) as relay, udp_socket() as forwarding:
                session.relay = relay
                forwarding.connect(self.origin.address)
                forwarding.settimeout(2)
                host, port = relay.getsockname()[:2]
                if self.bound == 'unspecified':
                    host = '0.0.0.0'
                elif self.bound == 'domain':
                    host = 'relay.fixture.invalid'
                response = b'\x05\x00\x00' + address(host, port)
                replacements = {
                    'reply-version': b'\x04' + response[1:],
                    'reply-reserved': response[:2] + b'\x01' + response[3:],
                    'reply-status': b'\x05\x05' + response[2:],
                    'reply-address-type': b'\x05\x00\x00\x7f' + response[4:],
                    'reply-port-zero': response[:-2] + b'\x00\x00',
                    'reply-truncated': response[:-1],
                }
                if self.mode in replacements:
                    self.expect_rejection(session, replacements[self.mode])
                    return
                self.send(control, response)
                while not self.closed.is_set() and not session.close_requested.is_set():
                    readable, _, _ = select.select([control, relay], [], [], 0.02)
                    if control in readable:
                        if control.recv(1):
                            raise AssertionError('UDP payload arrived on the TCP control connection')
                        return
                    if relay not in readable:
                        continue
                    wire, sender = relay.recvfrom(65535)
                    decoded = unpack_packet(wire)
                    _, destination, destination_port, payload = decoded
                    if not (destination in ('127.0.0.1', '::1') or destination.endswith('.fixture.invalid')):
                        raise AssertionError('Fixture refused a non-fixture destination')
                    if destination_port != self.origin.address[1]:
                        raise AssertionError('Fixture destination port was changed')
                    if session.client is not None and session.client != sender:
                        raise AssertionError('Different clients shared one upstream UDP association')
                    session.client = sender
                    session.datagrams.append(decoded)
                    self.datagrams.append(decoded)
                    forwarding.send(payload)
                    returned = forwarding.recv(65535)
                    if returned != PREFIX + payload:
                        raise AssertionError('Independent origin response mismatch')
                    with self.lock:
                        self.forwarded += 1
                    relay.sendto(packet(destination, destination_port, returned), sender)
        except (EOFError, ConnectionError):
            pass
        except OSError:
            if not self.closed.is_set() and not session.close_requested.is_set():
                self.errors.append(traceback.format_exc())
        finally:
            session.closed.set()

    def inject(self, data, rogue=False, index=0):
        session = self.sessions[index]
        if rogue:
            with socket.socket(session.relay.family, socket.SOCK_DGRAM) as other:
                other.bind(('::1' if other.family == socket.AF_INET6 else '127.0.0.1', 0))
                other.sendto(data, session.client)
        else:
            session.relay.sendto(data, session.client)

    def close_controls(self):
        for session in self.sessions:
            session.close_requested.set()

    def close(self):
        self.closed.set()
        self.release.set()
        self.close_controls()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        deadline = time.monotonic() + 3
        for session in self.sessions:
            session.closed.wait(max(0, deadline - time.monotonic()))
        if self.thread.is_alive() or any(not session.closed.is_set() for session in self.sessions) or self.errors:
            raise AssertionError(f'SOCKS5 peer did not close cleanly: {self.errors}')


class Association:
    def __init__(self, control, client, relay):
        self.control, self.client, self.relay = control, client, relay

    def close(self):
        self.control.close()
        self.client.close()


class Socks5UdpIntegration(unittest.TestCase):
    def setUp(self):
        harness = os.environ.get('SWIRL_RUST_HARNESS', '')
        self.assertTrue(harness and Path(harness).is_file(), 'Set SWIRL_RUST_HARNESS to a built native executable')
        self.fixtures, self.associations = [], []
        self.stderr = tempfile.TemporaryFile()
        self.process = subprocess.Popen([harness], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr, text=True)
        self.replies = queue.Queue(maxsize=32)

        def read_replies():
            for line in self.process.stdout:
                self.replies.put(line)
            self.replies.put(None)

        self.reader = threading.Thread(target=read_replies, daemon=True)
        self.reader.start()
        self.addCleanup(self.close)

    def close(self):
        for association in self.associations:
            association.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            self.fail('Native harness failed to stop')
        finally:
            self.reader.join(2)
            self.process.stdout.close()
            self.stderr.seek(0)
            diagnostic = self.stderr.read().decode(errors='replace')
            self.stderr.close()
            for fixture in reversed(self.fixtures):
                fixture.close()
        self.assertFalse(self.reader.is_alive(), 'Harness output reader remained alive')
        self.assertEqual(self.process.returncode, 0, diagnostic)

    def command(self, **value):
        self.process.stdin.write(json.dumps(value) + '\n')
        self.process.stdin.flush()
        try:
            line = self.replies.get(timeout=5)
        except queue.Empty:
            self.fail('Native control response exceeded five seconds')
        self.assertIsNotNone(line, 'Native harness exited before replying')
        return json.loads(line)

    def fixture(self, **options):
        origin = UdpOrigin()
        self.fixtures.append(origin)
        peer = Socks5Peer(origin, **options)
        self.fixtures.append(peer)
        return origin, peer

    def outbound(self, peer, udp=True):
        return {'type': 'socks5', 'host': '127.0.0.1', 'port': peer.port,
                'auth': {'username': USER, 'password': PASSWORD} if peer.auth else None,
                'udp': udp}

    def config(self, outbound, **extra):
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'n',
                'nodes': [{'id': 'n', 'outbound': outbound}], **extra}

    def start(self, config):
        response = self.command(op='start', config=config)
        self.assertTrue(response['ok'], response)
        self.handle = response['handle']
        self.port = int(response['status']['address'].rsplit(':', 1)[1])

    def stop(self):
        self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def associate(self, known_source=False):
        client = udp_socket()
        client.bind(('127.0.0.1', 0))
        client.settimeout(3)
        control = socket.create_connection(('127.0.0.1', self.port), timeout=3)
        try:
            control.sendall(b'\x05\x01\x00')
            self.assertEqual(exact(control, 2), b'\x05\x00')
            source = client.getsockname() if known_source else ('0.0.0.0', 0)
            control.sendall(b'\x05\x03\x00' + address(*source))
            self.assertEqual(exact(control, 3), b'\x05\x00\x00')
            _, host, port = read_address(lambda size: exact(control, size))
            self.assertNotEqual(port, 0)
            result = Association(control, client, (host, port))
            self.associations.append(result)
            return result
        except BaseException:
            control.close()
            client.close()
            raise

    def wait_for(self, predicate, message, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(predicate(), message)

    def silence(self, client, timeout=0.15):
        previous = client.gettimeout()
        client.settimeout(timeout)
        try:
            with self.assertRaises(socket.timeout):
                client.recvfrom(65535)
        finally:
            client.settimeout(previous)

    def exchange(self, association, origin, payload=b'udp-wire', host='127.0.0.1'):
        port = origin.address[1]
        association.client.sendto(packet(host, port, payload), association.relay)
        received, sender = association.client.recvfrom(65535)
        self.assertEqual(sender, association.relay)
        self.assertEqual(unpack_packet(received)[1:], (host, port, PREFIX + payload))
        return received

    def routed_config(self, peer, count):
        return {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'n0',
                'nodes': [{'id': f'n{i}', 'outbound': self.outbound(peer)} for i in range(count)],
                'rules': [{'matcher': {'type': 'domain', 'value': f'n{i}.fixture.invalid'},
                           'outbound': f'n{i}'} for i in range(count)]}

    def test_wire_addresses_authentication_and_datagram_boundaries(self):
        for authenticated in (False, True):
            with self.subTest(auth=authenticated):
                origin, peer = self.fixture(auth=authenticated)
                self.start(self.config(self.outbound(peer)))
                association = self.associate()
                for host in ('127.0.0.1', 'origin.fixture.invalid', '::1'):
                    for payload in (b'', b'separate-udp-message', bytes(range(256)) * 6):
                        self.exchange(association, origin, payload, host)
                        self.assertEqual(peer.datagrams[-1][1:], (host, origin.address[1], payload))
                # IPv4's legal outer UDP limit minus SOCKS overhead and the
                # independent application's response prefix, without truncation.
                boundary = self.exchange(association, origin, b'x' * (65507 - 10 - len(PREFIX)))
                self.assertEqual(len(boundary), 65507)
                self.assertEqual(peer.accepted, 1)
                self.assertNotEqual(peer.sessions[0].relay.getsockname()[1], peer.port)
                self.assertEqual(peer.forwarded, 10)
                self.assertEqual(len(origin.received), 10)
                self.assertEqual(peer.requests, [(1, '0.0.0.0', 0)])
                self.assertEqual(peer.credentials, [(USER.encode(), PASSWORD.encode())] if authenticated else [])
                self.stop()

    def test_bound_unspecified_domain_and_explicit_ipv6_relay(self):
        for bound in ('unspecified', 'domain', 'ipv6'):
            with self.subTest(bound=bound):
                origin, peer = self.fixture(bound=bound)
                # Disabling OS resolution requires an explicit DNS endpoint.
                # The configured hosts mapping must resolve the relay before
                # any DNS request; a local sink also keeps failure paths local.
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns_sink:
                    dns_sink.bind(('127.0.0.1', 0))
                    config = self.config(self.outbound(peer), dns={
                        'hosts': [{'name': 'relay.fixture.invalid', 'address': '::1'}],
                        'servers': [f'127.0.0.1:{dns_sink.getsockname()[1]}'],
                        'use_system_hosts': False})
                    self.start(config)
                    self.exchange(self.associate(), origin, bound.encode())
                    self.assertEqual(peer.forwarded, 1)
                    self.assertEqual(peer.sessions[0].relay.family, socket.AF_INET6 if bound in ('ipv6', 'domain') else socket.AF_INET)
                    self.silence(dns_sink, timeout=0.05)
                    self.stop()

    def test_fragment_malformed_and_foreign_relay_packets_are_dropped(self):
        origin, peer = self.fixture()
        self.start(self.config(self.outbound(peer)))
        association = self.associate()
        valid = self.exchange(association, origin)
        malformed = (b'', valid[:2], b'\x01' + valid[1:], valid[:2] + b'\x01' + valid[3:],
                     valid[:2] + b'\x80' + valid[3:], valid[:3] + b'\x7f' + valid[4:],
                     b'\x00\x00\x00\x03\xffshort', b'\x00\x00\x00\x04\x00')
        for index, wire in enumerate(malformed):
            with self.subTest(malformed=index):
                peer.inject(wire)
                self.silence(association.client)
        peer.inject(packet('127.0.0.1', origin.address[1], b'forged-from-another-source-port'), rogue=True)
        self.silence(association.client)
        self.exchange(association, origin, b'valid-after-rejected-packets')
        self.assertEqual(peer.forwarded, 2)

    def test_inbound_source_port_and_fragment_rejection(self):
        origin, peer = self.fixture()
        self.start(self.config(self.outbound(peer)))
        association = self.associate(known_source=True)
        valid = packet('127.0.0.1', origin.address[1], b'rogue-inbound')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rogue:
            rogue.bind(('127.0.0.1', 0))
            rogue.sendto(valid, association.relay)
        association.client.sendto(valid[:2] + b'\x01' + valid[3:], association.relay)
        self.silence(association.client)
        self.assertEqual(peer.accepted, 0)
        self.assertEqual(origin.received, [])
        self.exchange(association, origin, b'only-the-declared-client')
        self.assertEqual(peer.forwarded, 1)

    def test_control_eof_stops_upstream_without_reconnect_or_direct_fallback(self):
        origin, peer = self.fixture()
        self.start(self.config(self.outbound(peer)))
        association = self.associate()
        self.exchange(association, origin, b'before-control-eof')
        peer.close_controls()
        self.wait_for(lambda: all(s.closed.is_set() for s in peer.sessions), 'Reference controls did not close')
        for payload in (b'after-eof-one', b'after-eof-two'):
            association.client.sendto(packet('127.0.0.1', origin.address[1], payload), association.relay)
            self.silence(association.client)
        self.assertEqual(peer.accepted, 1, 'A closed upstream association was silently reconnected')
        self.assertEqual(origin.received, [b'before-control-eof'], 'A failed SOCKS path fell back to DIRECT')
        self.wait_for(lambda: self.command(op='snapshot', handle=self.handle)['status']['udp_dropped'] > 0,
                      'No UDP failure was recorded')
        self.exchange(self.associate(), origin, b'a-new-client-may-create-a-new-session')
        self.assertEqual(peer.accepted, 2)

    def test_associations_are_isolated_and_control_shutdown_releases_upstream(self):
        origin, peer = self.fixture(auth=True)
        self.start(self.config(self.outbound(peer)))
        first, second = self.associate(), self.associate()
        self.exchange(first, origin, b'first-client')
        self.exchange(second, origin, b'second-client')
        self.assertEqual(peer.accepted, 2)
        self.assertNotEqual(peer.sessions[0].client, peer.sessions[1].client)
        first.control.close()
        self.wait_for(lambda: peer.sessions[0].closed.is_set(), 'Inbound TCP EOF did not close upstream TCP')
        self.exchange(second, origin, b'second-client-remains-live')
        second.control.close()
        self.wait_for(lambda: peer.sessions[1].closed.is_set(), 'Second upstream control leaked')
        self.wait_for(lambda: self.command(op='snapshot', handle=self.handle)['status']['active'] == 0,
                      'Closed UDP associations remained active')

    def test_disabled_or_omitted_udp_never_reaches_peer_or_origin(self):
        for omitted in (False, True):
            with self.subTest(omitted=omitted):
                origin, peer = self.fixture()
                outbound = self.outbound(peer, udp=False)
                if omitted:
                    del outbound['udp']
                self.start(self.config(outbound))
                association = self.associate()
                association.client.sendto(packet('127.0.0.1', origin.address[1], b'blocked'), association.relay)
                self.silence(association.client)
                self.assertEqual(peer.accepted, 0)
                self.assertEqual(origin.received, [])
                self.assertGreater(self.command(op='snapshot', handle=self.handle)['status']['udp_dropped'], 0)
                self.stop()

    def test_tls_udp_combination_is_rejected_before_network(self):
        origin, peer = self.fixture()
        outbound = self.outbound(peer)
        outbound['tls'] = {'server_name': 'localhost'}
        response = self.command(op='start', config=self.config(outbound))
        self.assertFalse(response['ok'], response)
        self.assertIn('Socks5UdpTlsUnsupported', json.dumps(response))
        self.assertEqual(peer.accepted, 0)
        self.assertEqual(origin.received, [])

    def test_malformed_handshakes_and_auth_downgrade_fail_without_direct(self):
        modes = ('method-version', 'method-rejected', 'method-downgrade', 'auth-version', 'auth-denied',
                 'reply-version', 'reply-reserved', 'reply-status', 'reply-address-type',
                 'reply-port-zero', 'reply-truncated')
        for mode in modes:
            with self.subTest(mode=mode):
                origin, peer = self.fixture(auth=True, mode=mode)
                config = self.config(self.outbound(peer))
                if mode == 'reply-truncated':
                    # Unlike a complete invalid field, an incomplete reply is
                    # rejected by the configured protocol deadline, not EOF.
                    config['limits'] = {'max_connections': 128, 'handshake_timeout_ms': 1000}
                self.start(config)
                association = self.associate()
                association.client.sendto(packet('127.0.0.1', origin.address[1], b'must-not-go-direct'), association.relay)
                self.wait_for(lambda: peer.accepted == 1 and peer.sessions[0].closed.is_set(),
                              'Failed negotiation did not finish')
                self.assertIn(peer.sessions[0].rejection, ('eof', 'reset'), peer.errors)
                self.assertEqual(peer.errors, [])
                self.assertEqual(len(peer.credentials), 0 if mode.startswith('method-') else 1)
                self.assertEqual(len(peer.requests), 1 if mode.startswith('reply-') else 0)
                self.assertEqual(peer.datagrams, [])
                self.silence(association.client)
                self.assertEqual(origin.received, [])
                self.assertEqual(peer.forwarded, 0)
                self.assertGreater(self.command(op='snapshot', handle=self.handle)['status']['udp_dropped'], 0)
                self.stop()

    def test_stalled_handshakes_bound_inflight_work_and_cancel_on_client_close(self):
        origin, peer = self.fixture(mode='hold-method')
        self.start(self.routed_config(peer, 20))
        association = self.associate()
        for index in range(20):
            association.client.sendto(packet(f'n{index}.fixture.invalid', origin.address[1], str(index).encode()),
                                      association.relay)
        self.wait_for(lambda: peer.accepted >= 1, 'No reference control was opened')
        self.wait_for(lambda: self.command(op='snapshot', handle=self.handle)['status']['udp_dropped'] > 0,
                      'Excess in-flight datagrams were not bounded')
        self.silence(association.client)
        self.assertLessEqual(peer.accepted, 4, 'More than four preparation tasks reached the network')
        self.assertEqual(origin.received, [])
        association.control.close()
        self.wait_for(lambda: all(s.closed.is_set() for s in peer.sessions), 'Pending network tasks survived client close')
        peer.release.set()
        self.exchange(self.associate(), origin, b'capacity-released', 'n0.fixture.invalid')

    def test_sixteen_node_limit_includes_closed_tombstones(self):
        origin, peer = self.fixture()
        self.start(self.routed_config(peer, 17))
        association = self.associate()
        for index in range(16):
            self.exchange(association, origin, str(index).encode(), f'n{index}.fixture.invalid')
        self.assertEqual(peer.accepted, 16)
        peer.close_controls()
        self.wait_for(lambda: all(s.closed.is_set() for s in peer.sessions), 'Reference controls remained open')
        association.client.sendto(packet('n16.fixture.invalid', origin.address[1], b'over-association-limit'),
                                  association.relay)
        self.silence(association.client)
        self.assertEqual(peer.accepted, 16, 'Closing nodes incorrectly evicted session tombstones')
        self.assertEqual(len(origin.received), 16)
        self.exchange(self.associate(), origin, b'fresh-association', 'n16.fixture.invalid')
        self.assertEqual(peer.accepted, 17)

    def test_imported_udp_candidates_execute_through_the_reference(self):
        inspector = os.environ.get('SWIRL_RUST_INSPECTOR', '')
        self.assertTrue(inspector and Path(inspector).is_file(), 'Set SWIRL_RUST_INSPECTOR')
        origin, peer = self.fixture(auth=True)
        documents = (
            f'proxies: [{{name: synthetic, type: socks5, server: 127.0.0.1, port: {peer.port}, username: {USER}, password: {PASSWORD}, udp: true}}]',
            f'[Proxy]\nsynthetic = socks5, 127.0.0.1, {peer.port}, username={USER}, password={PASSWORD}, udp-relay=true\n',
        )
        for document in documents:
            result = subprocess.run([inspector, '--private-json'], input=document,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            inspected = json.loads(result.stdout)
            node = inspected['report']['nodes'][0]
            self.assertTrue(node['native_tcp_candidate'])
            self.assertTrue(node['native_udp_supported'])
            self.assertFalse(node['real_network_verified'])
            outbound = inspected['tcpCandidates'][0]
            self.assertEqual(outbound['type'], 'socks5')
            self.assertTrue(outbound['udp'])
            self.start(self.config(outbound))
            self.exchange(self.associate(), origin, b'parsed-does-not-mean-forwarded')
            self.stop()
        self.assertEqual(peer.forwarded, 2)
        self.assertEqual(len(origin.received), 2)

    @unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'), 'Windows Qt integration executable required')
    def test_qt_imported_socks5_udp_data_path(self):
        for authenticated in (False, True):
            with self.subTest(auth=authenticated):
                origin, peer = self.fixture(auth=authenticated)
                environment = {**os.environ, 'SWIRL_SOCKS5_UDP_REFERENCE_PORT': str(peer.port),
                               'SWIRL_SOCKS5_UDP_ORIGIN_PORT': str(origin.address[1]),
                               'SWIRL_SOCKS5_UDP_EXPECT_AUTH': str(int(authenticated))}
                with tempfile.TemporaryDirectory() as folder:
                    report = Path(folder) / 'socks5-udp-qt.xml'
                    result = subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'], 'socks5UdpThroughIndependentPeer',
                                             '-o', str(report) + ',xml'], env=environment,
                                            capture_output=True, text=True, timeout=40)
                    evidence = report.read_text(encoding='utf-8') if report.exists() else ''
                    self.assertEqual(result.returncode, 0, evidence + result.stdout + result.stderr)
                    root = ET.fromstring(evidence)
                    incidents = root.findall("./TestFunction[@name='socks5UdpThroughIndependentPeer']/Incident")
                    self.assertEqual([incident.get('type') for incident in incidents], ['pass'], evidence)
                    self.assertTrue(all(incident.get('type') == 'pass' for incident in root.iter('Incident')), evidence)
                self.assertEqual(peer.accepted, 2)
                self.assertEqual(peer.forwarded, 2)
                self.assertEqual(origin.received, [QT_PAYLOAD, QT_PAYLOAD])
                self.assertEqual(peer.requests, [(1, '0.0.0.0', 0)] * 2)
                self.assertEqual(peer.credentials, [(USER.encode(), PASSWORD.encode())] * 2 if authenticated else [])
                self.wait_for(lambda: all(s.closed.is_set() for s in peer.sessions), 'Qt engine leaked upstream controls')


if __name__ == '__main__':
    unittest.main(verbosity=2)
