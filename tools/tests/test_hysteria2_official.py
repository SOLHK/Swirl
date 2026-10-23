"""Real Hysteria 2 server -> independent TCP/UDP/HTTPS/DNS targets.

The only client proxy implementation is the compiled Swirl Rust example.
HY2_SERVER must be the pinned official server executable, never a client daemon.
Requires Python cryptography for isolated, ephemeral CA/server certificates.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import http.server
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
from urllib.parse import quote

from native_client_stack import client_command, stack_receipt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


OFFICIAL_VERSION = "v2.13.0"
OFFICIAL_COMMIT = "ca8fbd874fd6ca82413948de6dc5924405e103e1"
OFFICIAL_SHA256 = {
    "linux-amd64": "907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691",
    "darwin-arm64": "c8c3589239ce4ecf335c07a3f6ec11b3ef8fbdfe9e5a5ea0ef8ba8ce50d2bb90",
    "darwin-amd64": "7a155230ae4bbffc92657f486484a48ed703bd828abf7a3e19287fea1f9ca74a",
    "windows-amd64": "162ef8fe55dc7ec810dda662908f8e65ec36bd6da39cb87c3bd66184ab68f067",
}
BODY = b"swirl-hysteria2-native"


class TCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class UDP(socketserver.ThreadingUDPServer):
    daemon_threads = True


class TCP6(TCP):
    address_family = socket.AF_INET6


class UDP6(UDP):
    address_family = socket.AF_INET6


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(20)
        while True:
            data = self.request.recv(16384)
            if not data:
                self.request.shutdown(socket.SHUT_WR)
                return
            self.request.sendall(data)


class EchoUDP(socketserver.BaseRequestHandler):
    received_sizes = []

    def handle(self):
        data, connection = self.request
        self.received_sizes.append(len(data))
        connection.sendto(data, self.client_address)


class DelayedEcho(socketserver.BaseRequestHandler):
    received_bytes = 0

    def handle(self):
        self.request.settimeout(10)
        received = bytearray()
        try:
            while True:
                data = self.request.recv(16384)
                if not data:
                    break
                received.extend(data)
            type(self).received_bytes += len(received)
            self.request.sendall(received)
        except (ConnectionResetError, BrokenPipeError):
            # This target deliberately waits for FIN; the pinned server closes
            # both directions after either copy finishes. Evidence retains it.
            type(self).received_bytes += len(received)


class DNS(socketserver.BaseRequestHandler):
    def handle(self):
        data, connection = self.request
        if len(data) < 12:
            return
        response = data[:2] + b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + data[12:]
        response += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\xc0\x00\x02\x01"
        connection.sendto(response, self.client_address)


class HTTP(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    tls_close_errors = []

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def finish(self):
        super().finish()
        if isinstance(self.connection, ssl.SSLSocket):
            try:
                self.connection.unwrap()
            except (OSError, ssl.SSLError) as error:
                self.tls_close_errors.append(type(error).__name__)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(BODY)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *_):
        pass


def certificate_files(directory):
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Swirl isolated HY2 CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
              key_encipherment=False, data_encipherment=False, key_agreement=False,
              key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (x509.CertificateBuilder()
          .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hy2.test")]))
          .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(minutes=5))
          .not_valid_after(now + datetime.timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.DNSName("hy2.test"),
              x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
              x509.IPAddress(ipaddress.ip_address("::1"))]), critical=False)
          .sign(ca_key, hashes.SHA256()))
    cert_path, key_path = directory / "server.pem", directory / "server-key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path, base64.b64encode(ca.public_bytes(serialization.Encoding.DER)).decode(), certificate.fingerprint(hashes.SHA256()).hex()


class OfficialPeer:
    def __init__(self, binary, directory, cert, key, password, name, obfs_password=None,
                 host="127.0.0.1", ignore_client_bandwidth=True, bandwidth=None):
        self.binary, self.directory, self.name = binary, directory, name
        self.password = password
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM) as reserved:
            reserved.bind((host, 0))
            self.port = reserved.getsockname()[1]
        self.config = directory / f"{name}.json"
        config = {
            "listen": f"[{host}]:{self.port}" if ":" in host else f"{host}:{self.port}",
            "tls": {"cert": str(cert), "key": str(key)},
            "auth": {"type": "password", "password": password},
            "ignoreClientBandwidth": ignore_client_bandwidth,
        }
        if obfs_password is not None:
            config["obfs"] = {"type": "salamander", "salamander": {"password": obfs_password}}
        if bandwidth is not None:
            config["bandwidth"] = bandwidth
        self.config.write_text(json.dumps(config), encoding="utf-8")
        self.process = None
        self.log = None
        self.start()

    def start(self):
        self.log = (self.directory / f"{self.name}.log").open("ab")
        self.process = subprocess.Popen([str(self.binary), "server", "-c", str(self.config)],
            stdout=self.log, stderr=self.log)
        time.sleep(0.35)
        if self.process.poll() is not None:
            raise RuntimeError("OfficialHysteriaServerExited")

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None


class Hysteria2Official(unittest.TestCase):
    records = []

    @classmethod
    def setUpClass(cls):
        cls.server = Path(os.environ["HY2_SERVER"]).resolve(strict=True)
        cls.client = Path(os.environ["HY2_CLIENT"]).resolve(strict=True)
        cls.server_hash = hashlib.sha256(cls.server.read_bytes()).hexdigest()
        if cls.server_hash not in OFFICIAL_SHA256.values():
            raise RuntimeError("OfficialHysteriaServerDigestMismatch")
        version = subprocess.check_output([str(cls.server), "version"], stderr=subprocess.STDOUT, timeout=10).decode()
        if OFFICIAL_VERSION not in version or OFFICIAL_COMMIT not in version:
            raise RuntimeError("OfficialHysteriaServerVersionMismatch")
        cls.temp = tempfile.TemporaryDirectory(prefix="swirl-hy2-official-")
        cls.directory = Path(cls.temp.name)
        cert, key, cls.ca, cls.pin = certificate_files(cls.directory)
        cls.peers = []
        cls.origins = []
        cls.threads = []
        for label in ("a", "b"):
            cls.peers.append(OfficialPeer(cls.server, cls.directory, cert, key,
                f"synthetic:{label}-x14a-local-only", label))
        cls.obfs_password = "synthetic-obfs-x14a-local-only"
        cls.peers.append(OfficialPeer(cls.server, cls.directory, cert, key,
            "synthetic:obfuscated-x14a-local-only", "obfuscated", cls.obfs_password))
        cls.peers.append(OfficialPeer(cls.server, cls.directory, cert, key,
            "synthetic:capped-x14a-local-only", "capped", ignore_client_bandwidth=False,
            bandwidth={"down":"1 mbps"}))
        cls.peers.append(OfficialPeer(cls.server, cls.directory, cert, key,
            "synthetic:negotiated-x14a-local-only", "negotiated", ignore_client_bandwidth=False))
        cls.tcp = TCP(("127.0.0.1", 0), Echo)
        cls.delayed = TCP(("127.0.0.1", 0), DelayedEcho)
        cls.udp = UDP(("127.0.0.1", 0), EchoUDP)
        cls.dns = UDP(("127.0.0.1", 0), DNS)
        cls.https = TCP(("127.0.0.1", 0), HTTP)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        cls.https.socket = context.wrap_socket(cls.https.socket, server_side=True)
        for origin in (cls.tcp, cls.delayed, cls.udp, cls.dns, cls.https):
            cls.origins.append(origin)
            thread = threading.Thread(target=origin.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)
        cls.ipv6_available = False
        ipv6_origins=[]
        try:
            cls.tcp6 = TCP6(("::1",0),Echo)
            ipv6_origins.append(cls.tcp6)
            cls.udp6 = UDP6(("::1",0),EchoUDP)
            ipv6_origins.append(cls.udp6)
            cls.peers.append(OfficialPeer(cls.server, cls.directory, cert, key,
                "synthetic:ipv6-x14a-local-only", "ipv6", host="::1"))
        except OSError:
            # The receipt records an unavailable IPv6 environment explicitly.
            # A skipped platform is not counted as IPv6 interoperability.
            for origin in ipv6_origins:
                origin.server_close()
        else:
            cls.origins.extend(ipv6_origins)
            for origin in ipv6_origins:
                thread=threading.Thread(target=origin.serve_forever,daemon=True)
                thread.start()
                cls.threads.append(thread)
            cls.ipv6_available = True

    @classmethod
    def tearDownClass(cls):
        for peer in cls.peers:
            peer.stop()
        for origin in cls.origins:
            origin.shutdown()
            origin.server_close()
        summary = {"official_version": OFFICIAL_VERSION, "official_commit": OFFICIAL_COMMIT,
            "official_server_sha256": cls.server_hash,
            "client_sha256": hashlib.sha256(cls.client.read_bytes()).hexdigest(),
            "client_role": "Swirl native Rust", "server_role": "official Hysteria2 only",
            "records": cls.records, "qt_product_acceptance": False,
            "known_upstream_limitations": {
                "half_close": "Not passed: official copyTwoWay returns after either copy finishes and closes both directions.",
                "udp_reply_buffer": "Official v2.13.0 allocates 4096 bytes for encoded messages; payload plus Hysteria header must fit that buffer.",
                "source_urls": [
                    "https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/copy.go",
                    "https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/server.go",
                    "https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/udp.go",
                    "https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/internal/protocol/proxy.go"]}}
        destination = os.environ.get("HY2_EVIDENCE")
        if destination:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        cls.temp.cleanup()

    def config(self, peer=0):
        return {"host":"127.0.0.1", "port":self.peers[peer].port,
            "password":self.peers[peer].password,
            "tls":{"server_name":"hy2.test", "alpn":["h3"], "ca_der_base64":self.ca}}

    def request(self, case, *, mode="tcp", size=4096, config=None, source=None, success=True, code=None, target=None, target_tls=None, target_host="127.0.0.1", timeout_ms=10000, limitation=False):
        origin = target or (self.udp if mode == "udp" else self.dns if mode == "dns" else self.tcp)
        request = {"target_host":target_host, "target_port":origin.server_address[1],
            "mode":mode, "size":size, "timeout_ms":timeout_ms}
        if source is not None:
            request["source"] = source
        else:
            request["config"] = config if config is not None else self.config()
        if target_tls is not None:
            request["target_tls"] = target_tls
        before = time.monotonic()
        result = subprocess.run(client_command(self.client), input=json.dumps(request),
            text=True, capture_output=True, timeout=15)
        measured_stack = stack_receipt(result.stderr)
        try:
            report = json.loads(result.stdout)
        except (ValueError, TypeError):
            report = {"ok":False, "code":"AcceptanceDriverOutput"}
        self.records.append({"case":case, "expected_success":success, "upstream_limitation_probe":limitation,
            "client_exit":result.returncode, "elapsed_ms":round((time.monotonic()-before)*1000,3),
            "main_stack_limit":measured_stack, "result":report})
        self.assertEqual(report.get("ok"),success,case + ": " + str(report))
        self.assertEqual(result.returncode,0 if success else 1)
        if code is not None:
            self.assertEqual(report.get("code"),code)
        return report

    def test_01_tcp_and_clean_normal_close(self):
        self.assertEqual(self.request("tcp-clean-normal-close")["close"],"clean")

    def test_02_large_bidirectional_data(self):
        result = self.request("tcp-4mib-bidirectional",size=4*1024*1024)
        self.assertEqual(result["downloaded"],4*1024*1024)

    def test_03_udp_and_fragmented_datagrams(self):
        self.request("udp-small",mode="udp",size=200)
        self.request("udp-fragmented-3072",mode="udp",size=3072)
        self.request("udp-fragmented-4000",mode="udp",size=4000)

    def test_04_dns(self):
        self.request("dns-over-native-udp",mode="dns")

    def test_05_wrong_password(self):
        config=self.config();config["password"]="incorrect-synthetic-credential"
        self.request("wrong-password",config=config,success=False,code="Hysteria2AuthenticationRejected")

    def test_06_tls_trust_and_sni(self):
        config=self.config();del config["tls"]["ca_der_base64"]
        self.request("untrusted-server-certificate",config=config,success=False)
        config=self.config();config["tls"]["server_name"]="wrong.test"
        self.request("wrong-sni",config=config,success=False)

    def test_07_certificate_pin(self):
        config=self.config();config["pin_sha256"]=self.pin
        self.request("correct-certificate-pin",config=config)
        config["pin_sha256"]="00"*32
        self.request("wrong-certificate-pin",config=config,success=False)

    def test_08_imported_clash_and_uri(self):
        config=self.config()
        raw={"type":"hysteria2","server":config["host"],"port":config["port"],
            "password":config["password"],"sni":"hy2.test","ca-der-base64":self.ca}
        result=self.request("clash-import-to-native",source=json.dumps({"proxies":[raw]}))
        self.assertTrue(result["imported"])
        for scheme in ("hy2","hysteria2"):
            uri=f'{scheme}://{quote(config["password"],safe=":")}@127.0.0.1:{config["port"]}/?sni=hy2.test&ca-der-base64={quote(self.ca,safe="")}'
            result=self.request(scheme+"-uri-to-native",source=uri)
            self.assertTrue(result["imported"])

    def test_09_node_switch_and_new_session_after_restart(self):
        for index in (0,1,0,1):
            self.request("node-"+str(index),config=self.config(index))
        self.peers[0].stop()
        self.peers[0].start()
        self.request("new-session-after-server-restart")

    def test_10_https_through_native_proxy(self):
        # Releasing the final QUIC owner used to race the queued TLS alert.
        # Exercise repeated fresh sessions; a 200 response still cannot excuse
        # even one origin-side missing close_notify.
        for attempt in range(8):
            with self.subTest(attempt=attempt):
                self.request("verified-https-through-native-proxy-"+str(attempt),
                    mode="http",target=self.https,
                    target_tls={"server_name":"localhost","ca_der_base64":self.ca})
                self.assertEqual(HTTP.tls_close_errors,[])

    def test_11_invalid_options_fail_before_connection(self):
        for field,value,code in (("obfs","gecko","Hysteria2ObfsUnsupported"),
                ("ports","443,8443","Hysteria2PortHoppingUnsupported"),
                ("up_mbps",2**64-1,"Hysteria2BandwidthParameters"),
                ("ech","AAAA","Hysteria2EchUnsupported")):
            config=self.config();config[field]=value
            self.request("unsupported-"+field,config=config,success=False,code=code)

    def test_12_record_official_server_limitations_without_claiming_support(self):
        self.request("upstream-half-close-not-supported",mode="half-close",target=self.delayed,
            success=False,code="TcpTruncated",limitation=True)
        before=len(EchoUDP.received_sizes)
        self.request("upstream-4096-byte-udp-reply-drop",mode="udp",size=4096,
            timeout_ms=2000,success=False,code="Hysteria2AcceptanceTimeout",limitation=True)
        self.assertIn(4096,EchoUDP.received_sizes[before:])
        self.records[-1]["independent_udp_target_received_4096_bytes"]=True

    def test_13_salamander_tcp_udp_and_wrong_password(self):
        config=self.config(2)
        config.update(obfs="salamander",obfs_password=self.obfs_password)
        self.request("salamander-tcp-1mib",config=config,size=1024*1024)
        self.request("salamander-udp-fragmented-3072",config=config,mode="udp",size=3072)
        config["obfs_password"]="incorrect-synthetic-obfuscation-password"
        self.request("salamander-wrong-password",config=config,timeout_ms=1500,success=False)

    def test_14_explicit_insecure_still_enforces_certificate_pin(self):
        config=self.config()
        del config["tls"]["ca_der_base64"]
        config.update(insecure=True,pin_sha256=self.pin)
        self.request("explicit-insecure-correct-pin",config=config)
        config["pin_sha256"]="00"*32
        self.request("explicit-insecure-wrong-pin",config=config,success=False)

    def test_15_negotiated_bandwidth_is_enforced_in_real_transfers(self):
        config=self.config()
        config["up_mbps"]=1
        result=self.request("client-upload-rate-1mbps",config=config,size=256*1024)
        self.assertGreater(result["total_us"],1_500_000)
        result=self.request("server-receive-rate-1mbps",config=self.config(3),size=256*1024)
        self.assertGreater(result["total_us"],1_500_000)
        config=self.config(4)
        config["down_mbps"]=1
        result=self.request("negotiated-download-rate-1mbps",config=config,size=256*1024)
        self.assertGreater(result["total_us"],1_500_000)

    def test_16_ipv6_quic_and_ipv6_tcp_udp_targets(self):
        if not self.ipv6_available:
            self.records.append({"case":"ipv6","executed":False,"reason":"Ipv6LoopbackUnavailable"})
            self.skipTest("IPv6 loopback unavailable; not accepted as supported on this runner")
        config=self.config(5)
        config["host"]="::1"
        self.request("ipv6-quic-tcp",config=config,target=self.tcp6,target_host="::1")
        self.request("ipv6-quic-udp",config=config,mode="udp",size=3072,target=self.udp6,target_host="::1")

    def test_17_concurrent_connections_and_multi_address_resolution(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results=list(executor.map(lambda index:self.request(f"concurrent-{index}",size=256*1024),range(4)))
        self.assertEqual(sum(result["downloaded"] for result in results),1024*1024)
        config=self.config()
        config["host"]="localhost"
        self.request("multi-address-localhost-to-ipv4-server",config=config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
