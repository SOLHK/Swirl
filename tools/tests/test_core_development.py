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
    "test_reality_peer.py",
    "test_reality_tls.py",
    "test_product_subscription_chain.py",
)
REALITY_BUILD = "cargo build --release --locked -p swirl-transport --example reality-client"
BINARY_NAMES = ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_DIAGNOSTIC",
                "SWIRL_REALITY_CLIENT")
PIP_COMMAND = "          python -m pip install cryptography==50.0.2\n"
REALITY_VECTOR_COMMAND = "          python ../tools/tests/generate_reality_vectors.py --check\n"
VISION_VECTOR_COMMAND = "          python ../tools/tests/generate_vision_vectors.py --check\n"
VISION_FILES = (
    "tools/tests/generate_vision_vectors.py",
    "core/crates/swirl-protocol/tests/fixtures/vision-v1.txt",
    "core/crates/swirl-protocol/tests/fixtures/flow-v1.txt",
)


def vector_fixture(source, stage):
    """Independent fixture construction; never uses the updater's block definitions."""
    separator = "  windows-rust:\n"
    parts = source.split(separator)
    for index, part in enumerate(parts):
        status = "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n" if index else ""
        harness = ("          $env:SWIRL_RUST_HARNESS=(Resolve-Path target/release/swirl-api.exe).Path\n"
                   if index else '          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"\n')
        historical = PIP_COMMAND + harness
        reality = PIP_COMMAND + status + REALITY_VECTOR_COMMAND + status + harness
        final = PIP_COMMAND + status + REALITY_VECTOR_COMMAND + status + VISION_VECTOR_COMMAND + status + harness
        original = next((block for block in (final, reality, historical) if part.count(block) == 1), None)
        if original is None:
            raise AssertionError("Fixture's Python vector prefix drifted")
        parts[index] = part.replace(original, (historical, reality, final)[stage], 1)
    return separator.join(parts)


def previous_reality_stage(source):
    """Strip the entire later TLS-peer stage before making historical fixtures."""
    source = development.without_product_chain_steps(source)
    source = development.without_vision_xray_steps(source)
    source = development.without_xray_steps(source)
    source = vector_fixture(source, 0)
    separator = "  windows-rust:\n"
    parts = source.split(separator)
    for index, part in enumerate(parts):
        for before, after, _ in development._reality_blocks(windows=index == 1):
            part = part.replace(after, before, 1)
        parts[index] = part
    return separator.join(parts)


def previous_socks5_udp_stage(source):
    source = previous_reality_stage(source)
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
    def test_check_command_rejects_pending_update_without_writing(self):
        script = Path(development.__file__).read_bytes()
        for current in (False, True):
            with self.subTest(current=current), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(
                    root, development.updated_workflow(FIXTURE) if current else FIXTURE)
                (root / "tools/ApplyCoreDevelopment.py").write_bytes(script)
                before = workflow.read_bytes()
                result = subprocess.run(
                    [sys.executable, "tools/ApplyCoreDevelopment.py", "--check"],
                    cwd=root, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0 if current else 1, result.stderr)
                self.assertEqual(workflow.read_bytes(), before)
                self.assertEqual("@@" in result.stdout, not current)

    @unittest.skipIf(os.name == "nt", "The App source-identity job executes on Linux")
    def test_app_source_identity_shell_rejects_real_git_drift(self):
        # Execute the actual App shell with a real local Git repository. No
        # network, token, source formatting or branch write is needed.
        repository = Path(__file__).resolve().parents[2]
        source = (repository / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertNotIn("git push", source)
        self.assertNotIn("git add", source)
        self.assertNotIn("[swirl-core-autofix]", source)
        self.assertIn("          ref: ${{ github.sha }}\n", source)

        def body(title):
            step = source.split(f"      - name: {title}\n", 1)[1].split("      - ", 1)[0]
            return "\n".join(line[10:] for line in step.split("        run: |\n", 1)[1].splitlines()) + "\n"

        preflight = body("Verify exact pushed source and reviewed CI gates")
        export = body("Export exact source and result identity")
        cases = ("clean", "wrong-trigger", "formatter-write", "missing-gate",
                 "unstaged", "staged", "untracked", "moved-head", "wrong-tested")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                parent = Path(temporary)
                root, shim = parent / "repo", parent / "bin"
                root.mkdir()
                shim.mkdir()
                for relative in ("core/source.rs", "tools/tests/fixture.py", ".github/workflows/fixture.yml",
                                 "src/Swirl.Quick/engine/fixture.cpp", "src/Swirl.Quick/tests/fixture.cpp"):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("synthetic source\n", encoding="utf-8")
                (root / "tools/ApplyCoreDevelopment.py").write_text(
                    "import sys\nassert sys.argv[1:] == ['--check']\n"
                    f"raise SystemExit({1 if case == 'missing-gate' else 0})\n", encoding="utf-8")
                cargo = shim / "cargo"
                cargo.write_bytes(
                    b"#!/bin/sh\ntest \"$*\" = 'fmt --manifest-path core/Cargo.toml --all -- --check' || exit 23\n"
                    + (b"printf 'unexpected format write\\n' >> core/source.rs\n" if case == "formatter-write" else b""))
                cargo.chmod(0o755)

                def git(*args):
                    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.STDOUT).decode().strip()

                git("init", "-q")
                git("config", "user.name", "Source identity test")
                git("config", "user.email", "source-identity@example.invalid")
                git("add", ".")
                git("commit", "-qm", "Original source")
                original = git("rev-parse", "HEAD")
                environment = dict(os.environ, GITHUB_REF=development.DEVELOPMENT_REF,
                                   GITHUB_SHA="0" * 40 if case == "wrong-trigger" else original)
                environment["PATH"] = str(shim) + os.pathsep + environment.get("PATH", "")
                checked = subprocess.run(["bash", "-c", preflight], cwd=root, env=environment,
                                         capture_output=True, text=True, timeout=15)
                if case in ("wrong-trigger", "formatter-write", "missing-gate"):
                    self.assertNotEqual(checked.returncode, 0)
                    self.assertFalse((root / "CORE_TESTED_COMMIT").exists())
                    continue
                self.assertEqual(checked.returncode, 0, checked.stderr)
                if case in ("unstaged", "staged", "moved-head"):
                    (root / "core/source.rs").write_text("changed during tests\n", encoding="utf-8")
                    if case != "unstaged":
                        git("add", "core/source.rs")
                    if case == "moved-head":
                        git("commit", "-qm", "Unexpected changed source")
                elif case == "untracked":
                    (root / "core/injected.rs").write_text("unexpected source\n", encoding="utf-8")
                elif case == "wrong-tested":
                    (root / "CORE_TESTED_COMMIT").write_text("0" * 40 + "\n", encoding="utf-8")
                exported = subprocess.run(["bash", "-c", export], cwd=root, env=environment,
                                          capture_output=True, text=True, timeout=15)
                self.assertEqual(exported.returncode == 0, case == "clean", exported.stderr)
                self.assertEqual((root / "CORE_TRIGGER_COMMIT").read_text().strip(), original)
                self.assertTrue((root / "core-tested-source.tar").is_file())
                if case in ("unstaged", "staged", "moved-head"):
                    self.assertIn("changed during tests", (root / "CORE_SOURCE_DIFF.patch").read_text())
                if case == "untracked":
                    self.assertIn("core/injected.rs", (root / "CORE_UNTRACKED_SOURCE").read_text())

    def test_app_existing_peer_menu_requires_built_subscription_inspector(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        build_title = "      - name: Rust static and unit checks\n"
        peer_title = "      - name: Independent network peers\n"
        self.assertEqual(source.count(build_title), 1)
        self.assertEqual(source.count(peer_title), 1)
        self.assertLess(source.index(build_title), source.index(peer_title))
        build = source.split(build_title, 1)[1].split("      - ", 1)[0]
        self.assertIn("        working-directory: core\n", build)
        self.assertIn("          cargo build --release --locked -p swirl-api --bins\n", build)
        menu = source.split(peer_title, 1)[1].split("      - ", 1)[0]
        for step in (build, menu):
            self.assertNotIn("        if:", step)
            self.assertNotIn("continue-on-error:", step)
        self.assertIn("          set -euo pipefail\n", menu)
        export = '          export SWIRL_RUST_INSPECTOR="$PWD/core/target/release/swirl-inspect"\n'
        preflight = '          test -x "$SWIRL_RUST_INSPECTOR"\n'
        self.assertEqual(menu.count(export), 1)
        self.assertEqual(menu.count(preflight), 1)
        self.assertLess(menu.index(export), menu.index(preflight))
        self.assertLess(menu.index(preflight), menu.index("          python tools/tests/test_reality_peer.py\n"))
        self.assertIn("          if test -f tools/tests/test_socks4.py; then python tools/tests/test_socks4.py; fi\n", menu)

    def test_product_chain_gates_use_release_binaries_and_preserve_exact_evidence(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        self.assertEqual(development.updated_workflow(source), source)
        final = development.updated_workflow(FIXTURE)
        previous = development.without_product_chain_steps(final)
        self.assertNotIn("test_product_subscription_chain.py", previous)
        self.assertEqual(development.updated_workflow(previous), final)
        app = (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertIn("cargo build --release --locked -p swirl-api --bins\n", app)
        jobs = [("linux/macos", source.split("  windows-rust:\n")[0], False, False),
                ("windows", source.split("  windows-rust:\n")[1], True, False),
                ("windows Qt", source.split("  windows-rust:\n")[1], True, True),
                ("app", app, False, False)]
        for label, part, windows, qt in jobs:
            with self.subTest(job=label):
                title = ("Subscription through persisted Qt product configuration" if qt
                         else "Subscription to native proxy and target")
                step = part.split(f"      - name: {title}\n", 1)[1].split("      - ", 1)[0]
                self.assertIn("        working-directory: .\n", step)
                self.assertNotIn("        if:", step)
                self.assertNotIn("continue-on-error:", step)
                suffix = ".exe" if windows else ""
                for variable, binary in (("SWIRL_RUST_HARNESS", "swirl-api"),
                                         ("SWIRL_RUST_INSPECTOR", "swirl-inspect")):
                    self.assertIn(f"{variable}: ${{{{ github.workspace }}}}/core/target/release/{binary}{suffix}\n", step)
                    check = (f"if (-not (Test-Path $env:{variable} -PathType Leaf))"
                             if windows else f'test -x "${variable}"')
                    self.assertIn(check, step)
                stage = "qt" if qt else "rust"
                self.assertIn(f"SWIRL_PRODUCT_EVIDENCE: ${{{{ runner.temp }}}}/swirl-product-chain-{stage}\n", step)
                selection = " ProductQtIntegration" if qt else ""
                command = f"          python tools/tests/test_product_subscription_chain.py{selection} -v\n"
                self.assertEqual(step.count(command), 1)
                if windows:
                    self.assertIn(command + "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n", step)
                else:
                    self.assertIn("          set -euo pipefail\n", step)
                if qt:
                    self.assertIn("SWIRL_RUST_QT_TESTS: ${{ github.workspace }}/build/rust-qt/Release/SwirlRustCoreTests.exe\n", step)
                    self.assertIn("if (-not (Test-Path $env:SWIRL_RUST_QT_TESTS -PathType Leaf))", step)
                    self.assertLess(part.index("Run Qt to Rust integration without Mihomo"), part.index(title))
                    self.assertLess(part.index(title), part.index("Build complete native Rust application"))
                artifact = part.split(f"      - name: Preserve subscription product {stage} evidence\n", 1)[1].split("      - ", 1)[0]
                self.assertIn("        if: always()\n", artifact)
                self.assertIn("          if-no-files-found: error\n", artifact)
                self.assertIn("${{ github.sha }}-${{ github.run_attempt }}", artifact)
                self.assertIn(f"path: ${{{{ runner.temp }}}}/swirl-product-chain-{stage}\n", artifact)

    def test_product_chain_partial_blocks_wrong_binaries_and_failure_bypasses_are_rejected(self):
        final = development.updated_workflow(FIXTURE)
        for windows, qt in ((False, False), (True, False), (True, True)):
            block = development.product_chain_steps(windows=windows, qt=qt)
            edits = ["", block * 2,
                     block.replace("working-directory: .", "working-directory: core", 1),
                     block.replace("release/swirl-inspect", "debug/swirl-inspect", 1),
                     block.replace("release/swirl-api", "release/wrong-api", 1),
                     block.replace("SWIRL_PRODUCT_EVIDENCE:", "UNREVIEWED_EVIDENCE:", 1),
                     block.replace("        run: |\n", "        continue-on-error: true\n        run: |\n", 1),
                     block.replace("        run: |\n", "        if: false\n        run: |\n", 1),
                     block.replace("        if: always()\n", "        if: success()\n", 1),
                     block.replace("if-no-files-found: error", "if-no-files-found: ignore", 1),
                     block.replace("${{ github.sha }}", "unverified-source", 1)]
            if windows:
                edits.append(block.replace(development.WINDOWS_STATUS_GUARD, "", 1))
                edits.append(block.replace("Test-Path $env:SWIRL_RUST_INSPECTOR", "Test-Path $env:SWIRL_RUST_HARNESS", 1))
            else:
                edits.append(block.replace('          test -x "$SWIRL_RUST_INSPECTOR"\n', "", 1))
                edits.append(block.replace("set -euo pipefail", "set -u", 1))
            if qt:
                edits.append(block.replace(" ProductQtIntegration -v", " ProductChainIntegration -v", 1))
                edits.append(block.replace("Release/SwirlRustCoreTests.exe", "Debug/SwirlRustCoreTests.exe", 1))
            for index, edit in enumerate(edits):
                with self.subTest(windows=windows, qt=qt, drift=index), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    workflow = self.make_repository(root, final.replace(block, edit, 1))
                    before = workflow.read_bytes()
                    with self.assertRaises(ValueError):
                        development.apply_update(root, ENVIRONMENT)
                    self.assertEqual(workflow.read_bytes(), before)

    def test_product_chain_shell_propagates_missing_binary_and_peer_failure(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        windows = os.name == "nt"
        part = source.split("  windows-rust:\n")[int(windows)]
        for qt in ((False, True) if windows else (False,)):
            title = ("Subscription through persisted Qt product configuration" if qt
                     else "Subscription to native proxy and target")
            body = part.split(f"      - name: {title}\n", 1)[1].split("        run: |\n", 1)[1].split("      - ", 1)[0]
            body = "\n".join(line[10:] for line in body.splitlines() if line.strip()) + "\n"
            body += "Write-Output 'AFTER_PRODUCT_PEER'\n" if windows else "echo AFTER_PRODUCT_PEER\n"
            for missing, peer_exit in ((None, 0), (None, 29), ("SWIRL_RUST_INSPECTOR", 0)):
                with self.subTest(qt=qt, missing=missing, peer_exit=peer_exit), tempfile.TemporaryDirectory() as temporary:
                    work = Path(temporary)
                    script = work / "tools/tests/test_product_subscription_chain.py"
                    script.parent.mkdir(parents=True)
                    script.write_text("from pathlib import Path\nPath('PEER_WAS_RUN').touch()\n"
                                      f"raise SystemExit({peer_exit})\n", encoding="utf-8")
                    environment = dict(os.environ, SWIRL_TEST_ROOT=str(work / "qt-root"))
                    for name in ("SWIRL_RUST_HARNESS", "SWIRL_RUST_INSPECTOR", "SWIRL_RUST_QT_TESTS"):
                        path = work / name
                        if name != missing:
                            path.write_text("synthetic executable identity\n", encoding="utf-8")
                            path.chmod(0o755)
                        environment[name] = str(path)
                    if windows:
                        shell = work / "gate.ps1"
                        shell.write_text(body, encoding="utf-8")
                        args = ["pwsh", "-NoProfile", "-File", str(shell)]
                    else:
                        args = ["bash", "-c", body]
                    result = subprocess.run(args, cwd=work, env=environment,
                                            capture_output=True, text=True, timeout=15)
                    if missing:
                        self.assertNotEqual(result.returncode, 0)
                    else:
                        self.assertEqual(result.returncode, peer_exit, result.stderr)
                    self.assertEqual((work / "PEER_WAS_RUN").exists(), missing is None)
                    self.assertEqual("AFTER_PRODUCT_PEER" in result.stdout, missing is None and peer_exit == 0)

    def make_repository(self, root, source=FIXTURE):
        workflow = root / ".github/workflows/rust-core.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(source, encoding="utf-8")
        peers = root / "tools/tests"
        peers.mkdir(parents=True)
        for name in REQUIRED_TESTS:
            (peers / name).write_text("# test fixture\n", encoding="utf-8")
        (peers / development.REALITY_RUNTIME_TEST).write_text("# runtime peer fixture\n", encoding="utf-8")
        (root / "tools/Verify-PublicRustCore.py").write_text("# public check fixture\n", encoding="utf-8")
        (root / development.PUBLIC_REALITY_PROBE).write_text("# public REALITY check fixture\n", encoding="utf-8")
        (root / "tools/Diagnose-NativeConnectivity.py").write_text("# diagnostic fixture\n", encoding="utf-8")
        diagnostic = root / "core/crates/swirl-api/src/bin/swirl-diagnose.rs"
        diagnostic.parent.mkdir(parents=True)
        diagnostic.write_text("// diagnostic fixture\n", encoding="utf-8")
        for relative in development.REALITY_SOURCES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# synthetic REALITY source fixture\n", encoding="utf-8")
        for relative in VISION_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# public synthetic Vision fixture\n", encoding="utf-8")
        for relative in development.XRAY_SOURCES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# public synthetic Xray fixture\n", encoding="utf-8")
        for relative in development.VISION_XRAY_SOURCES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# public synthetic Vision stream fixture\n", encoding="utf-8")
        return workflow

    def test_reality_runtime_gates_require_actual_binary_and_preserve_every_prior_gate(self):
        final = development.updated_workflow(FIXTURE)
        previous = development.without_reality_runtime_steps(final)
        self.assertNotIn("test_reality_runtime.py", previous)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(development.updated_workflow(final), final)
        for windows, part in enumerate(final.split("  windows-rust:\n")):
            block = development.reality_runtime_steps(windows=bool(windows))
            self.assertEqual(part.count(block), 1)
            self.assertLess(part.index("python tools/Build-XrayPeer.py"), part.index(block))
            if windows:
                self.assertIn(development.reality_runtime_steps(windows=True, qt=True)
                              + development.reality_runtime_steps(windows=True, qt=True, vision=True)
                              + development.NATIVE_APPLICATION_BUILD, part)
        for source in (
            final.replace("python tools/tests/test_reality_runtime.py\n", "python tools/tests/test_reality_runtime.py || true\n", 1),
            final.replace(development.reality_runtime_steps(windows=True, qt=True), "", 1),
            final.replace("python tools/tests/test_reality_runtime.py --qt\n" + development.WINDOWS_STATUS_GUARD,
                          "python tools/tests/test_reality_runtime.py --qt\n", 1),
        ):
            with self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_combined_vision_runtime_upgrades_intact_p0_and_rejects_changed_gates(self):
        final = development.updated_workflow(FIXTURE)
        combinations = ({}, {"windows": True}, {"windows": True, "qt": True})
        previous = development.without_public_reality_runtime_steps(final)
        for flags in combinations:
            base = development.reality_runtime_steps(**flags)
            combined = development.reality_runtime_steps(**flags, vision=True)
            self.assertEqual(final.count(base + combined), 1)
            previous = previous.replace(combined, "", 1)
            self.assertIn("swirl-reality-vision-runtime-", combined)
            self.assertIn("if-no-files-found: error", combined)
            self.assertIn("if: always()", combined)
            self.assertIn("--vision\n", combined)
            broken = [combined.replace(" --vision\n", "\n"),
                      combined.replace("if: always()", "if: success()"),
                      combined.replace("swirl-reality-vision-runtime-", "swirl-reality-runtime-"),
                      ""]
            if flags.get("windows"):
                broken.append(combined.replace(development.WINDOWS_STATUS_GUARD, ""))
            for replacement in broken:
                with self.subTest(flags=flags, replacement=replacement), self.assertRaises(ValueError):
                    development.updated_workflow(final.replace(combined, replacement, 1))
            with self.assertRaises(ValueError):
                development.updated_workflow(final.replace(base + combined, combined + base, 1))
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(development.updated_workflow(final), final)
        app = (Path(__file__).resolve().parents[2] / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertIn(development.reality_runtime_steps(artifact_prefix="App")
                      + development.reality_runtime_steps(artifact_prefix="App", vision=True), app)

    def test_public_reality_and_vision_gates_are_required_linux_only_and_fail_closed(self):
        final = development.updated_workflow(FIXTURE)
        previous = development.without_public_reality_runtime_steps(final)
        self.assertNotIn(development.PUBLIC_REALITY_PROBE.as_posix(), previous)
        self.assertEqual(development.updated_workflow(previous), final)
        portable, windows = final.split("  windows-rust:\n")
        for vision in (False, True):
            block = development.public_reality_runtime_steps(vision=vision)
            self.assertEqual(portable.count(block), 1)
            self.assertNotIn(block, windows)
            self.assertIn("if: runner.os == 'Linux'", block)
            self.assertIn("if: always() && runner.os == 'Linux'", block)
            self.assertIn("if-no-files-found: error", block)
            for broken in ("", block + block,
                           block.replace("if: runner.os == 'Linux'", "if: false"),
                           block.replace("set -euo pipefail", "set +e"),
                           block.replace("if: always() && runner.os == 'Linux'", "if: success()"),
                           block.replace("--output", "--disabled-output"),
                           block.replace("report.json", "../private.json")):
                with self.subTest(vision=vision, broken=broken), self.assertRaises(ValueError):
                    development.updated_workflow(final.replace(block, broken, 1))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = self.make_repository(root)
            original = target.read_bytes()
            (root / development.PUBLIC_REALITY_PROBE).unlink()
            with self.assertRaises(ValueError):
                development.prepare_update(root)
            self.assertEqual(target.read_bytes(), original)

    def test_vision_stage_upgrades_both_reviewed_histories_and_is_idempotent(self):
        final = development.updated_workflow(FIXTURE)
        self.assertEqual(final.count(REALITY_VECTOR_COMMAND), 2)
        self.assertEqual(final.count(VISION_VECTOR_COMMAND), 2)
        for stage in (0, 1, 2):
            with self.subTest(stage=stage):
                self.assertEqual(development.updated_workflow(vector_fixture(final, stage)), final)
        for index, part in enumerate(final.split("  windows-rust:\n")):
            status = development.WINDOWS_STATUS_GUARD if index else ""
            prefix = PIP_COMMAND + status + REALITY_VECTOR_COMMAND + status + VISION_VECTOR_COMMAND + status
            self.assertEqual(part.count(prefix), 1)
            self.assertLess(part.index(prefix), part.index("SWIRL_RUST_HARNESS"))

    def test_vision_partial_duplicate_modes_order_and_windows_exits_fail_closed(self):
        final = vector_fixture(development.updated_workflow(FIXTURE), 2)
        status = development.WINDOWS_STATUS_GUARD
        broken = [
            final.replace(VISION_VECTOR_COMMAND, "", 1),
            final.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND * 2, 1),
            final.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND.replace("--check", "--write"), 1),
            final.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND.replace(" --check", ""), 1),
            final.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND.rstrip() + " || true\n", 1),
            final.replace(VISION_VECTOR_COMMAND + status, VISION_VECTOR_COMMAND, 1),
            final.replace(VISION_VECTOR_COMMAND + status, VISION_VECTOR_COMMAND + "          exit 0\n", 1),
            final.replace(REALITY_VECTOR_COMMAND, "", 1),
            final.replace(REALITY_VECTOR_COMMAND, REALITY_VECTOR_COMMAND * 2, 1),
            final.replace(REALITY_VECTOR_COMMAND + status, REALITY_VECTOR_COMMAND, 1),
            final.replace(PIP_COMMAND + status, PIP_COMMAND, 1),
            final.replace(REALITY_VECTOR_COMMAND + VISION_VECTOR_COMMAND,
                          VISION_VECTOR_COMMAND + REALITY_VECTOR_COMMAND, 1),
            final.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND.replace("../tools", "tools"), 1),
        ]
        portable, windows = final.split("  windows-rust:\n")
        broken.append(portable.replace(VISION_VECTOR_COMMAND, "", 1)
                      + "  windows-rust:\n" + windows.replace(VISION_VECTOR_COMMAND, VISION_VECTOR_COMMAND * 2, 1))
        for index, source in enumerate(broken):
            with self.subTest(drift=index), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_vision_material_is_required_before_an_atomic_workflow_write(self):
        for missing in VISION_FILES:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(root)
                (root / missing).unlink()
                initial = workflow.read_bytes()
                with self.assertRaises(ValueError):
                    development.apply_update(root, ENVIRONMENT)
                self.assertEqual(workflow.read_bytes(), initial)

    def test_checked_in_rust_and_app_vector_menus_are_mandatory(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        self.assertEqual(source.count(VISION_VECTOR_COMMAND), 2)
        self.assertEqual(development.updated_workflow(source), source)
        for index, part in enumerate(source.split("  windows-rust:\n")):
            status = development.WINDOWS_STATUS_GUARD if index else ""
            self.assertEqual(part.count(REALITY_VECTOR_COMMAND + status + VISION_VECTOR_COMMAND + status), 1)
        app = (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        prefix = ("          python tools/tests/generate_reality_vectors.py --check\n"
                  "          python tools/tests/generate_vision_vectors.py --check\n")
        self.assertEqual(app.count("generate_vision_vectors.py"), 1)
        marker = "      - name: Independent network peers\n"
        menu = app.split(marker, 1)[1].split("      - ", 1)[0]
        self.assertEqual(menu.count(prefix), 1)
        self.assertLess(menu.index("          set -euo pipefail\n"), menu.index(prefix))
        self.assertLess(menu.index(prefix), menu.index("          python tools/tests/test_reality_peer.py\n"))

    def test_vision_fixture_failure_stops_before_later_peer_execution(self):
        final = development.updated_workflow(FIXTURE)
        windows = os.name == "nt"
        part = final.split("  windows-rust:\n")[int(windows)]
        status = development.WINDOWS_STATUS_GUARD if windows else ""
        command = VISION_VECTOR_COMMAND + status
        self.assertEqual(part.count(command), 1)
        shell = shutil.which("pwsh" if windows else "bash")
        if shell is None:
            self.skipTest("The platform's GitHub Actions shell is unavailable")
        sentinel = "Write-Output 'PEERS_STARTED'" if windows else "printf 'PEERS_STARTED'"
        script = command + sentinel
        invocation = ([shell, "-NoProfile", "-NonInteractive", "-Command", script] if windows
                      else [shell, "-e", "-c", script])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "core").mkdir()
            generator = root / "tools/tests/generate_vision_vectors.py"
            generator.parent.mkdir(parents=True)
            generator.write_text("raise SystemExit(7)\n", encoding="utf-8")
            failed = subprocess.run(invocation, cwd=root / "core", capture_output=True, text=True, timeout=5)
            self.assertEqual(failed.returncode, 7)
            self.assertNotIn("PEERS_STARTED", failed.stdout)
            generator.write_text("raise SystemExit(0)\n", encoding="utf-8")
            passed = subprocess.run(invocation, cwd=root / "core", capture_output=True, text=True, timeout=5)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(passed.stdout.strip(), "PEERS_STARTED")

    def test_adds_only_reviewed_tests_and_exact_development_trigger(self):
        updated = development.updated_workflow(FIXTURE)
        portable, windows = updated.split("  windows-rust:\n")
        for name in REQUIRED_TESTS:
            command = (f"          python tools/tests/{name} -v\n" if name == "test_product_subscription_chain.py"
                       else f"          python ../tools/tests/{name}\n")
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

    def test_reality_stage_builds_release_preflights_and_runs_peers_first(self):
        final = development.updated_workflow(FIXTURE)
        self.assertEqual(final.count(REALITY_BUILD), 2)
        previous = previous_reality_stage(final)
        self.assertNotIn("SWIRL_REALITY_CLIENT", previous)
        self.assertNotIn("test_reality_", previous)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(development.updated_workflow(final), final)
        # The separately guarded product steps repeat their own preflight.
        historical_menu = development.without_product_chain_steps(final)
        for windows, part in enumerate(historical_menu.split("  windows-rust:\n")):
            first_peer = part.index("          python ../tools/tests/test_reality_peer.py\n")
            tls_peer = part.index("          python ../tools/tests/test_reality_tls.py\n")
            self.assertLess(part.index(REALITY_BUILD), first_peer)
            self.assertLess(part.index("python -m pip install cryptography==50.0.2"), first_peer)
            self.assertLess(first_peer, tls_peer)
            self.assertLess(tls_peer, part.index("          python ../tools/tests/test_rust_core.py\n"))
            for name in BINARY_NAMES:
                guard = (f"          if (-not (Test-Path $env:{name} -PathType Leaf)) {{ throw 'Required Rust test binary missing' }}\n"
                         if windows else f'          test -x "${name}"\n')
                self.assertEqual(part.count(guard), 1)
                self.assertLess(part.index(guard), first_peer)
            if windows:
                self.assertIn(REALITY_BUILD + "\n" + development.WINDOWS_STATUS_GUARD, part)
                self.assertIn("$env:SWIRL_REALITY_CLIENT=(Resolve-Path target/release/examples/reality-client.exe).Path\n", part)
                for name in ("test_reality_peer.py", "test_reality_tls.py"):
                    self.assertIn(f"          python ../tools/tests/{name}\n" + development.WINDOWS_STATUS_GUARD, part)
            else:
                self.assertIn('export SWIRL_REALITY_CLIENT="$PWD/target/release/examples/reality-client"\n', part)

    def test_reality_partial_build_environment_preflight_or_suites_fail_closed(self):
        final = development.updated_workflow(FIXTURE)
        commands = [f"          python ../tools/tests/{name}\n"
                    for name in ("test_reality_peer.py", "test_reality_tls.py")]
        markers = [
            '          export SWIRL_REALITY_CLIENT="$PWD/target/release/examples/reality-client"\n',
            "          $env:SWIRL_REALITY_CLIENT=(Resolve-Path target/release/examples/reality-client.exe).Path\n",
            '          test -x "$SWIRL_REALITY_CLIENT"\n',
            "          if (-not (Test-Path $env:SWIRL_REALITY_CLIENT -PathType Leaf)) { throw 'Required Rust test binary missing' }\n",
            *commands,
        ]
        broken = []
        for marker in markers:
            broken.extend((final.replace(marker, "", 1), final.replace(marker, marker * 2, 1)))
        for command in commands:
            broken.append(final.replace(command + development.WINDOWS_STATUS_GUARD, command, 1))
        broken.extend((
            final.replace(REALITY_BUILD, REALITY_BUILD.replace("--release ", ""), 1),
            final.replace(REALITY_BUILD, REALITY_BUILD.replace("--example reality-client", "--lib"), 1),
            final.replace(REALITY_BUILD + "\n" + development.WINDOWS_STATUS_GUARD, REALITY_BUILD + "\n", 1),
            final.replace("target/release/examples/reality-client", "target/debug/examples/reality-client", 1),
        ))
        for index, source in enumerate(broken):
            with self.subTest(drift=index), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_app_workflow_builds_and_requires_the_same_real_peer_client(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertEqual(source.count(REALITY_BUILD + "\n"), 1)
        marker = "      - name: Independent network peers\n"
        menu = source.split(marker, 1)[1].split("      - ", 1)[0]
        expected = (
            '          export SWIRL_REALITY_CLIENT="$PWD/core/target/release/examples/reality-client"\n'
            '          test -x "$SWIRL_RUST_HARNESS"\n'
            '          test -x "$SWIRL_RUST_INSPECTOR"\n'
            '          test -x "$SWIRL_REALITY_CLIENT"\n'
            '          python tools/tests/test_reality_peer.py\n'
            '          python tools/tests/test_reality_tls.py\n'
            '          python tools/tests/test_rust_core.py\n'
        )
        self.assertEqual(menu.count(expected), 1)
        self.assertLess(menu.index("python -m pip install cryptography==50.0.2"), menu.index(expected))
        self.assertIn("          set -euo pipefail\n", menu)
        self.assertLess(source.index(REALITY_BUILD), source.index(marker))
        # Include the peer builder and CI source as well as the actual test code.
        self.assertIn('git archive "$GITHUB_SHA" core tools .github/workflows src/Swirl.Quick/engine src/Swirl.Quick/tests > core-tested-source.tar\n', source)

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
        portable, windows = development.without_product_chain_steps(final).split("  windows-rust:\n")
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
                self.assertEqual(len(guards), 4)
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
            paths = {name: root / name for name in BINARY_NAMES}
            for path in paths.values():
                path.write_text("fixture\n", encoding="utf-8")
                path.chmod(0o700)
            environment = {**os.environ, **{name: str(path) for name, path in paths.items()}}
            for name, path in paths.items():
                with self.subTest(missing_binary=name):
                    path.unlink()
                    missing = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(missing.returncode, 0)
                    self.assertNotIn("SUITE_STARTED", missing.stdout)
                    path.write_text("fixture\n", encoding="utf-8")
                    path.chmod(0o700)
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
            "tools/tests/test_reality_peer.py",
            "tools/tests/test_reality_tls.py",
            "tools/tests/reality_peer.py",
            "core/crates/swirl-transport/examples/reality-client.rs",
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
            command = (f"          python tools/tests/{name} -v\n" if name == "test_product_subscription_chain.py"
                       else f"          python ../tools/tests/{name}\n")
            self.assertEqual(after.count(command), 2)
        self.assertEqual(development.updated_workflow(after), after)
        # Preparation alone is read-only, including when this test runs before
        # the App has made its first workflow-file commit.
        self.assertEqual((root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8"), before)

    def test_xray_stage_is_complete_pinned_and_after_the_existing_peers(self):
        root = Path(__file__).resolve().parents[2]
        final = development.updated_workflow(FIXTURE)
        previous = development.without_xray_steps(development.without_vision_xray_steps(final))
        self.assertNotIn("test_reality_xray.py", previous)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(development.updated_workflow(final), final)
        parts = final.split("  windows-rust:\n")
        for index, part in enumerate(parts):
            self.assertEqual(part.count("go-version: '1.27.2'"), 1)
            self.assertIn("actions/setup-go@924ae3a1cded613372ab5595356fb5720e22ba16", part)
            self.assertIn("          cache: false\n", part)
            self.assertEqual(part.count("python tools/tests/test_reality_xray.py\n"), 1)
            self.assertLess(part.index("python ../tools/tests/test_reality_tls.py"),
                            part.index("python tools/Build-XrayPeer.py"))
            self.assertLess(part.index("python tools/Build-XrayPeer.py"),
                            part.index("python tools/tests/test_reality_xray.py"))
            evidence = part.split("      - name: Preserve Xray build", 1)[1].split("      - ", 1)[0]
            self.assertIn("        if: always()\n", evidence)
            self.assertIn("          if-no-files-found: error\n", evidence)
            self.assertIn("build-manifest.json", evidence)
            self.assertIn("build.log", evidence)
            self.assertIn("${{ github.sha }}", evidence)
            if index:
                self.assertIn("reality-client.exe\n", part)
                self.assertIn("python tools/tests/test_reality_xray.py\n" + development.WINDOWS_STATUS_GUARD, part)
        app = (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertIn("          ref: ${{ github.sha }}\n", app)
        self.assertEqual(app.count("python tools/tests/test_reality_xray.py\n"), 1)
        self.assertIn(development.xray_steps(artifact_prefix="App-REALITY-Xray"), app)

    def test_xray_partial_missing_duplicate_and_ignored_failure_are_rejected(self):
        final = development.updated_workflow(FIXTURE)
        command = "          python tools/tests/test_reality_xray.py\n"
        bad = (
            final.replace(command, "", 1),
            final.replace(command, command * 2, 1),
            final.replace(command, command.rstrip() + " || true\n", 1),
            final.replace(command + development.WINDOWS_STATUS_GUARD, command, 1),
            final.replace("go-version: '1.27.2'", "go-version: 'stable'", 1),
            final.replace("setup-go@924ae3a1cded613372ab5595356fb5720e22ba16", "setup-go@v6", 1),
            final.replace("build-manifest.json", "unrelated.json", 1),
            final.replace("          if-no-files-found: error\n", "          if-no-files-found: ignore\n", 1),
            final.replace(development.xray_steps(), "", 1),
            final.replace(development.xray_steps(windows=True), "", 1),
            final + command,
        )
        for source in bad:
            with self.subTest(source=source[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(source)

    def test_xray_missing_material_prevents_any_workflow_write(self):
        for missing in development.XRAY_SOURCES:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(root)
                before = workflow.read_bytes()
                (root / missing).unlink()
                with self.assertRaises(ValueError):
                    development.apply_update(root, ENVIRONMENT)
                self.assertEqual(workflow.read_bytes(), before)

    def test_xray_build_failure_cannot_run_the_peer_or_become_success(self):
        # Execute the checked-in shell body with a failing builder. This tests
        # real exit propagation, independently of the textual migration guard.
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        windows = os.name == "nt"
        part = source.split("  windows-rust:\n")[int(windows)]
        body = part.split("      - name: Build pinned Xray and verify REALITY interoperability\n", 1)[1]
        body = body.split("        run: |\n", 1)[1].split("      - ", 1)[0]
        body = "\n".join(line[10:] for line in body.splitlines() if line.strip()) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "tools/tests").mkdir(parents=True)
            (work / "tools/Build-XrayPeer.py").write_text("raise SystemExit(23)\n", encoding="utf-8")
            (work / "tools/tests/test_reality_xray.py").write_text(
                "from pathlib import Path\nPath('PEER_WAS_RUN').write_text('bad')\n", encoding="utf-8")
            environment = dict(os.environ, SWIRL_XRAY_PEER_DIR=str(work / "peer"))
            if windows:
                script = work / "failure.ps1"
                script.write_text(body, encoding="utf-8")
                args = ["pwsh", "-NoProfile", "-File", str(script)]
            else:
                args = ["bash", "-c", body]
            result = subprocess.run(args, cwd=work, env=environment, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 23, result.stderr.decode(errors="replace"))
            self.assertFalse((work / "PEER_WAS_RUN").exists())

    def test_vision_xray_stage_preserves_r3_and_is_idempotent_on_all_jobs(self):
        root = Path(__file__).resolve().parents[2]
        final = development.updated_workflow(FIXTURE)
        previous = development.without_vision_xray_steps(final)
        self.assertNotIn("test_vision_xray.py", previous)
        self.assertNotIn("vision-client", previous)
        self.assertEqual(development.updated_workflow(previous), final)
        self.assertEqual(development.updated_workflow(final), final)
        for windows, part in enumerate(final.split("  windows-rust:\n")):
            self.assertEqual(part.count(development.xray_steps(windows=bool(windows))), 1)
            self.assertEqual(part.count(development.vision_xray_steps(windows=bool(windows))), 1)
            self.assertIn(development.xray_steps(windows=bool(windows))
                          + development.vision_xray_steps(windows=bool(windows)), part)
        checked_in = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        self.assertIn("os: [ubuntu-latest, macos-latest]", checked_in)
        self.assertIn("runs-on: windows-2022", checked_in)
        self.assertEqual(development.updated_workflow(checked_in), checked_in)
        app = (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")
        self.assertIn("          ref: ${{ github.sha }}\n", app)
        self.assertIn(development.xray_steps(artifact_prefix="App-REALITY-Xray")
                      + development.vision_xray_steps(artifact_prefix="App-Vision-Xray"), app)
        for label, part in (
            ("portable", checked_in.split("  windows-rust:\n")[0]),
            ("windows", checked_in.split("  windows-rust:\n")[1]),
            ("app", app),
        ):
            with self.subTest(job=label):
                build = ("cargo build --manifest-path core/Cargo.toml --release --locked "
                         "-p swirl-protocol --example vision-client")
                self.assertEqual(part.count(build), 1)
                self.assertEqual(part.count("python tools/tests/test_vision_xray.py"), 1)
                self.assertLess(part.index("python tools/tests/test_reality_xray.py"), part.index(build))
                self.assertLess(part.index(build), part.index("python tools/tests/test_vision_xray.py"))
                step = part.split("      - name: Build native Vision client and verify Xray interoperability\n", 1)[1]
                step = step.split("      - ", 1)[0]
                self.assertIn("        working-directory: .\n", step)
                self.assertNotIn("continue-on-error:", step)
                self.assertNotIn("        if:", step)
                self.assertIn("SWIRL_XRAY_PEER_DIR: ${{ runner.temp }}/swirl-xray-peer\n", step)
                self.assertIn("SWIRL_VISION_EVIDENCE: ${{ runner.temp }}/swirl-vision-results\n", step)
                self.assertIn("client-build.log", step)
                self.assertIn("peer-test.log", step)
                if label == "windows":
                    self.assertIn("        shell: pwsh\n", step)
                    self.assertIn("vision-client.exe\n", step)
                    self.assertIn("if (-not (Test-Path $env:SWIRL_VISION_CLIENT -PathType Leaf))", step)
                    for log in ("client-build.log", "peer-test.log"):
                        self.assertIn(f'/{log}"\n' + development.WINDOWS_STATUS_GUARD, step)
                else:
                    self.assertIn("        shell: bash\n", step)
                    self.assertIn("          set -euo pipefail\n", step)
                    self.assertIn('          test -x "$SWIRL_VISION_CLIENT"\n', step)
                evidence = part.split("      - name: Preserve Vision client and full Xray interoperability evidence\n", 1)[1]
                evidence = evidence.split("      - ", 1)[0]
                self.assertIn("        if: always()\n", evidence)
                self.assertIn("          if-no-files-found: error\n", evidence)
                self.assertIn("${{ github.sha }}-${{ github.run_attempt }}", evidence)
                self.assertIn("swirl-xray-peer/build-manifest.json\n", evidence)
                self.assertIn("swirl-xray-peer/build.log\n", evidence)
                self.assertIn("swirl-vision-results\n", evidence)

    def test_vision_xray_partial_drift_duplicates_and_bypass_fail_atomically(self):
        final = development.updated_workflow(FIXTURE)
        broken = []
        for windows in (False, True):
            block = development.vision_xray_steps(windows=windows)
            log = ('2>&1 | Tee-Object -FilePath "$env:SWIRL_VISION_EVIDENCE/peer-test.log"\n'
                   if windows else '2>&1 | tee "$SWIRL_VISION_EVIDENCE/peer-test.log"\n')
            command = "          python tools/tests/test_vision_xray.py " + log
            edits = (
                "", block * 2,
                block.replace(development.VISION_BUILD_COMMAND, development.VISION_BUILD_COMMAND.replace("--release ", ""), 1),
                block.replace(development.VISION_BUILD_COMMAND, development.VISION_BUILD_COMMAND.replace("--locked ", ""), 1),
                block.replace(command, "", 1),
                block.replace(command, command * 2, 1),
                block.replace("working-directory: .", "working-directory: core", 1),
                block.replace("vision-client.exe" if windows else "examples/vision-client", "examples/unrelated-client", 1),
                block.replace("SWIRL_XRAY_PEER_DIR:", "UNREVIEWED_PEER_DIR:", 1),
                block.replace("SWIRL_VISION_EVIDENCE:", "UNREVIEWED_VISION_EVIDENCE:", 1),
                block.replace("        run: |\n", "        continue-on-error: true\n        run: |\n", 1),
                block.replace("        run: |\n", "        if: always()\n        run: |\n", 1),
                block.replace("        if: always()\n", "        if: success()\n", 1),
                block.replace("if-no-files-found: error", "if-no-files-found: ignore", 1),
                block.replace("swirl-xray-peer/build-manifest.json", "swirl-xray-peer/unrelated.json", 1),
                block.replace("${{ github.sha }}", "unverified-source", 1),
            )
            broken.extend(final.replace(block, edit, 1) for edit in edits)
            if windows:
                broken.append(final.replace(block, block.replace(development.WINDOWS_STATUS_GUARD, "", 1), 1))
                broken.append(final.replace(block, block.replace(command + development.WINDOWS_STATUS_GUARD, command, 1), 1))
                preflight = ("          if (-not (Test-Path $env:SWIRL_VISION_CLIENT -PathType Leaf)) "
                             "{ throw 'Required Vision Release client missing' }\n")
            else:
                broken.append(final.replace(block, block.replace("set -euo pipefail", "set -eu", 1), 1))
                broken.append(final.replace(block, block.replace(command, command.rstrip() + " || true\n", 1), 1))
                preflight = '          test -x "$SWIRL_VISION_CLIENT"\n'
            broken.append(final.replace(block, block.replace(preflight, "", 1), 1))
            r3 = development.xray_steps(windows=windows)
            broken.append(final.replace(r3 + block, block + r3, 1))
        broken.append(final + "          python tools/tests/test_vision_xray.py\n")
        for index, source in enumerate(broken):
            with self.subTest(drift=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(root, source)
                before = workflow.read_bytes()
                with self.assertRaises(ValueError):
                    development.apply_update(root, ENVIRONMENT)
                self.assertEqual(workflow.read_bytes(), before)

    def test_vision_xray_missing_material_prevents_any_workflow_write(self):
        for missing in development.VISION_XRAY_SOURCES:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workflow = self.make_repository(root)
                before = workflow.read_bytes()
                (root / missing).unlink()
                with self.assertRaises(ValueError):
                    development.apply_update(root, ENVIRONMENT)
                self.assertEqual(workflow.read_bytes(), before)

    def test_vision_xray_shell_propagates_build_missing_binary_and_peer_failure(self):
        # Execute checked-in shell bodies, including their log pipelines, rather
        # than treating textual exit guards as evidence that failures propagate.
        root = Path(__file__).resolve().parents[2]
        source = (root / ".github/workflows/rust-core.yml").read_text(encoding="utf-8")
        windows = os.name == "nt"
        jobs = [("rust", source.split("  windows-rust:\n")[int(windows)])]
        if not windows:
            jobs.append(("app", (root / ".github/workflows/core-development.yml").read_text(encoding="utf-8")))
        for job, part in jobs:
            body = part.split("      - name: Build native Vision client and verify Xray interoperability\n", 1)[1]
            body = body.split("        run: |\n", 1)[1].split("      - ", 1)[0]
            body = "\n".join(line[10:] for line in body.splitlines() if line.strip()) + "\n"
            for build_exit, client_present, peer_exit in ((23, True, 0), (0, False, 0), (0, True, 29), (0, True, 0)):
                with self.subTest(job=job, build=build_exit, client=client_present, peer=peer_exit), tempfile.TemporaryDirectory() as temporary:
                    work = Path(temporary)
                    (work / "tools/tests").mkdir(parents=True)
                    shim = work / "bin"
                    shim.mkdir()
                    stub = shim / ("cargo.cmd" if windows else "cargo")
                    stub.write_text(
                        (f"@echo off\necho synthetic-build\nexit /b {build_exit}\n" if windows
                         else f"#!/bin/sh\necho synthetic-build\nexit {build_exit}\n"), encoding="utf-8")
                    stub.chmod(0o755)
                    client = work / ("vision-client.exe" if windows else "vision-client")
                    if client_present:
                        client.write_text("synthetic preflight fixture\n", encoding="utf-8")
                        client.chmod(0o755)
                    (work / "tools/tests/test_vision_xray.py").write_text(
                        "from pathlib import Path\nPath('PEER_WAS_RUN').write_text('yes')\n"
                        f"print('synthetic-peer', flush=True)\nraise SystemExit({peer_exit})\n", encoding="utf-8")
                    evidence = work / "evidence"
                    environment = dict(os.environ, SWIRL_VISION_CLIENT=str(client),
                                       SWIRL_VISION_EVIDENCE=str(evidence), SWIRL_XRAY_PEER_DIR=str(work / "peer"))
                    environment["PATH"] = str(shim) + os.pathsep + environment.get("PATH", "")
                    if windows:
                        script = work / "failure.ps1"
                        script.write_text(body, encoding="utf-8")
                        args = ["pwsh", "-NoProfile", "-File", str(script)]
                    else:
                        args = ["bash", "-c", body]
                    result = subprocess.run(args, cwd=work, env=environment, capture_output=True, timeout=15)
                    if client_present:
                        self.assertEqual(result.returncode, build_exit or peer_exit, result.stderr.decode(errors="replace"))
                    else:
                        self.assertNotEqual(result.returncode, 0)
                    ran = build_exit == 0 and client_present
                    self.assertEqual((work / "PEER_WAS_RUN").exists(), ran)
                    self.assertIn("synthetic-build", (evidence / "client-build.log").read_text(encoding="utf-8"))
                    self.assertEqual((evidence / "peer-test.log").exists(), ran)
                    if ran:
                        self.assertIn("synthetic-peer", (evidence / "peer-test.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
