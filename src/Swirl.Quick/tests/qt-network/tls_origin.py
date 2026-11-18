"""Independent loopback TLS peer for the real Qt downloader tests.

The Qt client retains its platform TLS backend. Python's SSL server supplies
server-side ALPN even where Qt Secure Transport only supports client-side ALPN.
This fixture never sends HTTP/2 frames; an h2 connection is recorded and closed.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import queue
import select
import socket
import ssl
import sys
import threading


def prepare(directory):
    import cryptography
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Swirl Temporary Network Test CA")])
    ca = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Swirl Loopback TLS Fixture")]))
        .issuer_name(ca_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1")),
        ]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM)
    (directory / "ca.pem").write_bytes(ca_pem)
    (directory / "leaf.pem").write_bytes(leaf_pem)
    (directory / "leaf-chain.pem").write_bytes(leaf_pem + ca_pem)
    key_path = directory / "leaf-key.pem"
    key_path.write_bytes(leaf_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    if os.name != "nt":
        key_path.chmod(0o600)
    print(json.dumps({"event": "prepared", "tls": ssl.OPENSSL_VERSION, "leaf_days": 2,
                      "ca_sha256": ca.fingerprint(hashes.SHA256()).hex(),
                      "leaf_sha256": leaf.fingerprint(hashes.SHA256()).hex(),
                      "prepared_utc": now.isoformat(), "python": sys.version.split()[0],
                      "cryptography": cryptography.__version__,
                      "ca_not_before_utc": ca.not_valid_before_utc.isoformat(),
                      "ca_not_after_utc": ca.not_valid_after_utc.isoformat(),
                      "leaf_not_before_utc": leaf.not_valid_before_utc.isoformat(),
                      "leaf_not_after_utc": leaf.not_valid_after_utc.isoformat(),
                      "chain_certificates": 2}), flush=True)


def serve(directory):
    if not ssl.HAS_ALPN:
        raise RuntimeError("The independent TLS fixture requires ALPN support")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(directory / "leaf-chain.pem", directory / "leaf-key.pem")
    context.set_alpn_protocols(["h2", "http/1.1"])
    # The advertised TLS hostname is localhost, whose native resolution may
    # prefer either loopback family. Serve both on the same port without ever
    # listening on a wildcard address or depending on client fallback behavior.
    listeners = []
    port = 0
    try:
        for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            listener = socket.socket(family, socket.SOCK_STREAM)
            listeners.append(listener)
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address, port))
            port = listener.getsockname()[1]
            listener.listen(8)
            listener.settimeout(0.2)
        resolved = sorted({(family.name, address[0]) for family, _, _, _, address in
                           socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM,
                                              proto=socket.IPPROTO_TCP)})
    except Exception:
        for listener in listeners:
            listener.close()
        raise
    stopping = threading.Event()
    output_lock, state_lock = threading.Lock(), threading.Lock()
    responses = {}
    workers = []

    def emit(event, **values):
        with output_lock:
            print(json.dumps({"event": event, **values}), flush=True)

    def connection(raw, identifier):
        tls = None
        stage = "accepted"
        try:
            addresses = {}
            for name, reader in (("local", raw.getsockname), ("peer", raw.getpeername)):
                try:
                    addresses[name] = list(reader())
                except OSError as error:
                    addresses[name + "_observation_error"] = str(error)
            emit("accepted", id=identifier, **addresses,
                 observed_utc=datetime.now(timezone.utc).isoformat())
            raw.settimeout(5)
            stage = "tls-handshake"
            tls = context.wrap_socket(raw, server_side=True)
            protocol = tls.selected_alpn_protocol() or ""
            emit("protocol", id=identifier, value=protocol)
            if protocol == "h2":
                return
            stage = "http-request-headers"
            headers = bytearray()
            while b"\r\n\r\n" not in headers:
                data = tls.recv(4096)
                if not data:
                    raise RuntimeError("Client closed before HTTP request headers")
                headers.extend(data)
                if len(headers) > 32768:
                    raise RuntimeError("Fixture request headers exceed 32 KiB")
            headers = bytes(headers).split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n"
            pending = queue.Queue(maxsize=1)
            with state_lock:
                responses[identifier] = pending
            emit("request", id=identifier, headers=base64.b64encode(headers).decode("ascii"))
            stage = "awaiting-fixture-response"
            response = pending.get(timeout=10)
            if response.get("hanging"):
                tls.settimeout(0.2)
                while not stopping.is_set():
                    try:
                        if not tls.recv(1024):
                            break
                    except socket.timeout:
                        continue
            else:
                stage = "http-response"
                body = base64.b64decode(response["body"], validate=True)
                location = response.get("location", "").encode("ascii")
                if b"\r" in location or b"\n" in location:
                    raise RuntimeError("Fixture Location must be one header value")
                wire = b"HTTP/1.1 " + str(int(response["status"])).encode("ascii") + b" Fixture\r\n"
                if location:
                    wire += b"Location: " + location + b"\r\n"
                wire += b"Content-Type: application/yaml\r\nConnection: close\r\nContent-Length: "
                tls.sendall(wire + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)
        except (OSError, RuntimeError, ValueError, queue.Empty) as error:
            emit("error", id=identifier, message=f"{type(error).__name__}: {error}", stage=stage,
                 observed_utc=datetime.now(timezone.utc).isoformat())
        finally:
            with state_lock:
                responses.pop(identifier, None)
            if tls is not None:
                tls.close()
                emit("disconnected", id=identifier)
            else:
                raw.close()

    def accept():
        identifier = 0
        while not stopping.is_set():
            try:
                readable, _, _ = select.select(listeners, [], [], 0.2)
            except (OSError, ValueError):
                if stopping.is_set():
                    break
                raise
            for listener in readable:
                try:
                    raw, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if stopping.is_set():
                        return
                    raise
                identifier += 1
                worker = threading.Thread(target=connection, args=(raw, identifier), daemon=True)
                workers.append(worker)
                worker.start()

    accept_thread = threading.Thread(target=accept, daemon=True)
    accept_thread.start()
    emit("ready", port=port, tls=ssl.OPENSSL_VERSION,
         listeners=[{"bound": list(listener.getsockname()), "family": listener.family.name}
                    for listener in listeners],
         localhost_resolution=[{"family": family, "address": address} for family, address in resolved],
         python=sys.version.split()[0],
         executable=sys.executable, observed_utc=datetime.now(timezone.utc).isoformat())
    try:
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("command") == "quit":
                break
            with state_lock:
                pending = responses.get(message.get("id"))
            if pending is None:
                raise RuntimeError("Response has no pending fixture request")
            pending.put_nowait(message)
    finally:
        stopping.set()
        for listener in listeners:
            listener.close()
        accept_thread.join(timeout=1)
        with state_lock:
            pending_responses = list(responses.values())
        for pending in pending_responses:
            try:
                pending.put_nowait({"hanging": True})
            except queue.Full:
                pass
        for worker in workers:
            worker.join(timeout=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", type=Path)
    mode.add_argument("--serve", type=Path)
    args = parser.parse_args()
    prepare(args.prepare) if args.prepare else serve(args.serve)
