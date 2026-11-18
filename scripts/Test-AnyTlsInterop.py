#!/usr/bin/env python3
"""Strict, loopback-only interoperability gate against pinned upstream AnyTLS.

Go is a test peer only. No peer executable or upstream source is installed in
the product. The upstream protocol implementation is left untouched; fixture
patches select a test certificate and expose counters on a loopback listener.
"""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import threading
import time

UPSTREAM = "https://github.com/anytls/anytls-go.git"
REVISION = "fd6167acd6d73b9fa3e607659951847fbc9e6c50"
TEST = "anytls::tests::official_peer_reuse_padding_tcp_udp_and_owner_retirement"


def run(command, cwd, env=None, timeout=180):
    result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command[0]}\n{result.stdout[-12000:]}")
    return result.stdout


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("pinned fixture source shape changed")
    return text.replace(old, new)


def prepare(source):
    if not source.exists():
        source.mkdir(parents=True)
        run(["git", "init", "--quiet"], source)
        run(["git", "remote", "add", "origin", UPSTREAM], source)
        run(["git", "fetch", "--quiet", "--depth=1", "origin", REVISION], source)
        run(["git", "checkout", "--quiet", "--detach", REVISION], source)
    if run(["git", "rev-parse", "HEAD"], source).strip() != REVISION:
        raise RuntimeError("fixture checkout has an unexpected revision")
    changed = set(run(["git", "diff", "--name-only", "HEAD"], source).splitlines())
    untracked = set(run(["git", "ls-files", "--others", "--exclude-standard"], source).splitlines())
    if changed - {"cmd/server/main.go", "cmd/server/inbound_tcp.go"} or untracked - {"cmd/server/fixture_stats.go"}:
        raise RuntimeError("fixture source contains changes outside the instrumentation boundary")
    def original(path):
        return run(["git", "show", f"{REVISION}:{path}"], source)
    main = replace_once(original("cmd/server/main.go"), '\n\t"time"', '')
    main = replace_once(main, 'tlsCert, _ := util.GenerateKeyPair(time.Now, "")',
                        'tlsCert, err := tls.LoadX509KeyPair(os.Getenv("SWIRL_FIXTURE_CERT"), os.Getenv("SWIRL_FIXTURE_KEY"))\n\tif err != nil { panic(err) }')
    main = replace_once(main, 'return tlsCert, nil', 'return &tlsCert, nil')
    main = replace_once(main, 'server := NewMyServer(tlsConfig)', 'server := NewMyServer(tlsConfig)\n fixtureReady.Store(true)')
    (source / "cmd/server/main.go").write_text(main, encoding="utf-8")
    inbound = replace_once(original("cmd/server/inbound_tcp.go"),
                           'func handleTcpConnection(ctx context.Context, c net.Conn, s *myServer) {',
                           'func handleTcpConnection(ctx context.Context, c net.Conn, s *myServer) {\n fixtureActive.Add(1);fixtureAccepted.Add(1);defer fixtureActive.Add(-1)')
    inbound = replace_once(inbound, 'paddingLen := binary.BigEndian.Uint16(by)',
                           'paddingLen := binary.BigEndian.Uint16(by)\n fixturePaddingLock.Lock();fixturePadding=append(fixturePadding,int(paddingLen));fixturePaddingLock.Unlock()')
    inbound = replace_once(inbound, 'defer stream.Close()', 'defer stream.Close()\n fixtureStreams.Add(1)')
    (source / "cmd/server/inbound_tcp.go").write_text(inbound, encoding="utf-8")
    (source / "cmd/server/fixture_stats.go").write_text('''package main
import ("sync/atomic";"sync";"encoding/json";"net/http";"os")
var fixtureActive atomic.Int64
var fixtureAccepted atomic.Int64
var fixtureStreams atomic.Int64
var fixtureReady atomic.Bool
var fixturePaddingLock sync.Mutex
var fixturePadding []int
func init(){ go func(){
 http.HandleFunc("/stats",func(w http.ResponseWriter,r *http.Request){
  fixturePaddingLock.Lock();defer fixturePaddingLock.Unlock()
  json.NewEncoder(w).Encode(map[string]any{"active":fixtureActive.Load(),"accepted":fixtureAccepted.Load(),"streams":fixtureStreams.Load(),"padding":fixturePadding,"ready":fixtureReady.Load()})
 })
 if err:=http.ListenAndServe(os.Getenv("SWIRL_FIXTURE_STATS"),nil);err!=nil{panic(err)}
}() }
''', encoding="utf-8")


class TcpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        try:
            while data := self.request.recv(65536):
                self.request.sendall(data)
        except (TimeoutError, ConnectionError):
            pass


class UdpEcho(socketserver.BaseRequestHandler):
    def handle(self):
        data, channel = self.request
        channel.sendto(data, self.client_address)


class TcpServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--go", default="go")
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--test-binary", type=Path, help="run an already built swirl-protocol unit test executable")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    receipt = {"result": "failed", "upstream": UPSTREAM, "revision": REVISION,
               "test": TEST, "peer_retired": False}
    receipt_path = work / "anytls-interop.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    source = work / "anytls-upstream"
    prepare(source)
    peer = work / ("anytls-fixture.exe" if os.name == "nt" else "anytls-fixture")
    build_env = dict(os.environ, GOTOOLCHAIN="local", GOWORK="off", GOFLAGS="-mod=readonly")
    go_version = run([args.go, "version"], source, build_env).strip()
    receipt["go"] = go_version
    build_log = run([args.go, "mod", "verify"], source, build_env)
    build_log += run([args.go, "build", "-o", str(peer), "./cmd/server"], source, build_env)
    (work / "anytls-peer-build.log").write_text(build_log, encoding="utf-8")
    padding = work / "padding.txt"
    padding.write_bytes(b"stop=3\n0=50-50\n1=250-250\n2=400-400")
    port, stats_port = free_port(), free_port()
    certificate = json.loads((repository / "core/crates/swirl-transport/tests/fixtures/reality_auth.json").read_text(encoding="utf-8"))["certificate"]
    for filename, kind, field in [("peer-cert.pem", "CERTIFICATE", "ordinary_self_signed_der_hex"),
                                   ("peer-key.pem", "PRIVATE KEY", "ed25519_pkcs8_der_hex")]:
        encoded = base64.b64encode(bytes.fromhex(certificate[field])).decode("ascii")
        lines = [encoded[index:index+64] for index in range(0, len(encoded), 64)]
        (work / filename).write_bytes((f"-----BEGIN {kind}-----\n" + "\n".join(lines) + f"\n-----END {kind}-----\n").encode("ascii"))
    receipt["peer_sha256"] = hashlib.sha256(peer.read_bytes()).hexdigest()
    receipt["module_sum_sha256"] = hashlib.sha256((source / "go.sum").read_bytes()).hexdigest()
    with TcpServer(("127.0.0.1", 0), TcpEcho) as tcp, socketserver.ThreadingUDPServer(("127.0.0.1", 0), UdpEcho) as udp:
        for server in (tcp, udp):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        environment = dict(os.environ, SWIRL_FIXTURE_CERT=str(work / "peer-cert.pem"),
                           SWIRL_FIXTURE_KEY=str(work / "peer-key.pem"),
                           SWIRL_FIXTURE_STATS=f"127.0.0.1:{stats_port}",
                           SWIRL_ANYTLS_PORT=str(port), SWIRL_ANYTLS_STATS_PORT=str(stats_port),
                           SWIRL_ECHO_TCP_PORT=str(tcp.server_address[1]), SWIRL_ECHO_UDP_PORT=str(udp.server_address[1]))
        with (work / "anytls-peer.log").open("w", encoding="utf-8") as log:
            peer_process = subprocess.Popen([str(peer), "-l", f"127.0.0.1:{port}", "-p", "swirl-fixture-password", "-padding-scheme", str(padding)], env=environment, stdout=log, stderr=log)
            try:
                ready = False
                for _ in range(100):
                    if peer_process.poll() is not None:
                        raise RuntimeError("official peer exited before readiness")
                    connection = http.client.HTTPConnection("127.0.0.1", stats_port, timeout=0.2)
                    try:
                        connection.request("GET", "/stats")
                        response = connection.getresponse()
                        current = json.loads(response.read())
                        ready = response.status == 200 and current["ready"] and current["accepted"] == 0
                    except (OSError, http.client.HTTPException):
                        pass
                    finally:
                        connection.close()
                    if ready:
                        break
                    time.sleep(0.05)
                if not ready:
                    raise RuntimeError("official peer did not become ready")
                if args.test_binary:
                    command = [str(args.test_binary.resolve()), TEST, "--ignored", "--exact", "--nocapture"]
                else:
                    command = [args.cargo, "test", "--locked", "-p", "swirl-protocol", "--lib", TEST, "--", "--ignored", "--exact", "--nocapture"]
                output = run(command, repository / "core", environment, timeout=240)
                (work / "anytls-interop.log").write_text(output, encoding="utf-8")
                if not re.search(r"test result: ok\. 1 passed; 0 failed; 0 ignored", output):
                    raise RuntimeError("required independent-peer test did not execute")
                if peer_process.poll() is not None:
                    raise RuntimeError("official peer exited during the test")
                receipt["result"] = "passed"
                receipt["scope"] = "loopback native Rust TCP/UDP, padding update, session reuse, owner retirement; no provider network"
                print(output)
            finally:
                peer_process.terminate()
                try:
                    peer_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    peer_process.kill()
                    peer_process.wait(timeout=5)
                receipt["peer_retired"] = peer_process.poll() is not None
                if not receipt["peer_retired"]:
                    receipt["result"] = "failed"
                receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                tcp.shutdown()
                udp.shutdown()


if __name__ == "__main__":
    main()
