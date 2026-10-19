"""Diagnostic: an authenticated TLS response followed by raw EOF is not TLS close.

Uses the final repository Origin fixture, a real synthetic subscription through
the Rust inspector/runtime, and an independent HTTP CONNECT relay. The expected
fixture assertion is captured explicitly; it is never suppressed in source.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time

ROOT = Path('/workspace/scratch/ca6cd1f88f6f/Swirl')
EVIDENCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/tests'))
from test_product_subscription_chain import BODY, Harness, Origin, Relay, certificates, exact, header

os.environ['SWIRL_RUST_HARNESS'] = str(ROOT / '.local-runtime/target/release/swirl-api')
os.environ['SWIRL_RUST_INSPECTOR'] = str(ROOT / '.local-runtime/target/release/swirl-inspect')


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, 'DiagnosticDeadlineExceeded'
        time.sleep(.002)


def run():
    with tempfile.TemporaryDirectory(prefix='swirl-tls-truncation-') as folder:
        context, _, ca_pem = certificates(folder)
        origin = Origin(context=context, client_closes_tls=True)
        relay = Relay('http', 'A', [origin.port])
        core = Harness()
        handle = None
        try:
            inspected = subprocess.run([os.environ['SWIRL_RUST_INSPECTOR'], '--private-json'],
                                       input=relay.document(), capture_output=True,
                                       text=True, timeout=8)
            assert inspected.returncode == 0
            parsed = json.loads(inspected.stdout)
            assert parsed['report']['parsed'] and parsed['report']['original_preserved']
            assert len(parsed['tcpCandidates']) == 1 and parsed['tcpCandidates'][0]
            started = core.command(op='start', config={
                'schema': 1, 'listen': '127.0.0.1:0', 'selected': 'A',
                'nodes': [{'id': 'A', 'outbound': parsed['tcpCandidates'][0]}]})
            assert started['ok']
            handle = started['handle']
            proxy_port = int(started['status']['address'].rsplit(':', 1)[1])
            wire = socket.create_connection(('127.0.0.1', proxy_port), timeout=8)
            authority = f'localhost:{origin.port}'.encode()
            wire.sendall(b'CONNECT ' + authority + b' HTTP/1.1\r\nHost: ' + authority + b'\r\n\r\n')
            assert header(wire).startswith(b'HTTP/1.1 200 ')
            client_context = ssl.create_default_context(cadata=ca_pem)
            secure = client_context.wrap_socket(wire, server_hostname='localhost',
                                                suppress_ragged_eofs=False)
            secure.sendall(b'GET /truncate-after-body HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            response = header(secure)
            expected = BODY + b':/truncate-after-body'
            assert response.startswith(b'HTTP/1.1 200 OK\r\n')
            assert b'Content-Length: ' + str(len(expected)).encode() in response
            assert exact(secure, len(expected)) == expected
            # Detach bypasses SSL shutdown deliberately: the server receives
            # TCP FIN without any client TLS close_notify record.
            truncated = socket.socket(fileno=secure.detach())
            truncated.shutdown(socket.SHUT_WR)
            truncated.close()
            wait_for(lambda: len(origin.errors) == 1)
            assert origin.errors[0]['type'] == 'SSLEOFError'
            assert origin.errors[0]['errno'] == ssl.SSL_ERROR_EOF
            assert origin.tls_closed == 0
            assert len(origin.requests) == 1 and origin.sni == ['localhost']
            assert [(event['host'], event['port']) for event in relay.connections] == [('localhost', origin.port)]
            wait_for(lambda: core.command(op='snapshot', handle=handle)['status']['active'] == 0)
            assert not relay.errors and not relay.denied
            assert core.command(op='stop', handle=handle)['ok']
            handle = None
            result = {
                'scope': 'Linux Python SSL negative diagnostic through real Rust and independent HTTP relay',
                'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source_fixture_module_sha256': hashlib.sha256((ROOT / 'tools/tests/test_product_subscription_chain.py').read_bytes()).hexdigest(),
                'passed': True, 'tls_certificate_verified': True, 'origin_http_count': len(origin.requests),
                'raw_truncation_rejected': True, 'origin_tls_closed': origin.tls_closed,
                'expected_fixture_errors': origin.errors, 'relay_errors': relay.errors,
                'relay_connections': [{key: value for key, value in event.items() if key != 'prefix'}
                                      for event in relay.connections]}
        finally:
            if handle is not None:
                assert core.command(op='stop', handle=handle)['ok']
            core.close()
            relay.close()
            try:
                origin.close()
            except AssertionError:
                # The unmodified fixture MUST fail its cleanup for truncation.
                assert len(origin.errors) == 1 and origin.errors[0]['type'] == 'SSLEOFError'
            else:
                raise AssertionError('BareTcpEofWasAcceptedAsTlsClose')
        return result


if __name__ == '__main__':
    result = run()
    (EVIDENCE / 'tls-truncation-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
