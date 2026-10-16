"""Independent Python socket/TLS peers exercise the compiled Rust control harness.

Requires Python cryptography only for generating ephemeral test certificates.
No credentials, subscription providers or complete proxy cores are used.
Set SWIRL_RUST_HARNESS to the built swirl-api executable.
"""
import base64
import concurrent.futures
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def exact(s, n):
    data = b''
    while len(data) < n:
        part = s.recv(n-len(data))
        if not part:
            raise EOFError()
        data += part
    return data


def header(s):
    data = b''
    while not data.endswith(b'\r\n\r\n'):
        data += exact(s, 1)
        if len(data) > 16384:
            raise ValueError('header limit')
    return data


def target(s):
    kind = exact(s, 1)[0]
    if kind == 1:
        host = socket.inet_ntop(socket.AF_INET, exact(s, 4))
    elif kind == 4:
        host = socket.inet_ntop(socket.AF_INET6, exact(s, 16))
    elif kind == 3:
        host = exact(s, exact(s, 1)[0]).decode()
    else:
        raise ValueError('address type')
    return host, int.from_bytes(exact(s, 2), 'big')


def certificates(folder):
    now = datetime.datetime.now(datetime.timezone.utc)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Swirl synthetic CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
          .not_valid_after(now+datetime.timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),False)
          .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,encipher_only=None,decipher_only=None),True)
          .sign(key, hashes.SHA256()))
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')]))
            .issuer_name(name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(days=1)).not_valid_after(now+datetime.timedelta(days=2))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()),False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = Path(folder)/'leaf.pem', Path(folder)/'leaf.key'
    cert_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    context.set_alpn_protocols(['http/1.1'])
    return context, base64.b64encode(ca.public_bytes(serialization.Encoding.DER)).decode(), ca.public_bytes(serialization.Encoding.PEM).decode()


class Reference(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    def handle_error(self, request, address):
        self.errors.append('ReferenceHandlerFailed')


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        s = self.request
        s.settimeout(6)
        if self.server.tls:
            try:
                s = self.server.tls.wrap_socket(s, server_side=True)
            except ssl.SSLError:
                return  # Expected in invalid certificate/name cases.
        with s:
            try:
                protocol = self.server.protocol
                if protocol == 'socks5':
                    assert exact(s, 3) == b'\x05\x01\x02'
                    s.sendall(b'\x05\x02')
                    assert exact(s, 1) == b'\x01'
                    user = exact(s, exact(s, 1)[0])
                    password = exact(s, exact(s, 1)[0])
                    if (user, password) != (b'fixture-user', b'fixture-password'):
                        s.sendall(b'\x01\x01'); return
                    s.sendall(b'\x01\x00')
                    assert exact(s, 3) == b'\x05\x01\x00'
                    destination = target(s)
                    s.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
                elif protocol == 'http_connect':
                    data = header(s)
                    self.server.requests.append(data)
                    required = b'Proxy-Authorization: Basic '+base64.b64encode(b'fixture-user:fixture-password')
                    if required not in data:
                        s.sendall(b'HTTP/1.1 407 Denied\r\nContent-Length: 0\r\n\r\n'); return
                    destination = ('synthetic', 1)
                    s.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                elif protocol == 'trojan':
                    password_hash = exact(s, 56)
                    if password_hash != hashlib.sha224(b'fixture-password').hexdigest().encode():
                        return
                    assert exact(s, 3) == b'\r\n\x01'
                    destination = target(s)
                    assert exact(s, 2) == b'\r\n'
                elif protocol == 'http-origin':
                    data = header(s); self.server.requests.append(data)
                    if data.startswith(b'GET /ws '):
                        s.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
                    elif data.startswith(b'GET /sse '):
                        s.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n')
                        for body in (b'data: before\n\n', b'data: after\n\n'):
                            s.sendall(f'{len(body):x}\r\n'.encode()+body+b'\r\n'); time.sleep(0.15)
                        s.sendall(b'0\r\n\r\n'); return
                    else:
                        s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 9\r\nConnection: close\r\n\r\norigin-ok'); return
                    destination = ('synthetic', 1)
                else:
                    destination = ('synthetic', 1)
                self.server.accepted += 1
                while True:
                    data = s.recv(65536)
                    if not data:
                        return
                    s.sendall(data)
            except (EOFError, ConnectionError, TimeoutError, ssl.SSLError):
                return


class RustCoreIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.context, cls.ca, cls.ca_pem = certificates(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.process = subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.close)
        self.servers = []

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        stderr = self.process.stderr.read()
        self.process.stdout.close(); self.process.stderr.close()
        for server in self.servers:
            server.shutdown(); server.server_close()
            self.assertEqual(server.errors, [])
        self.assertNotIn('fixture-password', stderr)

    def command(self, **command):
        self.process.stdin.write(json.dumps(command)+'\n'); self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def server(self, protocol='echo', tls=False):
        server = Reference(('127.0.0.1', 0), Handler)
        server.protocol, server.tls = protocol, self.context if tls else None
        server.requests, server.errors, server.accepted = [], [], 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server

    def start(self, outbound=None, **options):
        config = {'schema':1, 'listen':'127.0.0.1:0', 'selected':'node', 'nodes':[{'id':'node','outbound':outbound or {'type':'direct'}}], **options}
        result = self.command(op='start', config=config)
        self.assertTrue(result['ok'], result)
        self.handle = result['handle']
        self.port = int(result['status']['address'].rsplit(':',1)[1])
        return config

    def tunnel(self, port, auth=None):
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        authorization = b'' if auth is None else b'Proxy-Authorization: Basic '+base64.b64encode(auth)+b'\r\n'
        s.sendall(f'CONNECT 127.0.0.1:{port} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'.encode()+authorization+b'\r\n')
        response = header(s)
        return s, response

    def test_independent_socks_and_http_upstream_auth(self):
        for protocol in ('socks5', 'http_connect'):
            with self.subTest(protocol=protocol):
                server = self.server(protocol)
                self.start({'type':protocol,'host':'127.0.0.1','port':server.server_address[1], 'auth':{'username':'fixture-user','password':'fixture-password'}})
                with self.tunnel(443)[0] as s:
                    s.sendall(b'hello-independent-peer'); self.assertEqual(exact(s, 22), b'hello-independent-peer')
                self.assertEqual(server.accepted, 1)
                self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def test_tls_http_socks_and_trojan_with_validated_certificate(self):
        for protocol in ('http_connect','socks5','trojan'):
            with self.subTest(protocol=protocol):
                server = self.server(protocol, tls=True)
                outbound = {'type':protocol,'host':'127.0.0.1','port':server.server_address[1],
                            'tls':{'server_name':'localhost','alpn':['http/1.1'],'ca_der_base64':self.ca}}
                if protocol == 'trojan': outbound['password'] = 'fixture-password'
                else: outbound['auth'] = {'username':'fixture-user','password':'fixture-password'}
                self.start(outbound)
                s, response = self.tunnel(443)
                with s:
                    self.assertIn(b'200 Connection Established', response)
                    s.sendall(b'tls-payload'); self.assertEqual(exact(s, 11), b'tls-payload')
                self.assertEqual(server.accepted, 1)
                self.assertTrue(self.command(op='stop', handle=self.handle)['ok'])

    def test_untrusted_or_wrong_name_tls_fails_closed(self):
        server = self.server('trojan', tls=True)
        for tls in ({'server_name':'localhost'}, {'server_name':'wrong.example','ca_der_base64':self.ca}):
            self.start({'type':'trojan','host':'127.0.0.1','port':server.server_address[1],'password':'fixture-password','tls':tls})
            s, response = self.tunnel(443)
            with s: self.assertIn(b'502 Bad Gateway', response)
            self.assertEqual(server.accepted, 0)
            self.command(op='stop', handle=self.handle)

    def test_plain_http_proxy_and_websocket_upgrade(self):
        server = self.server('http-origin'); self.start()
        for path in ('/page','/ws'):
            with socket.create_connection(('127.0.0.1',self.port),timeout=4) as s:
                host = f'127.0.0.1:{server.server_address[1]}'
                headers = b'Upgrade: websocket\r\nConnection: Upgrade\r\n' if path == '/ws' else b''
                s.sendall(f'GET http://{host}{path} HTTP/1.1\r\nHost: {host}\r\n'.encode()+headers+b'\r\n')
                response = header(s)
                if path == '/ws':
                    self.assertIn(b'101 Switching',response); s.sendall(b'\x81\x05frame'); self.assertEqual(exact(s,7),b'\x81\x05frame')
                else:
                    self.assertIn(b'200 OK',response); self.assertEqual(exact(s,9),b'origin-ok')
        self.assertTrue(server.requests[0].startswith(b'GET /page HTTP/1.1'))

    def test_https_sse_and_wss_application_passthrough(self):
        server = self.server('http-origin',tls=True); self.start()
        context = ssl.create_default_context(cadata=self.ca_pem)
        for path in ('/sse','/ws'):
            raw, response = self.tunnel(server.server_address[1]); self.assertIn(b'200',response)
            with context.wrap_socket(raw,server_hostname='localhost') as s:
                s.sendall(f'GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode()); response = header(s)
                if path == '/sse':
                    data=b''
                    while not data.endswith(b'0\r\n\r\n'): data+=s.recv(1024)
                    self.assertIn(b'data: before',data); self.assertIn(b'data: after',data)
                else:
                    self.assertIn(b'101',response);s.sendall(b'opaque-encrypted-frame');self.assertEqual(exact(s,22),b'opaque-encrypted-frame')

    def test_auth_headers_not_forwarded_and_bad_framing_rejected(self):
        server=self.server('http-origin');self.start(inbound_auth={'username':'fixture-user','password':'fixture-password'})
        s,response=self.tunnel(server.server_address[1],b'bad:credentials')
        with s:
            self.assertIn(b'407 Proxy Authentication Required',response)
            self.assertEqual(s.recv(1024),b'')
        host=f'127.0.0.1:{server.server_address[1]}'
        with socket.create_connection(('127.0.0.1',self.port),timeout=4) as s:
            s.sendall(f'GET http://{host}/ HTTP/1.1\r\nHost: {host}\r\nProxy-Authorization: Basic '.encode()+base64.b64encode(b'fixture-user:fixture-password')+b'\r\n\r\n')
            self.assertIn(b'200',header(s));self.assertEqual(exact(s,9),b'origin-ok')
        self.assertNotIn(b'fixture-password',server.requests[-1]);self.assertNotIn(b'Proxy-Authorization',server.requests[-1])
        for framing in (b'Content-Length: 1\r\nContent-Length: 2',b'Content-Length: 1\r\nTransfer-Encoding: chunked'):
            with socket.create_connection(('127.0.0.1',self.port),timeout=4) as s:
                s.sendall(f'POST http://{host}/ HTTP/1.1\r\nHost: {host}\r\n'.encode()+framing+b'\r\n\r\n');self.assertIn(b'400',header(s))

    def test_concurrent_large_transfer_and_invalid_update(self):
        server=self.server();config=self.start()
        def transfer(i):
            s,response=self.tunnel(server.server_address[1]);self.assertIn(b'200',response)
            payload=bytes([i])*65536
            with s:
                for _ in range(8):s.sendall(payload);self.assertEqual(exact(s,len(payload)),payload)
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:list(pool.map(transfer,range(16)))
        config['nodes'][0]['outbound']={'type':'vless','secret':'MUST_NOT_LOG'}
        response=self.command(op='configure',handle=self.handle,config=config)
        self.assertFalse(response['ok']);self.assertNotIn('MUST_NOT_LOG',json.dumps(response))
        transfer(1)
        snapshot=self.command(op='snapshot',handle=self.handle)['status']
        self.assertGreaterEqual(snapshot['download'],17*8*65536)
        self.assertLessEqual(len(snapshot['connections']),256)


if __name__=='__main__':
    unittest.main(verbosity=2)
