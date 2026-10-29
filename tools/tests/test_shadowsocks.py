"""Independent SS AEAD wire peer using Python cryptography, no proxy core.

Run with SWIRL_RUST_HARNESS set. Synthetic credentials only.
"""
import hashlib, io, json, os, socket, socketserver, subprocess, tempfile, threading, traceback, unittest
import concurrent.futures
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from test_rust_core import exact, header, target

PASSWORD='synthetic-ss-password'
def cipher_key(method, salt, password=PASSWORD):
    length=16 if method=='aes-128-gcm' else 32
    key=previous=b''
    while len(key)<length:
        previous=hashlib.md5(previous+password.encode()).digest();key+=previous
    key=HKDF(algorithm=hashes.SHA1(),length=length,salt=salt,info=b'ss-subkey').derive(key[:length])
    return ChaCha20Poly1305(key) if method=='chacha20-ietf-poly1305' else AESGCM(key)

class Reader:
    def __init__(self,s,method):
        self.s=s;self.salt=exact(s,16 if method=='aes-128-gcm' else 32)
        self.cipher=cipher_key(method,self.salt);self.nonce=0
    def decrypt(self, data):
        result=self.cipher.decrypt(self.nonce.to_bytes(12,'little'),data,None);self.nonce+=1;return result
    def chunk(self, *, allow_boundary_eof=False):
        # Only EOF before the first encrypted length byte ends a record stream.
        # Partial length, payload and authentication-tag EOFs remain errors.
        first=self.s.recv(1)
        if not first:
            if allow_boundary_eof:return None
            raise EOFError('SS record boundary EOF')
        length=int.from_bytes(self.decrypt(first+exact(self.s,17)),'big')
        assert length<=16383
        return self.decrypt(exact(self.s,length+16))

class Writer:
    def __init__(self,method,salt=None):
        self.salt=salt or os.urandom(16 if method=='aes-128-gcm' else 32)
        assert len(self.salt)==(16 if method=='aes-128-gcm' else 32)
        self.cipher=cipher_key(method,self.salt);self.nonce=0
    def encrypt(self,data):
        result=self.cipher.encrypt(self.nonce.to_bytes(12,'little'),data,None);self.nonce+=1;return result
    def chunk(self,data):
        return self.encrypt(len(data).to_bytes(2,'big'))+self.encrypt(data)

class Peer(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
    def handle_error(self,request,address): self.errors.append(traceback.format_exc())

class UdpPeer(socketserver.ThreadingUDPServer):
    allow_reuse_address=True;daemon_threads=True
    def handle_error(self,request,address):self.errors.append('UdpReferenceFailure')

class UdpHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data,sock=self.request;server=self.server
        size=16 if server.method=='aes-128-gcm' else 32
        plain=cipher_key(server.method,data[:size]).decrypt(bytes(12),data[size:],None)
        server.received.append(plain)
        salt=os.urandom(size);response=salt+cipher_key(server.method,salt).encrypt(bytes(12),plain,None)
        damaged=bytearray(response);damaged[-1]^=1
        sock.sendto(damaged,self.client_address)
        sock.sendto(response,self.client_address)
        sock.sendto(response,self.client_address)  # authenticated duplicate must be dropped

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        s=self.request;s.settimeout(5);server=self.server
        if server.obfs:
            request=header(s)
            assert request.startswith(b'GET / HTTP/1.1\r\n')
            assert b'Host: obfs.example:' in request and b'Upgrade: websocket\r\n' in request
            server.headers.append(request)
            if server.mode=='bad-http':
                s.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n');return
            response=b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n'
            for byte in response: s.sendall(bytes([byte]))
        reader=Reader(s,server.method)
        address=reader.chunk()
        class Address:
            def __init__(self,data):self.data=io.BytesIO(data)
            def recv(self,n):return self.data.read(n)
        server.targets.append(target(Address(address)))
        writer=Writer(server.method,reader.salt if server.mode=='reflection' else server.fixed_salt)
        if server.mode=='bad-password':writer.cipher=cipher_key(server.method,writer.salt,'incorrect-password')
        initial=writer.salt
        if server.mode=='http-origin':
            request=b''
            while not request.endswith(b'\r\n\r\n'):
                request+=reader.chunk()
                assert len(request)<16384
            assert request.startswith(b'GET /ss HTTP/1.1')
            s.sendall(initial+writer.chunk(b'HTTP/1.1 200 OK\r\nContent-Length: 12\r\nConnection: close\r\n\r\nss-native-ok'));return
        if server.mode=='oversize': initial+=writer.encrypt((16384).to_bytes(2,'big'))
        elif server.mode=='truncated': initial+=writer.chunk(b'NEVER')[:-1]
        elif server.mode=='tampered':
            broken=bytearray(writer.chunk(b'NEVER'));broken[-1]^=1;initial+=broken
        elif server.mode=='bad-length-tag':
            broken=bytearray(writer.chunk(b'NEVER'));broken[4]^=1;initial+=broken
        elif server.mode in ('reflection','replay','bad-password'):initial+=writer.chunk(b'OK')
        elif server.mode=='empty-chunks':initial+=b''.join(writer.chunk(b'') for _ in range(80))+writer.chunk(b'OK')
        if server.mode!='echo':
            s.sendall(initial);return
        s.sendall(initial)
        try:
            while True:
                data=reader.chunk();server.received+=len(data)
                encoded=writer.chunk(data)
                # Deliberately split both encrypted length and authentication tag.
                s.sendall(encoded[:1]);s.sendall(encoded[1:17]);s.sendall(encoded[17:])
        except EOFError:
            s.sendall(writer.chunk(b'tail-after-halfclose'));s.shutdown(socket.SHUT_WR)
        except (ConnectionError,OSError):
            return

@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'),'compiled Rust harness required')
class ShadowsocksTests(unittest.TestCase):
    def setUp(self):
        self.process=subprocess.Popen([os.environ['SWIRL_RUST_HARNESS']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.servers=[]
    def tearDown(self):
        self.process.stdin.close();self.process.wait(timeout=6)
        self.assertNotIn(PASSWORD,self.process.stderr.read())
        self.process.stdout.close();self.process.stderr.close()
        for server in self.servers:
            server.shutdown();server.server_close();self.assertEqual(server.errors,[])
    def command(self,**data):
        self.process.stdin.write(json.dumps(data)+'\n');self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())
    def setup_peer(self,method='aes-128-gcm',obfs=False,mode='echo',salt=None,udp_enabled=True):
        server=Peer(('127.0.0.1',0),Handler)
        server.method=method;server.obfs=obfs;server.mode=mode;server.fixed_salt=salt
        server.targets=[];server.headers=[];server.errors=[];server.received=0
        threading.Thread(target=server.serve_forever,daemon=True).start();self.servers.append(server)
        outbound={'type':'shadowsocks','host':'127.0.0.1','port':server.server_address[1],'password':PASSWORD,'cipher':method,'udp':udp_enabled}
        if obfs:outbound['obfs_http']={'host':'obfs.example'}
        result=self.command(op='start',config={'schema':1,'listen':'127.0.0.1:0','selected':'node','nodes':[{'id':'node','outbound':outbound}]})
        self.assertTrue(result['ok'],result);self.handle=result['handle'];self.port=int(result['status']['address'].rsplit(':',1)[1])
        return server
    def tunnel(self,authority='example.org:443'):
        s=socket.create_connection(('127.0.0.1',self.port),timeout=5)
        s.sendall(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode())
        self.assertIn(b'200',header(s));return s
    def test_three_ciphers_plain_and_http_obfs_large_transfer_halfclose(self):
        for method in ('aes-128-gcm','aes-256-gcm','chacha20-ietf-poly1305'):
            for obfs in (False,True):
                with self.subTest(method=method,obfs=obfs):
                    server=self.setup_peer(method,obfs)
                    with self.tunnel() as s:
                        for _ in range(8):
                            data=os.urandom(32769);s.sendall(data);self.assertEqual(exact(s,len(data)),data)
                        s.shutdown(socket.SHUT_WR)
                        self.assertEqual(exact(s,20),b'tail-after-halfclose')
                        self.assertEqual(s.recv(1),b'')
                    self.assertEqual(server.targets,[('example.org',443)])
                    self.assertEqual(server.received,8*32769)
                    self.command(op='stop',handle=self.handle)
    def test_tampered_truncated_and_reserved_lengths_never_release_plaintext(self):
        for mode in ('tampered','bad-length-tag','truncated','oversize','reflection','bad-password','bad-http'):
            with self.subTest(mode=mode):
                self.setup_peer(mode=mode,obfs=mode=='bad-http')
                with self.tunnel() as s:self.assertEqual(s.recv(100),b'')
                snapshot=self.command(op='snapshot',handle=self.handle)['status']
                self.assertEqual(snapshot['download'],0)
                self.command(op='stop',handle=self.handle)
    def test_authenticated_empty_chunks_are_not_mistaken_for_eof(self):
        self.setup_peer(mode='empty-chunks')
        with self.tunnel() as s:self.assertEqual(exact(s,2),b'OK')
    def test_concurrent_encrypted_sessions_do_not_share_nonce_state(self):
        server=self.setup_peer(obfs=True)
        def exchange(index):
            data=bytes([index])*65536
            with self.tunnel() as s:
                s.sendall(data);self.assertEqual(exact(s,len(data)),data)
                s.shutdown(socket.SHUT_WR);self.assertEqual(exact(s,20),b'tail-after-halfclose')
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(exchange,range(16)))
        self.assertEqual(len(server.targets),16)
    def test_response_salt_replay_rejected_across_connections(self):
        self.setup_peer(mode='replay',salt=b'fixed-test-salt!')
        with self.tunnel() as s:self.assertEqual(exact(s,2),b'OK')
        with self.tunnel() as s:self.assertEqual(s.recv(2),b'')
    @unittest.skipUnless(os.environ.get('SWIRL_RUST_QT_TESTS'),'Qt integration executable required')
    def test_qt_facade_http_obfs_with_udp_declared(self):
        server=self.setup_peer(obfs=True,mode='http-origin')
        env={**os.environ,'SWIRL_SS_REFERENCE_PORT':str(server.server_address[1])}
        with tempfile.TemporaryDirectory() as folder:
            log=os.path.join(folder,'qt.txt')
            result=subprocess.run([os.environ['SWIRL_RUST_QT_TESTS'],'shadowsocksThroughIndependentPeer','loonShadowsocksThroughIndependentPeer','-o',log+',txt'],env=env,capture_output=True,text=True,timeout=15)
            output=Path(log).read_text(encoding='utf-8') if os.path.exists(log) else ''
            self.assertEqual(result.returncode,0,output+result.stdout+result.stderr)
        # One native case and four Loon cases, including both fast-open values.
        self.assertEqual(server.targets,[('origin.example',80)] * 5)
    def test_ipv4_and_ipv6_target_encodings(self):
        server=self.setup_peer()
        for authority,host in [('127.0.0.1:8080','127.0.0.1'),('[::1]:8080','::1')]:
            with self.tunnel(authority) as s:
                s.sendall(b'address');self.assertEqual(exact(s,7),b'address')
                s.shutdown(socket.SHUT_WR);self.assertEqual(exact(s,20),b'tail-after-halfclose')
            self.assertEqual(server.targets[-1],(host,8080))
    def test_udp_all_ciphers_boundaries_authentication_replay_and_client_pin(self):
        for method in ('aes-128-gcm','aes-256-gcm','chacha20-ietf-poly1305'):
            peer=self.setup_peer(method,True)
            udp=UdpPeer(peer.server_address,UdpHandler);udp.method=method;udp.received=[];udp.errors=[]
            threading.Thread(target=udp.serve_forever,daemon=True).start();self.servers.append(udp)
            with socket.create_connection(('127.0.0.1',self.port),timeout=3) as control, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
                control.sendall(b'\x05\x01\x00');self.assertEqual(exact(control,2),b'\x05\x00')
                control.sendall(b'\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00')
                self.assertEqual(exact(control,3),b'\x05\x00\x00');relay=target(control)
                client.bind(('127.0.0.1',0));client.settimeout(.2)
                for data in (b'',b'small',os.urandom(1400)):
                    addr=b'\x03\x0bexample.org\x00\x35'
                    packet=b'\x00\x00\x00'+addr+data
                    client.sendto(packet,relay);self.assertEqual(client.recvfrom(65535)[0],packet)
                    with self.assertRaises(socket.timeout):client.recvfrom(65535)
                count=len(udp.received)
                client.sendto(b'\x00\x00\x01'+addr+b'fragment',relay)
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as rogue:rogue.sendto(packet,relay)
                with self.assertRaises(socket.timeout):client.recvfrom(65535)
                self.assertEqual(len(udp.received),count)
            self.command(op='stop',handle=self.handle)
    def test_explicit_udp_false_never_sends_to_server(self):
        peer=self.setup_peer(udp_enabled=False)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as remote, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client, socket.create_connection(('127.0.0.1',self.port),timeout=3) as control:
            remote.bind(peer.server_address);remote.settimeout(.2)
            control.sendall(b'\x05\x01\x00');self.assertEqual(exact(control,2),b'\x05\x00')
            control.sendall(b'\x05\x03\x00\x01'+bytes(6));self.assertEqual(exact(control,3),b'\x05\x00\x00')
            relay=target(control);client.sendto(b'\x00\x00\x00\x01\x7f\x00\x00\x01\x00\x35blocked',relay)
            control.settimeout(.2)
            with self.assertRaises(socket.timeout):control.recv(1)
            with self.assertRaises(socket.timeout):remote.recvfrom(1024)
            self.assertGreater(self.command(op='snapshot',handle=self.handle)['status']['udp_dropped'],0)

if __name__=='__main__':unittest.main(verbosity=2)
