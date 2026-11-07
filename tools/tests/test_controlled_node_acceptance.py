"""Admission, real Windows Job retirement and loopback TLS/auth controls."""
import importlib.util
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location("controlled_node_acceptance",TOOLS/"RunControlledNodeAcceptance.py")
qa=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
FIXTURES=TOOLS.parent/"src/Swirl.Quick/tests/fixtures"


def manifest_for(fixture):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1",0))
        port=listener.getsockname()[1]
    return dict(schema=2,sourceSha="b"*40,nonce="a"*64,nodeOrdinal=1,proxyPort=port,
                fixture=dict(httpPort=fixture.http,httpsPort=fixture.https,socksPort=fixture.socks,
                             caSha256=qa.FIXTURE_CERT_SHA256))


class AdmissionTests(unittest.TestCase):
    def test_batches_have_explicit_distinct_bounded_nodes(self):
        self.assertEqual(qa.ordinals("2,4,6"),[2,4,6])
        for value in ["", "0", "1,1", "10001", "1,,2", ",".join(str(i) for i in range(1,14))]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                qa.ordinals(value)

    def test_child_does_not_inherit_proxy_or_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            parent={"PATH":"safe-path","GITHUB_TOKEN":"synthetic","HTTPS_PROXY":"synthetic",
                    "ALL_PROXY":"synthetic","APPDATA":"original-private-profile"}
            with patch.dict(os.environ,parent,clear=True):
                result=qa.environment(Path(directory))
                self.assertEqual(dict(os.environ),parent)
            for name in ["GITHUB_TOKEN","HTTPS_PROXY","ALL_PROXY"]:
                self.assertNotIn(name,result)
            self.assertNotEqual(result["APPDATA"],parent["APPDATA"])
            self.assertEqual(result["SWIRL_TEST_ROOT"],directory)

    def test_live_and_private_store_refuse_before_all_path_or_network_work(self):
        for flag in ("--live","--store"):
            for argv in ([flag],[flag+"="],[flag+"=synthetic-secret"],[flag,"synthetic-secret"]):
                with self.subTest(argv=argv),patch.object(qa,"local_file",side_effect=AssertionError("must not read")),\
                        patch.object(qa,"LoopbackFixture",side_effect=AssertionError("must not listen")),\
                        self.assertRaisesRegex(ValueError,"^"+qa.LIVE_REFUSAL+"$"):
                    qa.main(argv)

    def test_actual_cli_refuses_private_arguments_without_echo(self):
        for flag in ("--live","--store"):
            result=subprocess.run([sys.executable,str(TOOLS/"RunControlledNodeAcceptance.py"),
                                   flag+"=SYNTHETIC_PRIVATE_SENTINEL"],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,64)
            self.assertEqual(result.stdout,b"")
            self.assertEqual(json.loads(result.stderr),dict(errorCode=qa.LIVE_REFUSAL,networkStarted=False))
            self.assertNotIn(b"SYNTHETIC_PRIVATE_SENTINEL",result.stderr)

    def test_batch_is_rejected_before_platform_or_binary_reads(self):
        argv=["--exe","absent.exe","--exe-sha256","a"*64,"--core-sha256","b"*64,
              "--expected-source","c"*40,"--output-directory","absent-output",
              "--fixture-directory","absent-fixtures","--nodes","1,2"]
        with patch.object(qa,"local_file",side_effect=AssertionError("must not read")),\
                self.assertRaisesRegex(ValueError,"SingleSyntheticNodeRequired"):
            qa.main(argv)

    def test_json_cannot_construct_fixture_capability_or_start_process(self):
        with self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
            qa._FixtureProof(object(),None,b"x"*32)
        with patch.object(qa,"_WindowsJob",side_effect=AssertionError("must not spawn")),\
                self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
            qa.execute(Path("absent.exe"),Path("absent-output"),{}, {}, {"fixture":True})


class LoopbackTlsTests(unittest.TestCase):
    def setUp(self):
        self.fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem")
        self.manifest=manifest_for(self.fixture)
        self.proof=self.fixture.bind_session(self.manifest)

    def tearDown(self):
        self.fixture.close()

    def test_tls_positive_control_and_untrusted_certificate_rejection(self):
        trusted=ssl.create_default_context(cafile=str(FIXTURES/"localhost-cert.pem"))
        with socket.create_connection(("127.0.0.1",self.fixture.https)) as raw:
            with trusted.wrap_socket(raw,server_hostname="127.0.0.1") as peer:
                peer.sendall(b"GET /trace HTTP/1.1\r\nHost: localhost\r\n\r\n")
                self.assertIn(b"200 OK",peer.recv(4096))
        untrusted=ssl.create_default_context(cafile=str(FIXTURES/"xray-download-server-cert.pem"))
        with socket.create_connection(("127.0.0.1",self.fixture.https)) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):
                untrusted.wrap_socket(raw,server_hostname="127.0.0.1")

    def prove(self):
        frame=self.proof.pipe_frame(self.manifest)
        self.assertEqual(len(frame),len(qa.PROOF_MAGIC)+96)
        payload=frame[len(qa.PROOF_MAGIC):]
        request=qa.FIXTURE_MAGIC+payload[:32]+b"c"*32
        with socket.create_connection(("127.0.0.1",self.fixture.socks),timeout=2) as peer:
            peer.sendall(request)
            response=qa.LoopbackFixture.exact(peer,32)
        self.assertTrue(hmac.compare_digest(response,hmac.digest(payload[32:64],request,"sha256")))
        return request,response

    def test_actual_fixture_proof_is_bound_and_not_reusable(self):
        request,response=self.prove()
        self.assertEqual(self.fixture.proofs,1)
        with socket.create_connection(("127.0.0.1",self.fixture.socks),timeout=2) as peer:
            peer.sendall(request)
            self.assertEqual(peer.recv(32),b"")
        self.assertEqual(self.fixture.proofs,1)
        self.assertEqual(self.fixture.rejected,1)
        self.assertEqual(self.fixture.socks_connections,0)
        wrong=self.proof.pipe_frame(self.manifest,"wrong-proof")[len(qa.PROOF_MAGIC):]
        self.assertFalse(hmac.compare_digest(response,hmac.digest(wrong[32:64],request,"sha256")))

    def test_wrong_manifest_proof_and_early_socks_do_not_open_relay(self):
        with socket.create_connection(("127.0.0.1",self.fixture.socks),timeout=2) as peer:
            peer.sendall(qa.FIXTURE_MAGIC+b"z"*64)
            self.assertEqual(peer.recv(32),b"")
        with socket.create_connection(("127.0.0.1",self.fixture.socks),timeout=2) as peer:
            peer.sendall(b"\x05")
            self.assertEqual(peer.recv(2),b"")
        self.assertEqual(self.fixture.proofs,0)
        self.assertEqual(self.fixture.socks_connections,0)
        self.assertEqual(self.fixture.forwarded,0)

    def test_actual_capability_rejects_changed_manifest_and_closed_fixture(self):
        altered=dict(self.manifest,nonce="d"*64)
        with self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
            self.proof.pipe_frame(altered)
        self.fixture.close()
        with self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
            self.proof.pipe_frame(self.manifest)

    def test_fixture_manifest_is_exact_and_owned(self):
        changes=[{"nodeOrdinal":2},{"schema":True},{"fixture":True},{"privateStore":"not-opened"}]
        for change in changes:
            fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem")
            try:
                manifest=manifest_for(fixture)
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
                    fixture.bind_session(dict(manifest,**change))
                # Failed admission did not consume or authorize the instance.
                self.assertEqual(fixture.proofs,0)
                fixture.bind_session(manifest)
            finally:
                fixture.close()
        self.assertEqual(self.fixture.proofs,0)
        self.assertEqual(self.fixture.forwarded,0)

    def authenticated_peer(self):
        if self.fixture.proofs==0:
            self.prove()
        peer=socket.create_connection(("127.0.0.1",self.fixture.socks))
        peer.sendall(b"\x05\x01\x02")
        self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x05\x02")
        password=self.fixture._password.hex().encode()
        peer.sendall(b"\x01\x07fixture"+bytes([len(password)])+password)
        self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x01\x00")
        return peer

    def test_socks_authentication_and_destination_boundary(self):
        self.prove()
        with socket.create_connection(("127.0.0.1",self.fixture.socks)) as peer:
            peer.sendall(b"\x05\x01\x02")
            self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x05\x02")
            peer.sendall(b"\x01\x01x\x01x")
            self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x01\x01")
        with self.authenticated_peer() as peer:
            peer.sendall(b"\x05\x01\x00\x03\x0bexample.com"+self.fixture.http.to_bytes(2,"big"))
            self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x05\x02")
        self.assertEqual(self.fixture.forwarded,0)
        self.assertEqual(self.fixture.rejected,1)

    def test_authenticated_owned_relay_serves_only_its_http_origin(self):
        with self.authenticated_peer() as peer:
            peer.sendall(b"\x05\x01\x00\x01\x7f\x00\x00\x01"+self.fixture.http.to_bytes(2,"big"))
            self.assertEqual(qa.LoopbackFixture.exact(peer,10),b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            peer.sendall(b"HEAD /generate_204 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            self.assertIn(b"HTTP/1.1 204 No Content",peer.recv(4096))
        self.assertEqual(self.fixture.forwarded,1)
        self.assertEqual(self.fixture.socks_connections,1)

    def test_half_tls_handshake_is_owned_and_closed_within_original_cleanup_budget(self):
        entered=threading.Event()
        returned=threading.Event()
        native=ssl.SSLSocket.do_handshake
        def handshake(peer,*args,**kwargs):
            entered.set()
            try:
                return native(peer,*args,**kwargs)
            finally:
                returned.set()
        with patch.object(ssl.SSLSocket,"do_handshake",handshake):
            with socket.create_connection(("127.0.0.1",self.fixture.https),timeout=2) as peer:
                # Incomplete TLS record: the real server handshake must wait.
                peer.sendall(b"\x16\x03\x01\x00\x20\x01")
                self.assertTrue(entered.wait(1))
                self.assertFalse(returned.wait(0.02))
                with self.fixture.lock:
                    self.assertTrue(any(isinstance(item,ssl.SSLSocket) for item in self.fixture.sockets))
                started=time.monotonic()
                self.fixture.close()
                self.assertLess(time.monotonic()-started,3)
                self.assertTrue(returned.is_set())
                with self.fixture.lock:
                    self.assertEqual(self.fixture.sockets,set())
                    self.assertFalse(any(thread.is_alive() for thread in self.fixture.threads))


@unittest.skipUnless(os.name=="nt","Windows atomic Job boundary required")
class WindowsProcessTests(unittest.TestCase):
    def run_real_child(self,body):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem")
            try:
                manifest=manifest_for(fixture)
                proof=fixture.bind_session(manifest)
                qa.write_json(root/"session.json",manifest)
                actual=qa._WindowsProcess
                def launch(arguments,**keywords):
                    return actual([sys.executable,"-c",body,str(root)],**keywords)
                with patch.object(qa,"_WindowsProcess",launch):
                    return qa.execute(Path(sys.executable),root,manifest,dict(os.environ),proof)
            finally:
                fixture.close()

    def test_natural_exit_has_actual_process_and_job_proof(self):
        result=self.run_real_child("print('synthetic natural exit')")
        self.assertEqual(result["exitCode"],0)
        self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
        self.assertFalse(result["timedOut"])

    def test_native_deadline_exit_is_recorded_after_owned_process_retirement(self):
        result=self.run_real_child("raise SystemExit(124)")
        self.assertEqual(result["exitCode"],124)
        self.assertTrue(result["timedOut"] and result["processSignaled"] and result["ownedJobEmpty"])

    def test_stalled_request_is_killed_without_renewing_its_deadline(self):
        body="""import json,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);state=json.loads((root/'session.json').read_text());state['phase']='requests'
(root/'state.json').write_text(json.dumps(state));time.sleep(60)
"""
        started=time.monotonic()
        result=self.run_real_child(body)
        self.assertTrue(result["timedOut"] and result["requestPhaseObserved"])
        self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
        self.assertEqual(result["exitCode"],125)
        self.assertLess(time.monotonic()-started,12)


if __name__=="__main__":
    unittest.main()
