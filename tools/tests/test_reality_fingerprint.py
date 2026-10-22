#!/usr/bin/env python3
"""Compare Swirl's actual first ClientHello with locked upstream uTLS Chrome 133.

Only first-handshake randoms, session IDs, ephemeral public share values, GREASE
values, the documented ECH random payload-size family and extension permutation
are normalized. Cipher/group/signature/version/ALPN order and every fixed
extension byte remain significant. The observable relationship between the
hybrid and standalone X25519 public shares is also compared, never normalized
away. The Go oracle is test-only and never opens
a network connection. A wire-profile match is not a provider connection claim.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SERVER_NAME = "swirl-fingerprint.test"
UTLS_MODULE = "github.com/refraction-networking/utls"
UTLS_VERSION = "v1.8.3-0.20260301010127-aa6edf4b11af"
PROFILE = "HelloChrome_133"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def grease(value):
    return value & 0x0F0F == 0x0A0A and value >> 8 == value & 255


def identifier(value):
    return "GREASE" if grease(value) else value


class Reader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, length):
        if self.position + length > len(self.data):
            raise ValueError("Truncated ClientHello field")
        value = self.data[self.position:self.position + length]
        self.position += length
        return value

    def number(self, width):
        return int.from_bytes(self.take(width), "big")

    def vector(self, width):
        return self.take(self.number(width))

    def end(self):
        if self.position != len(self.data):
            raise ValueError("Trailing bytes in ClientHello field")


def numbers(data):
    if len(data) % 2:
        raise ValueError("Odd length in a TLS uint16 vector")
    return [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]


def parse_hello(raw):
    reader = Reader(raw)
    if reader.number(1) != 1 or reader.number(3) != len(raw) - 4:
        raise ValueError("Not an exactly bounded ClientHello handshake")
    hello = {"legacy_version": reader.number(2), "random": reader.take(32),
             "session_id": reader.vector(1), "cipher_suites": numbers(reader.vector(2)),
             "compression": reader.vector(1)}
    extensions = Reader(reader.vector(2))
    reader.end()
    hello["extensions"] = []
    seen = set()
    while extensions.position < len(extensions.data):
        kind, payload = extensions.number(2), extensions.vector(2)
        if kind in seen:
            raise ValueError("Repeated extension identifier")
        seen.add(kind)
        hello["extensions"].append((kind, payload))
    extensions.end()
    return hello


def encode_hello(hello):
    """Re-encode only test mutations, never construct the reference profile."""
    def vector(data, width):
        return len(data).to_bytes(width, "big") + data
    ciphers = b"".join(value.to_bytes(2, "big") for value in hello["cipher_suites"])
    extensions = b"".join(kind.to_bytes(2, "big") + vector(data, 2)
                          for kind, data in hello["extensions"])
    body = (hello["legacy_version"].to_bytes(2, "big") + hello["random"]
            + vector(hello["session_id"], 1) + vector(ciphers, 2)
            + vector(hello["compression"], 1) + vector(extensions, 2))
    return b"\x01" + len(body).to_bytes(3, "big") + body


def canonical(hello, ech_lengths):
    extensions, shares, random_values = [], [], {
        "random": hello["random"].hex(), "session_id": hello["session_id"].hex()}
    group_grease = None
    for kind, payload in hello["extensions"]:
        reader = Reader(payload)
        if kind in (10, 13, 43):
            values = numbers(reader.vector(1 if kind == 43 else 2))
            reader.end()
            value = [identifier(item) for item in values]
            if kind == 10:
                group_grease = next((item for item in values if grease(item)), None)
        elif kind == 51:
            entries = Reader(reader.vector(2))
            reader.end()
            value = []
            while entries.position < len(entries.data):
                group, key = entries.number(2), entries.vector(2)
                shares.append((group, key))
                value.append([identifier(group), len(key), key.hex() if grease(group) else "ephemeral"])
                if not grease(group):
                    random_values[f"key_share_{group}"] = key.hex()
                    if group == 0x11EC and len(key) == 1216:
                        random_values["hybrid_mlkem_public_key"] = key[:1184].hex()
                        random_values["hybrid_x25519_public_key"] = key[1184:].hex()
            entries.end()
        elif kind == 65037:
            outer, kdf, aead, _config_id = (reader.number(1), reader.number(2),
                                          reader.number(2), reader.number(1))
            enc, ciphertext = reader.vector(2), reader.vector(2)
            reader.end()
            if len(ciphertext) not in ech_lengths:
                raise ValueError("ECH GREASE payload length is outside the pinned profile family")
            value = [outer, kdf, aead, len(enc), "pinned-random-payload-length"]
            random_values["ech_enc"] = enc.hex()
            random_values["ech_payload"] = ciphertext.hex()
        else:
            # Includes SNI, ALPN, ALPS, cert compression, SCT, tickets and all
            # unknown extensions. No fixed field is dropped from comparison.
            value = payload.hex()
        extensions.append([identifier(kind), value])
    grease_positions = [index for index, (kind, _) in enumerate(hello["extensions"]) if grease(kind)]
    share_map = dict(shares)
    independent_x25519_shares = (
        share_map[0x11EC][-32:] != share_map[0x001D]
        if 0x11EC in share_map and 0x001D in share_map else None)
    normalized = {
        "legacy_version": hello["legacy_version"], "random_length": len(hello["random"]),
        "session_id_length": len(hello["session_id"]),
        "cipher_suites": [identifier(item) for item in hello["cipher_suites"]],
        "compression": hello["compression"].hex(),
        "extensions": sorted(extensions, key=lambda item: json.dumps(item, sort_keys=True)),
        "grease_positions": grease_positions,
        "group_grease_consistent": all(group == group_grease for group, _ in shares if grease(group)),
        "hybrid_and_standalone_x25519_are_independent": independent_x25519_shares,
    }
    return normalized, random_values


def assert_compatible(actual, reference, ech_lengths):
    observed, _ = canonical(parse_hello(actual), ech_lengths)
    expected, _ = canonical(parse_hello(reference), ech_lengths)
    if observed != expected:
        differing = [key for key in expected if observed[key] != expected[key]]
        raise AssertionError("ClientHello profile differs in " + ", ".join(differing))
    return observed


class RealityFingerprintInterop(unittest.TestCase):
    sequence = 0

    @classmethod
    def setUpClass(cls):
        cls.evidence = Path(os.environ.get("SWIRL_FINGERPRINT_EVIDENCE",
                                          ROOT / "build/reality-fingerprint-evidence")).resolve()
        cls.evidence.mkdir(parents=True, exist_ok=True)
        if not os.environ.get("SWIRL_REALITY_HELLO") or not os.environ.get("SWIRL_XRAY_PEER_DIR"):
            raise RuntimeError("SWIRL_REALITY_HELLO and SWIRL_XRAY_PEER_DIR are required; this gate cannot skip")
        cls.client = Path(os.environ["SWIRL_REALITY_HELLO"]).resolve(strict=True)
        directory = Path(os.environ["SWIRL_XRAY_PEER_DIR"]).resolve(strict=True)
        suffix = ".exe" if os.name == "nt" else ""
        cls.oracle = (directory / ("utls-hello" + suffix)).resolve(strict=True)
        cls.manifest = json.loads((directory / "build-manifest.json").read_text(encoding="utf-8"))
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        lock_path = ROOT / "tools/tests/xray_peer/lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        manifest = cls.manifest
        if (manifest["status"] != "success" or manifest["swirl_source_commit"] != revision
                or os.environ.get("GITHUB_SHA", revision) != revision
                or manifest["lock_sha256"] != sha256(lock_path)
                or manifest["go_version"] != lock["go_version"]
                or manifest["xray"] != lock["xray"]):
            raise RuntimeError("The independent oracle does not belong to this verified source/Go/Xray build")
        helper = ROOT / "tools/tests/xray_peer/utls_hello/main.go"
        if manifest["utls_helper_source_sha256"] != sha256(helper):
            raise RuntimeError("uTLS oracle source changed after its verified build")
        binary = manifest["binaries"]["utls_hello"]
        repeated = manifest["reproducible_rebuild"]["utls_hello"]
        if (binary["file"] != cls.oracle.name or binary["sha256"] != sha256(cls.oracle)
                or not repeated["matches"] or repeated["first_sha256"] != binary["sha256"]
                or repeated["repeated_sha256"] != binary["sha256"]):
            raise RuntimeError("uTLS oracle executable/repeated-build identity mismatch")
        version = json.loads(subprocess.check_output([str(cls.oracle), "--version"], text=True, timeout=5))
        if (version["event"] != "version" or version["profile"] != PROFILE
                or version["go_version"] != lock["go_version"]
                or version["xray_commit"] != lock["xray"]["commit"]
                or version["utls"]["module"] != UTLS_MODULE or version["utls"]["version"] != UTLS_VERSION
                or any(version["utls"][key] != manifest["utls"][key]
                       for key in ("module", "version", "sum"))):
            raise RuntimeError("uTLS oracle runtime identity differs from the pinned upstream build")
        cls.ech_lengths = [size + 16 for size in version["ech_encoded_inner_lengths"]]
        if cls.ech_lengths != [144, 176, 208, 240]:
            raise RuntimeError("Pinned Chrome 133 ECH payload-size family changed")
        identity = {"git_sha": revision, "python": sys.version, "platform": sys.platform,
                    "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                    "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                    "client_sha256": sha256(cls.client), "oracle_sha256": sha256(cls.oracle),
                    "test_source_sha256": sha256(Path(__file__)), "oracle_version": version,
                    "build_manifest": manifest,
                    "client_source_sha256": sha256(ROOT / "core/crates/swirl-transport/examples/reality-hello.rs")}
        (cls.evidence / "source-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")

    def invoke(self, profile=None):
        type(self).sequence += 1
        binary = self.oracle if profile is None else self.client
        command = [str(binary), "--server-name", SERVER_NAME]
        if profile is not None:
            command += ["--fingerprint", profile]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        label = f"{self.sequence:03d}-{profile or 'utls'}-{time.time_ns()}"
        (self.evidence / (label + ".stdout.json")).write_text(result.stdout, encoding="utf-8")
        (self.evidence / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        raw = bytes.fromhex(data["handshake_hex"])
        parsed = parse_hello(raw)
        if "handshake_sha256" in data:
            self.assertEqual(hashlib.sha256(raw).hexdigest(), data["handshake_sha256"])
        if profile is None:
            self.assertEqual(data["profile"], PROFILE)
            self.assertEqual(data["server_name"], SERVER_NAME)
        else:
            self.assertEqual(data["fingerprint"], profile)
            record = Reader(bytes.fromhex(data["record_hex"]))
            self.assertEqual(record.number(1), 22)
            self.assertEqual(record.number(2), 0x0301)
            self.assertEqual(record.vector(2), raw)
            record.end()
        normalized, _ = canonical(parsed, self.ech_lengths)
        (self.evidence / (label + ".profile.json")).write_text(
            json.dumps({"handshake_sha256": hashlib.sha256(raw).hexdigest(),
                        "normalized": normalized,
                        "extension_order": [kind for kind, _ in parsed["extensions"]]}, indent=2) + "\n",
            encoding="utf-8")
        return raw

    def test_chrome_and_versioned_alias_match_independent_utls_wire_profile(self):
        reference = self.invoke()
        for profile in ("chrome", "chrome_133"):
            with self.subTest(profile=profile):
                assert_compatible(self.invoke(profile), reference, self.ech_lengths)

    def test_default_rustls_is_a_negative_control(self):
        with self.assertRaises(AssertionError):
            assert_compatible(self.invoke("rustls"), self.invoke(), self.ech_lengths)

    def test_each_connection_uses_fresh_randoms_keys_ech_and_extension_permutation(self):
        for profile in (None, "chrome", "chrome_133"):
            samples = [parse_hello(self.invoke(profile)) for _ in range(8)]
            expected, _ = canonical(samples[0], self.ech_lengths)
            random_samples = []
            for sample in samples:
                normalized, randoms = canonical(sample, self.ech_lengths)
                self.assertEqual(normalized, expected)
                self.assertEqual(normalized["grease_positions"], [0, len(sample["extensions"]) - 1])
                self.assertTrue(normalized["group_grease_consistent"])
                self.assertTrue(normalized["hybrid_and_standalone_x25519_are_independent"])
                self.assertEqual(sample["extensions"][0][1], b"")
                self.assertEqual(sample["extensions"][-1][1], b"\x00")
                random_samples.append(randoms)
            for field in random_samples[0]:
                self.assertEqual(len({sample[field] for sample in random_samples}), len(samples), field)
            orders = {tuple(identifier(kind) for kind, _ in sample["extensions"]) for sample in samples}
            self.assertGreater(len(orders), 1, "middle extensions must be independently shuffled")

    def test_real_wire_mutations_are_not_hidden_by_normalization(self):
        reference = self.invoke()
        for mutation in ("cipher", "cipher-order", "extension", "alpn", "groups", "signatures", "versions", "grease-position", "keyshare-reuse"):
            with self.subTest(mutation=mutation):
                hello = parse_hello(reference)
                if mutation == "cipher":
                    hello["cipher_suites"][1] ^= 1
                elif mutation == "cipher-order":
                    hello["cipher_suites"][1:3] = reversed(hello["cipher_suites"][1:3])
                elif mutation == "extension":
                    hello["extensions"] = [(kind, data) for kind, data in hello["extensions"] if kind != 18]
                elif mutation == "grease-position":
                    hello["extensions"][0], hello["extensions"][1] = hello["extensions"][1], hello["extensions"][0]
                elif mutation == "keyshare-reuse":
                    for index, (kind, data) in enumerate(hello["extensions"]):
                        if kind != 51:
                            continue
                        entries = Reader(Reader(data).vector(2))
                        shares = []
                        while entries.position < len(entries.data):
                            shares.append((entries.number(2), entries.vector(2)))
                        hybrid_x25519 = dict(shares)[0x11EC][-32:]
                        payload = b"".join(group.to_bytes(2, "big") + len(key).to_bytes(2, "big")
                                           + (hybrid_x25519 if group == 0x001D else key)
                                           for group, key in shares)
                        hello["extensions"][index] = (kind, len(payload).to_bytes(2, "big") + payload)
                else:
                    target = {"alpn": 16, "groups": 10, "signatures": 13, "versions": 43}[mutation]
                    hello["extensions"] = [(kind, data[:-1] + bytes([data[-1] ^ 1]) if kind == target else data)
                                           for kind, data in hello["extensions"]]
                with self.assertRaises(AssertionError):
                    assert_compatible(encode_hello(hello), reference, self.ech_lengths)


if __name__ == "__main__":
    program = unittest.main(verbosity=2, exit=False)
    result = program.result
    evidence = Path(os.environ.get("SWIRL_FINGERPRINT_EVIDENCE", ROOT / "build/reality-fingerprint-evidence"))
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "results.json").write_text(json.dumps({
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "successful": result.wasSuccessful(),
    }, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
