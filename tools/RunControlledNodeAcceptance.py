"""Private Windows QA sessions; each actual UI child owns one selected node.

Traffic accounting is intentionally outside this owner-authorized acceptance
scope. TLS, authentication, explicit routing, request/parent deadlines and actual
Job-empty exit evidence remain mandatory. No system proxy or TUN is enabled.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
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
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    with Path(path).open("xb") as output:
        output.write(data)


def protect_fixture(data):
    """Synthetic catalog only, using the unchanged NodeStore DPAPI entropy."""
    from ctypes import wintypes as w
    class Blob(ctypes.Structure):
        _fields_ = [("length", w.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    private = ctypes.create_string_buffer(data)
    entropy = ctypes.create_string_buffer(b"Swirl.NodeStore.v1")
    source = Blob(len(data), ctypes.cast(private, ctypes.POINTER(ctypes.c_ubyte)))
    context = Blob(len(b"Swirl.NodeStore.v1"), ctypes.cast(entropy, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), w.LPCWSTR, ctypes.POINTER(Blob),
                                      ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = w.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        if not crypt.CryptProtectData(ctypes.byref(source), "Swirl synthetic node", ctypes.byref(context), None, None, 1, ctypes.byref(output)):
            raise ValueError("SyntheticCatalogProtectionFailed")
        return ctypes.string_at(output.data, output.length)
    finally:
        ctypes.memset(private, 0, len(private))
        if output.data:
            ctypes.memset(output.data, 0, output.length)
            kernel.LocalFree(output.data)


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
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(certificate), str(key))
        self.http = self.listen(lambda peer: self.origin(peer, False))
        self.https = self.listen(lambda peer: self.origin(peer, True))
        self.socks = self.listen(self.relay)

    def own(self, peer):
        with self.lock:
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
        def accept():
            while not self.done.is_set():
                try:
                    peer, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                peer = self.own(peer)
                def work(peer=peer):
                    try:
                        handler(peer)
                    except (OSError, ValueError, ssl.SSLError):
                        pass
                    finally:
                        self.retire(peer)
                thread = threading.Thread(target=work, daemon=True)
                self.threads.append(thread)
                thread.start()
        thread = threading.Thread(target=accept, daemon=True)
        self.threads.append(thread)
        thread.start()
        return listener.getsockname()[1]

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
        if tls:
            wrapped = self.context.wrap_socket(peer, server_side=True)
            with self.lock:
                self.sockets.discard(peer)
                self.sockets.add(wrapped)
            peer = wrapped
        try:
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
        version, methods = self.exact(peer, 2)
        if version != 5 or 2 not in self.exact(peer, methods):
            peer.sendall(b"\x05\xff")
            return
        peer.sendall(b"\x05\x02")
        version, size = self.exact(peer, 2)
        user = self.exact(peer, size)
        password = self.exact(peer, self.exact(peer, 1)[0])
        if version != 1 or user != b"fixture" or password != b"fixture-secret":
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
        if version != 5 or command != 1 or reserved or host not in {"127.0.0.1", "localhost"} or port not in {self.http, self.https}:
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

    def catalog(self):
        node = dict(id="6ba7b810-9dad-11d1-80b4-00c04fd430c8", name="Synthetic controlled SOCKS5",
                    protocol="socks5", host="127.0.0.1", port=self.socks,
                    username="fixture", password="fixture-secret", options={})
        return b"SWIRLNODE1\n"+protect_fixture(json.dumps(dict(schema=1,catalogVersion=2,selected="",nodes=[node],subscriptions=[])).encode())

    def close(self):
        self.done.set()
        with self.lock:
            sockets = list(self.sockets)
        for peer in sockets:
            try:
                peer.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.retire(peer)
        deadline = time.monotonic()+3
        for thread in self.threads:
            thread.join(timeout=max(0,deadline-time.monotonic()))
        if any(thread.is_alive() for thread in self.threads):
            raise ValueError("FixtureTaskRetirementUnconfirmed")


def execute(executable, root, manifest, child_environment):
    """Independent watchdog terminates the whole atomically owned process set."""
    job = _WindowsJob()
    process = None
    done = threading.Event()
    guard = {"timedOut":False, "error":None, "requestPhaseObserved":False}
    started = time.monotonic()
    try:
        process = _WindowsProcess([str(executable), "--controlled-node-session="+str(root)], job=job, environment=child_environment)
        job.verify_member(process)
        job.resume(process)
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--exe-sha256",required=True)
    parser.add_argument("--core-sha256",required=True)
    parser.add_argument("--expected-source",required=True)
    parser.add_argument("--store",type=Path)
    parser.add_argument("--nodes",default="1")
    parser.add_argument("--output-directory",type=Path,required=True)
    parser.add_argument("--qt-root",type=Path)
    parser.add_argument("--fixture-directory",type=Path)
    parser.add_argument("--fixture-wrong-ca",action="store_true")
    parser.add_argument("--fixture-stall",action="store_true")
    args=parser.parse_args(argv)
    if os.name!="nt":
        raise ValueError("NativeWindowsAcceptanceRequired")
    nodes=ordinals(args.nodes)
    executable=local_file(args.exe)
    core=local_file(executable.parent/"swirl_api.dll")
    if (not re.fullmatch(r"[0-9a-f]{40}",args.expected_source)
        or not all(re.fullmatch(r"[0-9a-f]{64}",value) for value in [args.exe_sha256,args.core_sha256])
        or digest(executable)!=args.exe_sha256 or digest(core)!=args.core_sha256):
        raise ValueError("TrustedQaBinaryIdentityRequired")
    output=args.output_directory.absolute()
    if output.exists() or any(item.is_symlink() for item in output.parents):
        raise ValueError("NewPrivateOutputRequired")
    fixture=None
    if args.fixture_directory:
        if args.store or nodes!=[1]:
            raise ValueError("SingleSyntheticNodeRequired")
        certificate=local_file(args.fixture_directory/"localhost-cert.pem")
        key=local_file(args.fixture_directory/"localhost-key.pem")
        ca=local_file(args.fixture_directory/("xray-download-server-cert.pem" if args.fixture_wrong_ca else "localhost-cert.pem"))
        fixture=LoopbackFixture(certificate,key,stall=args.fixture_stall)
        catalog=fixture.catalog()
    else:
        if args.fixture_wrong_ca or args.fixture_stall or not args.store:
            raise ValueError("PersistedPrivateNodeStoreRequired")
        store=local_file(args.store)
        if store.stat().st_size>32*1024*1024:
            raise ValueError("NodeStoreSizeRejected")
        catalog=store.read_bytes()
    storage=_WindowsStorage()
    cases=[]
    try:
        storage.prepare(output)
        for ordinal in nodes:
            root=output/f"node-{ordinal}"
            child_storage=_WindowsStorage()
            try:
                child_storage.prepare(root)
                # Ciphertext is copied; original private files are never edited.
                with (root/"nodes.dpapi").open("xb") as destination:
                    destination.write(catalog)
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1",0))
                    port=reservation.getsockname()[1]
                manifest=dict(schema=1,sourceSha=args.expected_source,nonce=secrets.token_hex(32),
                              nodeOrdinal=ordinal,proxyPort=port)
                if fixture:
                    (root/"fixture-ca.pem").write_bytes(ca.read_bytes())
                    manifest["fixture"]=dict(httpPort=fixture.http,httpsPort=fixture.https,caSha256=digest(ca))
                write_json(root/"session.json",manifest)
                retirement=execute(executable,root,manifest,environment(root,args.qt_root))
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
        if fixture:
            fixture.close()
        summary=dict(schema=1,sourceSha=args.expected_source,exeSha256=args.exe_sha256,coreSha256=args.core_sha256,
                     fixtureOnly=bool(fixture),trafficAccountingRequired=False,maxConcurrent=1,
                     cases=cases,passed=bool(cases) and all(case["result"].get("passed") and case["retirement"]["exitCode"]==0
                         and not case["retirement"]["timedOut"] and not case["retirement"]["error"] for case in cases))
        if fixture:
            summary["fixture"]=dict(forwarded=fixture.forwarded,rejected=fixture.rejected,tasksReleased=True)
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
    except (ValueError,BudgetError,OSError):
        print('{"error":"ControlledAcceptanceFailed","networkSettingsChanged":false}')
        raise SystemExit(2)
