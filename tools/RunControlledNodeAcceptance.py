"""Synthetic-only Windows UI/Core sessions against a parent-owned fixture.

There is no private-node-store or live mode. Real-provider acceptance still needs
the persistent billing ledger and pre-TLS Rust quota worker. This fixture proves
only bounded local UI/Core requests, TLS/authentication and native retirement;
its ownership proof is not budget authorization or production admission.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import ssl
import sys
import threading
import time

from PrivateSubscriptionBudget import BudgetError, _WindowsStorage
from PrivateSubscriptionProcess import _WindowsJob, _WindowsProcess


LIVE_REFUSAL = "LiveAcceptanceRequiresPersistentBudgetAndRustWorker"
PROOF_MAGIC = b"SWIRL-FIXTURE-PROOF-1\n"
FIXTURE_MAGIC = b"SWIRL-OWNED-FIXTURE-1\n"
FIXTURE_CERT_SHA256 = "a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311"
FIXTURE_KEY_SHA256 = "13eb4aa0855cc8e8280b879a0e3b125e8350bd27da76c60371a2755a8ac57d2f"
WRONG_CA_SHA256 = "e1075d330aab28049a89ba8e64f5f93f8ddbe2573c022c28508bb2ac2df26f1b"
ADMISSION_CONTROLS = ("missing-proof", "missing-fixture", "preexisting-store", "wrong-proof")
_PROOF_ISSUER = object()


def refuse_private_inputs(argv):
    # Refuse before argparse, file identities, output directories or sockets.
    if any(value == flag or value.startswith(flag + "=")
           for value in argv for flag in ("--live", "--store")):
        raise ValueError(LIVE_REFUSAL)


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class _FixtureProof:
    """Private capability for one actually listening LoopbackFixture instance."""
    __slots__ = ("_fixture", "_manifest_digest", "_issuer")

    def __init__(self, issuer, fixture, manifest_digest):
        if issuer is not _PROOF_ISSUER:
            raise ValueError("OwnedLoopbackFixtureRequired")
        self._fixture, self._manifest_digest, self._issuer = fixture, manifest_digest, issuer

    def pipe_frame(self, manifest, control=None):
        fixture = self._fixture
        if (self._issuer is not _PROOF_ISSUER or fixture._admission is not self
                or fixture.done.is_set() or not fixture._listeners_alive()
                or not hmac.compare_digest(self._manifest_digest, hashlib.sha256(json_bytes(manifest)).digest())
                or control not in (None, *ADMISSION_CONTROLS)):
            raise ValueError("OwnedLoopbackFixtureRequired")
        if control == "missing-proof":
            return b""
        key = fixture._proof_key
        if control == "wrong-proof":
            key = bytes([key[0] ^ 1]) + key[1:]
        return PROOF_MAGIC + self._manifest_digest + key + fixture._password


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordinals(value):
    if not re.fullmatch(r"[1-9][0-9]*(?:,[1-9][0-9]*){0,11}", value):
        raise ValueError("AtMostTwelveExplicitNodeOrdinalsRequired")
    result = [int(item) for item in value.split(",")]
    if len(set(result)) != len(result) or any(item > 10000 for item in result):
        raise ValueError("DistinctNodeOrdinalsRequired")
    return result


def local_file(value):
    path = Path(value).absolute()
    if not path.is_file() or any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError("PlainLocalFileRequired")
    return path


def environment(root, qt_root=None):
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "OS", "PATH", "SYSTEMDRIVE", "LANG", "LC_ALL"}
    result = {key: value for key, value in os.environ.items() if key.upper() in keep}
    for name in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        directory = root / name
        directory.mkdir()
        result[name] = str(directory)
    result.update(SWIRL_TEST_ROOT=str(root), QT_FORCE_STDERR_LOGGING="1", QT_QPA_PLATFORM="offscreen",
                  QT_QUICK_BACKEND="software", QT_QPA_FONTDIR=r"C:\Windows\Fonts")
    if qt_root:
        qt_root = Path(qt_root).resolve(strict=True)
        result.update(QT_PLUGIN_PATH=str(qt_root / "plugins"), QML_IMPORT_PATH=str(qt_root / "qml"))
        result["PATH"] = str(qt_root / "bin") + os.pathsep + result.get("PATH", "")
    return result


def write_json(path, value):
    data = json_bytes(value)
    with Path(path).open("xb") as output:
        output.write(data)


class LoopbackFixture:
    """Authenticated SOCKS5 permits only this fixture's two owned origins."""
    def __init__(self, certificate, key, *, stall=False):
        self.sockets = set()
        self.threads = []
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.stall = stall
        self.forwarded = 0
        self.rejected = 0
        self.proofs = 0
        self.socks_connections = 0
        self._proof_key = secrets.token_bytes(32)
        self._password = secrets.token_bytes(32)
        self._admission = None
        self._listeners = []
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(certificate), str(key))
        try:
            self.http = self.listen(lambda peer: self.origin(peer, False))
            self.https = self.listen(lambda peer: self.origin(peer, True))
            self.socks = self.listen(self.relay)
        except BaseException:
            self.close()
            raise

    def own(self, peer):
        with self.lock:
            if self.done.is_set():
                peer.close()
                raise ValueError("FixtureAlreadyClosing")
            self.sockets.add(peer)
        peer.settimeout(8)
        return peer

    def retire(self, peer):
        with self.lock:
            self.sockets.discard(peer)
        try:
            peer.close()
        except OSError:
            pass

    def listen(self, handler):
        listener = self.own(socket.socket())
        listener.bind(("127.0.0.1", 0))
        listener.listen(12)
        listener.settimeout(0.1)
        self._listeners.append(listener)
        def accept():
            while not self.done.is_set():
                try:
                    peer, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                try:
                    peer = self.own(peer)
                except ValueError:
                    return
                def work(peer=peer):
                    try:
                        handler(peer)
                    except (OSError, ValueError, ssl.SSLError):
                        pass
                    finally:
                        self.retire(peer)
                thread = threading.Thread(target=work, daemon=True)
                with self.lock:
                    if self.done.is_set():
                        peer.close()
                        self.sockets.discard(peer)
                        return
                    self.threads.append(thread)
                    thread.start()
        thread = threading.Thread(target=accept, daemon=True)
        with self.lock:
            self.threads.append(thread)
            thread.start()
        return listener.getsockname()[1]

    def _listeners_alive(self):
        return (len(self._listeners) == 3 and all(peer.fileno() >= 0 for peer in self._listeners)
                and {peer.getsockname() for peer in self._listeners}
                == {("127.0.0.1", self.http), ("127.0.0.1", self.https), ("127.0.0.1", self.socks)})

    def bind_session(self, manifest):
        """Bind only this fixed schema and our currently owned listening sockets."""
        if type(manifest) is not dict:
            raise ValueError("OwnedLoopbackFixtureRequired")
        fixture = manifest.get("fixture")
        if (self._admission is not None or self.done.is_set() or not self._listeners_alive()
                or set(manifest) != {"schema", "sourceSha", "nonce", "nodeOrdinal", "proxyPort", "fixture"}
                or type(manifest["schema"]) is not int or manifest["schema"] != 2
                or type(manifest["nodeOrdinal"]) is not int or manifest["nodeOrdinal"] != 1
                or not isinstance(manifest["sourceSha"], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["sourceSha"])
                or not isinstance(manifest["nonce"], str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["nonce"])
                or type(manifest["proxyPort"]) is not int or not 1 <= manifest["proxyPort"] <= 65535
                or type(fixture) is not dict or set(fixture) != {"httpPort", "httpsPort", "socksPort", "caSha256"}
                or any(type(fixture[key]) is not int for key in ("httpPort", "httpsPort", "socksPort"))
                or (fixture["httpPort"], fixture["httpsPort"], fixture["socksPort"]) != (self.http, self.https, self.socks)
                or fixture["caSha256"] not in (FIXTURE_CERT_SHA256, WRONG_CA_SHA256)
                or len({manifest["proxyPort"], self.http, self.https, self.socks}) != 4):
            raise ValueError("OwnedLoopbackFixtureRequired")
        proof = _FixtureProof(_PROOF_ISSUER, self, hashlib.sha256(json_bytes(manifest)).digest())
        self._admission = proof
        return proof

    @staticmethod
    def exact(peer, count):
        data = bytearray()
        while len(data) < count:
            chunk = peer.recv(count-len(data))
            if not chunk:
                raise ValueError("FixturePeerClosed")
            data.extend(chunk)
        return bytes(data)

    def origin(self, peer, tls):
        try:
            if tls:
                # Transfer descriptor ownership while close() is excluded, and
                # publish the SSLSocket before any handshake can block.
                with self.lock:
                    if self.done.is_set():
                        return
                    wrapped = self.context.wrap_socket(peer, server_side=True,
                                                       do_handshake_on_connect=False)
                    self.sockets.discard(peer)
                    self.sockets.add(wrapped)
                    peer = wrapped
                peer.do_handshake()
            headers = bytearray()
            while b"\r\n\r\n" not in headers and len(headers) <= 16384:
                chunk = peer.recv(1024)
                if not chunk:
                    return
                headers.extend(chunk)
            if len(headers) > 16384:
                return
            if self.stall:
                self.done.wait(10)
                return
            head = headers.startswith(b"HEAD /generate_204 ")
            body = b"" if head else b"ip=127.0.0.1\nfixture=owned-loopback\n"
            peer.sendall((b"HTTP/1.1 204 No Content\r\n" if head else b"HTTP/1.1 200 OK\r\n")
                         + b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        finally:
            self.retire(peer)

    def relay(self, peer):
        first = self.exact(peer, 1)
        if first == FIXTURE_MAGIC[:1]:
            if first + self.exact(peer, len(FIXTURE_MAGIC)-1) != FIXTURE_MAGIC:
                self.rejected += 1
                return
            proof = self.exact(peer, 64)
            with self.lock:
                if (self._admission is None or self.proofs != 0
                        or not hmac.compare_digest(proof[:32], self._admission._manifest_digest)):
                    self.rejected += 1
                    return
                self.proofs += 1
            peer.sendall(hmac.digest(self._proof_key, FIXTURE_MAGIC + proof, "sha256"))
            return
        if first != b"\x05" or self.proofs != 1:
            self.rejected += 1
            return
        self.socks_connections += 1
        version, methods = first[0], self.exact(peer, 1)[0]
        if version != 5 or 2 not in self.exact(peer, methods):
            peer.sendall(b"\x05\xff")
            return
        peer.sendall(b"\x05\x02")
        version, size = self.exact(peer, 2)
        user = self.exact(peer, size)
        password = self.exact(peer, self.exact(peer, 1)[0])
        if version != 1 or user != b"fixture" or not hmac.compare_digest(password, self._password.hex().encode()):
            peer.sendall(b"\x01\x01")
            return
        peer.sendall(b"\x01\x00")
        version, command, reserved, kind = self.exact(peer, 4)
        if kind == 1:
            host = socket.inet_ntoa(self.exact(peer, 4))
        elif kind == 3:
            host = self.exact(peer, self.exact(peer, 1)[0]).decode("ascii")
        else:
            host = "rejected"
        port = int.from_bytes(self.exact(peer, 2), "big")
        if version != 5 or command != 1 or reserved or host != "127.0.0.1" or port not in {self.http, self.https}:
            self.rejected += 1
            peer.sendall(b"\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        upstream = self.own(socket.create_connection(("127.0.0.1", port), timeout=3))
        self.forwarded += 1
        try:
            peer.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            while not self.done.is_set():
                ready, _, _ = select.select([peer, upstream], [], [], 0.1)
                for source in ready:
                    data = source.recv(16384)
                    if not data:
                        return
                    (upstream if source is peer else peer).sendall(data)
        finally:
            self.retire(upstream)

    def close(self):
        with self.lock:
            self.done.set()
            sockets = list(self.sockets)
            threads = list(self.threads)
        for peer in sockets:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.retire(peer)
        deadline = time.monotonic()+3
        for thread in threads:
            thread.join(timeout=max(0,deadline-time.monotonic()))
        if any(thread.is_alive() for thread in threads):
            raise ValueError("FixtureTaskRetirementUnconfirmed")


def execute(executable, root, manifest, child_environment, proof, *, admission_control=None):
    """Independent watchdog terminates the whole atomically owned process set."""
    if type(proof) is not _FixtureProof:
        raise ValueError("OwnedLoopbackFixtureRequired")
    pipe_frame = proof.pipe_frame(manifest, admission_control)
    job = _WindowsJob()
    process = None
    done = threading.Event()
    guard = {"timedOut":False, "error":None, "requestPhaseObserved":False}
    started = time.monotonic()
    try:
        process = _WindowsProcess([str(executable), "--controlled-node-session="+str(root)], job=job, environment=child_environment)
        job.verify_member(process)
        def watch():
            deadline = started+20
            while not done.wait(0.02):
                try:
                    if process.poll() is not None:
                        return
                    state_path=root/"state.json"
                    if state_path.exists():
                        state=json.loads(state_path.read_text("utf-8"))
                        if state.get("nonce")!=manifest["nonce"] or state.get("sourceSha")!=manifest["sourceSha"]:
                            raise ValueError("ChildStateIdentityMismatch")
                        if (state.get("phase")=="requests" or state.get("requestsStarted") is True) and not guard["requestPhaseObserved"]:
                            guard["requestPhaseObserved"]=True
                            deadline=min(started+28,time.monotonic()+8)
                    if time.monotonic()>=deadline:
                        guard["timedOut"]=True
                        job.terminate()
                        return
                except (OSError, ValueError, BudgetError):
                    guard["error"]="ChildSupervisionFailed"
                    job.terminate()
                    return
        watchdog=threading.Thread(target=watch,daemon=True)
        captures=[]
        def drain(stream, name):
            with (root/name).open("xb") as target:
                while True:
                    data=stream.read(4096)
                    if not data:
                        return
                    if target.tell()+len(data)>262144:
                        guard["error"]="ChildOutputLimitExceeded"
                        job.terminate()
                        return
                    target.write(data)
        for stream,name in ((process.stdout,"stdout.log"),(process.stderr,"stderr.log")):
            thread=threading.Thread(target=drain,args=(stream,name),daemon=True)
            captures.append(thread)
            thread.start()
        watchdog.start()
        # The watchdog is already live even if a synchronous pipe operation
        # stalls. Write the fixed frame before resuming this verified member.
        # The key is never placed in argv, environment or a file.
        if process.stdin.write(pipe_frame) != len(pipe_frame):
            raise ValueError("PrivateFixtureProofWriteFailed")
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None
        job.resume(process)
        while process.poll() is None and time.monotonic()<started+33:
            time.sleep(0.02)
        if process.poll() is None:
            guard["timedOut"]=True
            job.terminate()
        process.wait(timeout=5)
        if not job.empty(process):
            raise ValueError("OwnedJobExitUnconfirmed")
        done.set()
        watchdog.join(timeout=1)
        for thread in captures:
            thread.join(timeout=1)
        if any(thread.is_alive() for thread in captures) or watchdog.is_alive():
            raise ValueError("ChildReaderRetirementUnconfirmed")
        # The child's native watchdog can fire before the parent terminates its Job.
        guard["timedOut"] = guard["timedOut"] or process.returncode == 124
        return dict(exitCode=process.returncode,processSignaled=True,ownedJobEmpty=True,
                    elapsedMs=round((time.monotonic()-started)*1000),**guard)
    finally:
        done.set()
        if process:
            if process.poll() is None:
                job.terminate()
                process.wait(timeout=5)
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream:
                    stream.close()
            process.close_handles()
        job.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    refuse_private_inputs(argv)
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--exe-sha256",required=True)
    parser.add_argument("--core-sha256",required=True)
    parser.add_argument("--expected-source",required=True)
    parser.add_argument("--nodes",default="1")
    parser.add_argument("--output-directory",type=Path,required=True)
    parser.add_argument("--qt-root",type=Path)
    parser.add_argument("--fixture-directory",type=Path,required=True)
    parser.add_argument("--fixture-wrong-ca",action="store_true")
    parser.add_argument("--fixture-stall",action="store_true")
    parser.add_argument("--fixture-admission-control",choices=ADMISSION_CONTROLS)
    args=parser.parse_args(argv)
    nodes=ordinals(args.nodes)
    if nodes != [1] or (args.fixture_admission_control and (args.fixture_wrong_ca or args.fixture_stall)):
        raise ValueError("SingleSyntheticNodeRequired")
    if os.name!="nt":
        raise ValueError("NativeWindowsAcceptanceRequired")
    executable=local_file(args.exe)
    core=local_file(executable.parent/"swirl_api.dll")
    if (not re.fullmatch(r"[0-9a-f]{40}",args.expected_source)
        or not all(re.fullmatch(r"[0-9a-f]{64}",value) for value in [args.exe_sha256,args.core_sha256])
        or digest(executable)!=args.exe_sha256 or digest(core)!=args.core_sha256):
        raise ValueError("TrustedQaBinaryIdentityRequired")
    output=args.output_directory.absolute()
    if output.exists() or any(item.is_symlink() for item in output.parents):
        raise ValueError("NewPrivateOutputRequired")
    certificate=local_file(args.fixture_directory/"localhost-cert.pem")
    key=local_file(args.fixture_directory/"localhost-key.pem")
    ca=local_file(args.fixture_directory/("xray-download-server-cert.pem" if args.fixture_wrong_ca else "localhost-cert.pem"))
    if (digest(certificate) != FIXTURE_CERT_SHA256 or digest(key) != FIXTURE_KEY_SHA256
            or digest(ca) != (WRONG_CA_SHA256 if args.fixture_wrong_ca else FIXTURE_CERT_SHA256)):
        raise ValueError("CommittedSyntheticTlsFixtureRequired")
    fixture=None
    storage=_WindowsStorage()
    cases=[]
    try:
        storage.prepare(output)
        fixture=LoopbackFixture(certificate,key,stall=args.fixture_stall)
        for ordinal in nodes:
            root=output/f"node-{ordinal}"
            child_storage=_WindowsStorage()
            try:
                child_storage.prepare(root)
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1",0))
                    port=reservation.getsockname()[1]
                manifest=dict(schema=2,sourceSha=args.expected_source,nonce=secrets.token_hex(32),
                              nodeOrdinal=1,proxyPort=port,
                              fixture=dict(httpPort=fixture.http,httpsPort=fixture.https,
                                           socksPort=fixture.socks,caSha256=digest(ca)))
                proof=fixture.bind_session(manifest)
                (root/"fixture-ca.pem").write_bytes(ca.read_bytes())
                submitted=dict(manifest)
                if args.fixture_admission_control == "missing-fixture":
                    submitted.pop("fixture")
                if args.fixture_admission_control == "preexisting-store":
                    # Fixed non-secret marker. No arbitrary file can be supplied.
                    (root/"nodes.dpapi").write_bytes(b"Synthetic preexisting-store refusal control\n")
                write_json(root/"session.json",submitted)
                retirement=execute(executable,root,manifest,environment(root,args.qt_root),proof,
                                   admission_control=args.fixture_admission_control)
                result={}
                if (root/"result.json").exists():
                    result=json.loads((root/"result.json").read_text("utf-8"))
                    if result.get("nonce")!=manifest["nonce"] or result.get("sourceSha")!=args.expected_source:
                        raise ValueError("ChildReceiptIdentityMismatch")
                # Nonce is an IPC correlation value, not public acceptance data.
                result.pop("nonce",None)
                cases.append(dict(nodeOrdinal=ordinal,retirement=retirement,result=result))
                write_json(root/"parent-exit.json",retirement)
            finally:
                child_storage.close()
        fixture.close()
        summary=dict(schema=1,sourceSha=args.expected_source,exeSha256=args.exe_sha256,coreSha256=args.core_sha256,
                     fixtureOnly=True,liveReady=False,trafficAccountingRequiredForLive=True,
                     persistentBudgetGuardExercised=False,uiSubscriptionImportExercised=False,
                     uiPolicySelectionExercised=False,maxConcurrent=1,
                     cases=cases,passed=bool(cases) and all(case["result"].get("passed") and case["retirement"]["exitCode"]==0
                         and not case["retirement"]["timedOut"] and not case["retirement"]["error"] for case in cases))
        summary["fixture"]=dict(forwarded=fixture.forwarded,rejected=fixture.rejected,
                                ownershipProofs=fixture.proofs,socksConnections=fixture.socks_connections,
                                tasksReleased=True)
        if args.fixture_admission_control:
            summary["admissionControl"]=args.fixture_admission_control
            summary["admissionRefused"]=(len(cases)==1 and not cases[0]["result"]
                and cases[0]["retirement"]["exitCode"]==64 and not cases[0]["retirement"]["timedOut"]
                and not cases[0]["retirement"]["error"] and fixture.socks_connections==0 and fixture.forwarded==0)
        write_json(output/"summary.json",summary)
        print(json.dumps(summary,separators=(",",":")))
        return 0 if summary["passed"] else 2
    finally:
        if fixture:
            fixture.close()
        storage.close()


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        if str(error)==LIVE_REFUSAL:
            print('{"errorCode":"LiveAcceptanceRequiresPersistentBudgetAndRustWorker","networkStarted":false}',file=sys.stderr)
            raise SystemExit(64)
        print('{"error":"ControlledAcceptanceFailed","networkSettingsChanged":false}')
        raise SystemExit(2)
    except (BudgetError,OSError):
        print('{"error":"ControlledAcceptanceFailed","networkSettingsChanged":false}')
        raise SystemExit(2)
