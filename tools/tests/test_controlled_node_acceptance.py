"""Admission, real Windows Job retirement and loopback TLS/auth controls."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location("controlled_node_acceptance",TOOLS/"RunControlledNodeAcceptance.py")
qa=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
FIXTURES=TOOLS.parent/"src/Swirl.Quick/tests/fixtures"


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


class LoopbackTlsTests(unittest.TestCase):
    def setUp(self):
        self.fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem")

    def tearDown(self):
        self.fixture.close()

    def test_tls_positive_control_and_untrusted_certificate_rejection(self):
        trusted=ssl.create_default_context(cafile=str(FIXTURES/"localhost-cert.pem"))
        with socket.create_connection(("127.0.0.1",self.fixture.https)) as raw:
            with trusted.wrap_socket(raw,server_hostname="localhost") as peer:
                peer.sendall(b"GET /trace HTTP/1.1\r\nHost: localhost\r\n\r\n")
                self.assertIn(b"200 OK",peer.recv(4096))
        untrusted=ssl.create_default_context(cafile=str(FIXTURES/"xray-download-server-cert.pem"))
        with socket.create_connection(("127.0.0.1",self.fixture.https)) as raw:
            with self.assertRaises(ssl.SSLCertVerificationError):
                untrusted.wrap_socket(raw,server_hostname="localhost")

    def authenticated_peer(self):
        peer=socket.create_connection(("127.0.0.1",self.fixture.socks))
        peer.sendall(b"\x05\x01\x02")
        self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x05\x02")
        peer.sendall(b"\x01\x07fixture\x0efixture-secret")
        self.assertEqual(qa.LoopbackFixture.exact(peer,2),b"\x01\x00")
        return peer

    def test_socks_authentication_and_destination_boundary(self):
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


@unittest.skipUnless(os.name=="nt","Windows atomic Job boundary required")
class WindowsProcessTests(unittest.TestCase):
    def run_real_child(self,body):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest={"nonce":"a"*64,"sourceSha":"b"*40}
            qa.write_json(root/"session.json",manifest)
            actual=qa._WindowsProcess
            def launch(arguments,**keywords):
                return actual([sys.executable,"-c",body,str(root)],**keywords)
            with patch.object(qa,"_WindowsProcess",launch):
                return qa.execute(Path(sys.executable),root,manifest,dict(os.environ))

    def test_natural_exit_has_actual_process_and_job_proof(self):
        result=self.run_real_child("print('synthetic natural exit')")
        self.assertEqual(result["exitCode"],0)
        self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
        self.assertFalse(result["timedOut"])

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
