"""Independent Python socket/TLS peers exercise the compiled Rust control harness.

Requires Python cryptography only for generating ephemeral test certificates.
No credentials, subscription providers or complete proxy cores are used.
Set SWIRL_RUST_HARNESS to the built swirl-api executable.
"""
import base64
import concurrent.futures
import datetime
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import socket
import socketserver
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from dns_peer import DnsPeer
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

_public_spec = importlib.util.spec_from_file_location(
    'swirl_public_verifier', Path(__file__).resolve().parents[1] / 'Verify-PublicRustCore.py')
public_verifier = importlib.util.module_from_spec(_public_spec)
_public_spec.loader.exec_module(public_verifier)


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
                elif protocol.startswith('vless'):
                    assert exact(s,1)==b'\x00'
                    if exact(s,16)!=bytes.fromhex('00112233445566778899aabbccddeeff'):return
                    assert exact(s,2)==b'\x00\x01'
                    port=int.from_bytes(exact(s,2),'big');kind=exact(s,1)[0]
                    if kind==1:host=socket.inet_ntop(socket.AF_INET,exact(s,4))
                    elif kind==3:host=socket.inet_ntop(socket.AF_INET6,exact(s,16))
                    else:
                        assert kind==2;host=exact(s,exact(s,1)[0]).decode()
                    destination=(host,port);self.server.requests.append(destination)
                    if protocol=='vless-bad-version':s.sendall(b'\x01\x00NEVER');return
                    if protocol=='vless-addons':s.sendall(b'\x00\x01\x00NEVER');return
                    if protocol=='vless-truncated':s.sendall(b'\x00');return
                    s.sendall(b'\x00');s.sendall(b'\x00')
                    if protocol=='vless-http-origin':
                        assert header(s).startswith(b'GET /vless HTTP/1.1')
                        s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\nvless-ok');return
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
                elif protocol.startswith('https-head-'):
                    data = header(s); self.server.requests.append(data)
                    assert data.startswith(b'HEAD / HTTP/1.1\r\n')
                    s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                    if protocol == 'https-head-truncated':
                        return  # Deliberately omit TLS close_notify.
                    if protocol == 'https-head-stalled':
                        assert self.server.release_close.wait(3)
                    with s.unwrap() as plain:
                        self.server.tls_closed = True
                        plain.shutdown(socket.SHUT_WR)
                        self.server.tcp_closed = plain.recv(1) == b''
                        self.server.close_complete.set()
                    return
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
        server.tls_closed = server.tcp_closed = False
        server.release_close = threading.Event()
        server.close_complete = threading.Event()
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

    def test_resolving_rules_send_the_matched_ip_to_upstream(self):
        server=self.server('vless')
        outbound={'type':'vless','host':'127.0.0.1','port':server.server_address[1],
                  'uuid':'00112233-4455-6677-8899-aabbccddeeff'}
        self.start(outbound,rules=[
            {'matcher':{'type':'cidr','value':'127.0.0.0/8','resolve':True},'outbound':'node'},
            {'matcher':{'type':'cidr','value':'::1/128','resolve':True},'outbound':'node'}])
        with socket.create_connection(('127.0.0.1',self.port),timeout=5) as s:
            s.sendall(b'CONNECT localhost:443 HTTP/1.1\r\nHost: localhost:443\r\n\r\n')
            self.assertIn(b'200',header(s));s.sendall(b'pinned');self.assertEqual(exact(s,6),b'pinned')
        self.assertEqual(len(server.requests),1)
        self.assertTrue(ipaddress.ip_address(server.requests[0][0]).is_loopback)
        self.assertEqual(server.requests[0][1],443)

    def test_manual_selector_api_preserves_stream_and_never_falls_back(self):
        server=self.server('echo')
        self.start(nodes=[{'id':'node','outbound':{'type':'direct'}},{'id':'deny','outbound':{'type':'reject'}}],
                   selectors=[{'id':'manual','members':['node','deny'],'selected':'node'}],
                   rules=[{'matcher':{'type':'match'},'outbound':'manual'}])
        old,response=self.tunnel(server.server_address[1]);self.assertIn(b'200',response)
        with old:
            self.assertTrue(self.command(op='select_group',handle=self.handle,id='manual',member='deny')['ok'])
            state=self.command(op='snapshot',handle=self.handle)['status'];self.assertEqual(state['selectors'],{'manual':'deny'})
            self.assertFalse(self.command(op='select_group',handle=self.handle,id='manual',member='missing')['ok'])
            self.assertEqual(self.command(op='snapshot',handle=self.handle)['status']['generation'],state['generation'])
            old.sendall(b'old-alive');self.assertEqual(exact(old,9),b'old-alive')
            new,response=self.tunnel(server.server_address[1]);new.close();self.assertIn(b'502',response)
        self.assertEqual(server.accepted,1)

    def test_local_hosts_follow_proxy_toggle_and_preserve_tls_name(self):
        for force in (False,True):
            server=self.server('vless',tls=True)
            outbound={'type':'vless','host':'proxy.fixture.invalid','port':server.server_address[1],
                      'uuid':'00112233-4455-6677-8899-aabbccddeeff',
                      'tls':{'server_name':'localhost','ca_der_base64':self.ca}}
            self.start(outbound,dns={'hosts':[{'name':'proxy.fixture.invalid','address':'127.0.0.1'},
                                             {'name':'target.fixture.invalid','address':'127.0.0.7'}],
                                    'force_proxy_hosts':force})
            with socket.create_connection(('127.0.0.1',self.port),timeout=5) as s:
                s.sendall(b'CONNECT target.fixture.invalid:443 HTTP/1.1\r\nHost: target.fixture.invalid:443\r\n\r\n')
                self.assertIn(b'200',header(s));s.sendall(b'mapped');self.assertEqual(exact(s,6),b'mapped')
            self.assertEqual(server.requests,[('127.0.0.7' if force else 'target.fixture.invalid',443)])
            self.assertTrue(self.command(op='stop',handle=self.handle)['ok'])

    def test_hosts_update_preserves_old_stream_and_new_target(self):
        server=self.server('echo')
        cfg=self.start(dns={'hosts':[{'name':'local.fixture.invalid','address':'127.0.0.1'}]})
        with socket.create_connection(('127.0.0.1',self.port),timeout=5) as old:
            port=server.server_address[1]
            old.sendall(f'CONNECT local.fixture.invalid:{port} HTTP/1.1\r\nHost: local.fixture.invalid\r\n\r\n'.encode())
            self.assertIn(b'200',header(old))
            cfg['dns']['hosts'][0]['name']='updated.fixture.invalid'
            self.assertTrue(self.command(op='configure',handle=self.handle,config=cfg)['ok'])
            old.sendall(b'old');self.assertEqual(exact(old,3),b'old')
            with socket.create_connection(('127.0.0.1',self.port),timeout=5) as new:
                new.sendall(f'CONNECT updated.fixture.invalid:{port} HTTP/1.1\r\nHost: updated.fixture.invalid\r\n\r\n'.encode())
                self.assertIn(b'200',header(new));new.sendall(b'new');self.assertEqual(exact(new,3),b'new')
            bad=json.loads(json.dumps(cfg));bad['dns']['hosts'].append({'name':'UPDATED.FIXTURE.INVALID','address':'::1'})
            self.assertFalse(self.command(op='configure',handle=self.handle,config=bad)['ok'])
        self.assertEqual(server.accepted,2)

    def dns_peer(self,mode='normal',ttl=30):
        peer=DnsPeer(mode,ttl);self.addCleanup(peer.close);return peer

    def named_tunnel(self,host,port):
        s=socket.create_connection(('127.0.0.1',self.port),timeout=5)
        s.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'.encode())
        return s,header(s)

    def test_custom_dns_cache_expiry_and_zero_ttl(self):
        dns=self.dns_peer(ttl=1);server=self.server('echo')
        config=self.start(dns={'servers':[dns.address],'use_system_hosts':False})
        for _ in range(2):
            s,response=self.named_tunnel('cache.fixture.invalid',server.server_address[1])
            with s:self.assertIn(b'200',response);s.sendall(b'dns');self.assertEqual(exact(s,3),b'dns')
        self.assertEqual(len(dns.queries),2)
        time.sleep(1.1)
        s,response=self.named_tunnel('cache.fixture.invalid',server.server_address[1]);s.close();self.assertIn(b'200',response)
        self.assertEqual(len(dns.queries),4)
        dns.ttl=0;self.assertTrue(self.command(op='configure',handle=self.handle,config=config)['ok'])
        for _ in range(2):
            s,response=self.named_tunnel('zero.fixture.invalid',server.server_address[1]);s.close();self.assertIn(b'200',response)
        self.assertEqual(len(dns.queries),8)

    def test_custom_dns_cname_tcp_retry_and_declared_server_failover(self):
        server=self.server('echo')
        for mode in ('cname','truncated','normal'):
            dns=self.dns_peer(mode);bad=self.dns_peer('servfail')
            self.start(dns={'servers':[bad.address,dns.address],'use_system_hosts':False})
            s,response=self.named_tunnel('dns.fixture.invalid',server.server_address[1])
            with s:self.assertIn(b'200',response);s.sendall(b'wire');self.assertEqual(exact(s,4),b'wire')
            self.assertTrue(bad.queries)
            if mode=='cname':self.assertTrue(any(q[0]=='alias.fixture.invalid' for q in dns.queries))
            if mode=='truncated':self.assertEqual(sum(q[2] for q in dns.queries),2)
            self.assertTrue(self.command(op='stop',handle=self.handle)['ok'])

    def test_custom_dns_errors_never_fall_back_to_system(self):
        server=self.server('echo')
        for mode in ('wrong-id','wrong-question','trailing','nxdomain','silent'):
            dns=self.dns_peer(mode)
            self.start(dns={'servers':[dns.address],'use_system_hosts':False})
            began=time.monotonic();s,response=self.named_tunnel('localhost',server.server_address[1]);s.close()
            self.assertIn(b'502',response);self.assertLess(time.monotonic()-began,4)
            self.assertTrue(self.command(op='stop',handle=self.handle)['ok'])
        self.assertEqual(server.accepted,0)

    def test_custom_dns_udp_target_and_nxdomain_is_terminal(self):
        dns=self.dns_peer();echo=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);echo.bind(('127.0.0.1',0));echo.settimeout(4)
        self.addCleanup(echo.close)
        def worker():
            data,peer=echo.recvfrom(1024);echo.sendto(data,peer)
        thread=threading.Thread(target=worker);thread.start()
        self.start(dns={'servers':[dns.address],'use_system_hosts':False})
        with socket.create_connection(('127.0.0.1',self.port),timeout=4) as control:
            control.sendall(b'\x05\x01\x00');self.assertEqual(exact(control,2),b'\x05\x00')
            control.sendall(b'\x05\x03\x00\x01'+bytes(6));reply=exact(control,10);self.assertEqual(reply[1],0)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
                udp.settimeout(4);name=b'udp.fixture.invalid';packet=b'\0\0\0\x03'+bytes([len(name)])+name+echo.getsockname()[1].to_bytes(2,'big')+b'udp-dns'
                udp.sendto(packet,('127.0.0.1',int.from_bytes(reply[8:10],'big')));data,_=udp.recvfrom(1024);self.assertEqual(data[10:],b'udp-dns')
        thread.join(4);self.assertFalse(thread.is_alive());self.assertTrue(self.command(op='stop',handle=self.handle)['ok'])
        for mode in ('nxdomain','mixed-negative'):
            missing=self.dns_peer(mode);unused=self.dns_peer()
            self.start(dns={'servers':[missing.address,unused.address],'use_system_hosts':False})
            s,response=self.named_tunnel('missing.fixture.invalid',443);s.close();self.assertIn(b'502',response);self.assertFalse(unused.queries)
            self.assertTrue(self.command(op='stop',handle=self.handle)['ok'])

    def test_custom_dns_ipv6_server_and_tcp_retry(self):
        dns=DnsPeer('truncated',ipv6=True);self.addCleanup(dns.close);server=self.server('echo')
        self.start(dns={'servers':[dns.address],'use_system_hosts':False})
        s,response=self.named_tunnel('ipv6.fixture.invalid',server.server_address[1])
        with s:self.assertIn(b'200',response);s.sendall(b'v6dns');self.assertEqual(exact(s,5),b'v6dns')
        self.assertEqual(sum(q[2] for q in dns.queries),2)
    def test_vless_tcp_tls_addresses_and_invalid_responses(self):
        for tls in (False,True):
            server=self.server('vless',tls=tls)
            outbound={'type':'vless','host':'127.0.0.1','port':server.server_address[1],'uuid':'00112233-4455-6677-8899-aabbccddeeff'}
            if tls:outbound['tls']={'server_name':'localhost','ca_der_base64':self.ca}
            self.start(outbound)
            for address in ('example.org:443','127.0.0.1:443','[::1]:443'):
                with socket.create_connection(('127.0.0.1',self.port),timeout=3) as s:
                    s.sendall(f'CONNECT {address} HTTP/1.1\r\nHost: {address}\r\n\r\n'.encode());self.assertIn(b'200',header(s))
                    data=os.urandom(65536);s.sendall(data);self.assertEqual(exact(s,len(data)),data)
            self.assertEqual(server.requests,[('example.org',443),('127.0.0.1',443),('::1',443)])
            self.command(op='stop',handle=self.handle)
        for mode in ('vless-bad-version','vless-addons','vless-truncated'):
            server=self.server(mode)
            self.start({'type':'vless','host':'127.0.0.1','port':server.server_address[1],'uuid':'00112233-4455-6677-8899-aabbccddeeff'})
            with self.tunnel(443)[0] as s:self.assertEqual(s.recv(64),b'')
            self.assertEqual(self.command(op='snapshot',handle=self.handle)['status']['download'],0)
            self.command(op='stop',handle=self.handle)
    def test_vless_uuid_and_tls_fail_closed(self):
        server=self.server('vless',tls=True)
        for identity,tls in [('00112233-4455-6677-8899-aabbccddee00',{'server_name':'localhost','ca_der_base64':self.ca}),
                             ('00112233-4455-6677-8899-aabbccddeeff',{'server_name':'wrong.example','ca_der_base64':self.ca})]:
            self.start({'type':'vless','host':'127.0.0.1','port':server.server_address[1],'uuid':identity,'tls':tls})
            s,response=self.tunnel(443)
            with s:
                if tls['server_name']=='wrong.example':self.assertIn(b'502',response)
                else:self.assertEqual(s.recv(1),b'')
            self.command(op='stop',handle=self.handle)
        self.assertEqual(server.accepted,0)
    @unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'),'Qt executable required')
    def test_vless_qt_data_path(self):
        server=self.server('vless-http-origin')
        with tempfile.TemporaryDirectory() as folder:
            log=Path(folder)/'qt.txt'
            result=subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'],'vlessThroughIndependentPeer','-o',str(log)+',txt'],
                env={**os.environ,'SWIRL_VLESS_REFERENCE_PORT':str(server.server_address[1])},capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,log.read_text(encoding='utf-8') if log.exists() else 'Qt log unavailable')
        self.assertEqual(server.requests,[('origin.example',80)])

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

    def public_head(self, server):
        raw, response = self.tunnel(server.server_address[1])
        self.assertIn(b'200 Connection Established', response)
        context = ssl.create_default_context(cadata=self.ca_pem)
        try:
            stream = context.wrap_socket(raw, server_hostname='localhost')
        except BaseException:
            raw.close()
            raise
        try:
            stream.sendall(b'HEAD / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            response = public_verifier.read_header(stream, time.monotonic() + 3)
            self.assertTrue(response.startswith(b'HTTP/1.1 200 '))
            return stream
        except BaseException:
            stream.close()
            raise

    def settled_public_stats(self, deadline=None):
        outcome = {}
        state = public_verifier.settled_snapshot(
            lambda _deadline, **value: self.command(**value), self.handle,
            deadline if deadline is not None else time.monotonic() + 3, outcome)
        self.assertEqual(outcome['core'], state)
        return state

    def test_public_https_orderly_close_finishes_without_native_relay_errors(self):
        server = self.server('https-head-orderly', tls=True); self.start()
        with self.public_head(server) as stream:
            public_verifier.close_https(stream, time.monotonic() + 3)
        state = self.settled_public_stats()
        self.assertIsNone(public_verifier.native_traffic_error(state), state)
        self.assertTrue(server.close_complete.wait(1))
        self.assertTrue(server.tls_closed)
        self.assertTrue(server.tcp_closed)

    def test_public_https_missing_close_notify_is_not_success(self):
        server = self.server('https-head-truncated', tls=True); self.start()
        with self.public_head(server) as stream:
            with self.assertRaises(ssl.SSLError):
                public_verifier.close_https(stream, time.monotonic() + 3)
        self.settled_public_stats()
        self.assertFalse(server.tls_closed)

    def test_public_https_accounting_rejects_real_reset_after_http_success(self):
        server = self.server('https-head-orderly', tls=True); self.start()
        with self.public_head(server) as stream:
            # The origin waits for close_notify, so this deterministic client
            # reset happens after HTTP 200 and while the Rust relay is active.
            linger = struct.pack('HH' if os.name == 'nt' else 'ii', 1, 0)
            stream.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
        state = self.settled_public_stats()
        self.assertEqual(state['accepted'], 1)
        self.assertGreater(state['upload'], 0)
        self.assertGreater(state['download'], 0)
        self.assertEqual(state['failed'], 1)
        self.assertEqual(state['last_error'], 'StreamIo')
        self.assertEqual(public_verifier.native_traffic_error(state), 'NativeRelayFailed')

    def test_public_https_close_and_active_snapshot_share_the_deadline(self):
        server = self.server('https-head-stalled', tls=True); self.start()
        try:
            with self.public_head(server) as stream:
                # Successful HTTP and nonzero counters cannot bypass an active
                # relay; neither settling nor TLS shutdown gets a fresh budget.
                before = time.monotonic()
                with self.assertRaises(TimeoutError):
                    self.settled_public_stats(deadline=before + 0.15)
                self.assertLess(time.monotonic() - before, 2)
                before = time.monotonic()
                with self.assertRaises(TimeoutError):
                    public_verifier.close_https(stream, before + 0.15)
                self.assertLess(time.monotonic() - before, 2)
        finally:
            server.release_close.set()
        self.settled_public_stats()

    def test_public_https_missing_connection_record_is_not_success(self):
        # Clean-looking counters cannot stand in for the one completed session.
        status = {'accepted': 1, 'active': 0, 'failed': 0, 'upload': 1,
                  'download': 1, 'last_error': '', 'connections': []}
        outcome = {}
        state = public_verifier.settled_snapshot(
            lambda _deadline, **_value: {'ok': True, 'status': status},
            1, time.monotonic() + 1, outcome)
        self.assertEqual(state['recorded_connections'], 0)
        self.assertEqual(public_verifier.native_traffic_error(state),
                         'NativeConnectionRecordCount')

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
