"""Independent HTTPS DNS peers; loopback, ephemeral trust, no OS changes."""
import json,os,socket,socketserver,ssl,tempfile,threading,time,unittest
import test_dns_tls as dot_test
from dns_peer import DnsPeer
from test_rust_core import certificates,exact,header

class DohPeer(DnsPeer):
    def __init__(self,context,mode='normal',ttl=30,ipv6=False):
        self.mode,self.ttl=mode,ttl;self.queries,self.errors,self.requests=[],[],[];self.connections=0;self.ipv6=ipv6;owner=self
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads=True;address_family=socket.AF_INET6 if ipv6 else socket.AF_INET
            def handle_error(self,request,address):owner.errors.append('DoH handler failed')
        class Request(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                try:
                    with context.wrap_socket(self.request,server_side=True) as stream:
                        owner.connections+=1;raw=header(stream);owner.requests.append(raw)
                        lines=raw.decode('ascii').split('\r\n');assert lines[0]=='POST /dns-query?fixture=1 HTTP/1.1'
                        fields=dict(line.split(': ',1) for line in lines[1:] if ': ' in line)
                        assert fields['Host']==f'localhost:{owner.port}' or fields['Host']==f'[::1]:{owner.port}'
                        assert fields['Accept']==fields['Content-Type']=='application/dns-message'
                        assert 'Cookie' not in fields and 'Authorization' not in fields
                        size=int(fields['Content-Length']);assert 12<=size<=512
                        data=exact(stream,size);assert data[:2]==b'\0\0'
                        dns=owner.respond(data,True)
                        if dns is None:time.sleep(2);return
                        if mode=='dns-tc':dns=dns[:2]+bytes([dns[2]|2])+dns[3:]
                        status='302 Found' if mode=='redirect' else '503 Unavailable' if mode=='status' else '200 OK'
                        content='text/html' if mode=='type' else 'application/dns-message'
                        headers=f'HTTP/1.1 {status}\r\nContent-Type: {content}\r\n'
                        if mode=='redirect':headers+='Location: https://unconfigured.invalid/\r\n'
                        if mode in ('chunked','bad-chunk','trailers','ambiguous'):
                            headers+='Transfer-Encoding: chunked\r\n'
                            if mode=='ambiguous':headers+=f'Content-Length: {len(dns)}\r\n'
                            body=b''.join(f'{len(dns[i:i+7]):x}\r\n'.encode()+dns[i:i+7]+b'\r\n' for i in range(0,len(dns),7))+b'0\r\n\r\n'
                            if mode=='bad-chunk':body=b'XYZ\r\n'+body
                            if mode=='trailers':body=body[:-2]+b'Injected: value\r\n\r\n'
                        else:
                            length=65535 if mode=='oversize' else len(dns)
                            headers+=f'Content-Length: {length}\r\n';body=dns
                            if mode=='duplicate':headers+=f'Content-Length: {len(dns)}\r\n'
                            if mode=='short-body':body=body[:7]
                        if mode=='compressed':headers+='Content-Encoding: gzip\r\n'
                        if mode=='age':headers+='Age: 30\r\n'
                        if mode=='no-store':headers+='Cache-Control: no-store\r\n'
                        if mode=='max-age':headers+='Cache-Control: max-age=0\r\n'
                        if mode=='header-limit':headers+='X-Large: '+('a'*8500)+'\r\n'
                        response=headers.encode()+b'Connection: close\r\n\r\n'+body
                        for at in range(0,len(response),11):stream.sendall(response[at:at+11])
                except (EOFError,OSError,ssl.SSLError):pass
        self.tcp=Server(('::1' if ipv6 else '127.0.0.1',0),Request);self.port=self.tcp.server_address[1]
        threading.Thread(target=self.tcp.serve_forever,daemon=True).start()
    def close(self):self.tcp.shutdown();self.tcp.server_close();assert not self.errors,self.errors

@unittest.skipUnless(os.environ.get('SWIRL_RUST_HARNESS'),'set SWIRL_RUST_HARNESS')
class DnsHttpsIntegration(unittest.TestCase):
    setUp=dot_test.DnsTlsIntegration.setUp
    close=dot_test.DnsTlsIntegration.close
    command=dot_test.DnsTlsIntegration.command
    config=dot_test.DnsTlsIntegration.config
    start=dot_test.DnsTlsIntegration.start
    stop=dot_test.DnsTlsIntegration.stop
    origin=dot_test.DnsTlsIntegration.origin
    tunnel=dot_test.DnsTlsIntegration.tunnel
    assert_forward=dot_test.DnsTlsIntegration.assert_forward
    assert_denied=dot_test.DnsTlsIntegration.assert_denied
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.context,cls.ca,_=certificates(cls.temp.name)
        cls.context.set_alpn_protocols(['http/1.1'])
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def peer(self,**options):
        peer=DohPeer(self.context,**options);self.peers.append(peer);return peer
    def endpoint(self,peer,**tls):
        return {'address':peer.address,'path':'/dns-query?fixture=1','tls':{'server_name':'localhost','alpn':['http/1.1'],'ca_der_base64':self.ca,**tls}}
    def test_post_partial_response_and_cache(self):
        peer=self.peer();port=self.origin();self.start({'https_servers':[self.endpoint(peer)],'use_system_hosts':False})
        self.assert_forward(port);self.assert_forward(port);self.assertEqual(len(peer.queries),2);self.assertEqual(peer.connections,2)
    def test_chunked_cname_and_ipv6(self):
        for options in ({'mode':'chunked'},{'mode':'cname'},{'ipv6':True}):
            peer=self.peer(**options);self.start({'https_servers':[self.endpoint(peer)]});self.assert_forward(self.origin());self.stop()
            self.assertEqual(len(peer.queries),4 if options.get('mode')=='cname' else 2)
    def test_cache_age_no_store_max_age_and_zero_ttl(self):
        for options in ({'mode':'age'},{'mode':'no-store'},{'mode':'max-age'},{'ttl':0}):
            peer=self.peer(**options);port=self.origin();self.start({'https_servers':[self.endpoint(peer)]})
            self.assert_forward(port);self.assert_forward(port);self.assertEqual(len(peer.queries),4);self.stop()
    def test_bad_certificate_or_name_sends_no_dns(self):
        for tls in ({'server_name':'wrong.fixture.invalid'},{'ca_der_base64':None}):
            peer=self.peer();self.start({'https_servers':[self.endpoint(peer,**tls)],'use_system_hosts':False})
            self.assert_denied(self.origin(),name='localhost');self.assertFalse(peer.queries);self.stop()
    def test_http_errors_and_ambiguous_framing_fail_closed(self):
        port=self.origin()
        for mode in ('redirect','status','type','duplicate','ambiguous','compressed','bad-chunk','trailers','oversize','short-body','header-limit'):
            with self.subTest(mode=mode):
                peer=self.peer(mode=mode);self.start({'https_servers':[self.endpoint(peer)],'use_system_hosts':False})
                self.assert_denied(port,name='localhost');self.stop()
        self.assertEqual(self.origins[0].accepted,0)
    def test_bad_dns_and_deadline_never_fall_back(self):
        port=self.origin()
        for mode in ('wrong-id','wrong-question','trailing','dns-tc','silent'):
            peer=self.peer(mode=mode);self.start({'https_servers':[self.endpoint(peer)],'use_system_hosts':False})
            start=time.monotonic();self.assert_denied(port,name='localhost');self.assertLess(time.monotonic()-start,4);self.stop()
        self.assertEqual(self.origins[0].accepted,0)
    def test_only_configured_https_failover_and_terminal_nxdomain(self):
        for mode in ('status','nxdomain'):
            bad=self.peer(mode=mode);good=self.peer();self.start({'https_servers':[self.endpoint(bad),self.endpoint(good)]})
            if mode=='status':self.assert_forward(self.origin());self.assertTrue(good.queries)
            else:self.assert_denied(self.origin());self.assertFalse(good.queries)
            self.stop()
    def test_update_preserves_stream_and_replaces_resolver(self):
        a=self.peer();b=self.peer();port=self.origin();self.start({'https_servers':[self.endpoint(a)]})
        stream,response=self.tunnel(port);self.assertIn(b'200',response)
        with stream:
            self.assertTrue(self.command(op='configure',handle=self.handle,config=self.config({'https_servers':[self.endpoint(b)]}))['ok'])
            self.assert_forward(port);stream.sendall(b'old');self.assertEqual(exact(stream,3),b'old')
        self.assertEqual(len(a.queries),2);self.assertEqual(len(b.queries),2)
    def test_configuration_rejects_mixed_plaintext_and_unmapped_fields(self):
        peer=self.peer();endpoint=self.endpoint(peer)
        for extra in ({'servers':['127.0.0.1:53']},{'tls_servers':[{'address':'127.0.0.1:853','tls':{'server_name':'localhost'}}]}):
            self.assertFalse(self.command(op='start',config=self.config({'https_servers':[endpoint],**extra}))['ok'])
        for path in ('//bad.test','/bad\r\nHeader: x','/dns-query{?dns}'):
            e={**endpoint,'path':path};self.assertFalse(self.command(op='start',config=self.config({'https_servers':[e]}))['ok'])
        self.assertFalse(peer.queries)
    def test_positive_cache_expires(self):
        peer=self.peer(ttl=1);port=self.origin();self.start({'https_servers':[self.endpoint(peer)]})
        self.assert_forward(port);self.assert_forward(port);self.assertEqual(len(peer.queries),2)
        time.sleep(1.1);self.assert_forward(port);self.assertEqual(len(peer.queries),4)
    def test_udp_resolution_uses_https_and_keeps_old_snapshot(self):
        peer=self.peer();self.start({'https_servers':[self.endpoint(peer)],'use_system_hosts':False})
        echo=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);echo.bind(('127.0.0.1',0));echo.settimeout(4);self.addCleanup(echo.close)
        def worker():
            for _ in range(2):data,source=echo.recvfrom(1024);echo.sendto(data,source)
        thread=threading.Thread(target=worker,daemon=True);thread.start()
        with socket.create_connection(('127.0.0.1',self.port),timeout=4) as control:
            control.sendall(b'\x05\x01\x00');self.assertEqual(exact(control,2),b'\x05\x00')
            control.sendall(b'\x05\x03\x00\x01'+bytes(6));reply=exact(control,10);self.assertEqual(reply[1],0)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
                udp.settimeout(4)
                for name in (b'first.fixture.invalid',b'second.fixture.invalid'):
                    packet=b'\0\0\0\x03'+bytes([len(name)])+name+echo.getsockname()[1].to_bytes(2,'big')+b'doh-udp'
                    udp.sendto(packet,('127.0.0.1',int.from_bytes(reply[8:10],'big')));data,_=udp.recvfrom(1024);self.assertEqual(data[10:],b'doh-udp')
                    if name.startswith(b'first'):
                        bad=self.peer(mode='status');self.assertTrue(self.command(op='configure',handle=self.handle,config=self.config({'https_servers':[self.endpoint(bad)]}))['ok'])
        thread.join(4);self.assertFalse(thread.is_alive());self.assertEqual(len(peer.queries),4);self.assertFalse(bad.queries)

if __name__=='__main__':unittest.main(verbosity=2)
