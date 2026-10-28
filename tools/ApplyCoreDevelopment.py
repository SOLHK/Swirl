"""Apply the reviewed Rust CI gates using the existing scoped GitHub App job.

The only writable file is .github/workflows/rust-core.yml. The update enables
its existing jobs on this development branch, adds the already implemented
DoH, SOCKS4, WebSocket and automatic-policy peer suites, and runs fixed public-network
checks with an evidence artifact on Linux. The current stage adds negative DNS
and isolated native-outbound probe and connection-stage regressions alongside the existing SOCKS4
and WS Qt forwarding peers. The current update includes independent connectivity
and subscription-import gates, required-binary checks, all native release bins,
and the Windows diagnostic artifact. The SOCKS5 UDP stage adds independent
portable/Windows peers, its Qt forwarding hook and the complete native application
build using the existing Qt build tree. Shared subscription import tests also
run in the sole Rust Qt build, alongside its native DNS policy tests. The removed
non-Rust configure option must fail with its specific retirement diagnostic.
Fixed Qt XML reports and the configure log preserve diagnostics after failures.
The REALITY TLS stage builds its actual Release protocol client and runs both
independent peer suites only after all four required test binaries are present.
The Vision component stage requires both independent fixture checks, in order,
with immediate Windows exit propagation, before any protocol peer can run.
The Vision stream stage then builds its Release client and runs full Xray
interoperability after the complete REALITY R3 gate, preserving both raw logs.
The product stage runs subscription-to-target peers on every Rust platform and
the persisted Qt wrapper on Windows, with Release preflights and exact-source
evidence. Its separate steps preserve every existing protocol and build gate.
It does not change permissions, secrets,
existing actions, pull-request triggers or any product source.

Run ``python tools/ApplyCoreDevelopment.py --check`` to run the safety tests and
review the exact diff without writing; it fails if a reviewed update is missing.
The App validation workflow uses this read-only mode to test the pushed commit
without automatic source changes. With no arguments, writes are restricted
to this repository's existing development workflow and push ref. The caller
already owns committing and pushing the change through its GitHub App token.
"""

import argparse
from collections.abc import Mapping
import difflib
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPOSITORY = "SOLHK/Swirl"
DEVELOPMENT_REF = "refs/heads/work/core-completion-20261017"
WORKFLOW = Path(".github/workflows/rust-core.yml")
CALLER_WORKFLOW = (
    f"{REPOSITORY}/.github/workflows/core-development.yml@{DEVELOPMENT_REF}"
)
WINDOWS_STATUS_GUARD = "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
ADDITIONAL_TESTS = (
    "test_dns_https.py",
    "test_socks4.py",
    "test_websocket_transport.py",
    "test_core_development.py",
)
POLICY_TEST = "test_policy_groups.py"
DNS_PROBE_TESTS = ("test_dns_negative.py", "test_native_probe.py", "test_connection_stages.py")
CONNECTIVITY_IMPORT_TESTS = ("test_connectivity_diagnostics.py", "test_subscription_import.py")
SOCKS5_UDP_TEST = "test_socks5_udp.py"
SOCKS5_UDP_QT_TEST = "test_socks5_udp.py Socks5UdpIntegration.test_qt_imported_socks5_udp_data_path"
REALITY_TESTS = ("test_reality_peer.py", "test_reality_tls.py")
REALITY_SOURCES = (
    Path("core/crates/swirl-transport/examples/reality-client.rs"),
    Path("tools/tests/reality_peer.py"),
)
VISION_SOURCES = (
    Path("tools/tests/generate_vision_vectors.py"),
    Path("core/crates/swirl-protocol/tests/fixtures/vision-v1.txt"),
    Path("core/crates/swirl-protocol/tests/fixtures/flow-v1.txt"),
)
XRAY_SOURCES = (
    Path("tools/Build-XrayPeer.py"),
    Path("tools/tests/test_reality_xray.py"),
    Path("tools/tests/xray_peer/main.go"),
    Path("tools/tests/xray_peer/lock.json"),
)
XRAY_GO_ACTION = "actions/setup-go@924ae3a1cded613372ab5595356fb5720e22ba16"
VISION_XRAY_SOURCES = (
    Path("core/crates/swirl-protocol/examples/vision-client.rs"),
    Path("core/crates/swirl-protocol/src/vision/stream.rs"),
    Path("core/crates/swirl-protocol/src/vision/tls.rs"),
    Path("core/crates/swirl-protocol/tests/vision_stream.rs"),
    Path("core/crates/swirl-protocol/tests/vision_tls.rs"),
    Path("tools/tests/test_vision_xray.py"),
)
VISION_BUILD_COMMAND = (
    "cargo build --manifest-path core/Cargo.toml --release --locked "
    "-p swirl-protocol --example vision-client"
)
PRODUCT_CHAIN_TEST = "test_product_subscription_chain.py"
REALITY_RUNTIME_TEST = "test_reality_runtime.py"
QT_LIFECYCLE_TEST = "test_qt_reality_lifecycle.py"
PUBLIC_REALITY_PROBE = Path("tools/Verify-PublicRealityRuntime.py")
PUBLIC_QT_PROBE = Path("tools/Verify-PublicQtReality.py")
PUBLIC_QT_TEST = "test_public_qt_reality.py"
FINGERPRINT_SOURCES = (
    Path("core/crates/swirl-transport/examples/reality-hello.rs"),
    Path("tools/tests/test_reality_fingerprint.py"),
    Path("tools/tests/xray_peer/utls_hello/main.go"),
)
FINGERPRINT_BUILD_COMMAND = (
    "cargo build --manifest-path core/Cargo.toml --release --locked "
    "-p swirl-transport --example reality-hello"
)


def reality_runtime_steps(windows: bool = False, qt: bool = False,
                          artifact_prefix: str = "Swirl", vision: bool = False,
                          fingerprint: str | None = None) -> str:
    if qt and not windows:
        raise ValueError("The actual Qt/DPAPI runtime gate is Windows-only")
    if fingerprint not in (None, "chrome"):
        raise ValueError("Only the independently verified Chrome profile is a reviewed CI gate")
    stage, suffix = ("qt" if qt else "rust"), (".exe" if windows else "")
    protocol = "REALITY + Vision" if vision else "REALITY"
    directory = "swirl-reality-vision-runtime" if vision else "swirl-reality-runtime"
    artifact = "REALITY-Vision-Runtime" if vision else "REALITY-Runtime"
    if fingerprint:
        protocol += " + Chrome133"
        directory += "-chrome133"
        artifact += "-Chrome133"
    title = (f"Qt persisted {protocol} through full Xray to HTTP and HTTPS" if qt
             else f"Production {protocol} Runtime through full Xray to HTTP and HTTPS")
    environment = (
        "          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n"
        f"          SWIRL_RUST_HARNESS: ${{{{ github.workspace }}}}/core/target/release/swirl-api{suffix}\n"
        f"          SWIRL_RUST_INSPECTOR: ${{{{ github.workspace }}}}/core/target/release/swirl-inspect{suffix}\n"
        f"          SWIRL_REALITY_RUNTIME_EVIDENCE: ${{{{ runner.temp }}}}/{directory}-{stage}\n"
    )
    if qt:
        environment += (
            "          SWIRL_RUST_QT_TESTS: ${{ github.workspace }}/build/rust-qt/Release/SwirlRustCoreTests.exe\n"
            f"          SWIRL_TEST_ROOT: ${{{{ runner.temp }}}}/{directory}-qt-tests\n"
            "          QT_FORCE_STDERR_LOGGING: '1'\n"
        )
    body = "          $ErrorActionPreference = 'Stop'\n" if windows else "          set -euo pipefail\n"
    if qt:
        body += "          New-Item -ItemType Directory -Force -Path $env:SWIRL_TEST_ROOT | Out-Null\n"
    if qt and vision and fingerprint == "chrome":
        body += f"          python tools/tests/{QT_LIFECYCLE_TEST}\n" + WINDOWS_STATUS_GUARD
    selection = ((" --qt" if qt else "") + (" --vision" if vision else "")
                 + (" --fingerprint chrome" if fingerprint else ""))
    body += f"          python tools/tests/{REALITY_RUNTIME_TEST}{selection}\n"
    if windows:
        body += WINDOWS_STATUS_GUARD
    return (
        f"      - name: {title}\n"
        "        working-directory: .\n"
        f"        shell: {'pwsh' if windows else 'bash'}\n"
        "        env:\n" + environment + "        run: |\n" + body
        + f"      - name: Preserve production {protocol} Runtime {stage} evidence\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact_prefix}-{artifact}-${{{{ runner.os }}}}-{stage}-${{{{ github.sha }}}}-${{{{ github.run_attempt }}}}\n"
        f"          path: ${{{{ runner.temp }}}}/{directory}-{stage}\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def public_reality_runtime_steps(vision: bool = False, fingerprint: str | None = None) -> str:
    """Separate required Linux public-origin evidence, never provider evidence."""
    if fingerprint not in (None, "chrome"):
        raise ValueError("Only the independently verified Chrome profile is a reviewed public gate")
    protocol = "REALITY + Vision" if vision else "REALITY"
    directory = "swirl-public-reality-vision" if vision else "swirl-public-reality"
    artifact = "Swirl-Public-REALITY-Vision" if vision else "Swirl-Public-REALITY"
    if fingerprint:
        protocol += " + Chrome133"
        directory += "-chrome133"
        artifact += "-Chrome133"
    return (
        f"      - name: Native {protocol} to independent public HTTP and HTTPS\n"
        "        if: runner.os == 'Linux'\n"
        "        working-directory: .\n"
        "        shell: bash\n"
        "        env:\n"
        "          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n"
        f"          SWIRL_PUBLIC_REALITY_OUTPUT: ${{{{ runner.temp }}}}/{directory}/report.json\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        f"          python {PUBLIC_REALITY_PROBE.as_posix()} --harness core/target/release/swirl-api "
        "--inspector core/target/release/swirl-inspect "
        '--xray-peer-dir "$SWIRL_XRAY_PEER_DIR" --output "$SWIRL_PUBLIC_REALITY_OUTPUT"'
        + (" --vision" if vision else "")
        + (" --fingerprint chrome" if fingerprint else "") + "\n"
        + f"      - name: Preserve public {protocol} Runtime evidence\n"
        "        if: always() && runner.os == 'Linux'\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact}-${{{{ github.sha }}}}-${{{{ github.run_attempt }}}}\n"
        f"          path: ${{{{ runner.temp }}}}/{directory}\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def without_public_reality_runtime_steps(source: str) -> str:
    source = without_fingerprint_steps(source)
    markers = (PUBLIC_REALITY_PROBE.as_posix(), "SWIRL_PUBLIC_REALITY_", "swirl-public-reality",
               "Swirl-Public-REALITY", "Preserve public REALITY")
    if not any(marker in source for marker in markers):
        return source
    complete = public_reality_runtime_steps() + public_reality_runtime_steps(vision=True)
    parts = source.split("  windows-rust:\n")
    if (len(parts) != 2 or parts[0].count(reality_runtime_steps(vision=True) + complete) != 1
            or any(marker in parts[1] for marker in markers)):
        raise ValueError("Public REALITY/Vision gates must both follow Linux controlled Runtime verification")
    source = source.replace(complete, "", 1)
    if any(marker in source for marker in markers):
        raise ValueError("Public REALITY/Vision gates are partial, duplicated or changed")
    return source


def without_reality_runtime_steps(source: str) -> str:
    source = without_public_reality_runtime_steps(source)
    blocks = (reality_runtime_steps(), reality_runtime_steps(windows=True),
              reality_runtime_steps(windows=True, qt=True))
    vision_blocks = (reality_runtime_steps(vision=True), reality_runtime_steps(windows=True, vision=True),
                     reality_runtime_steps(windows=True, qt=True, vision=True))
    vision_markers = ("swirl-reality-vision-runtime-", "REALITY-Vision-Runtime-",
                      "Preserve production REALITY + Vision Runtime",
                      "Production REALITY + Vision Runtime", "Qt persisted REALITY + Vision",
                      REALITY_RUNTIME_TEST + " --vision", REALITY_RUNTIME_TEST + " --qt --vision")
    markers = (REALITY_RUNTIME_TEST, "SWIRL_REALITY_RUNTIME_", "swirl-reality-runtime-",
               "Preserve production REALITY Runtime", "REALITY-Runtime-", *vision_markers)
    if not any(marker in source for marker in markers):
        return source
    if any(source.count(block) != 1 for block in blocks):
        raise ValueError("Production REALITY Runtime gate is partial, duplicated or changed")
    with_vision = any(marker in source for marker in vision_markers)
    if with_vision and any(source.count(base + vision) != 1 for base, vision in zip(blocks, vision_blocks)):
        raise ValueError("Production REALITY + Vision Runtime must follow every intact REALITY gate")
    parts = source.split("  windows-rust:\n")
    if len(parts) != 2 or parts[0].count(blocks[0]) != 1:
        raise ValueError("Production REALITY Runtime job boundary changed")
    if any(parts[1].count(block) != 1 for block in blocks[1:]):
        raise ValueError("Production REALITY Runtime Windows/Qt gate moved")
    for index, block in enumerate(blocks):
        source = source.replace(block + (vision_blocks[index] if with_vision else ""), "", 1)
    if any(marker in source for marker in markers):
        raise ValueError("Production REALITY Runtime has an unreviewed extra command")
    return source


def _add_reality_runtime_steps(source: str) -> str:
    for windows in (False, True):
        anchor = vision_xray_steps(windows=windows)
        if source.count(anchor) != 1:
            raise ValueError("Production REALITY Runtime requires the fixed upstream peer stages")
        public = "" if windows else public_reality_runtime_steps() + public_reality_runtime_steps(vision=True)
        source = source.replace(anchor, anchor + reality_runtime_steps(windows=windows)
                                + reality_runtime_steps(windows=windows, vision=True) + public, 1)
    if source.count(NATIVE_APPLICATION_BUILD) != 1:
        raise ValueError("Production REALITY Qt gate requires the full native application build")
    return source.replace(NATIVE_APPLICATION_BUILD,
                          reality_runtime_steps(windows=True, qt=True)
                          + reality_runtime_steps(windows=True, qt=True, vision=True)
                          + NATIVE_APPLICATION_BUILD, 1)


def fingerprint_steps(windows: bool = False, artifact_prefix: str = "Swirl") -> str:
    """Compare actual native wire bytes against the unchanged pinned uTLS build."""
    suffix = ".exe" if windows else ""
    status = WINDOWS_STATUS_GUARD if windows else ""
    if windows:
        start = (
            "          $ErrorActionPreference = 'Stop'\n"
            "          New-Item -ItemType Directory -Force -Path $env:SWIRL_FINGERPRINT_EVIDENCE | Out-Null\n"
        )
        log = '2>&1 | Tee-Object -FilePath "$env:SWIRL_FINGERPRINT_EVIDENCE/{}"\n'
        preflight = (
            "          if (-not (Test-Path $env:SWIRL_REALITY_HELLO -PathType Leaf)) "
            "{ throw 'Required native ClientHello Release binary missing' }\n"
            "          if (-not (Test-Path (Join-Path $env:SWIRL_XRAY_PEER_DIR 'utls-hello.exe') -PathType Leaf)) "
            "{ throw 'Required pinned uTLS oracle missing' }\n"
        )
    else:
        start = '          set -euo pipefail\n          mkdir -p "$SWIRL_FINGERPRINT_EVIDENCE"\n'
        log = '2>&1 | tee "$SWIRL_FINGERPRINT_EVIDENCE/{}"\n'
        preflight = ('          test -x "$SWIRL_REALITY_HELLO"\n'
                     '          test -x "$SWIRL_XRAY_PEER_DIR/utls-hello"\n')
    return (
        "      - name: Build native ClientHello and verify independent Chrome133 fingerprint\n"
        "        working-directory: .\n"
        f"        shell: {'pwsh' if windows else 'bash'}\n"
        "        env:\n"
        "          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n"
        "          SWIRL_FINGERPRINT_EVIDENCE: ${{ runner.temp }}/swirl-fingerprint-results\n"
        f"          SWIRL_REALITY_HELLO: ${{{{ github.workspace }}}}/core/target/release/examples/reality-hello{suffix}\n"
        "        run: |\n"
        + start + f"          {FINGERPRINT_BUILD_COMMAND} " + log.format("client-build.log") + status
        + preflight
        + "          python tools/tests/test_reality_fingerprint.py " + log.format("oracle-test.log") + status
        + "      - name: Preserve raw ClientHello and independent uTLS fingerprint evidence\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact_prefix}-Chrome133-Fingerprint-${{{{ runner.os }}}}-${{{{ github.sha }}}}-${{{{ github.run_attempt }}}}\n"
        "          path: |\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build.log\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build-manifest.json\n"
        "            ${{ runner.temp }}/swirl-fingerprint-results\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def _fingerprint_insertions(windows: bool) -> tuple[tuple[str, str], ...]:
    oracle = (vision_xray_steps(windows=windows), fingerprint_steps(windows=windows))
    runtime_anchor = reality_runtime_steps(windows=windows, vision=True)
    runtime = (reality_runtime_steps(windows=windows, fingerprint="chrome")
               + reality_runtime_steps(windows=windows, vision=True, fingerprint="chrome"))
    if windows:
        qt = (reality_runtime_steps(windows=True, qt=True, vision=True),
              reality_runtime_steps(windows=True, qt=True, vision=True, fingerprint="chrome"))
        return oracle, (runtime_anchor, runtime), qt
    runtime_anchor += public_reality_runtime_steps() + public_reality_runtime_steps(vision=True)
    runtime += (public_reality_runtime_steps(fingerprint="chrome")
                + public_reality_runtime_steps(vision=True, fingerprint="chrome"))
    return oracle, (runtime_anchor, runtime)


def public_qt_steps() -> str:
    """The Windows product, not an isolated Runtime, owns every public request."""
    return """      - name: Windows Qt Chrome133 Vision product to public HTTP and HTTPS
        working-directory: .
        shell: pwsh
        env:
          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer
          SWIRL_RUST_HARNESS: ${{ github.workspace }}/core/target/release/swirl-api.exe
          SWIRL_RUST_INSPECTOR: ${{ github.workspace }}/core/target/release/swirl-inspect.exe
          SWIRL_RUST_QT_TESTS: ${{ github.workspace }}/build/rust-qt/Release/SwirlRustCoreTests.exe
          SWIRL_QT_PRIVATE_INSPECTOR: ${{ github.workspace }}/build/rust-qt/Release/SwirlPrivateSubscriptionInspect.exe
          SWIRL_TEST_ROOT: ${{ runner.temp }}/swirl-public-qt-tests
          QT_FORCE_STDERR_LOGGING: '1'
        run: |
          $ErrorActionPreference = 'Stop'
          New-Item -ItemType Directory -Force -Path $env:SWIRL_TEST_ROOT | Out-Null
          if (-not $IsWindows -or [string]::IsNullOrWhiteSpace($env:SWIRL_QT_PRIVATE_INSPECTOR) -or -not (Test-Path -LiteralPath $env:SWIRL_QT_PRIVATE_INSPECTOR -PathType Leaf)) { throw "Required Windows Qt DPAPI inspector is missing" }
          windeployqt --release "$env:SWIRL_QT_PRIVATE_INSPECTOR"
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python -m unittest tools.tests.test_subscription_capture.CaptureTests.test_qt_offline_inspector_reloads_and_redacts_actual_dpapi -v
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python tools/tests/test_public_qt_reality.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python tools/Verify-PublicQtReality.py --qt-tests "$env:SWIRL_RUST_QT_TESTS" --xray-peer-dir "$env:SWIRL_XRAY_PEER_DIR" --output "$env:RUNNER_TEMP/swirl-public-qt/report.json"
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
      - name: Preserve Windows Qt authenticated public exit evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: Swirl-Public-Qt-Chrome133-Vision-${{ github.sha }}-${{ github.run_attempt }}
          path: ${{ runner.temp }}/swirl-public-qt
          if-no-files-found: error
          retention-days: 14
"""


def without_public_qt_steps(source: str) -> str:
    markers = (PUBLIC_QT_PROBE.name, PUBLIC_QT_TEST, "swirl-public-qt", "Swirl-Public-Qt-")
    if not any(marker in source for marker in markers):
        return source
    parts = source.split("  windows-rust:\n")
    block = public_qt_steps()
    anchor = reality_runtime_steps(windows=True, qt=True, vision=True, fingerprint="chrome")
    if (len(parts) != 2 or any(marker in parts[0] for marker in markers)
            or parts[1].count(anchor + block + NATIVE_APPLICATION_BUILD) != 1):
        raise ValueError("Windows Qt public gate is incomplete, moved or weakened; review required")
    parts[1] = parts[1].replace(block, "", 1)
    if any(marker in parts[1] for marker in markers):
        raise ValueError("Windows Qt public gate contains duplicated or unreviewed commands")
    return "  windows-rust:\n".join(parts)


def _add_public_qt_steps(source: str) -> str:
    anchor = reality_runtime_steps(windows=True, qt=True, vision=True, fingerprint="chrome")
    if source.count(anchor + NATIVE_APPLICATION_BUILD) != 1:
        raise ValueError("Windows Qt public gate requires complete controlled Qt and application gates")
    return source.replace(anchor + NATIVE_APPLICATION_BUILD,
                          anchor + public_qt_steps() + NATIVE_APPLICATION_BUILD, 1)


def without_fingerprint_steps(source: str) -> str:
    """Allow an intact prior stage or the complete native/browser evidence stage."""
    source = without_public_qt_steps(source)
    markers = ("reality-hello", "utls-hello", "test_reality_fingerprint.py", "SWIRL_FINGERPRINT_",
               "swirl-fingerprint-results", "--fingerprint", "Chrome133")
    if not any(marker in source for marker in markers):
        return source
    parts = source.split("  windows-rust:\n")
    if len(parts) != 2:
        raise ValueError("Fingerprint gate job boundaries changed")
    for index, part in enumerate(parts):
        for anchor, block in _fingerprint_insertions(windows=bool(index)):
            if part.count(block) != 1 or part.count(anchor + block) != 1:
                raise ValueError("Native fingerprint oracle, runtime or public gate drifted; review required")
            part = part.replace(block, "", 1)
        if any(marker in part for marker in markers):
            raise ValueError("Native fingerprint stage is partial, duplicated or contains an unreviewed command")
        parts[index] = part
    return "  windows-rust:\n".join(parts)


def _add_fingerprint_steps(source: str) -> str:
    parts = source.split("  windows-rust:\n")
    if len(parts) != 2:
        raise ValueError("Fingerprint gate job boundaries changed")
    for index, part in enumerate(parts):
        for anchor, block in _fingerprint_insertions(windows=bool(index)):
            if part.count(anchor) != 1:
                raise ValueError("Fingerprint gates require the intact existing Xray and Runtime stages")
            part = part.replace(anchor, anchor + block, 1)
        parts[index] = part
    return "  windows-rust:\n".join(parts)


def product_chain_steps(windows: bool = False, qt: bool = False,
                        artifact_prefix: str = "Swirl") -> str:
    """Run the same committed subscription suite with exact Release identities."""
    if qt and not windows:
        raise ValueError("The product Qt wrapper is a Windows-only gate")
    stage = "qt" if qt else "rust"
    suffix = ".exe" if windows else ""
    title = ("Subscription through persisted Qt product configuration" if qt
             else "Subscription to native proxy and target")
    names = ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR")
    environment = (
        f"          SWIRL_RUST_HARNESS: ${{{{ github.workspace }}}}/core/target/release/swirl-api{suffix}\n"
        f"          SWIRL_RUST_INSPECTOR: ${{{{ github.workspace }}}}/core/target/release/swirl-inspect{suffix}\n"
        f"          SWIRL_PRODUCT_EVIDENCE: ${{{{ runner.temp }}}}/swirl-product-chain-{stage}\n"
    )
    if qt:
        names += ("SWIRL_RUST_QT_TESTS",)
        environment += (
            "          SWIRL_RUST_QT_TESTS: ${{ github.workspace }}/build/rust-qt/Release/SwirlRustCoreTests.exe\n"
            "          SWIRL_TEST_ROOT: ${{ runner.temp }}/swirl-product-qt-tests\n"
            "          QT_FORCE_STDERR_LOGGING: '1'\n"
        )
    if windows:
        body = "          $ErrorActionPreference = 'Stop'\n"
        body += "".join(
            f"          if (-not (Test-Path $env:{name} -PathType Leaf)) "
            "{ throw 'Required product chain binary missing' }\n" for name in names)
        if qt:
            body += ("          New-Item -ItemType Directory -Force "
                     "-Path $env:SWIRL_TEST_ROOT | Out-Null\n")
    else:
        body = "          set -euo pipefail\n"
        body += "".join(f'          test -x "${name}"\n' for name in names)
    selection = " ProductQtIntegration" if qt else ""
    body += f"          python tools/tests/{PRODUCT_CHAIN_TEST}{selection} -v\n"
    if windows:
        body += WINDOWS_STATUS_GUARD
    return (
        f"      - name: {title}\n"
        "        working-directory: .\n"
        f"        shell: {'pwsh' if windows else 'bash'}\n"
        "        env:\n" + environment + "        run: |\n" + body
        + f"      - name: Preserve subscription product {stage} evidence\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact_prefix}-Product-Chain-${{{{ runner.os }}}}-{stage}-"
        "${{ github.sha }}-${{ github.run_attempt }}\n"
        f"          path: ${{{{ runner.temp }}}}/swirl-product-chain-{stage}\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def without_product_chain_steps(source: str) -> str:
    """Accept a complete prior stage or all three exact product gates."""
    markers = (PRODUCT_CHAIN_TEST, "SWIRL_PRODUCT_EVIDENCE", "Product-Chain-",
               "Subscription to native proxy", "Subscription through persisted Qt")
    if not any(marker in source for marker in markers):
        return source
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI product job boundaries drifted; review required")
    parts = source.split(separator)
    for index, part in enumerate(parts):
        blocks = [product_chain_steps(windows=bool(index))]
        if index:
            blocks.append(product_chain_steps(windows=True, qt=True))
        for block in blocks:
            if part.count(block) != 1:
                raise ValueError("Rust CI product test/binary/evidence gate drifted; review required")
            part = part.replace(block, "", 1)
        if any(marker in part for marker in markers):
            raise ValueError("Rust CI product stage is partial or duplicated; review required")
        parts[index] = part
    return separator.join(parts)


def _add_product_chain_steps(source: str) -> str:
    separator = "  windows-rust:\n"
    parts = source.split(separator)
    for index, part in enumerate(parts):
        anchor = xray_steps(windows=bool(index))
        if part.count(anchor) != 1:
            raise ValueError("Rust CI product peer boundary drifted; review required")
        part = part.replace(anchor, product_chain_steps(windows=bool(index)) + anchor, 1)
        if index:
            if part.count(NATIVE_APPLICATION_BUILD) != 1:
                raise ValueError("Rust CI product Qt boundary drifted; review required")
            part = part.replace(NATIVE_APPLICATION_BUILD,
                                product_chain_steps(windows=True, qt=True) + NATIVE_APPLICATION_BUILD, 1)
        parts[index] = part
    return separator.join(parts)


def xray_steps(windows: bool = False, artifact_prefix: str = "Swirl-REALITY-Xray") -> str:
    """One reviewed build/test/evidence unit; the Go peer is test-only."""
    suffix = ".exe" if windows else ""
    shell = "pwsh" if windows else "bash"
    build = ('          python tools/Build-XrayPeer.py --output "$env:SWIRL_XRAY_PEER_DIR"\n'
             if windows else '          python tools/Build-XrayPeer.py --output "$SWIRL_XRAY_PEER_DIR"\n')
    status = WINDOWS_STATUS_GUARD if windows else ""
    start = "" if windows else "          set -euo pipefail\n"
    return (
        "      - name: Install pinned Go for the independent Xray peer\n"
        f"        uses: {XRAY_GO_ACTION}\n"
        "        with:\n"
        "          go-version: '1.27.2'\n"
        "          cache: false\n"
        "      - name: Build pinned Xray and verify REALITY interoperability\n"
        "        working-directory: .\n"
        f"        shell: {shell}\n"
        "        env:\n"
        "          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n"
        "          SWIRL_XRAY_EVIDENCE: ${{ runner.temp }}/swirl-xray-results\n"
        f"          SWIRL_REALITY_CLIENT: ${{{{ github.workspace }}}}/core/target/release/examples/reality-client{suffix}\n"
        "        run: |\n"
        + start + build + status
        + "          python tools/tests/test_reality_xray.py\n" + status
        + "      - name: Preserve Xray build identity and raw interoperability evidence\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact_prefix}-${{{{ runner.os }}}}-${{{{ github.sha }}}}-${{{{ github.run_attempt }}}}\n"
        "          path: |\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build.log\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build-manifest.json\n"
        "            ${{ runner.temp }}/swirl-xray-results\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def without_xray_steps(source: str) -> str:
    """Accept a complete prior stage or both exact R3 blocks, never a partial gate."""
    blocks = (xray_steps(), xray_steps(windows=True))
    markers = ("Build-XrayPeer.py", "test_reality_xray.py", "swirl-xray-",
               "Install pinned Go", "Preserve Xray build", "Swirl-REALITY-Xray")
    if not any(marker in source for marker in markers):
        return source
    if any(source.count(block) != 1 for block in blocks):
        raise ValueError("Rust CI Xray build, test or evidence gate drifted; review required")
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI Xray job boundaries drifted; review required")
    parts = source.split(separator)
    for index, block in enumerate(blocks):
        if parts[index].count(block) != 1:
            raise ValueError("Rust CI Xray gate is in the wrong platform job")
        parts[index] = parts[index].replace(block, "", 1)
    stripped = separator.join(parts)
    if any(marker in stripped for marker in markers):
        raise ValueError("Rust CI has duplicated or unreviewed Xray commands")
    return stripped


def _add_xray_steps(source: str) -> str:
    portable = "      - name: Native public HTTPS and DoH verification\n"
    windows = ("      - uses: actions/upload-artifact@v4\n"
               "        with:\n"
               "          name: Swirl-Rust-Core-Windows\n")
    for anchor, block in ((portable, xray_steps()), (windows, xray_steps(windows=True))):
        if source.count(anchor) != 1:
            raise ValueError("Rust CI Xray insertion boundary drifted; review required")
        source = source.replace(anchor, block + anchor, 1)
    return source


def vision_xray_steps(windows: bool = False, artifact_prefix: str = "Swirl-Vision-Xray") -> str:
    """Release build, full Xray peer and evidence are one mandatory gate."""
    suffix = ".exe" if windows else ""
    shell = "pwsh" if windows else "bash"
    status = WINDOWS_STATUS_GUARD if windows else ""
    if windows:
        start = (
            "          $ErrorActionPreference = 'Stop'\n"
            "          New-Item -ItemType Directory -Force -Path $env:SWIRL_VISION_EVIDENCE | Out-Null\n"
        )
        log = '2>&1 | Tee-Object -FilePath "$env:SWIRL_VISION_EVIDENCE/{}"\n'
        preflight = (
            "          if (-not (Test-Path $env:SWIRL_VISION_CLIENT -PathType Leaf)) "
            "{ throw 'Required Vision Release client missing' }\n"
        )
    else:
        start = '          set -euo pipefail\n          mkdir -p "$SWIRL_VISION_EVIDENCE"\n'
        log = '2>&1 | tee "$SWIRL_VISION_EVIDENCE/{}"\n'
        preflight = '          test -x "$SWIRL_VISION_CLIENT"\n'
    return (
        "      - name: Build native Vision client and verify Xray interoperability\n"
        "        working-directory: .\n"
        f"        shell: {shell}\n"
        "        env:\n"
        "          SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n"
        "          SWIRL_VISION_EVIDENCE: ${{ runner.temp }}/swirl-vision-results\n"
        f"          SWIRL_VISION_CLIENT: ${{{{ github.workspace }}}}/core/target/release/examples/vision-client{suffix}\n"
        "        run: |\n"
        + start + f"          {VISION_BUILD_COMMAND} " + log.format("client-build.log") + status
        + preflight
        + "          python tools/tests/test_vision_xray.py " + log.format("peer-test.log") + status
        + "      - name: Preserve Vision client and full Xray interoperability evidence\n"
        "        if: always()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: {artifact_prefix}-${{{{ runner.os }}}}-${{{{ github.sha }}}}-${{{{ github.run_attempt }}}}\n"
        "          path: |\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build.log\n"
        "            ${{ runner.temp }}/swirl-xray-peer/build-manifest.json\n"
        "            ${{ runner.temp }}/swirl-vision-results\n"
        "          if-no-files-found: error\n"
        "          retention-days: 14\n"
    )


def without_vision_xray_steps(source: str) -> str:
    # Strip the later complete runtime stage before reconstructing historical
    # component-stage workflows; incomplete runtime gates are still rejected.
    source = without_reality_runtime_steps(source)
    """Accept the prior R3 stage or both exact, correctly placed Vision gates."""
    blocks = (vision_xray_steps(), vision_xray_steps(windows=True))
    markers = ("vision-client", "test_vision_xray.py", "SWIRL_VISION_", "swirl-vision-",
               "Build native Vision client", "Preserve Vision client", "Swirl-Vision-Xray")
    if not any(marker in source for marker in markers):
        return source
    if any(source.count(block) != 1 for block in blocks):
        raise ValueError("Rust CI Vision build, test or evidence gate drifted; review required")
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI Vision job boundaries drifted; review required")
    parts = source.split(separator)
    for index, block in enumerate(blocks):
        # This stage consumes the independently verified R3 peer. It cannot
        # move before the build, enter another platform, or bypass a R3 failure.
        if parts[index].count(xray_steps(windows=index == 1) + block) != 1:
            raise ValueError("Rust CI Vision gate must follow the complete platform R3 gate")
        parts[index] = parts[index].replace(block, "", 1)
    stripped = separator.join(parts)
    if any(marker in stripped for marker in markers):
        raise ValueError("Rust CI has duplicated or unreviewed Vision commands")
    return stripped


def _add_vision_xray_steps(source: str) -> str:
    for windows in (False, True):
        anchor = xray_steps(windows=windows)
        if source.count(anchor) != 1:
            raise ValueError("Rust CI Vision insertion boundary drifted; review required")
        source = source.replace(anchor, anchor + vision_xray_steps(windows=windows), 1)
    return source


REALITY_BUILD_COMMAND = "cargo build --release --locked -p swirl-transport --example reality-client"
PORTABLE_REALITY_BUILD = f"      - run: {REALITY_BUILD_COMMAND}\n"
WINDOWS_REALITY_BUILD = (
    "      - name: Build native REALITY TLS peer client\n"
    "        shell: pwsh\n"
    "        run: |\n"
    f"          {REALITY_BUILD_COMMAND}\n"
    + WINDOWS_STATUS_GUARD
)
PORTABLE_REALITY_ENV = '          export SWIRL_REALITY_CLIENT="$PWD/target/release/examples/reality-client"\n'
WINDOWS_REALITY_ENV = "          $env:SWIRL_REALITY_CLIENT=(Resolve-Path target/release/examples/reality-client.exe).Path\n"
PORTABLE_REALITY_CHECK = '          test -x "$SWIRL_REALITY_CLIENT"\n'
WINDOWS_REALITY_CHECK = "          if (-not (Test-Path $env:SWIRL_REALITY_CLIENT -PathType Leaf)) { throw 'Required Rust test binary missing' }\n"
PREVIOUS_RELEASE_BUILD = "      - run: cargo build --release --locked -p swirl-api\n"
RELEASE_BUILD = "      - run: cargo build --release --locked --workspace --lib --bins\n"
PORTABLE_DIAGNOSTIC = '          export SWIRL_RUST_DIAGNOSTIC="$PWD/target/release/swirl-diagnose"\n'
WINDOWS_DIAGNOSTIC = "          $env:SWIRL_RUST_DIAGNOSTIC=(Resolve-Path target/release/swirl-diagnose.exe).Path\n"
DIAGNOSTIC_ARTIFACT = "            core/target/release/swirl-diagnose.exe\n"
DIAGNOSTIC_TOOL = Path("tools/Diagnose-NativeConnectivity.py")
DIAGNOSTIC_SOURCE = Path("core/crates/swirl-api/src/bin/swirl-diagnose.rs")
QT_PEER_TESTS = (
    "test_socks4.py Socks4Integration.test_qt_imported_socks4_and_4a_data_path",
    "test_websocket_transport.py WebSocketTransportTests.test_qt_vless_websocket_data_path",
)
PUBLIC_PROBE = Path("tools/Verify-PublicRustCore.py")
PUBLIC_VALIDATION_STEPS = """      - name: Native public HTTPS and DoH verification
        if: runner.os == 'Linux'
        run: python ../tools/Verify-PublicRustCore.py --harness target/release/swirl-api --output ../CORE_PUBLIC_NETWORK.json
      - name: Preserve public network evidence
        if: always() && runner.os == 'Linux'
        uses: actions/upload-artifact@v4
        with:
          name: Swirl-Core-Public-Network
          path: CORE_PUBLIC_NETWORK.json
          retention-days: 7
"""
NATIVE_APPLICATION_BUILD = """      - name: Build complete native Rust application
        working-directory: .
        run: |
          cmake --build build/rust-qt --config Release --target Swirl --parallel 2
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          if (-not (Test-Path build/rust-qt/Release/Swirl.exe -PathType Leaf)) { throw 'Native Swirl executable missing after build' }
"""
QT_TEST_ARTIFACT = """      - name: Preserve isolated Qt test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: Swirl-Rust-Qt-Tests-${{ github.sha }}-${{ github.run_attempt }}
          path: |
            build/rust-qt/swirl-rust-qt-integration.xml
            build/rust-qt/swirl-import-boundaries.xml
            build/removed-runtime/rejection.log
          if-no-files-found: warn
          retention-days: 7
"""
PREVIOUS_NATIVE_QT_REPORT = """          ctest --test-dir build/rust-qt -C Release -R '^swirl-(rust-qt-integration|storage-paths|import-boundaries)$' --output-on-failure
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
"""
DIAGNOSTIC_NATIVE_QT_REPORT = """          ctest --test-dir build/rust-qt -C Release -R '^swirl-(rust-qt-integration|storage-paths|import-boundaries)$' --output-on-failure
          $nativeQtExit = $LASTEXITCODE
          $nativeQtReport = 'build/rust-qt/swirl-rust-qt-integration.xml'
          if (-not (Test-Path $nativeQtReport -PathType Leaf)) { throw 'Required native Qt XML report missing' }
          Get-Content -LiteralPath $nativeQtReport
          if ($nativeQtExit -ne 0) { exit $nativeQtExit }
"""
NATIVE_QT_REPORT = """          ctest --test-dir build/rust-qt -C Release -R '^swirl-(rust-qt-integration|storage-paths|import-boundaries)$' --output-on-failure -V
          $nativeQtExit = $LASTEXITCODE
          foreach ($nativeQtReport in @(
            'build/rust-qt/swirl-rust-qt-integration.xml',
            'build/rust-qt/swirl-import-boundaries.xml'
          )) {
            if (-not (Test-Path $nativeQtReport -PathType Leaf)) { throw 'Required native Qt XML report missing' }
            Get-Content -LiteralPath $nativeQtReport
          }
          if ($nativeQtExit -ne 0) { exit $nativeQtExit }
"""
# Input-only migration fixture: the former external-runtime build must never be emitted.
HISTORICAL_COMPATIBILITY_GATE = """      - name: Reject native DNS policy in compatibility builds without starting a core
        working-directory: .
        run: |
          cmake -S src/Swirl.Quick -B build/compat-dns -G "Visual Studio 17 2022" -A x64 -DSWIRL_USE_RUST_CORE=OFF -DSWIRL_BUILD_UI_TESTS=ON
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          cmake --build build/compat-dns --config Release --target SwirlEngineTests --parallel
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          windeployqt --release build/compat-dns/Release/SwirlEngineTests.exe
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          $env:SWIRL_TEST_ROOT=Join-Path $env:RUNNER_TEMP 'swirl-compat-dns-tests'
          New-Item -ItemType Directory -Force -Path $env:SWIRL_TEST_ROOT | Out-Null
          ctest --test-dir build/compat-dns -C Release -R '^swirl-native-dns-compatibility-guard$' --output-on-failure
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
"""
REMOVED_RUNTIME_GATE = """      - name: Reject the removed runtime build option
        working-directory: .
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Force -Path build/removed-runtime | Out-Null
          cmake -S src/Swirl.Quick -B build/removed-runtime -G "Visual Studio 17 2022" -A x64 -DSWIRL_USE_RUST_CORE=OFF 2>&1 | Tee-Object -FilePath build/removed-runtime/rejection.log
          $runtimeConfigureExit = $LASTEXITCODE
          if ($runtimeConfigureExit -eq 0) { throw 'Removed runtime option was accepted.' }
          if (-not (Select-String -LiteralPath build/removed-runtime/rejection.log -Pattern 'SWIRL_USE_RUST_CORE=OFF is no longer supported' -SimpleMatch -Quiet)) { throw 'Configure failed before the Rust-only runtime guard.' }
          exit 0
"""


def _replace_checked(source: str, before: str, after: str, label: str,
                     intermediate: str | None = None) -> str:
    """Accept only an exact reviewed historical or final block, once."""
    historical = (before,) if intermediate is None else (before, intermediate)
    previous = sum(source.count(block) for block in historical)
    updated = source.count(after)
    if previous == 1 and updated == 0:
        original = next(block for block in historical if source.count(block) == 1)
        return source.replace(original, after, 1)
    if previous == 0 and updated == 1:
        return source
    raise ValueError(f"Rust CI {label} has drifted or is ambiguous; review required")


def _previous_workflow(source: str) -> str:
    """Return a bounded, idempotent update; validate all blocks before any write."""
    stage_counts = (
        source.count(f"          python ../tools/tests/{POLICY_TEST}\n"),
        source.count('          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n'),
        *(source.count(f"          python tools/tests/{test}\n") for test in QT_PEER_TESTS),
    )
    if stage_counts not in ((0, 0, 0, 0), (2, 1, 1, 1)):
        raise ValueError("Rust CI policy/Qt stage is only partially present; review required")
    current_branch_list = (
        "  push:\n    branches: [test, main, work/core-completion-20261017, "
        "work/core-rule-routing-20261021]\n"
    )
    network_fixes_branch_list = (
        "  push:\n    branches: [test, main, work/core-completion-20261017, "
        "work/core-rule-routing-20261021, work/rust-core-network-fixes-20261021]\n"
    )
    xray_branch_list = network_fixes_branch_list.replace(
        "]\n", ", work/xray-v2ray-json-import-20261021]\n"
    )
    if (source.count(current_branch_list) + source.count(network_fixes_branch_list)
            + source.count(xray_branch_list)) == 1:
        if source.count("  push:\n") != 1:
            raise ValueError("Rust CI push branch list has drifted or is ambiguous; review required")
    else:
        source = _replace_checked(
            source,
            "  push:\n    branches: [test, main]\n",
            "  push:\n    branches: [test, main, work/core-completion-20261017]\n",
            "push branch list",
        )
    anchor = "          python ../tools/tests/test_dns_tls.py\n"
    portable_tail = "  windows-rust:\n"
    portable_tests = "".join(
        f"          python ../tools/tests/{name}\n" for name in ADDITIONAL_TESTS
    )
    source = _replace_checked(
        source,
        anchor + portable_tail,
        anchor + portable_tests + f"          python ../tools/tests/{POLICY_TEST}\n" + PUBLIC_VALIDATION_STEPS + portable_tail,
        "portable peer menu",
        intermediate=anchor + portable_tests + PUBLIC_VALIDATION_STEPS + portable_tail,
    )
    windows_tail = "          python ../tools/tests/test_subscription_capture.py\n"
    windows_tests = "".join(
        f"          python ../tools/tests/{name}\n" + WINDOWS_STATUS_GUARD
        for name in ADDITIONAL_TESTS
    )
    source = _replace_checked(
        source,
        anchor + WINDOWS_STATUS_GUARD + windows_tail,
        anchor + WINDOWS_STATUS_GUARD + windows_tests + f"          python ../tools/tests/{POLICY_TEST}\n" + WINDOWS_STATUS_GUARD + windows_tail,
        "Windows peer menu",
        intermediate=anchor + WINDOWS_STATUS_GUARD + windows_tests + windows_tail,
    )
    portable_environment = '          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"\n'
    first_test = '          python ../tools/tests/test_rust_core.py\n'
    source = _replace_checked(
        source,
        portable_environment + first_test,
        portable_environment + '          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n' + first_test,
        "portable inspector identity",
    )
    # The currently reviewed workflow ends with this exact Qt command. Requiring
    # the entire tail prevents partially added/duplicated commands being accepted.
    qt_anchor = "          python tools/tests/test_rust_core.py RustCoreIntegration.test_vless_qt_data_path\n"
    qt_after = qt_anchor + WINDOWS_STATUS_GUARD + "".join(
        f"          python tools/tests/{test}\n" + WINDOWS_STATUS_GUARD for test in QT_PEER_TESTS
    )
    if source.count(qt_anchor) != 1:
        raise ValueError("Rust CI Qt peer menu has drifted or is ambiguous; review required")
    if source.endswith(qt_after):
        return source
    if source.endswith(qt_anchor):
        return source[:-len(qt_anchor)] + qt_after
    raise ValueError("Rust CI Qt peer menu has drifted or is ambiguous; review required")


def _connection_workflow(source: str) -> str:
    """Extend only the two reviewed test menus; reject partial/duplicate additions."""
    policy = f"          python ../tools/tests/{POLICY_TEST}\n"
    portable = policy + PUBLIC_VALIDATION_STEPS
    windows = policy + WINDOWS_STATUS_GUARD + "          python ../tools/tests/test_subscription_capture.py\n"
    added_portable = "".join(f"          python ../tools/tests/{name}\n" for name in DNS_PROBE_TESTS)
    added_windows = "".join(f"          python ../tools/tests/{name}\n" + WINDOWS_STATUS_GUARD for name in DNS_PROBE_TESTS)
    portable_after = policy + added_portable + PUBLIC_VALIDATION_STEPS
    windows_after = policy + WINDOWS_STATUS_GUARD + added_windows + "          python ../tools/tests/test_subscription_capture.py\n"
    counts = tuple(source.count(f"          python ../tools/tests/{name}\n") for name in DNS_PROBE_TESTS)
    if counts == (2, 2, 2):
        if source.count(portable_after) != 1 or source.count(windows_after) != 1:
            raise ValueError("Rust CI DNS/probe menus have drifted; review required")
        source = source.replace(portable_after, portable, 1).replace(windows_after, windows, 1)
    elif counts == (2, 2, 0):
        # The verified DNS stage predates the connection-stage peer suite.
        command = "          python ../tools/tests/test_connection_stages.py\n"
        old_portable = portable_after.replace(command, "")
        old_windows = windows_after.replace(command + WINDOWS_STATUS_GUARD, "")
        if source.count(old_portable) != 1 or source.count(old_windows) != 1:
            raise ValueError("Rust CI previous DNS/probe menus have drifted; review required")
        source = source.replace(old_portable, portable, 1).replace(old_windows, windows, 1)
    elif counts != (0, 0, 0):
        raise ValueError("Rust CI DNS/probe stage is only partially present; review required")
    source = _previous_workflow(source)
    source = _replace_checked(source, portable, portable_after, "portable DNS/probe menu")
    return _replace_checked(source, windows, windows_after, "Windows DNS/probe menu")


def _connectivity_blocks(windows: bool) -> tuple[tuple[str, str, str], ...]:
    """The complete reviewed addition for one existing job, including its binaries."""
    first_test = "          python ../tools/tests/test_rust_core.py\n"
    command = "          python ../tools/tests/test_connection_stages.py\n"
    if windows:
        inspector = "          $env:SWIRL_RUST_INSPECTOR=(Resolve-Path target/release/swirl-inspect.exe).Path\n"
        diagnostic = WINDOWS_DIAGNOSTIC
        status_guard = WINDOWS_STATUS_GUARD
        tail = "          python ../tools/tests/test_subscription_capture.py\n"
        binary_checks = "".join(
            f"          if (-not (Test-Path $env:{name} -PathType Leaf)) {{ throw 'Required Rust test binary missing' }}\n"
            for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC")
        )
    else:
        inspector = '          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n'
        diagnostic = PORTABLE_DIAGNOSTIC
        status_guard = ""
        tail = PUBLIC_VALIDATION_STEPS
        binary_checks = "".join(
            f'          test -x "${name}"\n'
            for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC")
        )
    new_tests = "".join(
        f"          python ../tools/tests/{name}\n" + status_guard for name in CONNECTIVITY_IMPORT_TESTS
    )
    blocks = (
        (PREVIOUS_RELEASE_BUILD, RELEASE_BUILD, "release library/binary targets"),
        (inspector + first_test, inspector + diagnostic + binary_checks + first_test,
         "required native test binaries"),
        (command + status_guard + tail, command + status_guard + new_tests + tail,
         "connectivity/import peer menu"),
    )
    if windows:
        inspector_artifact = "            core/target/release/swirl-inspect.exe\n"
        lock_artifact = "            core/Cargo.lock\n"
        blocks += ((inspector_artifact + lock_artifact,
                    inspector_artifact + DIAGNOSTIC_ARTIFACT + lock_artifact,
                    "Windows diagnostic artifact"),)
    return blocks


def _connectivity_workflow(source: str) -> str:
    """Upgrade a reviewed historical stage atomically, or validate the complete new stage."""
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI job boundaries have drifted; review required")
    counts = (
        *(source.count(f"          python ../tools/tests/{name}\n") for name in CONNECTIVITY_IMPORT_TESTS),
        source.count(PORTABLE_DIAGNOSTIC), source.count(WINDOWS_DIAGNOSTIC),
        source.count(DIAGNOSTIC_ARTIFACT), source.count(RELEASE_BUILD),
    )
    present = counts != (0, 0, 0, 0, 0, 0)
    if present and counts != (2, 2, 1, 1, 1, 2):
        raise ValueError("Rust CI connectivity/import stage is only partially present; review required")
    parts = source.split(separator)
    if present:
        # Remove only exact final blocks before invoking all historical checks.
        # A partial stage or a missing guard must never be silently repaired.
        for index, part in enumerate(parts):
            for before, after, label in _connectivity_blocks(windows=index == 1):
                if part.count(after) != 1 or part.count(before) != 0:
                    raise ValueError(f"Rust CI {label} has drifted; review required")
                part = part.replace(after, before, 1)
            parts[index] = part
    source = _connection_workflow(separator.join(parts))
    parts = source.split(separator)
    for index, part in enumerate(parts):
        for before, after, label in _connectivity_blocks(windows=index == 1):
            part = _replace_checked(part, before, after, label)
        parts[index] = part
    return separator.join(parts)


def _udp_workflow(source: str) -> str:
    """Add the complete UDP stage without weakening prior workflow guards."""
    command = f"          python ../tools/tests/{SOCKS5_UDP_TEST}\n"
    qt_command = f"          python tools/tests/{SOCKS5_UDP_QT_TEST}\n"
    counts = (source.count(command), source.count(qt_command),
              source.count(NATIVE_APPLICATION_BUILD), source.count(REMOVED_RUNTIME_GATE),
              source.count(NATIVE_QT_REPORT), source.count(QT_TEST_ARTIFACT))
    if counts not in ((0, 0, 0, 0, 0, 0), (2, 1, 1, 1, 1, 1)):
        raise ValueError("Rust CI SOCKS5 UDP stage is partial or duplicated; review required")
    anchor = "          python ../tools/tests/test_subscription_import.py\n"
    windows_tail = "          python ../tools/tests/test_subscription_capture.py\n"
    menus = (
        (anchor + PUBLIC_VALIDATION_STEPS, anchor + command + PUBLIC_VALIDATION_STEPS),
        (anchor + WINDOWS_STATUS_GUARD + windows_tail,
         anchor + WINDOWS_STATUS_GUARD + command + WINDOWS_STATUS_GUARD + windows_tail),
    )
    qt_before = f"          python tools/tests/{QT_PEER_TESTS[-1]}\n" + WINDOWS_STATUS_GUARD
    qt_after = qt_before + qt_command + WINDOWS_STATUS_GUARD + NATIVE_APPLICATION_BUILD + QT_TEST_ARTIFACT
    if counts == (2, 1, 1, 1, 1, 1):
        for before, after in menus:
            if source.count(after) != 1 or source.count(before) != 0:
                raise ValueError("Rust CI SOCKS5 UDP peer menu drifted; review required")
            source = source.replace(after, before, 1)
        if not source.endswith(qt_after):
            raise ValueError("Rust CI SOCKS5 UDP Qt/native build tail drifted; review required")
        source = source[:-len(qt_after)] + qt_before
        if source.count(HISTORICAL_COMPATIBILITY_GATE) != 0:
            raise ValueError("Rust CI removed-runtime gate duplicated; review required")
        source = source.replace(REMOVED_RUNTIME_GATE, HISTORICAL_COMPATIBILITY_GATE, 1)
        if source.count(PREVIOUS_NATIVE_QT_REPORT) != 0 or source.count(DIAGNOSTIC_NATIVE_QT_REPORT) != 0:
            raise ValueError("Rust CI native Qt report gate duplicated; review required")
        source = source.replace(NATIVE_QT_REPORT, PREVIOUS_NATIVE_QT_REPORT, 1)
    source = _connectivity_workflow(source)
    source = _replace_checked(source, HISTORICAL_COMPATIBILITY_GATE, REMOVED_RUNTIME_GATE,
                              "removed-runtime configure rejection gate")
    source = _replace_checked(source, PREVIOUS_NATIVE_QT_REPORT, NATIVE_QT_REPORT,
                              "native Qt report and exit-code gates", intermediate=DIAGNOSTIC_NATIVE_QT_REPORT)
    for before, after in menus:
        source = _replace_checked(source, before, after, "SOCKS5 UDP peer menu")
    if not source.endswith(qt_before):
        raise ValueError("Rust CI pre-UDP Qt peer tail drifted; review required")
    return source[:-len(qt_before)] + qt_after


def _reality_blocks(windows: bool) -> tuple[tuple[str, str, str], ...]:
    first_test = "          python ../tools/tests/test_rust_core.py\n"
    names = ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC")
    if windows:
        build = WINDOWS_REALITY_BUILD
        diagnostic = WINDOWS_DIAGNOSTIC
        environment = WINDOWS_REALITY_ENV
        extra_check = WINDOWS_REALITY_CHECK
        checks = "".join(
            f"          if (-not (Test-Path $env:{name} -PathType Leaf)) {{ throw 'Required Rust test binary missing' }}\n"
            for name in names
        )
        status = WINDOWS_STATUS_GUARD
    else:
        build = PORTABLE_REALITY_BUILD
        diagnostic = PORTABLE_DIAGNOSTIC
        environment = PORTABLE_REALITY_ENV
        extra_check = PORTABLE_REALITY_CHECK
        checks = "".join(f'          test -x "${name}"\n' for name in names)
        status = ""
    suites = "".join(f"          python ../tools/tests/{name}\n" + status for name in REALITY_TESTS)
    return (
        (RELEASE_BUILD, RELEASE_BUILD + build, "REALITY Release example build"),
        (diagnostic + checks + first_test,
         diagnostic + environment + checks + extra_check + suites + first_test,
         "REALITY environment, required binaries and peer menus"),
    )


def _reality_workflow(source: str) -> str:
    """Treat build, binary identity, preflight and both peers as one atomic stage."""
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI job boundaries have drifted; review required")
    markers = (
        PORTABLE_REALITY_BUILD, WINDOWS_REALITY_BUILD,
        PORTABLE_REALITY_ENV, WINDOWS_REALITY_ENV,
        PORTABLE_REALITY_CHECK, WINDOWS_REALITY_CHECK,
        *(f"          python ../tools/tests/{name}\n" for name in REALITY_TESTS),
    )
    counts = tuple(source.count(marker) for marker in markers)
    identities = tuple(source.count(marker) for marker in
                       ("reality-client", "SWIRL_REALITY_CLIENT", "test_reality_"))
    present = any(counts) or any(identities)
    if present and (counts != (1, 1, 1, 1, 1, 1, 2, 2) or identities != (4, 4, 4)):
        raise ValueError("Rust CI REALITY stage is partial or duplicated; review required")
    parts = source.split(separator)
    if present:
        for index, part in enumerate(parts):
            for before, after, label in _reality_blocks(windows=index == 1):
                if part.count(after) != 1:
                    raise ValueError(f"Rust CI {label} has drifted; review required")
                part = part.replace(after, before, 1)
            parts[index] = part
    # Preserve every historical guard. Only exact complete new blocks were
    # removed; deleting a guard or changing a command is never auto-repaired.
    source = _udp_workflow(separator.join(parts))
    parts = source.split(separator)
    for index, part in enumerate(parts):
        for before, after, label in _reality_blocks(windows=index == 1):
            part = _replace_checked(part, before, after, label)
        parts[index] = part
    return separator.join(parts)


def _vector_blocks(windows: bool) -> tuple[str, str, str]:
    """Exact pre-fixture, REALITY-only and complete fixture prefixes for one job."""
    install = "          python -m pip install cryptography==50.0.2\n"
    reality = "          python ../tools/tests/generate_reality_vectors.py --check\n"
    vision = "          python ../tools/tests/generate_vision_vectors.py --check\n"
    status = WINDOWS_STATUS_GUARD if windows else ""
    harness = ("          $env:SWIRL_RUST_HARNESS=(Resolve-Path target/release/swirl-api.exe).Path\n"
               if windows else '          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"\n')
    return (
        install + harness,
        install + status + reality + status + harness,
        install + status + reality + status + vision + status + harness,
    )


def updated_workflow(source: str) -> str:
    """Validate the whole fixture stage before preserving every prior CI guard."""
    source = without_public_qt_steps(source)
    source = without_product_chain_steps(source)
    source = without_vision_xray_steps(source)
    source = without_xray_steps(source)
    separator = "  windows-rust:\n"
    if source.count(separator) != 1:
        raise ValueError("Rust CI job boundaries have drifted; review required")
    counts = tuple(source.count(name) for name in
                   ("generate_reality_vectors.py", "generate_vision_vectors.py"))
    reviewed = ((0, 0), (2, 0), (2, 2))
    if counts not in reviewed:
        raise ValueError("Rust CI fixture stage is partial or duplicated; review required")
    stage = reviewed.index(counts)
    parts = source.split(separator)
    for index, part in enumerate(parts):
        blocks = _vector_blocks(windows=index == 1)
        if part.count(blocks[stage]) != 1:
            raise ValueError("Rust CI fixture commands or exit guards drifted; review required")
        parts[index] = part.replace(blocks[stage], blocks[0], 1)
    source = _reality_workflow(separator.join(parts))
    parts = source.split(separator)
    for index, part in enumerate(parts):
        historical, _, complete = _vector_blocks(windows=index == 1)
        parts[index] = _replace_checked(part, historical, complete, "Vision fixture checks")
    return _add_public_qt_steps(_add_fingerprint_steps(_add_reality_runtime_steps(
        _add_product_chain_steps(_add_vision_xray_steps(_add_xray_steps(separator.join(parts)))))))


def validate_context(environment: Mapping[str, str]) -> None:
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": DEVELOPMENT_REF,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_WORKFLOW_REF": CALLER_WORKFLOW,
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            # Do not print environment values: this helper never reads tokens.
            raise ValueError(f"Workflow writes are disabled in this {name} context")


def prepare_update(repository: Path) -> tuple[Path, str, str]:
    repository = repository.resolve()
    path = repository / WORKFLOW
    if path.is_symlink() or path.resolve() != path:
        raise ValueError("Rust CI target must be a regular file within the repository")
    if not path.is_file():
        raise ValueError("The existing Rust CI workflow is required")
    # Git checkouts may use CRLF on Windows. Both styles represent the same
    # workflow; writes still occur only in the existing Linux App job.
    before = path.read_text(encoding="utf-8")
    after = updated_workflow(before)
    for name in (*ADDITIONAL_TESTS, POLICY_TEST, *DNS_PROBE_TESTS, *CONNECTIVITY_IMPORT_TESTS,
                 SOCKS5_UDP_TEST, *REALITY_TESTS, PRODUCT_CHAIN_TEST, REALITY_RUNTIME_TEST, PUBLIC_QT_TEST, QT_LIFECYCLE_TEST):
        if not (repository / "tools/tests" / name).is_file():
            raise ValueError(f"Required CI suite is missing: {name}")
    if not (repository / PUBLIC_PROBE).is_file():
        raise ValueError("The required native public-network verification script is missing")
    if not (repository / PUBLIC_REALITY_PROBE).is_file():
        raise ValueError("The required public REALITY/Vision Runtime verification script is missing")
    if not (repository / PUBLIC_QT_PROBE).is_file():
        raise ValueError("The required Windows Qt public product verification script is missing")
    for relative in (DIAGNOSTIC_TOOL, DIAGNOSTIC_SOURCE):
        if not (repository / relative).is_file():
            raise ValueError(f"Required native diagnostic source is missing: {relative.as_posix()}")
    for relative in REALITY_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required REALITY peer source is missing: {relative.as_posix()}")
    for relative in VISION_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required Vision fixture source is missing: {relative.as_posix()}")
    for relative in XRAY_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required mature Xray peer source is missing: {relative.as_posix()}")
    for relative in VISION_XRAY_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required Vision stream peer source is missing: {relative.as_posix()}")
    for relative in FINGERPRINT_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required independent fingerprint source is missing: {relative.as_posix()}")
    return path, before, after


def apply_update(repository: Path, environment: Mapping[str, str]) -> bool:
    validate_context(environment)
    path, before, after = prepare_update(repository)
    if before == after:
        return False
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".rust-core-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(after.encode("utf-8"))
        temporary_path.chmod(path.stat().st_mode)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Run safety tests and fail on workflow drift without writes"
    )
    options = parser.parse_args()
    repository = Path(__file__).resolve().parent.parent
    if not options.check:
        validate_context(os.environ)
    # This is an explicit, mandatory gate in the existing App job; a missing or
    # failing safety suite prevents any workflow mutation or automatic commit.
    subprocess.run(
        [sys.executable, str(repository / "tools/tests/test_core_development.py")],
        cwd=repository,
        check=True,
    )
    _, before, after = prepare_update(repository)
    print(f"Reviewed workflow: {WORKFLOW.as_posix()}", flush=True)
    print(f"Before SHA-256: {hashlib.sha256(before.encode()).hexdigest()}", flush=True)
    print(f"After SHA-256:  {hashlib.sha256(after.encode()).hexdigest()}", flush=True)
    if options.check:
        sys.stdout.writelines(
            difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=WORKFLOW.as_posix(), tofile=WORKFLOW.as_posix(),
            )
        )
        return int(before != after)
    else:
        changed = apply_update(repository, os.environ)
        print("Applied reviewed Rust CI update" if changed else "Rust CI gates already current")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Core development validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
