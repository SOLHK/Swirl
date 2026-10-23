"""Prevent direct desktop/mobile framework dependencies in shared Rust crates."""
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2] / "core" / "crates"

class PortableCoreBoundary(unittest.TestCase):
    def test_platform_frameworks_stay_in_adapter(self):
        forbidden = re.compile(r"(?i)^(?:windows(?:-sys|-core)?|winapi|wintun|qt.*|cxx-qt.*|jni|ndk.*)$")
        for manifest in ROOT.glob("*/Cargo.toml"):
            if manifest.parent.name == "swirl-platform":
                continue
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
            sections = [data] + list(data.get("target", {}).values())
            for section in sections:
                for kind in ("dependencies", "build-dependencies"):
                    for name, dependency in section.get(kind, {}).items():
                        package = dependency.get("package", name) if isinstance(dependency, dict) else name
                        self.assertFalse(forbidden.fullmatch(package), f"{manifest.parent.name}: {package}")

    def test_platform_calls_stay_in_adapter(self):
        forbidden = re.compile(r"\b(?:windows_sys|winapi|wintun|QQuickWindow|CreateFileW|GetAdaptersAddresses)\b|System32/drivers/etc/hosts|std::os::windows")
        for path in ROOT.glob("*/src/**/*.rs"):
            if path.relative_to(ROOT).parts[0] == "swirl-platform":
                continue
            self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), str(path.relative_to(ROOT)))

if __name__ == "__main__":
    unittest.main()
