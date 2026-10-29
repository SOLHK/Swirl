"""Source-level regression gate, separate from actual DLL/network acceptance."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
QUICK = ROOT / 'src/Swirl.Quick'
REMOVED = ('MihomoAdapter', 'MihomoLogDiagnostic', 'SwirlEngineManager',
           'SwirlProxyEngine', 'NativeDuplexRelay', 'SwirlUdpExchange',
           'OwnedProcess', 'ProxyLatencyProbe')


def forbidden_reference(text):
    return re.search(r'\b(?:' + '|'.join(REMOVED) + r')\b', text)


class RustOnlyRuntimeTests(unittest.TestCase):
    def test_legacy_sources_and_downloader_are_physically_absent(self):
        for name in REMOVED:
            for suffix in ('.cpp', '.h'):
                self.assertFalse((QUICK / 'engine' / (name + suffix)).exists(), name + suffix)
        for path in ('scripts/stage-mihomo.ps1',
                     'src/Swirl.Quick/packaging/mihomo-manifest.json',
                     'src/Swirl.Quick/tests/ControlledProtocolPeers.h',
                     'scripts/Build-WindowsRustPortableAcceptance.ps1',
                     'scripts/Build-WindowsRustNetworkCheckInstaller.ps1',
                     'src/Swirl.Quick/packaging/SwirlRustProduct.nsi',
                     'src/Swirl.Quick/packaging/SwirlRustNetworkCheck.nsi',
                     'src/Swirl.Quick/packaging/README-RustNetworkCheckInstaller.txt',
                     'tools/Invoke-WindowsRustPortableCheck.ps1',
                     'tools/TEST-SWIRL-NETWORK.cmd'):
            self.assertFalse((ROOT / path).exists(), path)

    def test_no_production_or_test_includes_or_build_references(self):
        paths = list((QUICK / 'engine').glob('*.h')) + list((QUICK / 'engine').glob('*.cpp'))
        paths += list((QUICK / 'tests').glob('*.cpp')) + list((QUICK / 'tests').glob('*.h'))
        paths += [QUICK / 'main.cpp', QUICK / 'CMakeLists.txt',
                  QUICK / 'tools/InspectPrivateSubscription.cpp']
        for path in paths:
            text = path.read_text('utf-8-sig')
            self.assertIsNone(forbidden_reference(text), str(path))
            self.assertNotRegex(text, r'\bset(?:PreferCompatibility|ExecutablePath|ControlPort)\s*\(')
            if path.suffix in ('.cpp', '.h'):
                self.assertNotIn('SWIRL_USE_RUST_CORE', text, str(path))

    def test_guard_rejects_fixture_only_and_conditional_reintroduction(self):
        for name in REMOVED:
            for value in (f'#include "{name}.h"', f'new {name}()',
                          f'if(SWIRL_BUILD_UI_TESTS)\n target_sources(Swirl PRIVATE engine/{name}.cpp)'):
                self.assertIsNotNone(forbidden_reference(value))
        self.assertIsNone(forbidden_reference('Mihomo YAML historical data-format compatibility'))

    def test_one_native_factory_and_no_external_process_selector(self):
        thread = (QUICK / 'engine/ThreadedEngine.h').read_text(encoding='utf-8-sig')
        self.assertIn('m_engine=new RustCoreEngine(m_context)', thread)
        self.assertNotIn('SWIRL_USE_RUST_CORE', thread)
        controller = (QUICK / 'engine/EngineController.h').read_text(encoding='utf-8-sig')
        for name in ('preferCompatibility', 'setPreferCompatibility', 'setExecutablePath',
                     'expectedSha256', 'expectedVersion', 'controlPort'):
            self.assertNotIn(name, controller)
        self.assertNotIn('setPreferCompatibility', (QUICK / 'main.cpp').read_text(encoding='utf-8-sig'))

    def test_all_product_builds_require_paired_native_library(self):
        cmake = (QUICK / 'CMakeLists.txt').read_text(encoding='utf-8-sig')
        self.assertIn('SWIRL_USE_RUST_CORE=OFF is no longer supported', cmake)
        self.assertNotIn('set(SWIRL_USE_RUST_CORE ON CACHE', cmake)
        self.assertIn('unset(SWIRL_USE_RUST_CORE CACHE)', cmake)
        self.assertIn('set(SWIRL_RUNTIME rust CACHE INTERNAL', cmake)
        self.assertIn('swirl_pair_rust_core(SwirlEngine)', cmake)
        self.assertIn('swirl_stage_rust_core(Swirl)', cmake)
        pair = (QUICK / 'cmake/SwirlRustCore.cmake').read_text(encoding='utf-8-sig')
        self.assertNotIn('PUBLIC SWIRL_USE_RUST_CORE', pair)
        for required in ('build --release --locked --lib --target', 'RequireRustLibrary.cmake',
                         'SWIRL_RUST_BUILD_ID', 'SWIRL_SOURCE_SHA', 'copy_if_different'):
            self.assertIn(required, pair)

    def test_active_documentation_does_not_advertise_retired_core(self):
        for name in ('README.md', 'AGENTS.md', 'docs/ARCHITECTURE.md'):
            document = (ROOT / name).read_text('utf-8-sig')
            self.assertNotIn('stage-mihomo.ps1 -Destination', document, name)
            self.assertNotIn('默认 OFF', document, name)
            self.assertNotIn('MihomoAdapter（独立进程', document, name)
        cmake = (QUICK / 'CMakeLists.txt').read_text('utf-8-sig')
        self.assertNotIn('if(SWIRL_USE_RUST_CORE)', cmake)
        self.assertNotIn('if(NOT SWIRL_USE_RUST_CORE)', cmake)
        controller = (QUICK / 'engine/EngineController.cpp').read_text('utf-8-sig')
        self.assertNotIn('#ifdef SWIRL_USE_RUST_CORE', controller)

    def test_production_scripts_do_not_fetch_external_core(self):
        paths = list((ROOT / 'scripts').glob('*.ps1')) + list((ROOT / '.github/workflows').glob('*.yml'))
        for path in paths:
            text = path.read_text('utf-8-sig')
            self.assertNotIn('stage-mihomo.ps1', text, str(path))
            self.assertNotRegex(text, r'(?i)metacubex/mihomo/releases/download/')
            self.assertNotIn('-DSWIRL_USE_RUST_CORE=ON', text)
        for name in ('build-quick-windows.ps1', 'build-current-portable.ps1',
                     'Build-WindowsRustProductInstaller.ps1'):
            text = (ROOT / 'scripts' / name).read_text(encoding='utf-8-sig')
            self.assertNotIn('MihomoArchive', text)

    def test_subscription_parsers_and_os_integration_are_retained(self):
        for name in ('NodeImporter.cpp', 'SubscriptionNormalizer.cpp', 'NodeImportService.cpp',
                     'NodeStore.cpp', 'SystemProxySession.cpp', 'TelemetryService.cpp',
                     'RustCoreEngine.cpp', 'RustCoreLibrary.cpp'):
            self.assertTrue((QUICK / 'engine' / name).is_file(), name)
        for path in ('network/CaptureService.cpp', 'network/Http2Session.cpp',
                     'tools/ProxyGuard.cpp', 'app/SystemDataProvider.cpp'):
            self.assertTrue((QUICK / path).is_file(), path)

    def test_removed_process_tests_have_native_replacements(self):
        tests = (QUICK / 'tests/RustCoreTests.cpp').read_text(encoding='utf-8-sig')
        self.assertIn('retiredPreferenceCannotSelectAnEngineOrBlockRustStartup', tests)
        self.assertIn('unsupportedCapabilitiesCannotBeEnabledOrRewriteConfiguration', tests)
        self.assertIn('smartRoutingUsesBundledRulesUnlessDirectoryIsExplicit', tests)
        ui = (QUICK / 'tests/EngineUiChecks.cpp').read_text(encoding='utf-8-sig')
        self.assertNotIn('TerminateProcess', ui)
        self.assertIn('Rust stop releases its proxy listener', ui)
        for name in ('NodeTests.cpp', 'ImportTests.cpp', 'SubscriptionFormatTests.cpp',
                     'NetworkRegressionTests.cpp', 'RustCoreLibraryTests.cpp'):
            self.assertTrue((QUICK / 'tests' / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
