"""Safety and coverage checks for the one-file, App-owned Rust CI update.

These run before its first workflow write and in all three Rust CI platforms.
The fixture exercises the actual run-menu boundaries, including Windows error
propagation. No test contacts GitHub or accesses credentials.
"""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ApplyCoreDevelopment as development


FIXTURE = """name: Swirl Rust Core
on:
  push:
    branches: [test, main]
  pull_request:
    branches: [test, main]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  portable-rust:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
    steps:
      - uses: actions/checkout@v4
      - run: cargo build --release --locked -p swirl-api
      - name: Independent portable protocol peers
        run: |
          python -m pip install cryptography==50.0.2
          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"
          python ../tools/tests/test_rust_core.py
          python ../tools/tests/test_shadowsocks.py
          python ../tools/tests/test_dns_tls.py
  windows-rust:
    steps:
      - run: cargo build --release --locked -p swirl-api
      - name: Independent TLS and protocol peers
        shell: pwsh
        run: |
          python -m pip install cryptography==50.0.2
          $env:SWIRL_RUST_HARNESS=(Resolve-Path target/release/swirl-api.exe).Path
          $env:SWIRL_RUST_INSPECTOR=(Resolve-Path target/release/swirl-inspect.exe).Path
          python ../tools/tests/test_rust_core.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_shadowsocks.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_dns_tls.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_subscription_capture.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_codex_management.py
      - uses: actions/upload-artifact@v4
        with:
          name: Swirl-Rust-Core-Windows
          path: |
            core/target/release/swirl_api.dll
            core/target/release/swirl-api.exe
            core/target/release/swirl-inspect.exe
            core/Cargo.lock
      - name: Reject native DNS policy in compatibility builds without starting a core
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
      - name: Run Qt to Rust integration without Mihomo
        working-directory: .
        run: |
          ctest --test-dir build/rust-qt -C Release -R '^swirl-(rust-qt-integration|storage-paths|import-boundaries)$' --output-on-failure
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python tools/tests/test_rust_core.py RustCoreIntegration.test_vless_qt_data_path
"""

ENVIRONMENT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": "SOLHK/Swirl",
    "GITHUB_REF": "refs/heads/work/core-completion-20261017",
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_WORKFLOW_REF": (
        "SOLHK/Swirl/.github/workflows/core-development.yml"
        "@refs/heads/work/core-completion-20261017"
    ),
}

REQUIRED_TESTS = (
    "test_dns_https.py",
    "test_socks4.py",
    "test_websocket_transport.py",
    "test_core_development.py",
    "test_policy_groups.py",
    "test_dns_negative.py",
    "test_native_probe.py",
    "test_connection_stages.py",
    "test_connectivity_diagnostics.py",
    "test_subscription_import.py",
    "test_socks5_udp.py",
)


def previous_socks5_udp_stage(source):
    command = "          python ../tools/tests/test_socks5_udp.py\n"
    qt = "          python tools/tests/test_socks5_udp.py Socks5UdpIntegration.test_qt_imported_socks5_udp_data_path\n"
    return source.replace(development.QT_TEST_ARTIFACT, "").replace(
        development.NATIVE_QT_REPORT, development.PREVIOUS_NATIVE_QT_REPORT).replace(
        development.COMPATIBILITY_GATE, development.PREVIOUS_COMPATIBILITY_GATE).replace(
        development.NATIVE_APPLICATION_BUILD, "").replace(
        qt + development.WINDOWS_STATUS_GUARD, "").replace(
        command + development.WINDOWS_STATUS_GUARD, "").replace(command, "")


def previous_connection_stage(source):
    """Remove exactly this stage's reviewed additions to construct historical fixtures."""
    source = previous_socks5_udp_stage(source)
    for name in ("test_connectivity_diagnostics.py", "test_subscription_import.py"):
        command = f"          python ../tools/tests/{name}\n"
        source = source.replace(command + "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", "")
        source = source.replace(command, "")
    source = source.replace('          export SWIRL_RUST_DIAGNOSTIC="$PWD/target/release/swirl-diagnose"\n', "")
    source = source.replace("          $env:SWIRL_RUST_DIAGNOSTIC=(Resolve-Path target/release/swirl-diagnose.exe).Path\n", "")
    for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC"):
        source = source.replace(f'          test -x "${name}"\n', "")
        source = source.replace(
            f"          if (-not (Test-Path $env:{name} -PathType Leaf)) {{ throw 'Required Rust test binary missing' }}\n", "")
    source = source.replace("            core/target/release/swirl-diagnose.exe\n", "")
    return source.replace(
        "      - run: cargo build --release --locked --workspace --lib --bins\n",
        "      - run: cargo build --release --locked -p swirl-api\n",
    )


class CoreDevelopmentTests(unittest.TestCase):
    def make_repository(self, root, source=FIXTURE):
        workflow = root / ".github/workflows/rust-core.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(source, encoding="utf-8")
        peers = root / "tools/tests"
        peers.mkdir(parents=True)
        for name in REQUIRED_TESTS:
            (peers / name).write_text("# test fixture\n", encoding="utf-8")
        (root / "tools/Verify-PublicRustCore.py").write_text("# public check fixture\n", encoding="utf-8")
        (root / "tools/Diagnose-NativeConnectivity.py").write_text("# diagnostic fixture\n", encoding="utf-8")
        diagnostic = root / "core/crates/swirl-api/src/bin/swirl-diagnose.rs"
        diagnostic.parent.mkdir(parents=True)
        diagnostic.write_text("// diagnostic fixture\n", encoding="utf-8")
        return workflow

    def test_adds_only_reviewed_tests_and_exact_development_trigger(self):
        updated = development.updated_workflow(FIXTURE)
        portable, windows = updated.split("  windows-rust:\n")
        for name in REQUIRED_TESTS:
            command = f"          python ../tools/tests/{name}\n"
            self.assertEqual(portable.count(command), 1)
            self.assertEqual(windows.count(command), 1)
            self.assertIn(command + "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", windows)
        self.assertIn(
            "  push:\n    branches: [test, main, work/core-completion-20261017]\n", updated
        )
        self.assertIn("  pull_request:\n    branches: [test, main]\n", updated)
        self.assertIn("permissions:\n  contents: read\n", updated)
        self.assertIn(
            "        if: runner.os == 'Linux'\n"
            "        run: python ../tools/Verify-PublicRustCore.py --harness target/release/swirl-api --output ../CORE_PUBLIC_NETWORK.json\n",
            portable,
        )
        self.assertIn("        if: always() && runner.os == 'Linux'\n", portable)
        self.assertIn("          path: CORE_PUBLIC_NETWORK.json\n", portable)
        self.assertNotIn("Verify-PublicRustCore.py", windows)
        for command in (
            "          python tools/tests/test_socks4.py Socks4Integration.test_qt_imported_socks4_and_4a_data_path\n",
            "          python tools/tests/test_websocket_transport.py WebSocketTransportTests.test_qt_vless_websocket_data_path\n",
        ):
            self.assertEqual(windows.count(command), 1)
            self.assertIn(command + "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", windows)
        self.assertIn('          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n', portable)
        # Reversing only the reviewed additions must recover every original byte.
        restored = previous_connection_stage(updated).replace(
            "    branches: [test, main, work/core-completion-20261017]\n",
            "    branches: [test, main]\n",
        )
        for name in REQUIRED_TESTS:
            command = f"          python ../tools/tests/{name}\n"
            restored = restored.replace(command + "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", "")
            restored = restored.replace(command, "")
        restored = restored.replace('          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n', '')
        qt_anchor = "          python tools/tests/test_rust_core.py RustCoreIntegration.test_vless_qt_data_path\n"
        restored = restored[:restored.index(qt_anchor)] + qt_anchor
        restored = restored.replace(
            "      - name: Native public HTTPS and DoH verification\n"
            "        if: runner.os == 'Linux'\n"
            "        run: python ../tools/Verify-PublicRustCore.py --harness target/release/swirl-api --output ../CORE_PUBLIC_NETWORK.json\n"
            "      - name: Preserve public network evidence\n"
            "        if: always() && runner.os == 'Linux'\n"
            "        uses: actions/upload-artifact@v4\n"
            "        with:\n"
            "          name: Swirl-Core-Public-Network\n"
            "          path: CORE_PUBLIC_NETWORK.json\n"
            "          retention-days: 7\n",
            "",
        )
        self.assertEqual(restored, FIXTURE)

    def test_idempotence_prevents_repeated_app_commits(self):
        first = development.updated_workflow(FIXTURE)
        self.assertEqual(development.updated_workflow(first), first)

    def test_socks5_udp_adds_portable_qt_and_native_build_as_one_stage(self):
        final = development.updated_workflow(FIXTURE)
        previous = previous_socks5_udp_stage(final)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(final.count("          python ../tools/tests/test_socks5_udp.py\n"), 2)
        qt = "          python tools/tests/test_socks5_udp.py Socks5UdpIntegration.test_qt_imported_socks5_udp_data_path\n"
        self.assertEqual(final.count(qt), 1)
        self.assertIn(qt + development.WINDOWS_STATUS_GUARD, final)
        self.assertTrue(final.endswith(development.NATIVE_APPLICATION_BUILD + development.QT_TEST_ARTIFACT))
        self.assertEqual(final.count("cmake --build build/rust-qt --config Release --target Swirl --parallel 2"), 1)

    def test_socks5_udp_partial_commands_and_native_build_drift_are_rejected(self):
        final = development.updated_workflow(FIXTURE)
        command = "          python ../tools/tests/test_socks5_udp.py\n"
        qt = "          python tools/tests/test_socks5_udp.py Socks5UdpIntegration.test_qt_imported_socks5_udp_data_path\n"
        for broken in (
            final.replace(command, "", 1),
            final.replace(command, command * 2, 1),
            final.replace(command + development.WINDOWS_STATUS_GUARD, command),
            final.replace(qt, ""),
            final.replace(qt + development.WINDOWS_STATUS_GUARD, qt),
            final.replace(development.NATIVE_APPLICATION_BUILD, ""),
            final + development.NATIVE_APPLICATION_BUILD,
            final.replace("--target Swirl --parallel 2", "--target SwirlEngineTests --parallel 2"),
        ):
            with self.subTest(tail=broken[-180:]), self.assertRaises(ValueError):
                development.updated_workflow(broken)

    def test_compatibility_import_runs_alongside_the_existing_native_dns_guard(self):
        final = development.updated_workflow(FIXTURE)
        self.assertEqual(final.count(development.COMPATIBILITY_GATE), 1)
        self.assertNotIn(development.PREVIOUS_COMPATIBILITY_GATE, final)
        gate = development.COMPATIBILITY_GATE
        self.assertIn("-DSWIRL_USE_RUST_CORE=OFF -DSWIRL_BUILD_UI_TESTS=ON\n", gate)
        self.assertIn("--target SwirlEngineTests SwirlImportTests --parallel\n" + development.WINDOWS_STATUS_GUARD, gate)
        self.assertIn("'^swirl-(native-dns-compatibility-guard|import-boundaries)$' --output-on-failure -V\n"
                      + "          $compatQtExit = $LASTEXITCODE\n", gate)
        self.assertIn("          if ($compatQtExit -ne 0) { exit $compatQtExit }\n", gate)
        self.assertIn("$env:SWIRL_TEST_ROOT=Join-Path $env:RUNNER_TEMP 'swirl-compat-dns-tests'", gate)
        self.assertEqual(development.updated_workflow(previous_socks5_udp_stage(final)), final)

    def test_compatibility_import_partial_or_weakened_gates_are_rejected(self):
        final = development.updated_workflow(FIXTURE)
        gate = development.COMPATIBILITY_GATE
        for broken_gate in (
            "",
            gate + gate,
            development.PREVIOUS_COMPATIBILITY_GATE,
            gate.replace("-DSWIRL_USE_RUST_CORE=OFF", "-DSWIRL_USE_RUST_CORE=ON"),
            gate.replace("SwirlEngineTests SwirlImportTests", "SwirlEngineTests"),
            gate.replace("SwirlEngineTests SwirlImportTests", "SwirlImportTests"),
            gate.replace("native-dns-compatibility-guard|import-boundaries", "native-dns-compatibility-guard"),
            gate.replace("native-dns-compatibility-guard|import-boundaries", "import-boundaries"),
            gate.replace(development.WINDOWS_STATUS_GUARD, "", 1),
            gate.replace("          if ($compatQtExit -ne 0) { exit $compatQtExit }\n", ""),
        ):
            with self.subTest(gate=broken_gate), self.assertRaises(ValueError):
                development.updated_workflow(final.replace(gate, broken_gate, 1))

    def test_qt_reports_upgrade_diagnostic_stage_and_preserve_exact_artifact_paths(self):
        final = development.updated_workflow(FIXTURE)
        diagnostic = previous_socks5_udp_stage(final).replace(
            development.PREVIOUS_NATIVE_QT_REPORT, development.DIAGNOSTIC_NATIVE_QT_REPORT)
        self.assertEqual(development.updated_workflow(diagnostic), final)
        self.assertEqual(final.count(development.NATIVE_QT_REPORT), 1)
        self.assertEqual(final.count(development.QT_TEST_ARTIFACT), 1)
        self.assertTrue(final.endswith(development.QT_TEST_ARTIFACT))
        artifact = development.QT_TEST_ARTIFACT
        paths = [line.strip() for line in artifact.splitlines() if line.startswith("            ")]
        self.assertEqual(paths, [
            "build/rust-qt/swirl-rust-qt-integration.xml",
            "build/rust-qt/swirl-import-boundaries.xml",
            "build/compat-dns/swirl-native-dns-compatibility-guard.xml",
            "build/compat-dns/swirl-import-boundaries.xml",
        ])
        self.assertIn("        if: always()\n", artifact)
        self.assertIn("          retention-days: 7\n", artifact)
        self.assertIn("github.sha", artifact)

    def test_qt_reports_reject_missing_paths_expanded_artifacts_and_weakened_exits(self):
        final = development.updated_workflow(FIXTURE)
        native, compat, artifact = (development.NATIVE_QT_REPORT, development.COMPATIBILITY_GATE,
                                    development.QT_TEST_ARTIFACT)
        broken_blocks = [
            (artifact, ""),
            (artifact, artifact * 2),
            (artifact, artifact.replace("if: always()", "if: success()")),
            (artifact, artifact.replace("retention-days: 7", "retention-days: 30")),
            (artifact, artifact.replace("build/rust-qt/swirl-import-boundaries.xml", "build/**")),
            (artifact, artifact.replace("            build/compat-dns/swirl-import-boundaries.xml\n", "")),
            (artifact, artifact.replace("          if-no-files-found:",
                                        "            ${{ env.SWIRL_TEST_ROOT }}\n          if-no-files-found:")),
        ]
        for block, prefix in ((native, "native"), (compat, "compat")):
            exit_guard = f"          if (${prefix}QtExit -ne 0) {{ exit ${prefix}QtExit }}\n"
            capture = f"          ${prefix}QtExit = $LASTEXITCODE\n"
            broken_blocks.extend((
                (block, block.replace(capture, "")),
                (block, block.replace(exit_guard, "")),
                (block, block.replace(exit_guard, "          exit 0\n")),
                (block, block.replace("swirl-import-boundaries.xml", "../private-state.xml")),
                (block, block.replace("Get-Content -LiteralPath", "Write-Output")),
            ))
        for before, after in broken_blocks:
            with self.subTest(block=after), self.assertRaises(ValueError):
                development.updated_workflow(final.replace(before, after, 1))

    def test_previous_successful_workflow_upgrades_without_duplicate_suites(self):
        final = development.updated_workflow(FIXTURE)
        previous = previous_connection_stage(final)
        for name in ("test_dns_negative.py", "test_native_probe.py", "test_connection_stages.py"):
            command = f"          python ../tools/tests/{name}\n"
            previous = previous.replace(command + development.WINDOWS_STATUS_GUARD, "")
            previous = previous.replace(command, "")
        previous = previous.replace("          python ../tools/tests/test_policy_groups.py\n"
                                 "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", "")
        previous = previous.replace("          python ../tools/tests/test_policy_groups.py\n", "")
        previous = previous.replace('          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n', '')
        qt_anchor = "          python tools/tests/test_rust_core.py RustCoreIntegration.test_vless_qt_data_path\n"
        previous = previous[:previous.index(qt_anchor)] + qt_anchor
        self.assertEqual(development.updated_workflow(previous), final)

    def test_partial_qt_and_policy_additions_fail_closed(self):
        final = development.updated_workflow(FIXTURE)
        for source in (
            final.replace("          python ../tools/tests/test_policy_groups.py\n", "", 1),
            final.replace("          python tools/tests/test_websocket_transport.py WebSocketTransportTests.test_qt_vless_websocket_data_path\n", ""),
            final + "          python tools/tests/test_socks4.py Socks4Integration.test_qt_imported_socks4_and_4a_data_path\n",
        ):
            with self.subTest(tail=source[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_previous_dns_stage_upgrades_and_partial_new_menus_are_rejected(self):
        final = development.updated_workflow(FIXTURE)
        previous = previous_connection_stage(final)
        for name in ("test_dns_negative.py", "test_native_probe.py", "test_connection_stages.py"):
            command = f"          python ../tools/tests/{name}\n"
            previous = previous.replace(command + development.WINDOWS_STATUS_GUARD, "")
            previous = previous.replace(command, "")
        self.assertEqual(development.updated_workflow(previous), final)
        command = "          python ../tools/tests/test_dns_negative.py\n"
        for broken in (
            final.replace(command, "", 1),
            final.replace(command, command * 2, 1),
            final.replace(command + development.WINDOWS_STATUS_GUARD, command),
        ):
            with self.subTest(menu=broken[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(broken)

    def test_connection_suite_upgrades_verified_dns_stage_without_partial_acceptance(self):
        final = development.updated_workflow(FIXTURE)
        command = "          python ../tools/tests/test_connection_stages.py\n"
        previous = previous_connection_stage(final).replace(command + development.WINDOWS_STATUS_GUARD, "").replace(command, "")
        self.assertEqual(development.updated_workflow(previous), final)
        for broken in (final.replace(command, "", 1),
                       final.replace(command, command * 2, 1),
                       final.replace(command + development.WINDOWS_STATUS_GUARD, command)):
            with self.subTest(menu=broken[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(broken)

    def test_connectivity_stage_upgrades_previous_build_menus_and_artifact_together(self):
        final = development.updated_workflow(FIXTURE)
        previous = previous_connection_stage(final)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(final.count("      - run: cargo build --release --locked --workspace --lib --bins\n"), 2)
        self.assertNotIn("cargo build --release --locked -p swirl-api", final)
        self.assertEqual(final.count("            core/target/release/swirl-diagnose.exe\n"), 1)
        portable, windows = final.split("  windows-rust:\n")
        for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC"):
            portable_guard = f'          test -x "${name}"\n'
            windows_guard = f"          if (-not (Test-Path $env:{name} -PathType Leaf)) {{ throw 'Required Rust test binary missing' }}\n"
            self.assertEqual(portable.count(portable_guard), 1)
            self.assertEqual(windows.count(windows_guard), 1)
            self.assertLess(portable.index(portable_guard), portable.index("          python ../tools/tests/test_rust_core.py\n"))
            self.assertLess(windows.index(windows_guard), windows.index("          python ../tools/tests/test_rust_core.py\n"))

    def test_connectivity_stage_rejects_partial_menus_guards_environment_and_artifact(self):
        final = development.updated_workflow(FIXTURE)
        broken = []
        for name in ("test_connectivity_diagnostics.py", "test_subscription_import.py"):
            command = f"          python ../tools/tests/{name}\n"
            broken.extend((final.replace(command, "", 1), final.replace(command, command * 2, 1),
                           final.replace(command + development.WINDOWS_STATUS_GUARD, command)))
        for marker in (
            '          export SWIRL_RUST_DIAGNOSTIC="$PWD/target/release/swirl-diagnose"\n',
            "          $env:SWIRL_RUST_DIAGNOSTIC=(Resolve-Path target/release/swirl-diagnose.exe).Path\n",
            '          test -x "$SWIRL_RUST_DIAGNOSTIC"\n',
            "          if (-not (Test-Path $env:SWIRL_RUST_INSPECTOR -PathType Leaf)) { throw 'Required Rust test binary missing' }\n",
            "            core/target/release/swirl-diagnose.exe\n",
        ):
            broken.extend((final.replace(marker, "", 1), final + marker))
        broken.append(final.replace("--workspace --lib --bins", "--workspace --bins", 1))
        for source in broken:
            with self.subTest(tail=source[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_historical_build_and_artifact_drift_are_not_silently_overwritten(self):
        for source in (
            FIXTURE.replace("cargo build --release --locked -p swirl-api", "cargo build --release", 1),
            FIXTURE.replace("core/target/release/swirl-inspect.exe\n", "core/target/debug/swirl-inspect.exe\n"),
            FIXTURE.replace("$env:SWIRL_RUST_INSPECTOR=", "$env:OTHER_INSPECTOR="),
        ):
            with self.subTest(tail=source[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_missing_binary_preflight_stops_before_a_suite_can_skip(self):
        updated = development.updated_workflow(FIXTURE)
        scripts = {}
        for windows, step_name, prefix, sentinel in (
            (False, "Independent portable protocol peers", "          test -x ",
             "printf 'SUITE_STARTED'"),
            (True, "Independent TLS and protocol peers", "          if (-not (Test-Path",
             "Write-Output 'SUITE_STARTED'"),
        ):
            with self.subTest(preflight=step_name):
                # Check both menus on every platform. Later build steps also
                # check artifacts, but those files do not exist at preflight.
                marker = f"      - name: {step_name}\n"
                self.assertEqual(updated.count(marker), 1)
                source = updated.split(marker, 1)[1].split("      - ", 1)[0]
                guards = [line.strip() for line in source.splitlines()
                          if line.startswith(prefix)]
                self.assertEqual(len(guards), 3)
                scripts[windows] = "\n".join([*guards, sentinel])
        windows = os.name == "nt"
        shell = shutil.which("pwsh" if windows else "bash")
        if shell is None:
            self.skipTest("The platform's GitHub Actions shell is unavailable")
        script = scripts[windows]
        command = ([shell, "-NoProfile", "-NonInteractive", "-Command", script] if windows
                   else [shell, "-e", "-c", script])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = {name: root / name for name in
                     ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC")}
            for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR"):
                paths[name].write_text("fixture\n", encoding="utf-8")
                paths[name].chmod(0o700)
            environment = {**os.environ, **{name: str(path) for name, path in paths.items()}}
            missing = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(missing.returncode, 0)
            self.assertNotIn("SUITE_STARTED", missing.stdout)
            paths["SWIRL_RUST_DIAGNOSTIC"].write_text("fixture\n", encoding="utf-8")
            paths["SWIRL_RUST_DIAGNOSTIC"].chmod(0o700)
            present = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(present.returncode, 0, present.stderr)
            self.assertEqual(present.stdout.strip(), "SUITE_STARTED")

    def test_branch_and_menu_drift_fail_closed(self):
        for source in (
            FIXTURE.replace("branches: [test, main]", "branches: [main]", 1),
            FIXTURE.replace("test_dns_tls.py", "test_dns_tls_renamed.py", 1),
            FIXTURE.replace("  windows-rust:\n", "  renamed-windows:\n"),
            FIXTURE.replace(
                "          python ../tools/tests/test_dns_tls.py\n"
                "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n",
                "          python ../tools/tests/test_dns_tls.py\n",
            ),
            FIXTURE + FIXTURE,
        ):
            with self.subTest(source=source[-80:]), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_partial_or_duplicate_new_test_menu_fails_closed(self):
        for injected in (
            "          python ../tools/tests/test_dns_https.py\n",
            "          python ../tools/tests/test_websocket_transport.py\n" * 2,
        ):
            source = FIXTURE.replace("  windows-rust:\n", injected + "  windows-rust:\n")
            with self.subTest(injected=injected), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_forks_other_branches_manual_events_and_other_workflows_cannot_write(self):
        forbidden = {
            "GITHUB_ACTIONS": (None, "false"),
            "GITHUB_REPOSITORY": (None, "other/Swirl"),
            "GITHUB_REF": (None, "refs/heads/main", "refs/heads/test", "refs/heads/work/other"),
            "GITHUB_EVENT_NAME": (None, "pull_request", "workflow_dispatch"),
            "GITHUB_WORKFLOW_REF": (None, "SOLHK/Swirl/.github/workflows/rust-core.yml@refs/heads/main"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self.make_repository(root)
            initial = workflow.read_bytes()
            for key, values in forbidden.items():
                for value in values:
                    environment = dict(ENVIRONMENT)
                    if value is None:
                        environment.pop(key)
                    else:
                        environment[key] = value
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        development.apply_update(root, environment)
                    self.assertEqual(workflow.read_bytes(), initial)

    def test_failed_late_validation_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self.make_repository(
                root, FIXTURE.replace("test_subscription_capture.py", "renamed.py")
            )
            initial = workflow.read_bytes()
            with self.assertRaises(ValueError):
                development.apply_update(root, ENVIRONMENT)
            self.assertEqual(workflow.read_bytes(), initial)

    def test_crlf_checkout_is_validated_without_a_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self.make_repository(root)
            initial = FIXTURE.replace("\n", "\r\n").encode("utf-8")
            workflow.write_bytes(initial)
            _, before, after = development.prepare_update(root)
            self.assertEqual(before, FIXTURE)
            self.assertNotEqual(before, after)
            self.assertEqual(workflow.read_bytes(), initial)

    def test_missing_suite_prevents_workflow_claiming_it_is_covered(self):
        for missing in (
            "tools/tests/test_websocket_transport.py",
            "tools/tests/test_policy_groups.py",
            "tools/tests/test_dns_negative.py",
            "tools/tests/test_native_probe.py",
            "tools/tests/test_connection_stages.py",
            "tools/tests/test_connectivity_diagnostics.py",
            "tools/tests/test_subscription_import.py",
            "tools/Verify-PublicRustCore.py",
            "tools/Diagnose-NativeConnectivity.py",
            "core/crates/swirl-api/src/bin/swirl-diagnose.rs",
        ):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(root)
                (root / missing).unlink()
                initial = workflow.read_bytes()
                with self.assertRaises(ValueError):
                    development.apply_update(root, ENVIRONMENT)
                self.assertEqual(workflow.read_bytes(), initial)

    def test_update_touches_only_the_allowed_workflow_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self.make_repository(root)
            sibling = workflow.with_name("core-development.yml")
            sibling.write_text("# Existing token and permissions\n", encoding="utf-8")
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            original_mode = workflow.stat().st_mode
            self.assertTrue(development.apply_update(root, ENVIRONMENT))
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before.keys(), after.keys())
            changed = [path.as_posix() for path in before if before[path] != after[path]]
            self.assertEqual(changed, [".github/workflows/rust-core.yml"])
            self.assertEqual(workflow.stat().st_mode, original_mode)
            self.assertFalse(development.apply_update(root, ENVIRONMENT))

    def test_symlink_target_or_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = self.make_repository(root)
            other = root / "untouched.yml"
            other.write_text(FIXTURE, encoding="utf-8")
            workflow.unlink()
            try:
                workflow.symlink_to(other)
            except OSError as error:
                self.skipTest(f"Symlink creation unavailable on this runner: {error}")
            with self.assertRaises(ValueError):
                development.apply_update(root, ENVIRONMENT)
            self.assertEqual(other.read_text(encoding="utf-8"), FIXTURE)
            workflow.unlink()
            workflow.parent.rmdir()
            relocated = root / "relocated"
            relocated.mkdir()
            (relocated / "rust-core.yml").write_text(FIXTURE, encoding="utf-8")
            workflow.parent.symlink_to(relocated, target_is_directory=True)
            with self.assertRaises(ValueError):
                development.apply_update(root, ENVIRONMENT)
            self.assertEqual((relocated / "rust-core.yml").read_text(encoding="utf-8"), FIXTURE)

    def test_checked_in_workflow_can_be_reviewed_and_contains_every_added_gate(self):
        root = Path(__file__).resolve().parents[2]
        _, before, after = development.prepare_update(root)
        for name in REQUIRED_TESTS:
            self.assertEqual(after.count(f"          python ../tools/tests/{name}\n"), 2)
        self.assertEqual(development.updated_workflow(after), after)
        # Preparation alone is read-only, including when this test runs before
        # the App has made its first workflow-file commit.
        self.assertEqual((root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
