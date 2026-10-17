"""Safety and coverage checks for the one-file, App-owned Rust CI update.

These run before its first workflow write and in all three Rust CI platforms.
The fixture exercises the actual run-menu boundaries, including Windows error
propagation. No test contacts GitHub or accesses credentials.
"""

from pathlib import Path
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
      - name: Independent portable protocol peers
        run: |
          python -m pip install cryptography==50.0.2
          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"
          python ../tools/tests/test_rust_core.py
          python ../tools/tests/test_shadowsocks.py
          python ../tools/tests/test_dns_tls.py
  windows-rust:
    steps:
      - name: Independent TLS and protocol peers
        shell: pwsh
        run: |
          python -m pip install cryptography==50.0.2
          $env:SWIRL_RUST_HARNESS=(Resolve-Path target/release/swirl-api.exe).Path
          python ../tools/tests/test_rust_core.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_shadowsocks.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_dns_tls.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_subscription_capture.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          python ../tools/tests/test_codex_management.py
      - name: Run Qt to Rust integration without Mihomo
        working-directory: .
        run: |
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
        restored = updated.replace(
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

    def test_previous_successful_workflow_upgrades_without_duplicate_suites(self):
        final = development.updated_workflow(FIXTURE)
        previous = final
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
        previous = final
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
        previous = final.replace(command + development.WINDOWS_STATUS_GUARD, "").replace(command, "")
        self.assertEqual(development.updated_workflow(previous), final)
        for broken in (final.replace(command, "", 1),
                       final.replace(command, command * 2, 1),
                       final.replace(command + development.WINDOWS_STATUS_GUARD, command)):
            with self.subTest(menu=broken[-100:]), self.assertRaises(ValueError):
                development.updated_workflow(broken)

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
            "tools/Verify-PublicRustCore.py",
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
