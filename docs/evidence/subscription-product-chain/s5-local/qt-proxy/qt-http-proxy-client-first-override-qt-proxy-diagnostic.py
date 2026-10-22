"""Local diagnostic only: Qt TLS client -> Rust -> independent relay -> HTTPS.

This script does not exercise Windows DPAPI, C++ compilation, or GUI import.
It imports synthetic subscription documents with the real Rust inspector.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import ssl
import subprocess
import sys
import tempfile
import time

REPOSITORY = Path('/workspace/scratch/ca6cd1f88f6f/Swirl')
EVIDENCE = Path(__file__).resolve().parent
sys.path.insert(0, '/tmp/swirl-qt-tls-repro')
sys.path.insert(0, str(REPOSITORY / 'tools/tests'))
from PySide6.QtCore import QCoreApplication, qVersion
from PySide6.QtNetwork import QAbstractSocket, QNetworkProxy, QSslCertificate, QSslConfiguration, QSslError, QSslSocket
from PySide6.QtTest import QTest
import shiboken6
from test_product_subscription_chain import BODY, Harness, Origin, Relay, certificates

os.environ['SWIRL_RUST_HARNESS'] = str(REPOSITORY / '.local-runtime/target/release/swirl-api')
os.environ['SWIRL_RUST_INSPECTOR'] = str(REPOSITORY / '.local-runtime/target/release/swirl-inspect')
app = QCoreApplication([])
PROXY_MODE = os.environ.get('SWIRL_QT_PROXY_MODE', 'explicit-connect')
CLOSE_DIRECTION = os.environ.get('SWIRL_QT_CLOSE_DIRECTION', 'server-first')
if CLOSE_DIRECTION == 'client-first':
    original_unwrap = ssl.SSLSocket.unwrap

    def client_first_unwrap(stream):
        stream.suppress_ragged_eofs = False
        assert stream.recv(1) == b'', 'ExpectedAuthenticatedClientTlsEof'
        return original_unwrap(stream)

    ssl.SSLSocket.unwrap = client_first_unwrap


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, 'DiagnosticDeadlineExceeded'
        QTest.qWait(1)
        time.sleep(0.001)  # Allow the separate Python fixture threads to run.


def connection(proxy_port, host, target_port, ca_pem, negative=False):
    stream = QSslSocket()
    tls = QSslConfiguration.defaultConfiguration()
    tls.setCaCertificates(QSslCertificate.fromData(ca_pem.encode()))
    tls.setPeerVerifyMode(QSslSocket.VerifyPeer)
    stream.setSslConfiguration(tls)
    try:
        if PROXY_MODE == 'explicit-connect':
            stream.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
            stream.connectToHost('127.0.0.1', proxy_port)
            wait_for(lambda: stream.state() == QAbstractSocket.ConnectedState)
            authority = f'{host}:{target_port}'.encode()
            message = b'CONNECT ' + authority + b' HTTP/1.1\r\nHost: ' + authority + b'\r\n\r\n'
            assert stream.write(message) == len(message)
            handshake = bytearray()

            def connected():
                handshake.extend(bytes(stream.readAll()))
                assert len(handshake) <= 65536
                return b'\r\n\r\n' in handshake

            wait_for(connected)
            assert handshake.startswith(b'HTTP/1.1 200 ')
            assert handshake.endswith(b'\r\n\r\n')
            stream.setPeerVerifyName(host)
            stream.startClientEncryption()
        else:
            assert PROXY_MODE == 'qt-http-proxy'
            stream.setProxy(QNetworkProxy(QNetworkProxy.HttpProxy, '127.0.0.1', proxy_port))
            stream.connectToHostEncrypted(host, target_port)
        wait_for(lambda: stream.isEncrypted() or stream.state() == QAbstractSocket.UnconnectedState)
        if negative:
            assert not stream.isEncrypted(), 'WrongNameWasAccepted'
            assert stream.error() == QAbstractSocket.SslHandshakeFailedError
            assert any(error.error() == QSslError.HostNameMismatch for error in stream.sslHandshakeErrors())
            return {'tls_verified': False, 'error': 'SslHandshakeFailedError',
                    'verification_error': 'HostNameMismatch', 'http_sent': False}
        assert stream.isEncrypted(), str(stream.error())
        target = b'/through-qt-proxy'
        message = b'GET ' + target + b' HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'
        assert stream.write(message) == len(message)
        response = bytearray()
        expected = BODY + b':' + target

        def complete():
            response.extend(bytes(stream.readAll()))
            assert len(response) <= 65536
            return b'\r\n\r\n' in response and response.endswith(expected)

        wait_for(complete)
        headers, body = bytes(response).split(b'\r\n\r\n', 1)
        assert headers.startswith(b'HTTP/1.1 200 OK\r\n')
        assert body == expected
        stream.disconnectFromHost()
        wait_for(lambda: stream.state() == QAbstractSocket.UnconnectedState)
        return {'tls_verified': True, 'http_sent': True, 'http_status': 200,
                'body': body.decode(), 'socket_state': 'UnconnectedState'}
    finally:
        shiboken6.delete(stream)


def run_protocol(protocol):
    with tempfile.TemporaryDirectory(prefix='swirl-local-qt-proxy-') as folder:
        context, _, ca_pem = certificates(folder)
        origin = Origin(context=context)
        relay = Relay(protocol, 'A', [origin.port])
        core = Harness()
        handle = None
        try:
            document = relay.document()
            inspector = subprocess.run([os.environ['SWIRL_RUST_INSPECTOR'], '--private-json'],
                                       input=document, text=True, capture_output=True, timeout=8)
            assert inspector.returncode == 0
            parsed = json.loads(inspector.stdout)
            assert parsed['report']['parsed'] and parsed['report']['original_preserved']
            assert len(parsed['tcpCandidates']) == 1 and parsed['tcpCandidates'][0] is not None
            config = {'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'A',
                      'nodes': [{'id': 'A', 'outbound': parsed['tcpCandidates'][0]}]}
            started = core.command(op='start', config=config)
            assert started['ok']
            handle = started['handle']
            proxy_port = int(started['status']['address'].rsplit(':', 1)[1])
            positive = connection(proxy_port, 'localhost', origin.port, ca_pem)
            wait_for(lambda: origin.tls_closed == 1)
            assert len(origin.requests) == 1 and not origin.errors
            assert [(event['host'], event['port']) for event in relay.connections] == [('localhost', origin.port)]
            negative = connection(proxy_port, 'wrong.fixture.invalid', origin.port, ca_pem, negative=True)
            wait_for(lambda: len(relay.connections) == 2)
            assert len(origin.requests) == 1
            assert origin.sni == ['localhost', 'wrong.fixture.invalid']
            assert origin.tls_closed == 1 and not origin.errors
            assert [(event['host'], event['port']) for event in relay.connections] == [
                ('localhost', origin.port), ('wrong.fixture.invalid', origin.port)]
            wait_for(lambda: core.command(op='snapshot', handle=handle)['status']['active'] == 0)
            assert not relay.errors and not relay.denied
            assert core.command(op='stop', handle=handle)['ok']
            handle = None
            result = {'protocol': protocol, 'status': 'passed', 'parsed_subscription': True,
                      'positive': positive, 'negative': negative,
                      'origin_http_count': len(origin.requests), 'origin_sni': origin.sni,
                      'origin_tls_closed': origin.tls_closed, 'origin_errors': origin.errors,
                      'relay_errors': relay.errors,
                      'relay_connections': [{key: value for key, value in event.items() if key != 'prefix'}
                                            for event in relay.connections]}
        except Exception:
            snapshot = {'protocol': protocol, 'origin_http_count': len(origin.requests),
                        'origin_sni': origin.sni, 'origin_tls_closed': origin.tls_closed,
                        'origin_errors': origin.errors, 'relay_errors': relay.errors,
                        'relay_connections': [{key: value for key, value in event.items() if key != 'prefix'}
                                              for event in relay.connections]}
            print(json.dumps({'failure_snapshot': snapshot}), flush=True)
            raise
        finally:
            if handle is not None:
                assert core.command(op='stop', handle=handle)['ok']
            core.close()
            relay.close()
            origin.close()
        return result


if __name__ == '__main__':
    metadata = {'scope': 'Linux PySide QtNetwork -> Rust harness -> independent relay -> HTTPS; diagnostic only, not Windows DPAPI/C++ product acceptance',
                'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY, text=True).strip(),
                'qt_version': qVersion(), 'qt_ssl_backend': QSslSocket.activeBackend(),
                'proxy_mode': PROXY_MODE,
                'diagnostic_fixture_close_direction': CLOSE_DIRECTION,
                'source_fixture_module_sha256': hashlib.sha256((REPOSITORY / 'tools/tests/test_product_subscription_chain.py').read_bytes()).hexdigest(),
                'qt_ssl_library': QSslSocket.sslLibraryVersionString(),
                'python_version': platform.python_version(), 'system': platform.system(),
                'rust_binary_sha256': {name: hashlib.sha256((REPOSITORY / '.local-runtime/target/release' / name).read_bytes()).hexdigest()
                                       for name in ('swirl-api', 'swirl-inspect')}}
    results = []
    try:
        for protocol in ('http', 'socks5', 'ss', 'vless'):
            result = run_protocol(protocol)
            results.append(result)
            print(json.dumps(result), flush=True)
        metadata.update(passed=True, cases=results)
    except Exception as error:
        metadata.update(passed=False, cases=results, error_type=type(error).__name__)
        raise
    finally:
        (EVIDENCE / 'result.json').write_text(json.dumps(metadata, indent=2) + '\n')
