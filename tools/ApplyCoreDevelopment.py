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
run in the existing compatibility build, alongside its native-DNS rejection gate.
Four fixed Qt XML reports preserve diagnostics even after a failed test or build.
The REALITY TLS stage builds its actual Release protocol client and runs both
independent peer suites only after all four required test binaries are present.
The Vision component stage requires both independent fixture checks, in order,
with immediate Windows exit propagation, before any protocol peer can run.
It does not change permissions, secrets,
existing actions, pull-request triggers or any product source.

Run ``python tools/ApplyCoreDevelopment.py --check`` to run the safety tests and
review the exact diff without writing. With no arguments, writes are restricted
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
            build/compat-dns/swirl-native-dns-compatibility-guard.xml
            build/compat-dns/swirl-import-boundaries.xml
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
COMPATIBILITY_TEST_REPORT = """          ctest --test-dir build/compat-dns -C Release -R '^swirl-(native-dns-compatibility-guard|import-boundaries)$' --output-on-failure -V
          $compatQtExit = $LASTEXITCODE
          foreach ($compatQtReport in @(
            'build/compat-dns/swirl-native-dns-compatibility-guard.xml',
            'build/compat-dns/swirl-import-boundaries.xml'
          )) {
            if (-not (Test-Path $compatQtReport -PathType Leaf)) { throw 'Required compatibility Qt XML report missing' }
            Get-Content -LiteralPath $compatQtReport
          }
          if ($compatQtExit -ne 0) { exit $compatQtExit }
"""
PREVIOUS_COMPATIBILITY_GATE = """      - name: Reject native DNS policy in compatibility builds without starting a core
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
COMPATIBILITY_GATE = PREVIOUS_COMPATIBILITY_GATE.replace(
    "        working-directory: .\n",
    "        working-directory: .\n        env:\n          QT_FORCE_STDERR_LOGGING: '1'\n",
).replace(
    "--target SwirlEngineTests --parallel\n",
    "--target SwirlEngineTests SwirlImportTests --parallel\n",
).replace(
    "          ctest --test-dir build/compat-dns -C Release -R '^swirl-native-dns-compatibility-guard$' --output-on-failure\n"
    + WINDOWS_STATUS_GUARD,
    COMPATIBILITY_TEST_REPORT,
)


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
              source.count(NATIVE_APPLICATION_BUILD), source.count(COMPATIBILITY_GATE),
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
        if source.count(PREVIOUS_COMPATIBILITY_GATE) != 0:
            raise ValueError("Rust CI compatibility import gate duplicated; review required")
        source = source.replace(COMPATIBILITY_GATE, PREVIOUS_COMPATIBILITY_GATE, 1)
        if source.count(PREVIOUS_NATIVE_QT_REPORT) != 0 or source.count(DIAGNOSTIC_NATIVE_QT_REPORT) != 0:
            raise ValueError("Rust CI native Qt report gate duplicated; review required")
        source = source.replace(NATIVE_QT_REPORT, PREVIOUS_NATIVE_QT_REPORT, 1)
    source = _connectivity_workflow(source)
    source = _replace_checked(source, PREVIOUS_COMPATIBILITY_GATE, COMPATIBILITY_GATE,
                              "compatibility import and native-DNS gates")
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
    return separator.join(parts)


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
                 SOCKS5_UDP_TEST, *REALITY_TESTS):
        if not (repository / "tools/tests" / name).is_file():
            raise ValueError(f"Required CI suite is missing: {name}")
    if not (repository / PUBLIC_PROBE).is_file():
        raise ValueError("The required native public-network verification script is missing")
    for relative in (DIAGNOSTIC_TOOL, DIAGNOSTIC_SOURCE):
        if not (repository / relative).is_file():
            raise ValueError(f"Required native diagnostic source is missing: {relative.as_posix()}")
    for relative in REALITY_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required REALITY peer source is missing: {relative.as_posix()}")
    for relative in VISION_SOURCES:
        if not (repository / relative).is_file():
            raise ValueError(f"Required Vision fixture source is missing: {relative.as_posix()}")
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
        "--check", action="store_true", help="Run safety tests and show the diff without writes"
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
