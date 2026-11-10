"""Admission, real Windows Job retirement and loopback TLS/auth controls."""
import importlib.util
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location("controlled_node_acceptance",TOOLS/"RunControlledNodeAcceptance.py")
qa=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
import ControlledNodeWatchdog as watchdog_receipt
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

    def test_fixed_native_control_rejects_other_modes_before_any_side_effect(self):
        base=["--exe","absent.exe","--exe-sha256","a"*64,"--core-sha256","b"*64,
              "--expected-source","c"*40,"--output-directory","absent-output",
              "--fixture-directory","absent-fixtures","--fixture-native-watchdog-500ms"]
        for extra in ([],["--fixture-stall","--fixture-wrong-ca"],
                      ["--fixture-stall","--fixture-admission-control","wrong-proof"],
                      ["--fixture-stall","--nodes","1,2"]):
            with self.subTest(extra=extra),\
                    patch.object(qa,"local_file",side_effect=AssertionError("must not read")),\
                    patch.object(qa,"LoopbackFixture",side_effect=AssertionError("must not listen")),\
                    patch.object(qa,"_WindowsStorage",side_effect=AssertionError("must not create")),\
                    self.assertRaisesRegex(ValueError,"SingleSyntheticNodeRequired|FixedNativeWatchdogControlRequired"):
                qa.main(base+extra)


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


class NativeWatchdogReceiptTests(unittest.TestCase):
    def setUp(self):
        self.initial = watchdog_receipt.initial_record(123, {"nonce":"a"*64,"sourceSha":"b"*40}, 1000, 10_000_000)

    def record(self, *, request=2_000_000_000, fired=10_000_000_001, committed=1):
        data = bytearray(self.initial)
        struct.pack_into("<5Q", data, 128, 1_000_000_000, 29_000_000_000, request,
                         request+8_000_000_000 if request else 21_000_000_000, fired)
        struct.pack_into("<Q", data, 176, 90_000_000)
        struct.pack_into("<II", data, 192, 2 if request else 1, committed)
        return bytes(data)

    def verify(self, data, exit_code=124):
        return watchdog_receipt.verify_record(data,initial=self.initial,exit_code=exit_code,exited_qpc=91_000_000)

    def test_complete_native_request_receipt_has_exact_original_deadline(self):
        result=self.verify(self.record())
        self.assertTrue(result["triggered"])
        self.assertEqual(result["phase"],"requests")
        self.assertEqual(result["deadlineMs"],8000)
        self.assertEqual(result["absoluteLimitMs"],28000)
        self.assertEqual(result["deadlineOverrunNs"],"1")
        self.assertEqual(len(result["receiptSha256"]),64)
        self.assertNotIn("nonce",result)
        self.assertTrue(self.verify(self.record(),exit_code=125)["triggered"])

    def test_startup_deadline_remains_twenty_seconds(self):
        result=self.verify(self.record(request=0,fired=21_000_000_000))
        self.assertEqual((result["phase"],result["deadlineMs"]),("startup",20000))

    def test_bare_exit_124_or_incomplete_record_cannot_assert_timeout(self):
        for data in (self.initial,self.record(committed=0)):
            with self.subTest(data=data is self.initial),self.assertRaisesRegex(ValueError,"NativeWatchdogExitUnproven"):
                self.verify(data)
            result=self.verify(data,exit_code=125)
            self.assertFalse(result["triggered"])
        self.assertFalse(self.verify(self.initial,exit_code=0)["triggered"])

    def test_changed_process_nonce_source_or_parent_clock_is_rejected(self):
        for offset in (0,16,20,24,88,168,184,200,255):
            data=bytearray(self.record());data[offset]^=1
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,"IdentityMismatch"):
                self.verify(bytes(data))

    def test_early_trigger_forged_deadline_or_outside_process_clock_is_rejected(self):
        for offset,value in ((128,0),(136,29_000_000_001),(144,21_000_000_000),
                             (152,9_000_000_000),(160,9_999_999_999),(176,999),(176,91_000_001)):
            data=bytearray(self.record());struct.pack_into("<Q",data,offset,value)
            with self.subTest(offset=offset,value=value),self.assertRaisesRegex(ValueError,"DeadlineUnproven"):
                self.verify(bytes(data))
        for offset,value in ((192,1),(196,2)):
            data=bytearray(self.record());struct.pack_into("<I",data,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):
                self.verify(bytes(data))
        for exit_code in (0,2,64):
            with self.subTest(exit_code=exit_code),self.assertRaisesRegex(ValueError,"DeadlineUnproven"):
                self.verify(self.record(),exit_code=exit_code)

    def test_invalid_lengths_and_invalid_initial_identity_are_rejected(self):
        for data in (b"",self.record()[:-1],self.record()+b"x"):
            with self.subTest(length=len(data)),self.assertRaises(ValueError):
                self.verify(data)
        for pid in (0,-1,True,2**32):
            with self.subTest(pid=pid),self.assertRaisesRegex(ValueError,"IdentityRejected"):
                watchdog_receipt.initial_record(pid,{"nonce":"a"*64,"sourceSha":"b"*40},1000,1)

    def fixed_initial(self):
        return watchdog_receipt.initial_record(123,dict(nonce="a"*64,sourceSha="b"*40,
            nativeWatchdogControl=qa.NATIVE_REQUEST_500MS_CONTROL),1000,10_000_000)

    def fixed_record(self, *, committed=1):
        data=bytearray(self.record(fired=2_500_000_001,committed=committed))
        struct.pack_into("<Q",data,152,2_500_000_000)
        struct.pack_into("<I",data,200,1)
        return bytes(data)

    def test_fixed_native_contract_requires_parent_bound_exact_500ms_record(self):
        initial=self.fixed_initial()
        self.assertEqual(initial[:200],self.initial[:200])
        self.assertEqual(struct.unpack_from("<I",initial,200)[0],1)
        self.assertEqual(initial[204:],bytes(52))
        result=watchdog_receipt.verify_record(self.fixed_record(),initial=initial,
                                              exit_code=124,exited_qpc=91_000_000)
        self.assertTrue(result["triggered"] and result["committed"])
        self.assertEqual((result["controlCode"],result["phase"],result["deadlineMs"]),(1,"requests",500))
        self.assertEqual(result["absoluteLimitMs"],28000)
        normal=self.verify(self.record())
        self.assertEqual((normal["controlCode"],normal["deadlineMs"]),(0,8000))

    def test_fixed_and_normal_contracts_or_intervals_cannot_be_interchanged(self):
        for data,initial in ((self.record(),self.fixed_initial()),(self.fixed_record(),self.initial)):
            with self.subTest(code=initial[200]),self.assertRaisesRegex(ValueError,"IdentityMismatch"):
                watchdog_receipt.verify_record(data,initial=initial,exit_code=124,exited_qpc=91_000_000)
        for data,initial in ((self.record(),self.fixed_initial()),(self.fixed_record(),self.initial)):
            changed=bytearray(data);changed[200:204]=initial[200:204]
            with self.subTest(code=initial[200]),self.assertRaisesRegex(ValueError,"DeadlineUnproven"):
                watchdog_receipt.verify_record(bytes(changed),initial=initial,exit_code=124,exited_qpc=91_000_000)
        bad=bytearray(self.fixed_initial());struct.pack_into("<I",bad,200,2)
        with self.assertRaisesRegex(ValueError,"IdentityMismatch"):
            watchdog_receipt.verify_record(bytes(bad),initial=bytes(bad),exit_code=0,exited_qpc=91_000_000)

    def test_fixed_native_control_needs_real_124_and_committed_record(self):
        initial=self.fixed_initial()
        with self.assertRaisesRegex(ValueError,"DeadlineUnproven"):
            watchdog_receipt.verify_record(self.fixed_record(),initial=initial,exit_code=125,exited_qpc=91_000_000)
        for data in (initial,self.fixed_record(committed=0)):
            with self.subTest(partial=data!=initial),self.assertRaisesRegex(ValueError,"NativeWatchdogExitUnproven"):
                watchdog_receipt.verify_record(data,initial=initial,exit_code=124,exited_qpc=91_000_000)
            result=watchdog_receipt.verify_record(data,initial=initial,exit_code=125,exited_qpc=91_000_000)
            self.assertFalse(result["triggered"] or result["committed"])

    def test_unknown_or_numeric_native_control_is_rejected(self):
        for control in (None,True,1,500,"normal","native-watchdog-501ms",{}):
            with self.subTest(control=control),self.assertRaisesRegex(ValueError,"NativeWatchdogControlRejected"):
                watchdog_receipt.initial_record(123,dict(nonce="a"*64,sourceSha="b"*40,
                    nativeWatchdogControl=control),1000,10_000_000)


class FixedNativeFixtureTests(unittest.TestCase):
    def test_fixed_control_needs_the_owned_stall_and_correct_tls_fixture(self):
        for stall in (False,True):
            fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem",stall=stall)
            try:
                manifest=manifest_for(fixture)
                manifest["nativeWatchdogControl"]=qa.NATIVE_REQUEST_500MS_CONTROL
                if stall:
                    manifest["fixture"]["caSha256"]=qa.WRONG_CA_SHA256
                with self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
                    fixture.bind_session(manifest)
                self.assertEqual((fixture.proofs,fixture.socks_connections,fixture.forwarded),(0,0,0))
            finally:
                fixture.close()

    def test_complete_manifest_hmac_binds_fixed_control_without_changing_proof_size(self):
        fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem",stall=True)
        try:
            manifest=manifest_for(fixture)
            manifest["nativeWatchdogControl"]=qa.NATIVE_REQUEST_500MS_CONTROL
            proof=fixture.bind_session(manifest)
            frame=proof.pipe_frame(manifest)
            self.assertEqual(len(frame),len(qa.PROOF_MAGIC)+96)
            self.assertEqual(len(frame+struct.pack("<Q",123)),len(qa.PROOF_MAGIC)+104)
            payload=frame[len(qa.PROOF_MAGIC):]
            self.assertEqual(payload[:32],hashlib.sha256(qa.json_bytes(manifest)).digest())
            changed=dict(manifest);changed.pop("nativeWatchdogControl")
            with self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
                proof.pipe_frame(changed)
            for admission in qa.ADMISSION_CONTROLS:
                with self.subTest(admission=admission),self.assertRaisesRegex(ValueError,"OwnedLoopbackFixtureRequired"):
                    proof.pipe_frame(manifest,admission)
            request=qa.FIXTURE_MAGIC+payload[:32]+b"c"*32
            with socket.create_connection(("127.0.0.1",fixture.socks),timeout=2) as peer:
                peer.sendall(request)
                response=qa.LoopbackFixture.exact(peer,32)
            self.assertTrue(hmac.compare_digest(response,hmac.digest(payload[32:64],request,"sha256")))
            self.assertEqual((fixture.proofs,fixture.socks_connections,fixture.forwarded),(1,0,0))
        finally:
            fixture.close()


class ControlledCleanupTests(unittest.TestCase):
    def owners(self):
        process, job, receipt = Mock(), Mock(), Mock()
        process.poll.return_value=0
        process.stdin=None
        return process,job,receipt

    def test_pipe_and_handle_close_failures_cannot_skip_mapping_or_job_close(self):
        process,job,receipt=self.owners()
        process.stdout.close.side_effect=OSError("SyntheticFirstCleanupFailure")
        process.close_handles.side_effect=ValueError("SyntheticHandleFailure")
        receipt.close.side_effect=ValueError("SyntheticMappingFailure")
        with self.assertRaisesRegex(OSError,"SyntheticFirstCleanupFailure"):
            qa._cleanup_controlled_owner(process,job,receipt,None)
        process.stderr.close.assert_called_once()
        process.close_handles.assert_called_once()
        receipt.close.assert_called_once()
        job.close.assert_called_once()

    def test_primary_error_is_preserved_when_cleanup_also_fails(self):
        process,job,receipt=self.owners()
        receipt.close.side_effect=OSError("SyntheticMappingFailure")
        with self.assertRaisesRegex(ValueError,"OriginalFailure") as caught:
            try:
                raise ValueError("OriginalFailure")
            finally:
                qa._cleanup_controlled_owner(process,job,receipt,sys.exception())
        self.assertEqual(caught.exception.__notes__,["ControlledOwnerCleanupFailed:OSError"])
        job.close.assert_called_once()

    def test_unconfirmed_exit_still_closes_mapping_and_kill_on_close_job(self):
        process,job,receipt=self.owners()
        process.poll.return_value=None
        process.wait.side_effect=TimeoutError("SyntheticExitUnconfirmed")
        with self.assertRaisesRegex(TimeoutError,"SyntheticExitUnconfirmed"):
            qa._cleanup_controlled_owner(process,job,receipt,None)
        job.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        process.stdout.close.assert_not_called()
        process.stderr.close.assert_not_called()
        process.close_handles.assert_called_once()
        receipt.close.assert_called_once()
        job.close.assert_called_once()


class ControlledRetirementTests(unittest.TestCase):
    def setUp(self):
        self.process,self.job=Mock(),Mock()
        self.now=100.0
        self.sleeps=[]

    def process_wait(self, *, timeout):
        self.assertEqual(timeout,5)
        self.now+=4.99

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now=round(self.now+duration,9)

    def test_delayed_job_empty_uses_only_remaining_process_wait_budget(self):
        self.process.wait.side_effect=self.process_wait
        self.job.empty.side_effect=[False,False,True]
        with patch.object(qa.time,"monotonic",side_effect=lambda:self.now),patch.object(qa.time,"sleep",side_effect=self.sleep):
            qa._wait_for_controlled_retirement(self.process,self.job)
        self.assertEqual(self.job.empty.call_args_list,[unittest.mock.call(self.process)]*3)
        self.assertAlmostEqual(self.now,105)
        self.assertAlmostEqual(sum(self.sleeps),0.01)

    def test_permanently_nonempty_job_fails_within_same_five_second_budget(self):
        self.process.wait.side_effect=self.process_wait
        self.job.empty.return_value=False
        with patch.object(qa.time,"monotonic",side_effect=lambda:self.now),patch.object(qa.time,"sleep",side_effect=self.sleep):
            with self.assertRaisesRegex(ValueError,"OwnedJobExitUnconfirmed"):
                qa._wait_for_controlled_retirement(self.process,self.job)
        self.assertEqual(self.job.empty.call_count,3)
        self.assertAlmostEqual(self.now,105)
        self.assertAlmostEqual(sum(self.sleeps),0.01)


@unittest.skipUnless(os.name=="nt","Windows snapshot sharing and ACL boundary required")
class WindowsStateSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.storage=qa._WindowsStorage()
        self.root=Path(self.temporary.name)/"owned"
        self.storage.prepare(self.root)
        self.path=self.root/"state.json"
        self.old=dict(nonce="a"*64,sourceSha="b"*40,phase="starting",requestsStarted=False)
        self.new=dict(self.old,phase="requests",requestsStarted=True)
        self.write_private_json(self.path,self.old)

    def tearDown(self):
        self.storage.close()
        self.temporary.cleanup()

    def replacement(self):
        path=self.root/"replacement.json"
        self.write_private_json(path,self.new)
        return path

    def write_private_json(self,path,value):
        # Match the native publisher's explicit TokenUser owner/DACL even when
        # an elevated runner token would otherwise choose Administrators.
        with os.fdopen(self.storage.open(path,create=True),"wb") as stream:
            stream.write(json.dumps(value).encode("utf-8"))

    def replace_snapshot(self,replacement):
        # ReplaceFileW can replace an open snapshot with FILE_SHARE_DELETE;
        # MoveFileExW/os.replace rejects an open destination on Windows.
        c=self.storage.c
        replace=self.storage.kernel.ReplaceFileW
        replace.argtypes=[c.c_wchar_p,c.c_wchar_p,c.c_wchar_p,c.c_ulong,c.c_void_p,c.c_void_p]
        replace.restype=c.c_int
        self.assertTrue(replace(str(self.path),str(replacement),None,0,None,None),c.get_last_error())

    def test_atomic_replacement_completes_while_snapshot_read_handle_is_open(self):
        replacement=self.replacement()
        original_fdopen=qa.os.fdopen
        reads=[]
        case=self

        class ReplacingReader:
            def __init__(self,*args,**kwargs):
                self.stream=original_fdopen(*args,**kwargs)
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self,*args):
                return self.stream.__exit__(*args)
            def read(self,size):
                case.replace_snapshot(replacement)
                reads.append(size)
                return self.stream.read(size)

        with patch.object(qa.os,"fdopen",ReplacingReader):
            self.assertEqual(qa.read_controlled_state(self.path),self.old)
        self.assertEqual(reads,[4097])
        self.assertFalse(replacement.exists())
        self.assertEqual(qa.read_controlled_state(self.path),self.new)

    def test_replacement_before_validation_accepts_snapshot_but_not_a_ledger_handle(self):
        replacement=self.replacement()
        original_validate=qa._WindowsStorage.validate
        snapshots=[]
        case=self

        def replace_then_validate(storage,handle,directory=False,*,allow_unlinked=False):
            case.assertFalse(directory)
            case.assertTrue(allow_unlinked)
            case.replace_snapshot(replacement)
            with case.assertRaisesRegex(qa.BudgetError,"PrivateStorageRequired"):
                original_validate(storage,handle)
            snapshots.append(handle)
            return original_validate(storage,handle,directory,allow_unlinked=allow_unlinked)

        with patch.object(qa._WindowsStorage,"validate",replace_then_validate):
            self.assertEqual(qa.read_controlled_state(self.path),self.old)
        self.assertEqual(len(snapshots),1)
        self.assertEqual(qa.read_controlled_state(self.path),self.new)

    def test_state_bound_accepts_complete_limit_and_rejects_excess_before_json_decode(self):
        encoded=json.dumps(self.old).encode("utf-8")
        self.path.write_bytes(encoded+b" "*(4096-len(encoded)))
        self.assertEqual(qa.read_controlled_state(self.path),self.old)
        self.path.write_bytes(encoded+b" "*(4097-len(encoded)))
        with patch.object(qa.json,"loads",side_effect=AssertionError("oversized JSON decoded")),\
                self.assertRaisesRegex(ValueError,"ControlledStateTooLarge"):
            qa.read_controlled_state(self.path)

    def test_non_object_state_is_rejected_at_snapshot_boundary(self):
        for value in ([],None):
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"ControlledStateObjectRequired"):
                    qa.read_controlled_state(self.path)

    def test_hard_link_state_is_rejected_even_with_private_acl(self):
        alias=self.root/"state-alias.json"
        os.link(self.path,alias)
        with self.assertRaisesRegex(qa.BudgetError,"PrivateStorageRequired"):
            qa.read_controlled_state(self.path)

    def test_everyone_readable_state_is_rejected_without_changing_its_acl(self):
        command=subprocess.run(["icacls.exe",str(self.path),"/grant","*S-1-1-0:(R)"],
                               capture_output=True,timeout=10)
        self.assertEqual(command.returncode,0,command.stderr.decode(errors="replace"))
        before=self.path.read_bytes()
        with self.assertRaisesRegex(qa.BudgetError,"PrivateAclRequired"):
            qa.read_controlled_state(self.path)
        self.assertEqual(self.path.read_bytes(),before)
        with self.assertRaisesRegex(qa.BudgetError,"PrivateAclRequired"):
            qa.read_controlled_state(self.path)

    def test_reparse_state_is_rejected(self):
        link=self.root/"state-link.json"
        try:
            os.symlink(self.path,link)
        except OSError as error:
            if getattr(error,"winerror",None)==1314:
                self.skipTest("Windows token lacks symbolic-link privilege")
            raise
        with self.assertRaises(qa.BudgetError):
            qa.read_controlled_state(link)


@unittest.skipUnless(os.name=="nt","Windows atomic Job boundary required")
class WindowsProcessTests(unittest.TestCase):
    def run_real_child(self,body):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/"owned"
            storage=qa._WindowsStorage()
            try:
                storage.prepare(root)
                fixture=qa.LoopbackFixture(FIXTURES/"localhost-cert.pem",FIXTURES/"localhost-key.pem")
                try:
                    manifest=manifest_for(fixture)
                    proof=fixture.bind_session(manifest)
                    qa.write_json(root/"session.json",manifest)
                    initial=dict(manifest,phase="starting",requestsStarted=False)
                    with os.fdopen(storage.open(root/"state.json",create=True),"wb") as stream:
                        stream.write(json.dumps(initial).encode("utf-8"))
                    # Prove valid identity and ACL admission before an invalid
                    # identity can cause the same fixed supervision error.
                    self.assertEqual(qa.read_controlled_state(root/"state.json"),initial)
                    publisher="""import ctypes,json,os,sys
sys.path.insert(0,%r)
from PrivateSubscriptionBudget import _WindowsStorage
def publish_state(root,state):
    storage=_WindowsStorage()
    try:
        temporary=root/'child-state.tmp'
        with os.fdopen(storage.open(temporary,create=True),'wb') as stream:
            stream.write(json.dumps(state).encode('utf-8'))
        replace=storage.kernel.ReplaceFileW
        replace.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_void_p]
        replace.restype=ctypes.c_int
        if not replace(str(root/'state.json'),str(temporary),None,0,None,None):
            raise OSError('ControlledStatePublishFailed')
    finally:
        storage.close()
"""%str(TOOLS)
                    actual=qa._WindowsProcess
                    def launch(arguments,**keywords):
                        return actual([sys.executable,"-c",publisher+body,str(root)],**keywords)
                    with patch.object(qa,"_WindowsProcess",launch):
                        return qa.execute(Path(sys.executable),root,manifest,dict(os.environ),proof)
                finally:
                    fixture.close()
            finally:
                storage.close()

    def test_natural_exit_has_actual_process_and_job_proof(self):
        result=self.run_real_child("print('synthetic natural exit')")
        self.assertEqual(result["exitCode"],0)
        self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
        self.assertFalse(result["timedOut"])
        self.assertFalse(result["nativeWatchdog"]["triggered"])
        self.assertEqual(result["stopOrigin"],"natural-exit")

    def test_actual_bare_exit_124_is_rejected_without_native_record(self):
        with self.assertRaisesRegex(ValueError,"NativeWatchdogExitUnproven"):
            self.run_real_child("import sys;sys.exit(124)")

    def test_request_state_cannot_substitute_for_native_deadline_proof(self):
        body="""import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);state=json.loads((root/'session.json').read_text());state['phase']='requests'
publish_state(root,state);raise SystemExit(124)
"""
        with self.assertRaisesRegex(ValueError,"NativeWatchdogExitUnproven"):
            self.run_real_child(body)

    def test_state_identity_mismatch_retires_child_without_accepting_request_phase(self):
        for key,value in (("nonce","c"*64),("sourceSha","d"*40)):
            with self.subTest(key=key):
                body="""import json,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);state=json.loads((root/'session.json').read_text())
state.update(phase='requests',requestsStarted=True)
state[%r]=%r
publish_state(root,state);time.sleep(60)
"""%(key,value)
                result=self.run_real_child(body)
                self.assertEqual(result["error"],"ChildSupervisionFailed")
                self.assertFalse(result["requestPhaseObserved"])
                self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
                self.assertFalse(result["nativeWatchdog"]["triggered"])

    def test_stalled_request_is_killed_without_renewing_its_deadline(self):
        body="""import json,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);state=json.loads((root/'session.json').read_text());state['phase']='requests'
publish_state(root,state);time.sleep(60)
"""
        started=time.monotonic()
        result=self.run_real_child(body)
        self.assertTrue(result["timedOut"] and result["requestPhaseObserved"])
        self.assertTrue(result["processSignaled"] and result["ownedJobEmpty"])
        self.assertEqual(result["exitCode"],125)
        self.assertTrue(result["parentTimedOut"])
        self.assertFalse(result["nativeWatchdog"]["triggered"])
        self.assertEqual(result["stopOrigin"],"parent-watchdog")
        self.assertLess(time.monotonic()-started,12)


if __name__=="__main__":
    unittest.main()
