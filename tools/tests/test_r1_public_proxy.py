"""Required, explicitly opted-in public evidence through native Shadowsocks.

Run this module explicitly with SWIRL_R1_PUBLIC_NETWORK=1,
SWIRL_RUST_HARNESS=<built swirl-api>, and SWIRL_R1_PUBLIC_REPORT=<JSON path>.
Missing prerequisites fail instead of producing a skipped/empty success.

Two independent Python AES-GCM peers authenticate synthetic nodes and forward
only to example.com:80 and www.gstatic.com:443. Raw sockets never consult
HTTP(S)_PROXY. This verifies a controlled node reaching public origins; it does
not claim private-provider, Windows UI, TUN or latency-comparison acceptance.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import queue
import socket
import socketserver
import ssl
import subprocess
import sys
import threading
import time
import unittest

from cryptography.exceptions import InvalidTag
from test_product_subscription_chain import Relay, Server, SsStream
from test_rust_core import public_verifier, target


PUBLIC_TARGETS = {('example.com', 80), ('www.gstatic.com', 443)}
TOTAL_SECONDS = 120
MAX_BODY = 128 * 1024
remaining = public_verifier.remaining
read_header = public_verifier.read_header


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def safe_error(error):
    # No exception message, request bytes, environment or node configuration.
    result = {'type': type(error).__name__}
    for key in ('errno', 'winerror'):
        value = getattr(error, key, None)
        if type(value) is int:
            result[key] = value
    if isinstance(error, AssertionError) and len(error.args) == 1:
        code = error.args[0]
        if isinstance(code, str) and code.isascii() and code.isalnum() and len(code) < 80:
            result['code'] = code
    return result


def exact(stream, count, deadline):
    result = bytearray()
    while len(result) < count:
        stream.settimeout(remaining(deadline, 8))
        data = stream.recv(count - len(result))
        if not data:
            raise EOFError('FixedPublicResponseClosed')
        result.extend(data)
    return bytes(result)


def line(stream, deadline, limit=8192):
    result = bytearray()
    while not result.endswith(b'\r\n'):
        require(len(result) < limit, 'PublicResponseLineLimit')
        result.extend(exact(stream, 1, deadline))
    return bytes(result)


def public_response(stream, deadline, expected, outcome):
    fields = read_header(stream, deadline).split(b'\r\n')
    status = fields[0].split(b' ', 2)
    require(len(status) >= 2 and status[0] in (b'HTTP/1.0', b'HTTP/1.1')
            and status[1].isdigit(), 'PublicStatusSyntax')
    code = int(status[1])
    outcome['http_status'] = code
    require(code == expected, 'PublicStatusUnexpected')
    headers = {}
    for field in fields[1:]:
        if not field:
            continue
        require(b':' in field, 'PublicHeaderSyntax')
        key, value = field.split(b':', 1)
        key, value = key.lower(), value.strip().lower()
        if key in (b'content-length', b'transfer-encoding'):
            require(key not in headers or headers[key] == value, 'PublicFramingAmbiguous')
            headers[key] = value
    if code == 204:
        require(headers.get(b'content-length', b'0') == b'0'
                and b'transfer-encoding' not in headers, 'Public204HasBody')
        return code, b''
    body = bytearray()
    if b'transfer-encoding' in headers:
        require(headers[b'transfer-encoding'] == b'chunked'
                and b'content-length' not in headers, 'PublicTransferEncodingUnsupported')
        while True:
            size = line(stream, deadline, 128)[:-2].split(b';', 1)[0]
            require(size and all(byte in b'0123456789abcdefABCDEF' for byte in size),
                    'PublicChunkSizeInvalid')
            count = int(size, 16)
            require(count <= MAX_BODY - len(body), 'PublicBodyLimit')
            if not count:
                trailers = 0
                while True:
                    trailer = line(stream, deadline)
                    trailers += len(trailer)
                    require(trailers <= 8192, 'PublicTrailerLimit')
                    if trailer == b'\r\n':
                        break
                break
            body.extend(exact(stream, count, deadline))
            require(exact(stream, 2, deadline) == b'\r\n', 'PublicChunkTerminator')
    elif b'content-length' in headers:
        length = headers[b'content-length']
        require(length.isdigit() and len(length) <= 8, 'PublicContentLengthInvalid')
        count = int(length)
        require(count <= MAX_BODY, 'PublicBodyLimit')
        body.extend(exact(stream, count, deadline))
    else:
        while True:
            stream.settimeout(remaining(deadline, 8))
            data = stream.recv(8192)
            if not data:
                break
            require(len(data) <= MAX_BODY - len(body), 'PublicBodyLimit')
            body.extend(data)
    return code, bytes(body)


def resolve_public_targets(deadline):
    # getaddrinfo has no Python cancellation deadline. Isolate each fixed-host
    # lookup in a bounded child so a broken resolver cannot hang the CI job.
    script = ('import json,socket,sys\n'
              'try:\n'
              ' rows=[(v[0],v[4][0]) for v in socket.getaddrinfo(sys.argv[1],None,type=socket.SOCK_STREAM)]\n'
              ' print(json.dumps({"ok":True,"addresses":rows}))\n'
              'except OSError as error:\n'
              ' print(json.dumps({"ok":False,"errno":error.errno}))\n')
    endpoints, evidence = {}, []
    for host, port in sorted(PUBLIC_TARGETS):
        result = subprocess.run([sys.executable, '-c', script, host], capture_output=True,
                                text=True, timeout=remaining(deadline, 10), check=True)
        require(len(result.stdout) <= 16384, 'PublicDnsAnswerLimit')
        answer = json.loads(result.stdout)
        if not answer.get('ok'):
            raise socket.gaierror(answer.get('errno'), 'PublicDnsLookupFailed')
        addresses = []
        for family, address in answer['addresses']:
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            require(ipaddress.ip_address(address).is_global, 'PublicDnsReturnedNonPublicAddress')
            item = (family, address)
            if item not in addresses:
                addresses.append(item)
        # Prefer IPv4 for this Windows x64 product gate; permit IPv6 if no A
        # answer exists. At most two connect attempts are possible per request.
        addresses.sort(key=lambda item: item[0] != socket.AF_INET)
        require(bool(addresses), 'PublicDnsHasNoUsableAddress')
        endpoints[(host, port)] = addresses[:2]
        evidence.append({'host': host, 'port': port, 'resolved': True,
                         'connect_candidate_count': len(endpoints[(host, port)]),
                         'resolution_owner': 'independent-node'})
    return endpoints, evidence


class PublicShadowsocksRelay(Relay):
    """Relay's node/document API with a separate, fixed public destination policy.

    The original Relay deliberately permits only loopback origins. Reuse its
    independent SsStream/Server primitives without weakening that old policy.
    """
    def __init__(self, identity, endpoints, deadline):
        self.protocol, self.identity = 'ss', identity
        self.password = 'r1-synthetic-public-' + identity
        self.cipher = 'aes-128-gcm'
        self.connections, self.denied, self.errors = [], [], []
        self.upload, self.download = 0, 0
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.live_sockets, self.workers = set(), set()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                wire, upstream, event, uploader = self.request, None, None, None
                with owner.lock:
                    owner.live_sockets.add(wire)
                    owner.workers.add(threading.current_thread())
                try:
                    wire.settimeout(remaining(deadline, 8))
                    stream = SsStream(wire, owner.cipher, owner.password)
                    destination = target(stream)  # AEAD tags verify before target parsing.
                    require(destination in PUBLIC_TARGETS, 'PublicRelayDestinationDenied')
                    host, port = destination
                    for family, address in endpoints[destination]:
                        candidate = socket.socket(family, socket.SOCK_STREAM)
                        candidate.settimeout(remaining(deadline, 8))
                        try:
                            candidate.connect((address, port))
                            upstream = candidate
                            break
                        except OSError:
                            candidate.close()
                    require(upstream is not None, 'PublicRelayTargetConnectionFailed')
                    with owner.lock:
                        owner.live_sockets.add(upstream)
                        event = {'peer': identity, 'host': host, 'port': port,
                                 'authenticated': True, 'upload': 0, 'download': 0,
                                 'closed': False}
                        owner.connections.append(event)

                    def upload():
                        try:
                            while data := stream.recv(8191):
                                upstream.settimeout(remaining(deadline, 8))
                                upstream.sendall(data)
                                with owner.lock:
                                    owner.upload += len(data)
                                    event['upload'] += len(data)
                        except Exception as error:
                            if not owner.stopped.is_set():
                                owner.errors.append({'phase': 'upload', **safe_error(error)})
                        finally:
                            try:
                                upstream.shutdown(socket.SHUT_WR)
                            except OSError:
                                pass

                    uploader = threading.Thread(target=upload, daemon=True)
                    uploader.start()
                    while True:
                        upstream.settimeout(remaining(deadline, 8))
                        data = upstream.recv(8191)
                        if not data:
                            break
                        wire.settimeout(remaining(deadline, 8))
                        stream.sendall(data)
                        with owner.lock:
                            owner.download += len(data)
                            event['download'] += len(data)
                    wire.shutdown(socket.SHUT_WR)
                    uploader.join(remaining(deadline, 8))
                    require(not uploader.is_alive(), 'PublicRelayUploaderDidNotStop')
                    event['closed'] = True
                except InvalidTag:
                    owner.denied.append('Authentication')
                except Exception as error:
                    if not owner.stopped.is_set():
                        owner.errors.append({'phase': 'relay', **safe_error(error)})
                finally:
                    for resource in (wire, upstream):
                        if resource is not None:
                            try:
                                resource.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                            resource.close()
                            with owner.lock:
                                owner.live_sockets.discard(resource)
                    if uploader is not None:
                        uploader.join(1)
                    with owner.lock:
                        owner.workers.discard(threading.current_thread())

        self.server = Server(('127.0.0.1', 0), Handler)
        self.server.errors = self.errors
        self.server.fixture_kind = 'r1-public-ss-' + identity
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def outbound(self):
        return {'type': 'shadowsocks', 'host': '127.0.0.1', 'port': self.port,
                'password': self.password, 'cipher': self.cipher, 'udp': False}

    def close(self):
        self.stopped.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)
        with self.lock:
            resources, workers = list(self.live_sockets), list(self.workers)
        for resource in resources:
            try:
                resource.shutdown(socket.SHUT_RDWR)
                resource.close()
            except OSError:
                pass
        for worker in workers:
            worker.join(1)
        require(not self.thread.is_alive() and not any(worker.is_alive() for worker in workers),
                'PublicRelayDidNotStop')


class BoundedControl:
    def __init__(self, harness):
        environment = {key: value for key, value in os.environ.items()
                       if key.lower() not in ('http_proxy', 'https_proxy', 'all_proxy')}
        self.process = subprocess.Popen([str(harness)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, env=environment)
        self.replies = queue.Queue(maxsize=4)
        self.usable = True

        def reader():
            try:
                while True:
                    value = self.process.stdout.readline(65537)
                    if not value or len(value) > 65536 or not value.endswith('\n'):
                        self.replies.put_nowait(None)
                        return
                    self.replies.put_nowait(value)
            except (OSError, ValueError, queue.Full):
                return

        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()

    def command(self, deadline, **value):
        require(self.usable, 'NativeControlUnavailable')
        encoded = json.dumps(value) + '\n'
        require(len(encoded.encode()) < 4096, 'NativeControlCommandLimit')
        try:
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
            reply = self.replies.get(timeout=remaining(deadline, 6))
            require(reply is not None, 'NativeControlClosed')
            result = json.loads(reply)
            require(isinstance(result, dict), 'NativeControlInvalidReply')
            return result
        except Exception:
            self.usable = False
            raise

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
            raise AssertionError('NativeControlShutdownTimeout')
        finally:
            self.reader.join(1)
            if not self.reader.is_alive():
                self.process.stdout.close()
        require(self.process.returncode == 0 and not self.reader.is_alive(), 'NativeControlExitFailed')


def request(port, kind, deadline, result):
    host, target_port = ('example.com', 80) if kind == 'http' else ('www.gstatic.com', 443)
    path = '/' if kind == 'http' else '/generate_204'
    expected = 200 if kind == 'http' else 204
    result.update(inbound=kind, host=host, port=target_port, path=path,
                  expected_status=expected, success=False, certificate_verified=False,
                  stage='local-connection')
    stream = socket.create_connection(('127.0.0.1', port), timeout=remaining(deadline, 8))
    try:
        stream.settimeout(remaining(deadline, 8))
        result['stage'] = 'inbound-handshake'
        if kind == 'connect':
            authority = f'{host}:{target_port}'
            stream.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
            require(read_header(stream, deadline).startswith(b'HTTP/1.1 200 '), 'NativeConnectRejected')
        elif kind == 'socks5':
            stream.sendall(b'\x05\x01\x00')
            require(exact(stream, 2, deadline) == b'\x05\x00', 'NativeSocksGreetingRejected')
            name = host.encode('ascii')
            stream.sendall(b'\x05\x01\x00\x03' + bytes([len(name)]) + name + target_port.to_bytes(2, 'big'))
            require(exact(stream, 3, deadline) == b'\x05\x00\x00', 'NativeSocksConnectRejected')
            target(stream)
        if kind != 'http':
            result['stage'] = 'origin-tls'
            context = ssl.create_default_context()
            context.set_alpn_protocols(['http/1.1'])
            stream = context.wrap_socket(stream, server_hostname=host,
                                         do_handshake_on_connect=False, suppress_ragged_eofs=False)
            stream.settimeout(remaining(deadline, 8))
            stream.do_handshake()
            result['certificate_verified'] = True
            result['tls_version'] = stream.version()
        request_target = f'http://{host}{path}' if kind == 'http' else path
        result['stage'] = 'public-response'
        # Initiate TLS shutdown after the complete 204 instead of relying on
        # an HTTP Connection:close server policy. Missing close_notify remains
        # an error: suppress_ragged_eofs=False and strict unwrap are unchanged.
        connection = 'close' if kind == 'http' else 'keep-alive'
        result['connection_policy'] = connection
        stream.sendall(f'GET {request_target} HTTP/1.1\r\nHost: {host}\r\nConnection: {connection}\r\n\r\n'.encode())
        code, body = public_response(stream, deadline, expected, result)
        result['stage'] = 'origin-close'
        if kind == 'http':
            require(b'Example Domain' in body, 'PublicHttpBodyUnexpected')
            stream.shutdown(socket.SHUT_WR)
            stream.settimeout(remaining(deadline, 8))
            require(stream.recv(1) == b'', 'PublicHttpTrailingData')
        else:
            public_verifier.close_https(stream, deadline)
        result.update(http_status=code, body_bytes=len(body),
                      body_sha256=hashlib.sha256(body).hexdigest(), orderly_close=True, success=True,
                      stage='complete')
        return result
    finally:
        stream.close()


class R1PublicProxyTests(unittest.TestCase):
    def test_shadowsocks_public_http_https_socks5_and_switch(self):
        require(os.environ.get('SWIRL_R1_PUBLIC_NETWORK') == '1', 'PublicNetworkOptInRequired')
        require(bool(os.environ.get('SWIRL_RUST_HARNESS')), 'CompiledNativeHarnessRequired')
        require(bool(os.environ.get('SWIRL_R1_PUBLIC_REPORT')), 'PublicEvidenceOutputRequired')
        harness = Path(os.environ['SWIRL_RUST_HARNESS']).resolve(strict=True)
        output = Path(os.environ['SWIRL_R1_PUBLIC_REPORT']).resolve()
        started = time.monotonic()
        deadline = started + TOTAL_SECONDS
        work_deadline = deadline - 10
        repository = Path(__file__).resolve().parents[2]
        report = {'schema': 1, 'success': False, 'platform': platform.system(),
                  'scope': 'controlled-independent-SS-nodes-to-public-origins',
                  'private_subscription_tested': False, 'environment_proxy_used': False,
                  'cipher': 'aes-128-gcm', 'requests': [], 'cleanup': {},
                  'harness_sha256': hashlib.sha256(harness.read_bytes()).hexdigest()}
        peers, control, handle, local_port = [], None, None, None
        failure = None
        phase = 'identity'
        try:
            report['source_sha'] = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repository,
                capture_output=True, text=True, check=True, timeout=5).stdout.strip()
            paths = ['core', 'tools/tests/test_r1_public_proxy.py',
                     'tools/tests/test_product_subscription_chain.py',
                     'tools/tests/test_shadowsocks.py', 'tools/tests/test_rust_core.py',
                     'tools/Verify-PublicRustCore.py']
            status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal', '--', *paths],
                cwd=repository, capture_output=True, check=True, text=True, timeout=5)
            report['tested_worktree_clean'] = not status.stdout.strip()
            report['fixture_sha256'] = {name: hashlib.sha256((repository / name).read_bytes()).hexdigest()
                                       for name in paths[1:]}
            phase = 'public-dns'
            endpoints, report['dns'] = resolve_public_targets(work_deadline)
            for name in ('A', 'B'):
                peers.append(PublicShadowsocksRelay(name, endpoints, work_deadline))
            control = BoundedControl(harness)
            # Reuse the reviewed isolated-outbound schema. Its selected node is
            # mandatory and no DIRECT node or fallback exists in this fixture.
            config = public_verifier.probe_configuration(outbound=peers[0].outbound())
            config.update(selected='A', nodes=[{'id': peer.identity, 'outbound': peer.outbound()} for peer in peers])
            phase = 'native-start'
            response = control.command(work_deadline, op='start', config=config)
            require(response.get('ok') is True, 'NativeStartRejected')
            handle = response['handle']
            state = response['status']
            require(state.get('engine') == 'swirl-rust' and state.get('selected') == 'A', 'NativeIdentityMismatch')
            address, local_port = state['address'].rsplit(':', 1)
            require(address == '127.0.0.1', 'NativeListenerNotLoopback')
            local_port = int(local_port)
            require(0 < local_port < 65536, 'NativeListenerPortInvalid')
            report['engine'] = state['engine']
            for peer in peers:
                if peer.identity == 'B':
                    phase = 'node-switch'
                    selected = control.command(work_deadline, op='select', handle=handle, id='B')
                    require(selected.get('ok') is True, 'NativeNodeSwitchRejected')
                    snapshot = control.command(work_deadline, op='snapshot', handle=handle)
                    require(snapshot.get('ok') is True and snapshot['status']['selected'] == 'B',
                            'NativeNodeSwitchNotApplied')
                    report['node_switch_verified'] = True
                for kind in ('http', 'connect', 'socks5'):
                    phase = peer.identity + '-' + kind
                    before = [len(value.connections) for value in peers]
                    result = {'node': peer.identity}
                    report['requests'].append(result)
                    request(local_port, kind, work_deadline, result)
                    outcome = {}
                    settled = public_verifier.settled_snapshot(control.command, handle, work_deadline, outcome)
                    require(settled['failed'] == 0 and not settled['last_error']
                            and not settled['last_error_stage'], 'NativePublicRelayFailure')
                    after = [len(value.connections) for value in peers]
                    expected_counts = list(before)
                    expected_counts[0 if peer.identity == 'A' else 1] += 1
                    require(after == expected_counts, 'WrongIndependentNodeUsed')
                    event = peer.connections[-1]
                    require(event['host'] == result['host'] and event['port'] == result['port']
                            and event['authenticated'] and event['upload'] > 0 and event['download'] > 0,
                            'IndependentAuthOrTrafficMissing')
                    report['core'] = settled
            phase = 'accounting'
            peer_deadline = min(work_deadline, time.monotonic() + 5)
            while any(peer.workers for peer in peers) and time.monotonic() < peer_deadline:
                time.sleep(min(0.02, remaining(peer_deadline, 0.02)))
            require(report['core']['accepted'] == 6 and report['core']['recorded_connections'] == 6
                    and report['core']['active'] == 0 and report['core']['upload'] > 0
                    and report['core']['download'] > 0, 'NativeTrafficAccountingInvalid')
            require(all(len(peer.connections) == 3 and not peer.errors and not peer.denied for peer in peers),
                    'IndependentPeerFailure')
            require(all(not peer.workers and all(event['closed'] for event in peer.connections) for peer in peers),
                    'IndependentPeerConnectionsNotSettled')
        except Exception as error:
            failure = error
            report['failure_phase'] = phase
            report['failure'] = safe_error(error)
        finally:
            if control is not None and handle is not None and control.usable:
                try:
                    require(control.command(deadline - 3, op='stop', handle=handle).get('ok') is True,
                            'NativeStopRejected')
                    report['cleanup']['native_stopped'] = True
                except Exception as error:
                    report['cleanup']['native_stop_error'] = safe_error(error)
                    failure = failure or error
            if control is not None:
                try:
                    control.close()
                    report['cleanup']['process_exited'] = True
                except Exception as error:
                    report['cleanup']['process_error'] = safe_error(error)
                    failure = failure or error
            if local_port is not None:
                try:
                    with socket.socket() as released:
                        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                            released.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                        else:
                            released.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        released.bind(('127.0.0.1', local_port))
                        released.listen(1)
                    report['cleanup']['listener_released'] = True
                except OSError as error:
                    report['cleanup']['listener_error'] = safe_error(error)
                    failure = failure or error
            for peer in peers:
                try:
                    peer.close()
                except Exception as error:
                    report['cleanup']['peer_' + peer.identity + '_error'] = safe_error(error)
                    failure = failure or error
            report['peers'] = [{'identity': peer.identity, 'authenticated_connections': peer.connections,
                                'upload': peer.upload, 'download': peer.download,
                                'errors': peer.errors, 'denied': peer.denied} for peer in peers]
            report['elapsed_ms'] = round((time.monotonic() - started) * 1000)
            report['success'] = failure is None and len(report['requests']) == 6
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        self.assertTrue(report['success'], json.dumps({key: report.get(key) for key in
                        ('failure_phase', 'failure', 'cleanup')}, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
