"""Run the NativeUdpFlow empty-packet regression against the pinned local peer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--cargo", type=Path, default=shutil.which("cargo"))
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--server", type=Path, default=os.environ.get("HY2_SERVER"))
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.cargo is None or arguments.server is None:
        parser.error("cargo and HY2_SERVER or --server are required")
    repository = arguments.repo.resolve(strict=True)
    cargo = arguments.cargo.resolve(strict=True)
    server = arguments.server.resolve(strict=True)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    if arguments.report.exists() or arguments.report.with_suffix(".cargo.txt").exists():
        raise RuntimeError("FreshEvidencePathRequired")
    sys.path.insert(0, str(repository / "tools" / "tests"))
    import test_hysteria2_official as reference
    import test_socks5_udp as socks5

    class LoopbackProxyPeer(reference.OfficialPeer):
        def start(self):
            config = json.loads(self.config.read_text(encoding="utf-8"))
            config["outbounds"] = [{
                "name": "loopback-udp-fixture", "type": "socks5",
                "socks5": {"addr": f"127.0.0.1:{bridge.port}"},
            }]
            self.config.write_text(json.dumps(config), encoding="utf-8")
            super().start()

    # All child processes belong to this fixture, including Cargo and the peer.
    original_popen = subprocess.Popen
    if os.name == "nt":
        def hidden_popen(*args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            return original_popen(*args, **kwargs)
        subprocess.Popen = hidden_popen

    peer_hash = hashlib.sha256(server.read_bytes()).hexdigest()
    if peer_hash not in reference.OFFICIAL_SHA256.values():
        raise RuntimeError("OfficialHysteriaServerDigestMismatch")
    version = subprocess.check_output(
        [str(server), "version"], stderr=subprocess.STDOUT, timeout=10
    ).decode("utf-8", errors="replace")
    if reference.OFFICIAL_VERSION not in version or reference.OFFICIAL_COMMIT not in version:
        raise RuntimeError("OfficialHysteriaServerVersionMismatch")
    test_name = "v2::native_flow::tests::native_hysteria2_empty_udp_error_preserves_the_authenticated_flow"
    command = [
        str(cargo), "test", "--offline", "--locked", "-p", "swirl-core", "--lib",
    ]
    if arguments.target:
        command.extend(["--target", arguments.target])
    if arguments.target_dir:
        command.extend(["--target-dir", str(arguments.target_dir)])
    command.extend([test_name, "--", "--ignored", "--exact", "--nocapture"])
    report = {
        "schema": 1,
        "test_name": test_name,
        "requires_explicit_ignored_invocation": True,
        "default_cargo_run_proves_this_test": False,
        "official_version": reference.OFFICIAL_VERSION,
        "official_commit": reference.OFFICIAL_COMMIT,
        "official_server_sha256": peer_hash,
        "source_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip(),
        "test_fixture_sha256": hashlib.sha256(
            (repository / "core/crates/swirl-core/src/native_flow_tests.rs").read_bytes()
        ).hexdigest(),
        "production_file_sha256": hashlib.sha256(
            (repository / "core/crates/swirl-core/src/native_flow.rs").read_bytes()
        ).hexdigest(),
        "cargo_command": command,
        "fixture_endpoints": "QUIC, official SOCKS5 outbound and independent UDP origin all use literal127.0.0.1; existing SOCKS5 peer maps only fixture names at its fixed origin port",
        "new_provider_or_public_requests": 0,
        "peer_cleanup_completed": False,
        "bridge_cleanup_completed": False,
        "origin_cleanup_completed": False,
    }
    origin = socks5.UdpOrigin()
    bridge = socks5.Socks5Peer(origin)
    try:
        with tempfile.TemporaryDirectory(prefix="hy2-native-", dir=arguments.report.parent) as temporary:
            directory = Path(temporary)
            cert, key, ca, _ = reference.certificate_files(directory)
            peer = LoopbackProxyPeer(
                server, directory, cert, key, "synthetic-native-empty-only", "native-empty",
                host="127.0.0.1",
            )
            try:
                fixture = directory / "fixture.json"
                fixture.write_text(json.dumps({
                    "outbound": {
                        "type": "hysteria2", "host": "127.0.0.1", "port": peer.port,
                        "password": peer.password,
                        "tls": {"server_name": "hy2.test", "alpn": ["h3"], "ca_der_base64": ca},
                        "udp": True,
                    },
                    "target_port": origin.address[1],
                    "reply_prefix": socks5.PREFIX.decode("ascii"),
                }), encoding="utf-8")
                environment = os.environ.copy()
                environment["SWIRL_NATIVE_HY2_UDP_FIXTURE"] = str(fixture)
                completed = subprocess.run(
                    command, cwd=repository / "core", env=environment,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                )
                output = completed.stdout + completed.stderr
                output_file = arguments.report.with_suffix(".cargo.txt")
                output_file.write_text(output, encoding="utf-8")
                matched = re.search(re.escape(test_name) + r"\s+\.\.\.\s+(ok|FAILED)", output)
                report.update(
                    cargo_exit_code=completed.returncode,
                    test_result=matched.group(1) if matched else "NOT_RECORDED",
                    success=completed.returncode == 0 and matched is not None and matched.group(1) == "ok",
                    cargo_output_file=output_file.name,
                    cargo_output_sha256=hashlib.sha256(output_file.read_bytes()).hexdigest(),
                )
                expected = [b"baseline", b"after-empty", b"before-empty", b"after-empty"]
                origin_matches = origin.received == expected
                report.update(
                    independent_origin_datagrams=len(origin.received),
                    independent_origin_empty_datagrams=sum(not value for value in origin.received),
                    independent_origin_payloads_match=origin_matches,
                    independent_bridge_forwarded=bridge.forwarded,
                    independent_bridge_error_count=len(bridge.errors),
                )
                report["success"] = report["success"] and origin_matches and bridge.forwarded == 4
            finally:
                peer.stop()
                report["peer_cleanup_completed"] = peer.process is None and peer.log is None
    finally:
        try:
            bridge.close()
            report["bridge_cleanup_completed"] = True
        finally:
            try:
                origin.close()
                report["origin_cleanup_completed"] = True
            finally:
                arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
