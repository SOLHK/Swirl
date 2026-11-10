"""Bounded, real V2/SOCKS5/TLS/SSE endurance gate; never reconnects or skips.

All connections remain open in one production V2 core until the requested
interval has elapsed and every final event has arrived. This is controlled
local network evidence, not Windows Desktop or private-provider acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import ssl
import sys
import tempfile
import threading
import time
import traceback

from test_product_subscription_chain import Relay, Server, USER
from test_rust_core import certificates, exact, header
from test_shadowsocks import PASSWORD
from test_windows_proxy_compat import NODE, REQUEST, STORE, TARGET, V2Host


def event_bytes(connection, sequence):
    return (f'id: {sequence}\nevent: tick\n'
            f'data: connection={connection};sequence={sequence}\n\n').encode()


def failure(error, stage, connection=None):
    frames = traceback.extract_tb(error.__traceback__)[-5:]
    code = error.args[0] if error.args else None
    return {'stage': stage, 'connection': connection, 'type': type(error).__name__,
            'code': code if isinstance(code, str) and code.isidentifier() else None,
            'errno': getattr(error, 'errno', None), 'winerror': getattr(error, 'winerror', None),
            'frames': [{'file': Path(frame.filename).name, 'line': frame.lineno,
                        'function': frame.name} for frame in frames]}


class State:
    def __init__(self, duration, connections):
        self.duration, self.connections = duration, connections
        self.lock = threading.Lock()
        self.start, self.finish, self.abort = (threading.Event() for _ in range(3))
        self.started_at = None
        self.ready, self.delivered, self.admitted = set(), set(), set()
        self.clients, self.origins, self.errors = {}, {}, []

    def fail(self, error, stage, connection=None):
        with self.lock:
            self.errors.append(failure(error, stage, connection))
        self.abort.set()

    def wait(self, event, limit, code):
        deadline = time.monotonic() + limit
        while not event.wait(0.05):
            assert not self.abort.is_set(), 'SoakAborted'
            assert time.monotonic() < deadline, code
        assert not self.abort.is_set(), 'SoakAborted'


class SoakRelay(Relay):
    def __init__(self, origin_port, duration):
        super().__init__('socks5', 'soak-node', [origin_port])
        base_handler = self.server.RequestHandlerClass

        class QuietUploadSocket:
            def __init__(self, raw):
                self.raw = raw

            def settimeout(self, _seconds):
                # The short-test Relay normally times out silent uploads at
                # eight seconds. SSE legitimately sends only downstream data
                # until TLS close_notify. Extend only this peer's socket idle
                # budget, not core handshakes or client/origin I/O deadlines.
                self.raw.settimeout(duration + 40)

            def __getattr__(self, name):
                return getattr(self.raw, name)

        class Handler(base_handler):
            def setup(self):
                self.request = QuietUploadSocket(self.request)
                super().setup()

        # Installed on this one fixture server before the core has any client.
        # Authentication, routing and relay code remain the independent peer's.
        self.server.RequestHandlerClass = Handler


class SoakOrigin:
    def __init__(self, state, context):
        self.errors = []
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                stream, connection = self.request, None
                stream.settimeout(8)
                try:
                    stream = context.wrap_socket(stream, server_side=True,
                                                 suppress_ragged_eofs=False)
                    assert stream.selected_alpn_protocol() == 'http/1.1', 'OriginAlpn'
                    request = header(stream)
                    first = request.split(b'\r\n', 1)[0]
                    method, path, version = first.split(b' ')
                    assert method == b'GET' and version == b'HTTP/1.1', 'OriginRequest'
                    assert path.startswith(b'/soak/'), 'OriginPath'
                    connection = int(path[len(b'/soak/'):])
                    assert 0 <= connection < state.connections, 'OriginConnectionId'
                    with state.lock:
                        assert connection not in state.admitted, 'OriginReconnect'
                        state.admitted.add(connection)
                    stream.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                                   b'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n')
                    state.wait(state.start, 30, 'OriginStartDeadline')
                    digest = hashlib.sha256()
                    for sequence in range(state.duration + 1):
                        due = state.started_at + sequence
                        assert not state.abort.wait(max(0, due - time.monotonic())), 'SoakAborted'
                        payload = event_bytes(connection, sequence)
                        stream.sendall(f'{len(payload):x}\r\n'.encode() + payload + b'\r\n')
                        digest.update(payload)
                    # Keep every connection alive until the coordinator has
                    # observed all final events and the full elapsed interval.
                    state.wait(state.finish, 8, 'OriginFinishDeadline')
                    stream.sendall(b'0\r\n\r\n')
                    stream = stream.unwrap()
                    stream.shutdown(socket.SHUT_WR)
                    assert stream.recv(1) == b'', 'OriginMissingTcpEof'
                    with state.lock:
                        state.origins[connection] = {'events': state.duration + 1,
                                                     'sha256': digest.hexdigest(),
                                                     'tls_close_notify': True, 'tcp_eof': True}
                except Exception as error:
                    state.fail(error, 'origin', connection)
                finally:
                    stream.close()

        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.errors, self.server.fixture_kind = owner.errors, 'v2-sse-soak-origin'
        self.port = self.server.server_address[1]
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.worker.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)
        assert not self.worker.is_alive(), 'OriginListenerDidNotStop'
        assert not self.errors, 'OriginServerFailure'


def consume(state, connection, port, origin_port, ca):
    stream = None
    try:
        stream = socket.create_connection(('127.0.0.1', port), timeout=8)
        authority = f'{TARGET}:{origin_port}'.encode()
        stream.sendall(b'CONNECT ' + authority + b' HTTP/1.1\r\nHost: '
                       + authority + b'\r\n\r\n')
        response = header(stream)
        assert response.split(b'\r\n', 1)[0].split(b' ')[1] == b'200', 'ConnectRejected'
        context = ssl.create_default_context(cadata=ca)
        context.set_alpn_protocols(['http/1.1'])
        stream = context.wrap_socket(stream, server_hostname='localhost',
                                     suppress_ragged_eofs=False)
        assert stream.selected_alpn_protocol() == 'http/1.1', 'ClientAlpn'
        stream.sendall(f'GET /soak/{connection} HTTP/1.1\r\nHost: localhost\r\n'
                       'Accept: text/event-stream\r\n\r\n'.encode())
        response = header(stream)
        assert response.startswith(b'HTTP/1.1 200 OK\r\n'), 'SseStatus'
        assert b'Content-Type: text/event-stream\r\n' in response, 'SseContentType'
        assert b'Transfer-Encoding: chunked\r\n' in response, 'SseFraming'
        with state.lock:
            state.ready.add(connection)
        digest, count, pending = hashlib.sha256(), 0, b''
        while True:
            line = b''
            while not line.endswith(b'\r\n'):
                line += exact(stream, 1)
                assert len(line) <= 16, 'ChunkLineLimit'
            size = int(line[:-2], 16)
            assert 0 <= size <= 1024, 'ChunkSizeLimit'
            if not size:
                assert exact(stream, 2) == b'\r\n', 'ChunkTerminator'
                break
            pending += exact(stream, size)
            assert exact(stream, 2) == b'\r\n', 'ChunkBoundary'
            while b'\n\n' in pending:
                payload, pending = pending.split(b'\n\n', 1)
                payload += b'\n\n'
                assert count <= state.duration, 'ExtraSseEvent'
                assert payload == event_bytes(connection, count), 'SseSequenceOrContent'
                digest.update(payload)
                count += 1
                if count == state.duration + 1:
                    with state.lock:
                        state.delivered.add(connection)
            assert len(pending) <= 1024, 'SseEventLimit'
        assert count == state.duration + 1 and not pending, 'SseEventCount'
        stream = stream.unwrap()
        stream.shutdown(socket.SHUT_WR)
        assert stream.recv(1) == b'', 'ClientMissingTcpEof'
        with state.lock:
            state.clients[connection] = {'events': count, 'sha256': digest.hexdigest(),
                                         'tls_close_notify': True, 'tcp_eof': True}
    except Exception as error:
        state.fail(error, 'client', connection)
    finally:
        if stream is not None:
            stream.close()


def linux_resources(pid):
    """Optional observations only; these samples do not prove absence of leaks."""
    if not sys.platform.startswith('linux'):
        return {}
    try:
        status = Path(f'/proc/{pid}/status').read_text()
        rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith('VmRSS:'))
        return {'rss_kib': rss, 'fd_count': sum(1 for _ in Path(f'/proc/{pid}/fd').iterdir())}
    except (OSError, StopIteration):
        return {}


def run(duration, connections, evidence):
    state, host, origin, relay, handle = State(duration, connections), None, None, None, None
    workers = []
    folder = tempfile.TemporaryDirectory(prefix='swirl-v2-soak-')
    evidence.update({'samples': [], 'client_results': [], 'origin_results': []})
    try:
        binary = Path(os.environ['SWIRL_RUST_HARNESS']).resolve(strict=True)
        with binary.open('rb') as source:
            digest = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        evidence['binary_sha256'] = digest.hexdigest()
        context, _, ca = certificates(folder.name)
        origin = SoakOrigin(state, context)
        relay = SoakRelay(origin.port, duration)
        host = V2Host()
        candidate = {'schema': 2, 'listen': '127.0.0.1:0',
                     'nodes': [{'id': NODE, 'outbound': {
                         'type': 'socks5', 'host': '127.0.0.1', 'port': relay.port,
                         'auth': {'username': USER, 'password': PASSWORD}}}],
                     'policy': {'schema': 2, 'mode': 'global', 'default_policy': {
                         'id': 'policy:default', 'target': {'kind': 'node', 'id': NODE}}},
                     'limits': {'max_connections': connections + 4, 'handshake_timeout_ms': 3000}}
        result = host.command(control_schema=2, op='start_v2', request_id=REQUEST,
                              store_id=STORE, saved_revision='1', candidate=candidate)
        assert result['ok'], 'CoreStartRejected'
        assert result['status']['configuration']['applied_mode'] == 'global', 'CoreMode'
        handle = int(result['handle'])
        port = int(result['status']['address'].rsplit(':', 1)[1])
        evidence['core_pid'] = host.process.pid

        def healthy():
            assert not state.errors, 'SoakWorkerFailure'
            assert not relay.errors and not origin.errors, 'SoakFixtureFailure'
            assert not relay.denied, 'SoakNodeAuthentication'

        def wait_for(predicate, limit, code):
            deadline = time.monotonic() + limit
            while True:
                healthy()
                if predicate():
                    return
                assert time.monotonic() < deadline, code
                time.sleep(0.02)

        def snapshot():
            response = host.command(op='snapshot', handle=handle)
            assert response['ok'], 'CoreSnapshotRejected'
            return response['status']

        def live_sample():
            healthy()
            status = snapshot()
            assert status['schema'] == 2 and status['running'], 'CoreNotRunning'
            assert status['active'] == connections, 'SoakConnectionInterrupted'
            assert status['accepted'] == connections, 'SoakReconnectOrExtraConnection'
            assert status['failed'] == 0 and status['rejected'] == 0, 'SoakCoreFailure'
            records = status['connections']
            assert len(records) == connections, 'SoakRecordCount'
            assert all(record['node'] == NODE and record['category'] == 'proxy'
                       and not record['ended'] and not record['error'] for record in records), 'SoakRouteOrEnd'
            elapsed = time.monotonic() - state.started_at
            evidence['samples'].append({'elapsed_seconds': round(elapsed, 3),
                                        'active': status['active'], 'accepted': status['accepted'],
                                        **linux_resources(host.process.pid)})

        for connection in range(connections):
            worker = threading.Thread(target=consume, args=(state, connection, port, origin.port, ca),
                                      name=f'soak-client-{connection}', daemon=True)
            workers.append(worker)
            worker.start()
        wait_for(lambda: len(state.ready) == connections, 25, 'SoakReadyDeadline')
        assert len(state.admitted) == connections, 'OriginAdmissionCount'
        state.started_at = time.monotonic()
        live_sample()
        state.start.set()
        end, next_sample = state.started_at + duration, state.started_at + 1
        while time.monotonic() < end:
            assert not state.abort.wait(max(0, min(next_sample, end) - time.monotonic())), 'SoakAborted'
            live_sample()
            next_sample = time.monotonic() + 1
        wait_for(lambda: len(state.delivered) == connections, 5, 'SoakFinalEventDeadline')
        live_sample()
        evidence['observed_stream_seconds'] = round(time.monotonic() - state.started_at, 6)
        assert evidence['observed_stream_seconds'] >= duration, 'SoakDurationTooShort'
        state.finish.set()
        wait_for(lambda: len(state.clients) == connections and len(state.origins) == connections,
                 12, 'SoakCloseDeadline')
        for worker in workers:
            worker.join(1)
            assert not worker.is_alive(), 'SoakClientDidNotStop'

        final = None

        def complete():
            nonlocal final
            final = snapshot()
            return (final['active'] == 0 and len(final['connections']) == connections
                    and all(record['ended'] for record in final['connections'])
                    and len(relay.connections) == connections
                    and all(peer['upload_eof'] and peer['download_eof'] for peer in relay.connections))

        wait_for(complete, 5, 'SoakCompletionDeadline')
        assert final['failed'] == 0 and final['rejected'] == 0, 'SoakFinalCoreFailure'
        assert final['accepted'] == connections, 'SoakFinalAcceptCount'
        assert all(record['node'] == NODE and record['category'] == 'proxy'
                   and record['ended'] and not record['error']
                   and record['upload'] > 0 and record['download'] > 0
                   for record in final['connections']), 'SoakFinalRecords'
        assert all(peer['host'] == TARGET and peer['port'] == origin.port
                   and peer['upload'] > 0 and peer['download'] > 0
                   for peer in relay.connections), 'SoakPeerRoute'
        assert final['upload'] == relay.upload and final['download'] == relay.download, 'SoakByteCounters'
        for connection in range(connections):
            expected = hashlib.sha256(b''.join(event_bytes(connection, sequence)
                                              for sequence in range(duration + 1))).hexdigest()
            assert state.clients[connection] == state.origins[connection], 'SoakPeerDigestMismatch'
            assert state.clients[connection]['sha256'] == expected, 'SoakExpectedDigestMismatch'
        evidence['client_results'] = [{'connection': key, **value} for key, value in sorted(state.clients.items())]
        evidence['origin_results'] = [{'connection': key, **value} for key, value in sorted(state.origins.items())]
        evidence['final_core'] = {'active': final['active'], 'accepted': final['accepted'],
                                  'failed': final['failed'], 'upload': final['upload'],
                                  'download': final['download'], 'ended_records': len(final['connections'])}
        assert host.command(op='stop', handle=handle)['ok'], 'CoreStopRejected'
        assert not host.command(op='snapshot', handle=handle)['ok'], 'CoreHandleSurvivedStop'
        handle = None
        try:
            unexpected = socket.create_connection(('127.0.0.1', port), timeout=0.5)
        except OSError:
            pass
        else:
            unexpected.close()
            raise AssertionError('CoreListenerSurvivedStop')
        evidence['listener_closed'] = True
        healthy()
    except Exception as error:
        state.fail(error, 'coordinator')
    finally:
        state.abort.set()
        state.start.set()
        state.finish.set()
        if host is not None and handle is not None:
            try:
                assert host.command(op='stop', handle=handle)['ok'], 'CleanupStopRejected'
            except Exception as error:
                state.fail(error, 'cleanup-stop')
        deadline = time.monotonic() + 10
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))
            if worker.is_alive():
                state.fail(AssertionError('CleanupClientStillRunning'), 'cleanup-client')
        for name, resource in [('relay', relay), ('origin', origin), ('core', host)]:
            if resource is not None:
                try:
                    resource.close()
                except Exception as error:
                    state.fail(error, 'cleanup-' + name)
        folder.cleanup()
        evidence['ready_connections'] = sorted(state.ready)
        evidence['delivered_connections'] = sorted(state.delivered)
        evidence['independent_fixture_errors'] = ((relay.errors if relay else [])
                                                 + (origin.errors if origin else []))
        evidence['errors'] = state.errors
        evidence['passed'] = not state.errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration-seconds', type=int, default=120)
    parser.add_argument('--connections', type=int, default=8)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 60 <= args.duration_seconds <= 3600:
        parser.error('--duration-seconds must be between 60 and 3600')
    if not 2 <= args.connections <= 64:
        parser.error('--connections must be between 2 and 64')
    evidence = {'schema': 1, 'test': 'production_v2_authenticated_socks5_verified_tls_sse_soak',
                'requested_duration_seconds': args.duration_seconds, 'connections': args.connections,
                'event_interval_seconds': 1, 'expected_events_per_connection': args.duration_seconds + 1,
                'peer_read_idle_budget_seconds': args.duration_seconds + 40,
                'client_origin_io_timeout_seconds': 8, 'core_handshake_timeout_ms': 3000,
                'reconnection_permitted': False, 'platform': sys.platform,
                'scope': 'controlled_local_network_no_desktop_acceptance',
                'resource_observation_limit': 'RSS and FD samples do not prove absence of leaks'}
    run(args.duration_seconds, args.connections, evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': evidence['passed'], 'connections': args.connections,
                      'observed_stream_seconds': evidence.get('observed_stream_seconds'),
                      'errors': evidence['errors']}), flush=True)
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
