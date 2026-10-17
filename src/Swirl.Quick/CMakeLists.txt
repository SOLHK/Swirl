cmake_minimum_required(VERSION 3.25)
project(Swirl VERSION 1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(SWIRL_TEST_FONT_DIRECTORY "C:/Windows/Fonts" CACHE PATH "Offscreen test font directory")
option(SWIRL_BUILD_UI_TESTS "Build the Qt input-driven overview checks" OFF)
option(SWIRL_USE_RUST_CORE "Use Swirl Rust Core for production sessions and node probes; reject unsupported capabilities without external fallback" OFF)
find_package(Qt6 6.9 REQUIRED COMPONENTS Quick Qml QuickControls2 Network Svg GuiPrivate ShaderTools)
qt_standard_project_setup(REQUIRES 6.8)
qt_policy(SET QTP0004 NEW)
add_subdirectory(third_party)
add_executable(SwirlScriptRunner tools/ScriptRunner.cpp)
target_link_libraries(SwirlScriptRunner PRIVATE Qt6::Core Qt6::Qml)
target_compile_definitions(SwirlScriptRunner PRIVATE NOMINMAX)
qt_add_executable(Swirl WIN32 main.cpp app/DismissalController.h app/DismissalController.cpp app/SystemDataProvider.cpp app/SystemDataProvider.h app/WindowsBackdrop.cpp app/WindowsBackdrop.h network/CaptureService.cpp network/CaptureService.h app/ModuleDraftStore.cpp app/ModuleDraftStore.h)
execute_process(COMMAND git rev-parse --short HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" OUTPUT_VARIABLE SWIRL_BUILD_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT SWIRL_BUILD_REVISION)
 set(SWIRL_BUILD_REVISION "source-archive")
endif()
target_compile_definitions(Swirl PRIVATE SWIRL_BUILD_REVISION="${SWIRL_BUILD_REVISION}")
target_sources(Swirl PRIVATE app/FontManager.h app/FontManager.cpp)
qt_add_resources(Swirl harmony_fonts PREFIX "/swirl/fonts" BASE "${CMAKE_CURRENT_SOURCE_DIR}/assets/fonts" FILES
 assets/fonts/HarmonyOS_Sans_SC_Regular.ttf assets/fonts/HarmonyOS_Sans_SC_Medium.ttf assets/fonts/HarmonyOS_Sans_SC_Bold.ttf assets/fonts/LICENSE_HarmonyOS_Sans.txt)
add_library(SwirlEngine STATIC
 app/DiagnosticService.h app/DiagnosticService.cpp
 engine/TelemetryService.h engine/TelemetryService.cpp
 engine/ProxyLatencyProbe.h engine/ProxyLatencyProbe.cpp
 engine/NodeTestService.h engine/NodeTestService.cpp
 engine/SystemProxySession.h engine/SystemProxySession.cpp
 engine/ProxyEngine.h engine/OwnedProcess.h engine/OwnedProcess.cpp
 engine/MihomoAdapter.h engine/MihomoAdapter.cpp
 engine/MihomoLogDiagnostic.h engine/MihomoLogDiagnostic.cpp
 engine/EngineController.h engine/EngineController.cpp)
target_sources(SwirlEngine PRIVATE engine/ProxyNode.h engine/ProxyNode.cpp engine/NodeStore.h engine/NodeStore.cpp)
target_sources(SwirlEngine PRIVATE engine/NodeImporter.h engine/NodeImporter.cpp)
target_sources(SwirlEngine PRIVATE engine/SubscriptionNormalizer.h engine/SubscriptionNormalizer.cpp)
target_sources(SwirlEngine PRIVATE engine/SwirlProtocolRegistry.h engine/SwirlProtocolRegistry.cpp engine/SwirlProxyEngine.h engine/SwirlProxyEngine.cpp)
target_sources(SwirlEngine PRIVATE engine/NativeDuplexRelay.h engine/NativeDuplexRelay.cpp)
target_sources(SwirlEngine PRIVATE engine/ConnectionDiagnostics.h engine/ConnectionDiagnostics.cpp)
target_sources(SwirlEngine PRIVATE engine/SwirlEngineManager.h engine/SwirlEngineManager.cpp)
target_sources(SwirlEngine PRIVATE engine/SwirlUdpExchange.h engine/SwirlUdpExchange.cpp)
target_sources(SwirlEngine PRIVATE engine/NodeImportService.h engine/NodeImportService.cpp)
target_sources(SwirlEngine PRIVATE engine/RustCoreEngine.h engine/RustCoreEngine.cpp)
if(SWIRL_USE_RUST_CORE)
 if(NOT WIN32)
  message(FATAL_ERROR "Rust Qt packaging is currently validated on Windows only")
 endif()
 find_program(SWIRL_CARGO cargo REQUIRED)
 get_filename_component(SWIRL_RUST_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../core" ABSOLUTE)
 set(SWIRL_RUST_TARGET "${CMAKE_CURRENT_BINARY_DIR}/rust-target")
 file(GLOB_RECURSE SWIRL_RUST_INPUTS CONFIGURE_DEPENDS "${SWIRL_RUST_SOURCE}/crates/*.rs" "${SWIRL_RUST_SOURCE}/crates/Cargo.toml" "${SWIRL_RUST_SOURCE}/crates/*/Cargo.toml")
 add_custom_command(OUTPUT "${SWIRL_RUST_TARGET}/release/swirl_api.dll"
  COMMAND "${SWIRL_CARGO}" build --release --locked --manifest-path "${SWIRL_RUST_SOURCE}/Cargo.toml" --target-dir "${SWIRL_RUST_TARGET}" -p swirl-api
  DEPENDS ${SWIRL_RUST_INPUTS} "${SWIRL_RUST_SOURCE}/Cargo.toml" "${SWIRL_RUST_SOURCE}/Cargo.lock"
  VERBATIM)
 # Refresh the deployed DLL even when only Rust sources changed and no Qt
 # target needs relinking (POST_BUILD alone leaves a stale runtime in that case).
 add_custom_target(SwirlRustCore
  COMMAND "${CMAKE_COMMAND}" -E make_directory "$<TARGET_FILE_DIR:Swirl>"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${SWIRL_RUST_TARGET}/release/swirl_api.dll" "$<TARGET_FILE_DIR:Swirl>/swirl_api.dll"
  DEPENDS "${SWIRL_RUST_TARGET}/release/swirl_api.dll")
 add_dependencies(SwirlEngine SwirlRustCore)
 target_compile_definitions(SwirlEngine PUBLIC SWIRL_USE_RUST_CORE)
 add_custom_command(TARGET Swirl POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_if_different
  "${SWIRL_RUST_TARGET}/release/swirl_api.dll" "$<TARGET_FILE_DIR:Swirl>/swirl_api.dll")
endif()
target_link_libraries(SwirlEngine PUBLIC Qt6::Core Qt6::Network Qt6::Gui)
add_library(SwirlExtensions STATIC app/ExtensionService.h app/ExtensionService.cpp)
target_link_libraries(SwirlExtensions PUBLIC SwirlEngine Qt6::Core Qt6::Qml)
target_include_directories(SwirlExtensions PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_include_directories(SwirlEngine PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
if(WIN32)
 add_library(SwirlCodexLaunchSupport STATIC tools/CodexLaunchSupport.h tools/CodexLaunchSupport.cpp)
 target_include_directories(SwirlCodexLaunchSupport PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
 target_compile_definitions(SwirlCodexLaunchSupport PUBLIC NOMINMAX UNICODE _UNICODE)
 target_link_libraries(SwirlCodexLaunchSupport PUBLIC wininet advapi32 ws2_32)
 add_executable(SwirlCodexLauncher WIN32 tools/CodexLauncher.cpp)
 target_link_libraries(SwirlCodexLauncher PRIVATE SwirlCodexLaunchSupport shell32 user32)
 if(MSVC)
  set_property(TARGET SwirlCodexLaunchSupport SwirlCodexLauncher PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  target_compile_options(SwirlCodexLaunchSupport PRIVATE /utf-8)
  target_compile_options(SwirlCodexLauncher PRIVATE /utf-8)
 else()
  target_link_options(SwirlCodexLauncher PRIVATE -municode -static)
 endif()
 add_dependencies(Swirl SwirlCodexLauncher)
 add_custom_target(SwirlCodexManagementTools
  COMMAND "${CMAKE_COMMAND}" -E make_directory "$<TARGET_FILE_DIR:Swirl>"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/SwirlCodexManage.py" "$<TARGET_FILE_DIR:Swirl>/SwirlCodexManage.py"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/SubscriptionCapture.py" "$<TARGET_FILE_DIR:Swirl>/SubscriptionCapture.py")
 add_dependencies(Swirl SwirlCodexManagementTools)
 target_compile_definitions(SwirlEngine PUBLIC NOMINMAX)
 target_link_libraries(SwirlEngine PRIVATE advapi32 ws2_32 iphlpapi crypt32 wininet)
 add_executable(SwirlGatewayGuard WIN32 tools/GatewayGuard.cpp network/GatewayRouting.cpp)
 target_include_directories(SwirlGatewayGuard PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 target_link_libraries(SwirlGatewayGuard PRIVATE Qt6::Core Qt6::Network)
 add_dependencies(Swirl SwirlGatewayGuard)
 add_executable(SwirlProxyGuard tools/ProxyGuard.cpp)
 target_link_libraries(SwirlProxyGuard PRIVATE SwirlEngine ole32 propsys shell32 shlwapi uuid)
 add_dependencies(Swirl SwirlProxyGuard)
endif()
if(MSVC)
 target_compile_options(SwirlEngine PRIVATE /utf-8)
 target_compile_options(SwirlExtensions PRIVATE /utf-8)
 target_compile_options(SwirlScriptRunner PRIVATE /utf-8)
 if(TARGET SwirlGatewayGuard)
  target_compile_options(SwirlGatewayGuard PRIVATE /utf-8)
 endif()
endif()
target_sources(Swirl PRIVATE network/GatewayService.h network/GatewayService.cpp network/GatewayRouting.h network/GatewayRouting.cpp network/DhcpServer.h network/DhcpServer.cpp network/Http2Session.h network/Http2Session.cpp network/TlsCertificateService.h network/TlsCertificateService.cpp)
target_link_libraries(Swirl PRIVATE SwirlEngine SwirlHttp2 SwirlExtensions)
add_dependencies(Swirl SwirlScriptRunner)
qt_add_resources(Swirl engine_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging"
 FILES packaging/mihomo-manifest.json)
set(SWIRL_QML_FILES
 qml/controls/SwirlText.qml
 qml/controls/SwirlLinkedDetail.qml
 qml/controls/SwirlNodeTransfer.qml
 qml/components/SwirlFontSettings.qml
 qml/components/SwirlSecondaryWindow.qml
 qml/components/SwirlWindowTitleBar.qml
 qml/controls/RewriteRulesDialog.qml
 qml/components/ReferenceSection.qml qml/components/ReferenceOutline.qml qml/components/ReferenceCheckBox.qml qml/pages/CaptureInspectorPage.qml
 qml/controls/SwirlStatusCapsule.qml qml/controls/SwirlScrollBar.qml qml/pages/ProcessesPage.qml
 qml/Main.qml qml/Theme.qml qml/AppState.qml qml/FeatureCatalog.qml qml/SwirlMotion.qml qml/SwirlTransitionRegistry.qml
 qml/controls/SwirlTransitionCoordinator.qml qml/controls/SwirlHeroCard.qml qml/controls/SwirlHeroTitle.qml
 qml/components/SwirlContinuousSurface.qml qml/components/SwirlBlurLayer.qml qml/components/SwirlGlassMaterial.qml qml/components/SwirlTrafficLights.qml qml/components/SwirlDailyTrafficChart.qml
 qml/controls/SwirlClickLight.qml qml/controls/SwirlActivityIndicator.qml qml/controls/SwirlExpander.qml
 qml/controls/SwirlPressMotion.qml qml/controls/SwirlAnimatedModel.qml qml/controls/SwirlMotionButton.qml qml/controls/SwirlSpring.qml qml/controls/SwirlPageHost.qml
 qml/pages/FeatureHubPage.qml qml/pages/FeatureModulePage.qml qml/components/SwirlBrandIcon.qml
 qml/controls/SwirlPillSurface.qml qml/controls/SwirlIconButton.qml qml/controls/SwirlButton.qml qml/controls/SwirlSegmentedControl.qml qml/controls/SwirlToggle.qml
 qml/controls/SwirlSearchField.qml qml/controls/SwirlTextField.qml
 qml/controls/SwirlComboBox.qml qml/controls/SwirlDialog.qml
 qml/controls/SwirlDataTable.qml qml/controls/SwirlContextMenu.qml
 qml/components/SwirlGlassPanel.qml qml/components/SwirlNavigationItem.qml
 qml/components/SwirlSidebar.qml qml/components/SwirlTrafficChart.qml
 qml/components/SwirlMetricCard.qml qml/components/SwirlStatusBadge.qml
 qml/components/SwirlInspectorPanel.qml qml/components/SwirlEmptyState.qml
 qml/components/SwirlSparkline.qml qml/components/SwirlListRow.qml qml/components/SwirlRegionBadge.qml qml/components/SwirlIcon.qml
 qml/pages/OverviewPage.qml qml/pages/CapturePage.qml qml/pages/ExternalToolsPage.qml qml/pages/ConnectionsPage.qml
 qml/pages/ProxiesPage.qml qml/pages/InspectorPage.qml
 qml/pages/ScriptsPage.qml qml/pages/SettingsPage.qml
 qml/pages/WorkbenchPage.qml qml/pages/ToolboxPage.qml
 qml/pages/ActivityPage.qml qml/pages/DNSPage.qml
 qml/pages/RulesPage.qml qml/pages/LogsPage.qml
 qml/pages/TLSPage.qml qml/pages/ReplayPage.qml qml/pages/RewritePage.qml
 qml/pages/ProfilesPage.qml qml/pages/SubscriptionsPage.qml qml/pages/PolicyGroupsPage.qml
 qml/pages/TrafficAnalyticsPage.qml qml/pages/BreakpointPage.qml qml/pages/MapPage.qml
 qml/pages/ModulesPage.qml qml/pages/AutomationPage.qml
 qml/pages/ApiPage.qml qml/pages/GatewayPage.qml
)
foreach(file IN LISTS SWIRL_QML_FILES)
    string(REGEX REPLACE "^qml/" "" qml_alias "${file}")
    set_source_files_properties("${file}" PROPERTIES QT_RESOURCE_ALIAS "${qml_alias}")
endforeach()
set_source_files_properties(qml/SwirlMotion.qml qml/SwirlTransitionRegistry.qml qml/Theme.qml qml/AppState.qml qml/FeatureCatalog.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)
qt_add_qml_module(Swirl
    URI SwirlQuick
    VERSION 1.0
    RESOURCE_PREFIX /qt/qml
    NO_GENERATE_EXTRA_QMLDIRS
    QML_FILES ${SWIRL_QML_FILES}
    SOURCES app/JavascriptHighlighter.h app/JavascriptHighlighter.cpp app/WindowEdge.h app/WindowEdge.cpp
)
set(SWIRL_ASSET_PATH "${CMAKE_CURRENT_SOURCE_DIR}/assets")
file(GLOB SWIRL_UI_ICONS CONFIGURE_DEPENDS "${SWIRL_ASSET_PATH}/icons/ui/*.svg")
qt_add_resources(Swirl ui_icons PREFIX "/swirl" BASE "${SWIRL_ASSET_PATH}" FILES ${SWIRL_UI_ICONS})
qt_add_resources(Swirl brand PREFIX "/swirl" BASE "${SWIRL_ASSET_PATH}" FILES
    "${SWIRL_ASSET_PATH}/icons/swirl_knot_light.svg"
    "${SWIRL_ASSET_PATH}/icons/swirl_knot_dark.svg"
    "${SWIRL_ASSET_PATH}/icons/swirl_knot_mark_light.svg"
    "${SWIRL_ASSET_PATH}/icons/swirl_knot_mark_dark.svg"
)
qt_add_shaders(Swirl hdr_ui PREFIX "/swirl" BASE "${CMAKE_CURRENT_SOURCE_DIR}" FILES shaders/hdr-ui.frag shaders/swirlclicklight.frag shaders/swirlclicklight.vert)
qt_add_shaders(Swirl glass_ui PREFIX "/swirl" BASE "${CMAKE_CURRENT_SOURCE_DIR}" FILES shaders/swirl-surface.frag shaders/swirl-blur.frag shaders/swirl-glass.frag)
qt_add_shaders(Swirl window_edge BATCHABLE PREFIX "/swirl" BASE "${CMAKE_CURRENT_SOURCE_DIR}" FILES shaders/window-edge.vert shaders/window-edge.frag)
if(WIN32)
 target_link_libraries(Swirl PRIVATE ole32 uuid)
endif()
target_sources(Swirl PRIVATE app/HdrOutput.h app/HdrOutput.cpp app/MotionPolicy.h app/MotionPolicy.cpp)
target_link_libraries(Swirl PRIVATE Qt6::GuiPrivate)

target_include_directories(Swirl PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/app")
target_sources(Swirl PRIVATE app/SvgIconProvider.h app/SvgIconProvider.cpp)
target_link_libraries(Swirl PRIVATE Qt6::Quick Qt6::Qml Qt6::QuickControls2 Qt6::Network Qt6::Svg)
if(MSVC)
 target_compile_options(Swirl PRIVATE /utf-8)
endif()
if(SWIRL_BUILD_UI_TESTS)
 file(COPY "${CMAKE_CURRENT_SOURCE_DIR}/packaging/rules" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}")
 find_package(Qt6 REQUIRED COMPONENTS Test)
 add_executable(SwirlFontTests tests/FontTests.cpp app/FontManager.h app/FontManager.cpp)
 target_include_directories(SwirlFontTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 target_link_libraries(SwirlFontTests PRIVATE Qt6::Quick Qt6::Test)
 if(MSVC)
  target_compile_options(SwirlFontTests PRIVATE /utf-8)
 endif()
 qt_add_resources(SwirlFontTests harmony_test_fonts PREFIX "/swirl/fonts" BASE "${CMAKE_CURRENT_SOURCE_DIR}/assets/fonts" FILES
  assets/fonts/HarmonyOS_Sans_SC_Regular.ttf assets/fonts/HarmonyOS_Sans_SC_Medium.ttf assets/fonts/HarmonyOS_Sans_SC_Bold.ttf assets/fonts/LICENSE_HarmonyOS_Sans.txt)
 target_sources(Swirl PRIVATE tests/GatewayChecks.cpp tests/GatewayChecks.h tests/HdrChecks.cpp tests/HdrChecks.h tests/OverviewChecks.cpp tests/OverviewChecks.h tests/CaptureChecks.cpp tests/CaptureChecks.h tests/WindowChecks.cpp tests/WindowChecks.h)
 target_sources(Swirl PRIVATE tests/UiQualityChecks.h tests/UiQualityChecks.cpp)
 target_sources(Swirl PRIVATE tests/RuntimeEvidence.cpp tests/RuntimeEvidence.h)
 target_sources(Swirl PRIVATE tests/MaterialChecks.cpp tests/MaterialChecks.h)
 target_sources(Swirl PRIVATE tests/HeroChecks.cpp tests/HeroChecks.h tests/NavigationChecks.cpp tests/NavigationChecks.h)
 target_sources(Swirl PRIVATE tests/AppearanceChecks.cpp tests/AppearanceChecks.h)
 add_test(NAME swirl-appearance-ui COMMAND Swirl --appearance-test)
 set_tests_properties(swirl-appearance-ui PROPERTIES TIMEOUT 45 RUN_SERIAL TRUE ENVIRONMENT "QT_QPA_PLATFORM=windows;QSG_RHI_BACKEND=d3d11" ENVIRONMENT_MODIFICATION "QT_QUICK_BACKEND=unset:")
 qt_add_resources(Swirl material_tests PREFIX "/tests" BASE "${CMAKE_CURRENT_SOURCE_DIR}/tests" FILES tests/MaterialBench.qml)
 target_link_libraries(Swirl PRIVATE Qt6::Test)
 target_compile_definitions(Swirl PRIVATE SWIRL_UI_TESTS)
 enable_testing()
 if(SWIRL_USE_RUST_CORE)
  add_executable(SwirlRustCoreTests tests/RustCoreTests.cpp)
  target_link_libraries(SwirlRustCoreTests PRIVATE SwirlEngine Qt6::Test)
  add_custom_command(TARGET SwirlRustCore POST_BUILD
   COMMAND "${CMAKE_COMMAND}" -E make_directory "$<TARGET_FILE_DIR:SwirlRustCoreTests>"
   COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${SWIRL_RUST_TARGET}/release/swirl_api.dll" "$<TARGET_FILE_DIR:SwirlRustCoreTests>/swirl_api.dll")
  target_compile_definitions(SwirlRustCoreTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
  if(MSVC)
   target_compile_options(SwirlRustCoreTests PRIVATE /utf-8)
  endif()
  add_custom_command(TARGET SwirlRustCoreTests POST_BUILD COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${SWIRL_RUST_TARGET}/release/swirl_api.dll" "$<TARGET_FILE_DIR:SwirlRustCoreTests>/swirl_api.dll")
  add_test(NAME swirl-rust-qt-integration COMMAND SwirlRustCoreTests)
  set_tests_properties(swirl-rust-qt-integration PROPERTIES TIMEOUT 60)
 endif()
 if(WIN32)
  add_executable(SwirlCodexLauncherTests tests/CodexLauncherTests.cpp)
  target_link_libraries(SwirlCodexLauncherTests PRIVATE SwirlCodexLaunchSupport)
  if(MSVC)
   set_property(TARGET SwirlCodexLauncherTests PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
   target_compile_options(SwirlCodexLauncherTests PRIVATE /utf-8)
  else()
   target_link_options(SwirlCodexLauncherTests PRIVATE -municode -static)
  endif()
  add_test(NAME swirl-codex-proxy-launcher COMMAND SwirlCodexLauncherTests)
  set_tests_properties(swirl-codex-proxy-launcher PROPERTIES TIMEOUT 15)
 endif()
 add_test(NAME swirl-font-selection COMMAND SwirlFontTests)
 set_tests_properties(swirl-font-selection PROPERTIES TIMEOUT 30 ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}")
 if(WIN32)
  add_test(NAME swirl-font-native-raster COMMAND SwirlFontTests nativeGlyphsHaveNoColourFringes)
  set_tests_properties(swirl-font-native-raster PROPERTIES TIMEOUT 30 RUN_SERIAL TRUE ENVIRONMENT "QT_QPA_PLATFORM=windows;QSG_RHI_BACKEND=d3d11" ENVIRONMENT_MODIFICATION "QT_QUICK_BACKEND=unset:")
 endif()
 add_executable(SwirlExtensionTests tests/ExtensionTests.cpp)
 if(MSVC)
  target_compile_options(SwirlExtensionTests PRIVATE /utf-8)
 endif()
 target_link_libraries(SwirlExtensionTests PRIVATE SwirlExtensions Qt6::Test)
 add_dependencies(SwirlExtensionTests SwirlScriptRunner)
 qt_add_resources(SwirlExtensionTests extension_engine_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging" FILES packaging/mihomo-manifest.json)
 add_test(NAME swirl-local-extensions COMMAND SwirlExtensionTests)
 set_tests_properties(swirl-local-extensions PROPERTIES TIMEOUT 60)
 add_executable(SwirlTelemetryTests tests/TelemetryTests.cpp)
 target_link_libraries(SwirlTelemetryTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlTelemetryTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 qt_add_resources(SwirlTelemetryTests telemetry_engine_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging" FILES packaging/mihomo-manifest.json)
 if(MSVC)
  target_compile_options(SwirlTelemetryTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-telemetry-accounting COMMAND SwirlTelemetryTests)
 add_executable(SwirlDiagnosticTests tests/DiagnosticTests.cpp)
 target_link_libraries(SwirlDiagnosticTests PRIVATE SwirlEngine Qt6::Test)
 if(MSVC)
  target_compile_options(SwirlDiagnosticTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-diagnostic-export COMMAND SwirlDiagnosticTests)
 if(WIN32)
  add_executable(SwirlSystemProxyTests tests/SystemProxyTests.cpp)
  target_link_libraries(SwirlSystemProxyTests PRIVATE SwirlEngine Qt6::Test)
  add_dependencies(SwirlSystemProxyTests SwirlProxyGuard)
  # Explicit opt-in: normal CI and CTest never modify the runner's proxy.
  if(DEFINED ENV{SWIRL_SYSTEM_PROXY_TEST})
   add_test(NAME swirl-system-proxy-recovery COMMAND SwirlSystemProxyTests)
   set_tests_properties(swirl-system-proxy-recovery PROPERTIES RUN_SERIAL TRUE TIMEOUT 45)
  endif()
  add_executable(SwirlAcceptance tests/AcceptanceSession.cpp)
  target_link_libraries(SwirlAcceptance PRIVATE SwirlEngine)
  if(MSVC)
   target_compile_options(SwirlSystemProxyTests PRIVATE /utf-8)
   target_compile_options(SwirlAcceptance PRIVATE /utf-8)
  endif()
 endif()
 add_executable(SwirlEngineFixture tests/EngineFixture.cpp)
 target_link_libraries(SwirlEngineFixture PRIVATE Qt6::Core Qt6::Network)
 add_executable(SwirlEngineTests tests/EngineTests.cpp)
 target_link_libraries(SwirlEngineTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlEngineTests PRIVATE SWIRL_TEST_MANIFEST="${CMAKE_CURRENT_SOURCE_DIR}/packaging/mihomo-manifest.json")
 if(MSVC)
  target_compile_options(SwirlEngineTests PRIVATE /utf-8)
 endif()
 add_dependencies(SwirlEngineTests SwirlEngineFixture)
 add_executable(SwirlNodeTests tests/NodeTests.cpp tests/ControlledNetwork.h)
 target_link_libraries(SwirlNodeTests PRIVATE SwirlEngine Qt6::Test)
 qt_add_resources(SwirlNodeTests node_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging" FILES packaging/mihomo-manifest.json)
 target_compile_definitions(SwirlNodeTests PRIVATE SWIRL_TEST_MANIFEST="${CMAKE_CURRENT_SOURCE_DIR}/packaging/mihomo-manifest.json" SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 if(MSVC)
  target_compile_options(SwirlNodeTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-node-real-chain COMMAND SwirlNodeTests -o node-chain.txt,txt)
 add_executable(SwirlNativeTests tests/NativeEngineTests.cpp tests/ControlledProtocolPeers.h)
 target_link_libraries(SwirlNativeTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlNativeTests PRIVATE SWIRL_TEST_MANIFEST="${CMAKE_CURRENT_SOURCE_DIR}/packaging/mihomo-manifest.json" SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 if(MSVC)
  target_compile_options(SwirlNativeTests PRIVATE /utf-8)
 endif()
 add_executable(SwirlNetworkRegressionTests tests/NetworkRegressionTests.cpp)
 target_link_libraries(SwirlNetworkRegressionTests PRIVATE SwirlEngine Qt6::Test)
 qt_add_resources(SwirlNetworkRegressionTests regression_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging" FILES packaging/mihomo-manifest.json)
 target_compile_definitions(SwirlNetworkRegressionTests PRIVATE SWIRL_TEST_MANIFEST="${CMAKE_CURRENT_SOURCE_DIR}/packaging/mihomo-manifest.json" SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 add_test(NAME swirl-stream-regression COMMAND SwirlNetworkRegressionTests -o stream-regression.txt,txt)
 set_tests_properties(swirl-stream-regression PROPERTIES TIMEOUT 180)
 add_test(NAME swirl-native-engine COMMAND SwirlNativeTests -o native-engine.txt,txt)
 set_tests_properties(swirl-native-engine PROPERTIES TIMEOUT 180)
 add_executable(SwirlImportTests tests/ImportTests.cpp tests/ControlledNetwork.h)
 add_executable(SwirlSubscriptionFormatTests tests/SubscriptionFormatTests.cpp tests/ControlledProtocolPeers.h)
 add_executable(SwirlPrivateSubscriptionInspect tools/InspectPrivateSubscription.cpp)
 target_link_libraries(SwirlPrivateSubscriptionInspect PRIVATE SwirlEngine)
 if(MSVC)
  target_compile_options(SwirlPrivateSubscriptionInspect PRIVATE /utf-8)
 endif()
 target_link_libraries(SwirlSubscriptionFormatTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlSubscriptionFormatTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 if(MSVC)
  target_compile_options(SwirlSubscriptionFormatTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-subscription-formats COMMAND SwirlSubscriptionFormatTests -o subscription-formats.txt,txt)
 set_tests_properties(swirl-subscription-formats PROPERTIES TIMEOUT 180)
 target_link_libraries(SwirlImportTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlImportTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 qt_add_resources(SwirlImportTests import_manifest PREFIX "/engine" BASE "${CMAKE_CURRENT_SOURCE_DIR}/packaging" FILES packaging/mihomo-manifest.json)
 if(MSVC)
  target_compile_options(SwirlImportTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-import-subscription COMMAND SwirlImportTests -o import-subscription.txt,txt)
 set_tests_properties(swirl-import-subscription PROPERTIES TIMEOUT 120)
 set_tests_properties(swirl-node-real-chain PROPERTIES TIMEOUT 180)
 add_test(NAME swirl-engine-contract COMMAND SwirlEngineTests -o engine-contract.txt,txt)
 set_tests_properties(swirl-engine-contract PROPERTIES TIMEOUT 90)
 add_test(NAME swirl-engine-real COMMAND SwirlEngineTests realEngine -o engine-real.txt,txt)
 set_tests_properties(swirl-engine-real PROPERTIES TIMEOUT 90 ENVIRONMENT "SWIRL_REAL_ENGINE_TEST=1")
 target_sources(Swirl PRIVATE tests/EngineUiChecks.cpp tests/EngineUiChecks.h tests/NodeUiChecks.cpp tests/NodeUiChecks.h tests/MotionChecks.cpp tests/MotionChecks.h)
 target_compile_definitions(Swirl PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 add_test(NAME swirl-node-ui COMMAND Swirl --node-self-test)
 set_tests_properties(swirl-node-ui PROPERTIES TIMEOUT 180 ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}")
 add_test(NAME swirl-engine-ui COMMAND Swirl --engine-self-test)
 set_tests_properties(swirl-engine-ui PROPERTIES TIMEOUT 60
  ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}")
 add_test(NAME swirl-overview-input COMMAND Swirl --interaction-test)
 add_test(NAME swirl-all-pages COMMAND Swirl --smoke-test)
 add_test(NAME swirl-motion COMMAND Swirl --motion-test --motion-output=motion-report.json)
 if(WIN32)
  add_test(NAME swirl-hero COMMAND Swirl --hero-test --hero-output=hero-evidence)
  add_test(NAME swirl-navigation-ui COMMAND Swirl --navigation-test --navigation-output=navigation-evidence --hero-no-recording)
  set_tests_properties(swirl-navigation-ui PROPERTIES TIMEOUT 90 RUN_SERIAL TRUE ENVIRONMENT "QT_QPA_PLATFORM=windows;QSG_RHI_BACKEND=d3d11" ENVIRONMENT_MODIFICATION "QT_QUICK_BACKEND=unset:")
  set_tests_properties(swirl-hero PROPERTIES TIMEOUT 120 RUN_SERIAL TRUE ENVIRONMENT "QT_QPA_PLATFORM=windows;QSG_RHI_BACKEND=d3d11" ENVIRONMENT_MODIFICATION "QT_QUICK_BACKEND=unset:")
 endif()
 set_tests_properties(swirl-motion PROPERTIES TIMEOUT 120
  ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}")
 if(WIN32)
  # Popup.Window has native grabs and activation; the offscreen plugin cannot
  # exercise its opening/closing behavior. Keep this check on Windows QPA.
  set_tests_properties(swirl-motion PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=windows;QT_QUICK_BACKEND=software")
 endif()
 add_test(NAME swirl-gateway-network COMMAND Swirl --gateway-self-test)
 set_tests_properties(swirl-gateway-network PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}" TIMEOUT 60)
 add_test(NAME swirl-capture-network COMMAND Swirl --capture-self-test)
 set_tests_properties(swirl-overview-input swirl-all-pages swirl-capture-network PROPERTIES
  ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}" TIMEOUT 60)
endif()
if(WIN32)
 # Generate the Windows-only ICO from the canonical Swirl SVG before RC compilation.
 add_executable(SwirlIconBuilder tools/BuildWindowsIcon.cpp)
 target_link_libraries(SwirlIconBuilder PRIVATE Qt6::Gui Qt6::Svg)
 set(SWIRL_GENERATED_ICON "${CMAKE_CURRENT_BINARY_DIR}/brand/Swirl.ico")
 add_custom_command(
  OUTPUT "${SWIRL_GENERATED_ICON}"
  COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/brand"
  COMMAND $<TARGET_FILE:SwirlIconBuilder>
          "${SWIRL_ASSET_PATH}/icons/swirl_knot_mark_light.svg"
          "${SWIRL_GENERATED_ICON}"
  DEPENDS SwirlIconBuilder app/BrandRaster.h "${SWIRL_ASSET_PATH}/icons/swirl_knot_mark_light.svg"
  COMMENT "Generate Windows ICO from Swirl SVG"
  VERBATIM
 )
 add_custom_target(swirl-generate-icon DEPENDS "${SWIRL_GENERATED_ICON}")
 add_dependencies(Swirl swirl-generate-icon)
 configure_file(app/Swirl.rc.in "${CMAKE_CURRENT_BINARY_DIR}/Swirl.rc" @ONLY)
 target_sources(Swirl PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/Swirl.rc")
 target_link_libraries(Swirl PRIVATE dwmapi advapi32 psapi shell32)
endif()
