"""Prevent direct desktop/mobile framework dependencies in shared Rust crates."""
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2] / "core" / "crates"
WORKSPACE = ROOT.parent / "Cargo.toml"

FORBIDDEN = re.compile(
    r"(?i)^(?:windows(?:-.*)?|winapi(?:-.*)?|winreg|wintun|"
    r"qt.*|cxx-qt.*|qmetaobject|jni(?:-sys)?|ndk.*|android-.*|"
    r"objc2?(?:-.*)?|cocoa|core-foundation(?:-sys)?|"
    r"ohos(?:-.*)?|harmony(?:os)?(?:-.*)?)$"
)
SDK_MODULE = r"(?:windows_sys|winapi|wintun)"
RUST_SPACE = r"(?:\s|/\*[\s\S]*?\*/|//[^\n]*(?:\n|$))*"
FORBIDDEN_SOURCE = re.compile(
    # A serialized driver filename is data. Actual SDK imports (including
    # aliases/group imports) and module-qualified calls cross this boundary.
    rf"\b(?:r#)?{SDK_MODULE}{RUST_SPACE}::"
    rf"|\b(?:use\b|extern\b{RUST_SPACE}crate\b){RUST_SPACE}(?:::)?{RUST_SPACE}(?:r#)?{SDK_MODULE}\b"
    rf"|\buse\b{RUST_SPACE}\{{[^;]*\b(?:r#)?{SDK_MODULE}\b"
    r"|\b(?:QQuickWindow|CreateFileW|GetAdaptersAddresses|JNIEnv|VpnService|"
    r"VpnExtensionAbility|NEPacketTunnelProvider)\b|System32/drivers/etc/hosts|"
    r"std::os::(?:windows|unix)|#\s*\[\s*link\s*\([^\]]*"
    r"(?:kind\s*=\s*\"framework\"|kernel32|user32)"
)


def platform_dependencies(manifest, workspace):
    """Resolve Cargo aliases and workspace inheritance before checking SDK names."""
    violations = []
    sections = [manifest] + list(manifest.get("target", {}).values())
    for section in sections:
        for kind in ("dependencies", "build-dependencies", "dev-dependencies"):
            for name, dependency in section.get(kind, {}).items():
                definition = dependency
                if isinstance(dependency, dict) and dependency.get("workspace"):
                    definition = workspace.get("dependencies", {}).get(name, {})
                package = definition.get("package", name) if isinstance(definition, dict) else name
                if FORBIDDEN.fullmatch(package):
                    violations.append(package)
    return violations

class PortableCoreBoundary(unittest.TestCase):
    def test_platform_frameworks_stay_in_adapter(self):
        workspace = tomllib.loads(WORKSPACE.read_text(encoding="utf-8"))["workspace"]
        for manifest in ROOT.glob("*/Cargo.toml"):
            if manifest.parent.name == "swirl-platform":
                continue
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(platform_dependencies(data, workspace), [], manifest.parent.name)

    def test_platform_calls_stay_in_adapter(self):
        for path in ROOT.glob("*/src/**/*.rs"):
            if path.relative_to(ROOT).parts[0] == "swirl-platform":
                continue
            self.assertIsNone(FORBIDDEN_SOURCE.search(path.read_text(encoding="utf-8")), str(path.relative_to(ROOT)))

    def test_serialized_driver_configuration_is_data_not_a_platform_call(self):
        for source in (
            r'json!({"driver_path":"C:\\Swirl\\wintun.dll","adapter_name":"Swirl Native TUN"})',
            r'let path = r#"C:\Swirl\wintun.dll"#;',
            r'let manifest = "windows_sys winapi wintun";',
        ):
            with self.subTest(source=source):
                self.assertIsNone(FORBIDDEN_SOURCE.search(source))

    def test_sdk_imports_aliases_raw_identifiers_and_qualified_calls_are_rejected(self):
        for sdk in ("windows_sys", "winapi", "wintun"):
            for source in (
                f"{sdk}::Adapter::open();",
                f"::{sdk} \n :: Adapter::open();",
                f"use {sdk};",
                f"use :: {sdk} as native;",
                f"use\n {sdk} \n as native;",
                f"use/* outer /* nested */ comment */{sdk} as native;",
                f"{sdk}/* namespace separator */::Adapter::open();",
                f"use {{std::net, {sdk} as native}};",
                f"pub extern\n crate {sdk} as native;",
                f"extern// comment\ncrate {sdk} as native;",
                f"extern crate r#{sdk} as native;",
            ):
                with self.subTest(source=source):
                    self.assertIsNotNone(FORBIDDEN_SOURCE.search(source))

    def test_raw_ffi_os_calls_and_multiline_link_attributes_remain_rejected(self):
        for source in (
            'unsafe extern "system" { fn CreateFileW(); }',
            'unsafe extern "system" { fn GetAdaptersAddresses(); }',
            'use std::os::unix::fs::OpenOptionsExt;',
            'use std::os::windows::process::CommandExt;',
            '#[link (\n name="kernel32"\n)] unsafe extern "system" {}',
            '#[link(name="user32")] extern "C" {}',
            '#[link(\n name="NetworkExtension",\n kind = "framework"\n)] extern "C" {}',
            'JNIEnv VpnService VpnExtensionAbility NEPacketTunnelProvider QQuickWindow',
        ):
            with self.subTest(source=source):
                self.assertIsNotNone(FORBIDDEN_SOURCE.search(source))

    def test_workspace_alias_cannot_hide_windows_sdk(self):
        workspace = {"dependencies": {"host": {"package": "windows-sys", "version": "0.61"}}}
        self.assertEqual(platform_dependencies({"dependencies": {"host": {"workspace": True}}}, workspace), ["windows-sys"])

    def test_target_and_build_dependencies_are_checked(self):
        manifest = {"target": {'cfg(target_os = "ios")': {"build-dependencies": {"host": {"package": "objc2-network-extension"}}}}}
        self.assertEqual(platform_dependencies(manifest, {}), ["objc2-network-extension"])

    def test_mobile_sdk_dependencies_are_rejected(self):
        for sdk in ("jni", "ndk", "ohos-napi-sys", "harmonyos", "android-activity"):
            with self.subTest(sdk=sdk):
                self.assertEqual(platform_dependencies({"dependencies": {sdk: "1"}}, {}), [sdk])

    def test_target_gating_does_not_authorize_windows_dependencies_in_core(self):
        for sdk in ("windows-link", "windows-strings", "windows-sys", "winreg"):
            with self.subTest(sdk=sdk):
                manifest = {"target": {"cfg(windows)": {"dependencies": {"host": {"package": sdk}}}}}
                self.assertEqual(platform_dependencies(manifest, {}), [sdk])

    def test_portable_libraries_with_os_backends_remain_allowed(self):
        manifest = {"dependencies": {name: "1" for name in ("tokio", "ring", "quinn", "serde", "socket2", "rustls")}}
        self.assertEqual(platform_dependencies(manifest, {}), [])

if __name__ == "__main__":
    unittest.main()
