#!/usr/bin/env python3
"""Independent, bounded, loopback-only REALITY/TLS 1.3 test server.

This is a protocol test peer, not a production proxy. The static REALITY key,
Ed25519 key, SNI and short ID are public synthetic fixture material. Every live
TLS ECDHE key, ML-KEM encapsulation and ServerHello random is generated freshly
by cryptography/OpenSSL or os.urandom. No Swirl Rust client code is imported.

Independently implemented after reading RFC 8446 sections 4, 5, 6 and 7;
RFC 10024 section 4; and pinned XTLS source behavior. No source code from
Xray or REALITY is incorporated. Primary references:
https://www.rfc-editor.org/rfc/rfc8446.html
https://www.rfc-editor.org/rfc/rfc10024.html
https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/tls.go
https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/handshake_server_tls13.go Only an extension-free HMAC/Ed25519
certificate profile is supported. Vision, camouflage forwarding, ML-DSA,
fingerprint emulation, resumption, client certificates and KeyUpdate are absent.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import threading
import time
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "core/crates/swirl-transport/tests/fixtures/reality_auth.json"
)
TLS13 = b"\x03\x04"
TLS12 = b"\x03\x03"
HYBRID = 0x11EC
X25519 = 0x001D
MAX_RECORD = (1 << 14) + 256
MAX_PLAINTEXT = 1 << 14
MAX_HELLO = 1 << 16
MAX_RECORDS = 256
MAX_APPLICATION = 1 << 20
HRR_RANDOM = bytes.fromhex(
    "cf21ad74e59a6111be1d8c021e65b891c2a211167abb8c5e079e09e2c8a8339c"
)
MODES = (
    "valid",
    "wrong_auth",
    "bad_certificate_mac",
    "bad_certificate_verify",
    "bad_finished",
    "bad_session_echo",
    "hello_retry_request",
    "unoffered_alpn",
    "eof_without_close_notify",
)
BAD_SERVER_FLIGHT_MODES = frozenset(MODES) - {"valid", "wrong_auth", "eof_without_close_notify"}


class PeerError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ClientAlert(PeerError):
    def __init__(self, payload: bytes):
        if len(payload) != 2:
            super().__init__("malformed_client_alert")
        else:
            super().__init__(f"client_alert_{payload[0]}_{payload[1]}")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PeerError(code)


def vector(data: bytes, width: int = 2) -> bytes:
    require(len(data) < 1 << (width * 8), "vector_overflow")
    return len(data).to_bytes(width, "big") + data


def handshake(kind: int, body: bytes) -> bytes:
    return bytes([kind]) + vector(body, 3)


def extension(kind: int, body: bytes) -> bytes:
    return kind.to_bytes(2, "big") + vector(body)


def flipped(data: bytes) -> bytes:
    require(bool(data), "empty_mutation")
    return bytes([data[0] ^ 1]) + data[1:]


class Cursor:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def take(self, count: int) -> bytes:
        require(0 <= count <= len(self.data) - self.offset, "truncated_vector")
        out = self.data[self.offset : self.offset + count]
        self.offset += count
        return out

    def uint(self, width: int) -> int:
        return int.from_bytes(self.take(width), "big")

    def vector(self, width: int = 2) -> bytes:
        return self.take(self.uint(width))

    def done(self) -> None:
        require(self.offset == len(self.data), "trailing_vector_bytes")

    def remaining(self) -> int:
        return len(self.data) - self.offset


def uint16_list(data: bytes) -> tuple[int, ...]:
    require(len(data) > 0 and len(data) % 2 == 0, "invalid_uint16_list")
    c = Cursor(data)
    return tuple(c.uint(2) for _ in range(len(data) // 2))


def vector_contents(data: bytes, width: int = 2) -> bytes:
    c = Cursor(data)
    out = c.vector(width)
    c.done()
    return out


@dataclass(frozen=True)
class ClientHello:
    raw: bytes
    random: bytes
    session_id: bytes
    session_offset: int
    suites: tuple[int, ...]
    groups: tuple[int, ...]
    shares: dict[int, bytes]
    server_name: str
    alpn: tuple[bytes, ...]

    @classmethod
    def parse(cls, data: bytes, expected_name: str) -> ClientHello:
        require(4 <= len(data) <= MAX_HELLO, "hello_size")
        outer = Cursor(data)
        require(outer.uint(1) == 1, "expected_client_hello")
        body = outer.vector(3)
        outer.done()
        c = Cursor(body)
        require(c.take(2) == TLS12, "client_legacy_version")
        random = c.take(32)
        session_id = c.vector(1)
        session_offset = 4 + c.offset - len(session_id)
        require(len(session_id) == 32, "session_id_length")
        suites = uint16_list(c.vector())
        require(c.vector(1) == b"\x00", "client_compression")
        exts = Cursor(c.vector())
        c.done()
        extensions: dict[int, bytes] = {}
        while exts.remaining():
            tag, value = exts.uint(2), exts.vector()
            require(tag not in extensions, "duplicate_extension")
            extensions[tag] = value
        require({0, 10, 13, 43, 51} <= extensions.keys(), "missing_required_extension")
        require(not ({41, 42, 0xFE0D} & extensions.keys()), "unsupported_psk_early_data_ech")
        versions = uint16_list(vector_contents(extensions[43], 1))
        require(0x0304 in versions, "tls13_not_offered")
        sigs = uint16_list(vector_contents(extensions[13]))
        require(0x0807 in sigs, "ed25519_not_offered")
        groups = uint16_list(vector_contents(extensions[10]))
        names = Cursor(vector_contents(extensions[0]))
        require(names.uint(1) == 0, "sni_type")
        try:
            name = names.vector().decode("ascii")
        except UnicodeDecodeError as exc:
            raise PeerError("sni_encoding") from exc
        names.done()
        require(name == expected_name, "sni_mismatch")
        encoded_shares = Cursor(vector_contents(extensions[51]))
        shares: dict[int, bytes] = {}
        while encoded_shares.remaining():
            group, share = encoded_shares.uint(2), encoded_shares.vector()
            require(group not in shares, "duplicate_key_share")
            require(group in groups, "share_not_in_supported_groups")
            shares[group] = share
        # Explicit modern test profile: the optional classical offer must be
        # backed by the same X25519 owner used for authentication and the hybrid.
        require(list(shares) in ([HYBRID], [HYBRID, X25519]), "modern_share_order")
        require(len(shares[HYBRID]) == 1216, "hybrid_share_length")
        if X25519 in shares:
            require(shares[X25519] == shares[HYBRID][-32:], "distinct_classical_owner")
        alpn: list[bytes] = []
        if 16 in extensions:
            protocols = Cursor(vector_contents(extensions[16]))
            while protocols.remaining():
                protocol = protocols.vector(1)
                require(bool(protocol) and protocol not in alpn, "invalid_alpn_list")
                alpn.append(protocol)
            require(bool(alpn), "empty_alpn_list")
        return cls(data, random, session_id, session_offset, suites, groups, shares, name, tuple(alpn))

    def zero_session_hello(self) -> bytes:
        start = self.session_offset
        return self.raw[:start] + bytes(32) + self.raw[start + 32 :]


def authenticate_client(
    hello: ClientHello,
    private_key: x25519.X25519PrivateKey,
    short_id: bytes,
    now: int,
    *,
    max_clock_skew: int = 60,
    wrong_auth: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    peer = x25519.X25519PublicKey.from_public_bytes(hello.shares[HYBRID][-32:])
    try:
        shared = private_key.exchange(peer)
    except ValueError as exc:
        raise PeerError("invalid_auth_x25519") from exc
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hello.random[:20], info=b"REALITY").derive(shared)
    if wrong_auth:
        key = flipped(key)
    try:
        plain = AESGCM(key).decrypt(hello.random[20:], hello.session_id, hello.zero_session_hello())
    except InvalidTag as exc:
        raise PeerError("authentication_tag") from exc
    require(len(plain) == 16, "authentication_plaintext_length")
    require(plain[3] == 0, "authentication_reserved")
    require(plain[:3] == bytes([26, 10, 19]), "authentication_version")
    timestamp = int.from_bytes(plain[4:8], "big")
    require(abs(now - timestamp) <= max_clock_skew, "authentication_time")
    require(hmac.compare_digest(plain[8:], short_id), "authentication_short_id")
    return key, {"clientVersion": list(plain[:3]), "timestampVerified": True, "shortIdVerified": True}


def digest(data: bytes, hash_name: str) -> bytes:
    return hashlib.new(hash_name, data).digest()


def expand_label(secret: bytes, label: bytes, context: bytes, hash_name: str, length: int | None = None) -> bytes:
    algorithm = hashes.SHA256() if hash_name == "sha256" else hashes.SHA384()
    size = algorithm.digest_size if length is None else length
    info = size.to_bytes(2, "big") + vector(b"tls13 " + label, 1) + vector(context, 1)
    return HKDFExpand(algorithm=algorithm, length=size, info=info).derive(secret)


def handshake_secrets(shared: bytes, transcript: bytes, hash_name: str) -> tuple[bytes, bytes, bytes]:
    zero = bytes(len(digest(b"", hash_name)))
    early = hmac.digest(zero, zero, hash_name)
    derived = expand_label(early, b"derived", digest(b"", hash_name), hash_name)
    secret = hmac.digest(derived, shared, hash_name)
    checkpoint = digest(transcript, hash_name)
    return (
        secret,
        expand_label(secret, b"c hs traffic", checkpoint, hash_name),
        expand_label(secret, b"s hs traffic", checkpoint, hash_name),
    )


def finished(traffic_secret: bytes, transcript: bytes, hash_name: str) -> bytes:
    key = expand_label(traffic_secret, b"finished", b"", hash_name)
    return handshake(20, hmac.digest(key, digest(transcript, hash_name), hash_name))


def application_secrets(secret: bytes, transcript: bytes, hash_name: str) -> tuple[bytes, bytes]:
    zero = bytes(len(digest(b"", hash_name)))
    derived = expand_label(secret, b"derived", digest(b"", hash_name), hash_name)
    master = hmac.digest(derived, zero, hash_name)
    checkpoint = digest(transcript, hash_name)
    return (
        expand_label(master, b"c ap traffic", checkpoint, hash_name),
        expand_label(master, b"s ap traffic", checkpoint, hash_name),
    )


def der(tag: int, data: bytes) -> bytes:
    count = len(data)
    size = bytes([count]) if count < 128 else vector(count.to_bytes((count.bit_length() + 7) // 8, "big"), 1)
    if count >= 128:
        size = bytes([size[0] | 0x80]) + size[1:]
    return bytes([tag]) + size + data


def authenticated_certificate(template: bytes, key: bytes, signing_key: ed25519.Ed25519PrivateKey) -> bytes:
    parsed = x509.load_der_x509_certificate(template)
    require(not parsed.extensions, "certificate_template_extensions")
    public = signing_key.public_key().public_bytes_raw()
    require(parsed.public_key().public_bytes_raw() == public, "certificate_template_key")
    mac = hmac.digest(key, public, "sha512")
    algorithm = bytes.fromhex("300506032b6570")
    return der(0x30, parsed.tbs_certificate_bytes + algorithm + der(3, b"\x00" + mac))


@dataclass(frozen=True)
class KeyExchange:
    group: int
    server_share: bytes
    shared_secret: bytes

    @classmethod
    def fresh(cls, hello: ClientHello, group: int) -> KeyExchange:
        require(group in hello.shares, "selected_group_not_offered")
        key = x25519.X25519PrivateKey.generate()
        public = key.public_key().public_bytes_raw()
        try:
            classical = key.exchange(x25519.X25519PublicKey.from_public_bytes(hello.shares[group][-32:]))
        except ValueError as exc:
            raise PeerError("invalid_tls_x25519") from exc
        if group == X25519:
            return cls(group, public, classical)
        require(group == HYBRID, "unsupported_group")
        try:
            kem = mlkem.MLKEM768PublicKey.from_public_bytes(hello.shares[group][:-32])
            kem_secret, ciphertext = kem.encapsulate()
        except ValueError as exc:
            raise PeerError("invalid_mlkem_encapsulation_key") from exc
        require(len(ciphertext) == 1088 and len(kem_secret) == 32, "mlkem_output_size")
        return cls(group, ciphertext + public, kem_secret + classical)


@dataclass(frozen=True)
class ServerFlight:
    server_hello: bytes
    encrypted_extensions: bytes
    certificate: bytes
    certificate_verify: bytes
    server_finished: bytes
    hello_transcript: bytes
    before_certificate_verify: bytes
    before_finished: bytes
    through_server_finished: bytes
    handshake_secret: bytes
    client_handshake_secret: bytes
    server_handshake_secret: bytes
    client_application_secret: bytes
    server_application_secret: bytes
    suite: int
    hash_name: str

    def encrypted_handshake_messages(self) -> bytes:
        return self.encrypted_extensions + self.certificate + self.certificate_verify + self.server_finished


def build_server_flight(
    hello: ClientHello,
    authentication_key: bytes,
    exchange: KeyExchange,
    suite: int,
    certificate_template: bytes,
    signing_key: ed25519.Ed25519PrivateKey,
    *,
    alpn: bytes | None = None,
    mode: str = "valid",
    server_random: bytes | None = None,
) -> ServerFlight:
    require(suite in (0x1301, 0x1302, 0x1303) and suite in hello.suites, "selected_suite_not_offered")
    require(exchange.group in hello.shares, "selected_group_not_offered")
    random = os.urandom(32) if server_random is None else server_random
    require(len(random) == 32 and random != HRR_RANDOM, "server_random")
    name = "sha384" if suite == 0x1302 else "sha256"
    session_id = flipped(hello.session_id) if mode == "bad_session_echo" else hello.session_id
    exts = extension(43, TLS13) + extension(51, exchange.group.to_bytes(2, "big") + vector(exchange.server_share))
    sh = handshake(2, TLS12 + random + vector(session_id, 1) + suite.to_bytes(2, "big") + b"\x00" + vector(exts))
    ee_extensions = extension(0, b"")
    if mode == "unoffered_alpn":
        alpn = b"swirl-invalid-alpn"
        require(alpn not in hello.alpn, "negative_alpn_already_offered")
    elif alpn is not None:
        require(alpn in hello.alpn, "selected_alpn_not_offered")
    if alpn is not None:
        ee_extensions += extension(16, vector(vector(alpn, 1)))
    ee = handshake(8, vector(ee_extensions))
    cert_key = flipped(authentication_key) if mode == "bad_certificate_mac" else authentication_key
    cert_der = authenticated_certificate(certificate_template, cert_key, signing_key)
    cert_message = handshake(11, vector(b"", 1) + vector(vector(cert_der, 3) + vector(b""), 3))
    hello_transcript = hello.raw + sh
    before_cv = hello_transcript + ee + cert_message
    cv_input = b" " * 64 + b"TLS 1.3, server CertificateVerify\x00" + digest(before_cv, name)
    signature = signing_key.sign(cv_input)
    if mode == "bad_certificate_verify":
        signature = flipped(signature)
    cv = handshake(15, b"\x08\x07" + vector(signature))
    secret, client_hs, server_hs = handshake_secrets(exchange.shared_secret, hello_transcript, name)
    before_finished = before_cv + cv
    sf = finished(server_hs, before_finished, name)
    if mode == "bad_finished":
        sf = sf[:4] + flipped(sf[4:])
    through_finished = before_finished + sf
    client_ap, server_ap = application_secrets(secret, through_finished, name)
    return ServerFlight(sh, ee, cert_message, cv, sf, hello_transcript, before_cv, before_finished,
                        through_finished, secret, client_hs, server_hs, client_ap, server_ap, suite, name)


class RecordCipher:
    def __init__(self, secret: bytes, suite: int):
        require(suite in (0x1301, 0x1302, 0x1303), "unsupported_record_suite")
        name = "sha384" if suite == 0x1302 else "sha256"
        key_len = 16 if suite == 0x1301 else 32
        key = expand_label(secret, b"key", b"", name, key_len)
        self.iv = expand_label(secret, b"iv", b"", name, 12)
        self.aead = ChaCha20Poly1305(key) if suite == 0x1303 else AESGCM(key)
        self.sequence = 0

    def nonce(self) -> bytes:
        require(self.sequence < 1 << 64, "record_sequence_exhausted")
        count = self.sequence.to_bytes(12, "big")
        return bytes(a ^ b for a, b in zip(self.iv, count))

    def encrypt(self, kind: int, content: bytes, *, padding: int = 0) -> bytes:
        require(kind in (21, 22, 23), "invalid_inner_type")
        require(kind == 23 or bool(content), "empty_control_record")
        require(padding >= 0 and len(content) + padding <= MAX_PLAINTEXT, "plaintext_record_overflow")
        plain = content + bytes([kind]) + bytes(padding)
        header = b"\x17\x03\x03" + (len(plain) + 16).to_bytes(2, "big")
        encrypted = self.aead.encrypt(self.nonce(), plain, header)
        self.sequence += 1
        return header + encrypted

    def decrypt(self, record: bytes) -> tuple[int, bytes]:
        require(len(record) >= 5 and record[:3] == b"\x17\x03\x03", "encrypted_record_header")
        size = int.from_bytes(record[3:5], "big")
        require(17 <= size <= MAX_RECORD and len(record) == 5 + size, "encrypted_record_size")
        try:
            plain = self.aead.decrypt(self.nonce(), record[5:], record[:5])
        except InvalidTag as exc:
            raise PeerError("record_authentication") from exc
        self.sequence += 1
        require(len(plain) <= MAX_PLAINTEXT + 1, "plaintext_record_overflow")
        unpadded = plain.rstrip(b"\x00")
        require(bool(unpadded), "missing_inner_type")
        kind, content = unpadded[-1], unpadded[:-1]
        require(kind in (21, 22, 23), "invalid_inner_type")
        require(kind == 23 or bool(content), "empty_control_record")
        return kind, content


class Wire:
    def __init__(self, connection: socket.socket, timeout: float):
        self.connection = connection
        self.deadline = time.monotonic() + timeout
        self.records = 0
        self.ccs = 0

    def set_timeout(self) -> None:
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "deadline_exceeded")
        self.connection.settimeout(remaining)

    def exact(self, count: int) -> bytes:
        require(0 <= count <= MAX_RECORD, "read_bound")
        out = bytearray()
        while len(out) < count:
            self.set_timeout()
            try:
                chunk = self.connection.recv(count - len(out))
            except TimeoutError as exc:
                raise PeerError("deadline_exceeded") from exc
            except ConnectionResetError as exc:
                raise PeerError("transport_reset") from exc
            require(bool(chunk), "transport_eof_without_close_notify")
            out.extend(chunk)
        return bytes(out)

    def read(self) -> bytes:
        self.records += 1
        require(self.records <= MAX_RECORDS, "record_count_limit")
        header = self.exact(5)
        size = int.from_bytes(header[3:], "big")
        require(0 < size <= MAX_RECORD, "record_length")
        require(header[1:3] in (b"\x03\x01", TLS12), "record_version")
        if header[0] != 23:
            require(size <= MAX_PLAINTEXT, "plaintext_record_overflow")
        return header + self.exact(size)

    def send(self, data: bytes) -> None:
        self.set_timeout()
        try:
            self.connection.sendall(data)
        except ConnectionResetError as exc:
            raise PeerError("transport_reset") from exc
        except BrokenPipeError as exc:
            raise PeerError("transport_broken_pipe") from exc

    def plain(self, kind: int, data: bytes) -> None:
        require(0 < len(data) <= MAX_PLAINTEXT, "plaintext_record_overflow")
        self.send(bytes([kind]) + TLS12 + vector(data))

    def client_hello(self) -> bytes:
        pending = bytearray()
        for _ in range(MAX_RECORDS):
            record = self.read()
            require(record[0] == 22, "expected_client_hello_record")
            pending.extend(record[5:])
            require(len(pending) <= MAX_HELLO, "hello_size")
            if len(pending) >= 4:
                target = int.from_bytes(pending[1:4], "big") + 4
                require(target <= MAX_HELLO, "hello_size")
                require(len(pending) <= target, "early_client_handshake_bytes")
                if len(pending) == target:
                    return bytes(pending)
        raise PeerError("record_count_limit")

    def protected(self, cipher: RecordCipher, *, allow_ccs: bool = True) -> tuple[int, bytes]:
        for _ in range(3):
            record = self.read()
            if record[0] == 20:
                require(allow_ccs, "compatibility_ccs_after_finished")
                require(record == b"\x14\x03\x03\x00\x01\x01", "invalid_compatibility_ccs")
                self.ccs += 1
                require(self.ccs <= 2, "excess_compatibility_ccs")
                continue
            if record[0] == 21:
                raise ClientAlert(record[5:])
            return cipher.decrypt(record)
        raise PeerError("excess_compatibility_ccs")


class RealityPeer:
    """One bounded connection; context exit raises any unacknowledged failure.

For deliberate bad client authentication, pass expected_failure with its exact
peer code, e.g. ``authentication_tag``. Negative server modes expect a fatal
client alert or EOF before client Finished/application data. A timeout, internal
exception or unexpected client acceptance is never classified as success.
"""

    def __init__(
        self,
        mode: str = "valid",
        *,
        suite: int = 0x1301,
        group: int = HYBRID,
        alpn: bytes | None = None,
        fixture: Path = DEFAULT_FIXTURE,
        timeout: float = 15.0,
        expected_failure: str | None = None,
        now: int | None = None,
        fragment_handshake: int = 0,
    ):
        require(mode in MODES, "invalid_test_mode")
        require(suite in (0x1301, 0x1302, 0x1303) and group in (HYBRID, X25519), "invalid_test_selection")
        require(0 < timeout <= 30 and 0 <= fragment_handshake <= MAX_PLAINTEXT, "invalid_test_bounds")
        data = json.loads(Path(fixture).read_bytes())
        require(data["public_test_material"] is True, "fixture_must_be_public_synthetic")
        auth = data["cases"][1]
        self.server_name = auth["server_name"]
        self.short_id = bytes.fromhex(auth["short_id_hex"])
        self.private = x25519.X25519PrivateKey.from_private_bytes(bytes.fromhex(auth["server_private_key_hex"]))
        self.public_key = self.private.public_key().public_bytes_raw()
        self.signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(data["certificate"]["ed25519_seed_hex"]))
        self.certificate_template = bytes.fromhex(data["certificate"]["der_hex"])
        self.mode, self.suite, self.group, self.alpn = mode, suite, group, alpn
        self.timeout, self.expected_failure, self.now = timeout, expected_failure, now
        self.fragment_handshake = fragment_handshake
        self.listener: socket.socket | None = None
        self.connection: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.port: int | None = None
        self.result: dict[str, Any] = {
            "mode": mode,
            "status": "pending",
            "clientHelloAuthenticated": False,
            "clientFinishedVerified": False,
            "serverFlightSent": False,
            "applicationBytesReceived": 0,
            "applicationBytesSent": 0,
            "closeNotifyReceived": False,
            "closeNotifySent": False,
            "publicSyntheticMaterialOnly": True,
        }

    def __enter__(self) -> RealityPeer:
        require(self.thread is None, "peer_already_started")
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.settimeout(self.timeout)
            self.listener.bind(("127.0.0.1", 0))
            self.port = self.listener.getsockname()[1]
            self.listener.listen(1)
            self.thread = threading.Thread(target=self._run, name="swirl-reality-test-peer", daemon=True)
            self.thread.start()
        except BaseException:
            self.listener.close()
            raise
        return self

    def settings(self) -> dict[str, Any]:
        return {"host": "127.0.0.1", "port": self.port, "server_name": self.server_name,
                "public_key_hex": self.public_key.hex(), "short_id_hex": self.short_id.hex(),
                "version": [26, 10, 19], "alpn": self.alpn.decode("ascii") if self.alpn else None}

    def wait(self, timeout: float | None = None) -> dict[str, Any]:
        require(self.thread is not None, "peer_not_started")
        self.thread.join(self.timeout + 1 if timeout is None else timeout)
        require(not self.thread.is_alive(), "peer_thread_timeout")
        return dict(self.result)

    def assert_outcome(self) -> None:
        status = self.result["status"]
        if self.expected_failure is not None:
            require(status == "failed" and self.result.get("error") == self.expected_failure,
                    f"unexpected_peer_result:{status}:{self.result.get('error', '')}")
        elif self.mode == "valid":
            require(status == "completed", f"unexpected_peer_result:{status}:{self.result.get('error', '')}")
        elif self.mode == "eof_without_close_notify":
            require(status == "intentional_unclean_eof" and self.result["closeNotifyReceived"]
                    and not self.result["closeNotifySent"], "unclean_eof_scenario_not_executed")
        else:
            require(status in ("client_rejected", "authentication_rejected"),
                    f"negative_peer_not_rejected:{status}:{self.result.get('error', '')}")

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self.thread is not None:
                self.thread.join(self.timeout + 1 if exc is None else 0.1)
            if self.thread is not None and self.thread.is_alive():
                if self.connection is not None:
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                if self.listener is not None:
                    self.listener.close()
                self.thread.join(1)
            require(self.thread is not None and not self.thread.is_alive(), "peer_thread_leak")
            self.assert_outcome()
        except Exception as peer_error:
            if exc is None:
                raise
            exc.add_note(f"Independent REALITY peer also reported: {peer_error}")
        finally:
            if self.listener is not None:
                self.listener.close()
        return False

    def _run(self) -> None:
        try:
            require(self.listener is not None, "missing_listener")
            with self.listener.accept()[0] as connection:
                self.connection = connection
                self._serve(Wire(connection, self.timeout))
        except PeerError as exc:
            self.result.update(status="failed", error=exc.code)
        except TimeoutError:
            self.result.update(status="failed", error="deadline_exceeded")
        except OSError as exc:
            self.result.update(status="failed", error="socket_error", socketErrno=exc.errno,
                               winerror=getattr(exc, "winerror", None))
        except Exception as exc:
            self.result.update(status="failed", error=f"internal_{type(exc).__name__}")
        finally:
            self.connection = None

    def _serve(self, wire: Wire) -> None:
        raw = wire.client_hello()
        hello = ClientHello.parse(raw, self.server_name)
        self.result.update(clientHelloSha256=hashlib.sha256(raw).hexdigest(), clientHelloBytes=len(raw))
        try:
            key, auth_metadata = authenticate_client(hello, self.private, self.short_id,
                int(time.time()) if self.now is None else self.now, wrong_auth=self.mode == "wrong_auth")
        except PeerError as exc:
            try:
                wire.plain(21, b"\x02\x28")
            except OSError:
                pass
            if self.mode == "wrong_auth" and exc.code == "authentication_tag":
                self.result.update(status="authentication_rejected", error=exc.code)
                return
            raise
        self.result.update(clientHelloAuthenticated=True, **auth_metadata)
        if self.mode == "hello_retry_request":
            exts = extension(43, TLS13) + extension(44, vector(b"swirl-public-test-cookie"))
            retry = handshake(2, TLS12 + HRR_RANDOM + vector(hello.session_id, 1)
                              + self.suite.to_bytes(2, "big") + b"\x00" + vector(exts))
            wire.plain(22, retry)
            self._expect_rejection(wire, None)
            return
        exchange = KeyExchange.fresh(hello, self.group)
        flight = build_server_flight(hello, key, exchange, self.suite, self.certificate_template,
                                    self.signing_key, alpn=self.alpn, mode=self.mode)
        self.result.update(selectedSuite=self.suite, selectedGroup=self.group,
                           helloTranscriptHash=digest(flight.hello_transcript, flight.hash_name).hex(),
                           serverFinishedTranscriptHash=digest(flight.through_server_finished, flight.hash_name).hex())
        server_hs = RecordCipher(flight.server_handshake_secret, self.suite)
        client_hs = RecordCipher(flight.client_handshake_secret, self.suite)
        messages = flight.encrypted_handshake_messages()
        size = self.fragment_handshake or len(messages)
        records = [b"\x16\x03\x03" + vector(flight.server_hello), b"\x14\x03\x03\x00\x01\x01"]
        for offset in range(0, len(messages), size):
            records.append(server_hs.encrypt(22, messages[offset : offset + size]))
        require(len(records) <= MAX_RECORDS, "server_flight_record_limit")
        try:
            wire.send(b"".join(records))
        except PeerError as exc:
            if self.mode in BAD_SERVER_FLIGHT_MODES and exc.code in ("transport_reset", "transport_broken_pipe"):
                self.result.update(status="client_rejected", error=exc.code, rejectionEvidence="transport_closed")
                return
            raise
        self.result["serverFlightSent"] = True
        if self.mode in BAD_SERVER_FLIGHT_MODES:
            self._expect_rejection(wire, client_hs)
            return
        self._read_finished(wire, client_hs, flight)
        self.result["clientFinishedVerified"] = True
        client_ap = RecordCipher(flight.client_application_secret, self.suite)
        server_ap = RecordCipher(flight.server_application_secret, self.suite)
        for _ in range(MAX_RECORDS):
            kind, data = wire.protected(client_ap, allow_ccs=False)
            if kind == 21:
                require(data == b"\x01\x00", "expected_close_notify")
                self.result["closeNotifyReceived"] = True
                if self.mode == "eof_without_close_notify":
                    self.result["status"] = "intentional_unclean_eof"
                    return
                wire.send(server_ap.encrypt(21, b"\x01\x00"))
                self.result["closeNotifySent"] = True
                self.result["status"] = "completed"
                return
            require(kind == 23, "unexpected_post_handshake_message")
            self.result["applicationBytesReceived"] += len(data)
            require(self.result["applicationBytesReceived"] <= MAX_APPLICATION, "application_byte_limit")
            wire.send(server_ap.encrypt(23, data))
            self.result["applicationBytesSent"] += len(data)
        raise PeerError("record_count_limit")

    def _read_finished(self, wire: Wire, cipher: RecordCipher, flight: ServerFlight) -> None:
        expected = finished(flight.client_handshake_secret, flight.through_server_finished, flight.hash_name)
        data = bytearray()
        for _ in range(MAX_RECORDS):
            kind, part = wire.protected(cipher)
            if kind == 21:
                raise ClientAlert(part)
            require(kind == 22, "application_before_client_finished")
            data.extend(part)
            require(len(data) <= len(expected), "unexpected_client_handshake_length")
            if len(data) == len(expected):
                require(hmac.compare_digest(data, expected), "client_finished_verification")
                return
        raise PeerError("record_count_limit")

    def _expect_rejection(self, wire: Wire, cipher: RecordCipher | None) -> None:
        try:
            if cipher is not None:
                kind, data = wire.protected(cipher)
                if kind == 21:
                    raise ClientAlert(data)
                raise PeerError("client_accepted_corrupt_server_flight")
            for _ in range(3):
                record = wire.read()
                if record[0] == 20 and record[5:] == b"\x01":
                    continue
                if record[0] == 21:
                    raise ClientAlert(record[5:])
                raise PeerError("client_retried_or_accepted_hrr")
            raise PeerError("excess_compatibility_ccs")
        except PeerError as exc:
            # EOF alone is acceptable only for these deliberately corrupted
            # server-flight scenarios, never for a purported completed stream.
            transport_closed = exc.code in ("transport_eof_without_close_notify", "transport_reset", "transport_broken_pipe")
            if transport_closed or (
                exc.code.startswith("client_alert_2_") and not exc.code.endswith("_0")
            ):
                self.result.update(status="client_rejected", error=exc.code,
                                   rejectionEvidence="transport_closed" if transport_closed else "tls_fatal_alert")
                return
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="valid")
    parser.add_argument("--suite", type=lambda s: int(s, 0), default=0x1301)
    parser.add_argument("--group", type=lambda s: int(s, 0), default=HYBRID)
    parser.add_argument("--alpn")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--expected-failure")
    parser.add_argument("--fragment-handshake", type=int, default=0)
    args = parser.parse_args()
    peer = RealityPeer(args.mode, suite=args.suite, group=args.group,
                       alpn=args.alpn.encode("ascii") if args.alpn else None,
                       fixture=args.fixture, timeout=args.timeout,
                       expected_failure=args.expected_failure,
                       fragment_handshake=args.fragment_handshake)
    try:
        with peer:
            print(json.dumps({"event": "ready", **peer.settings()}), flush=True)
            peer.wait()
        print(json.dumps({"event": "result", **peer.result}), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"event": "result", **peer.result, "runnerError": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
