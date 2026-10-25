cmake_minimum_required(VERSION 3.25)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/PRODUCT_VERSION.txt")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/PRODUCT_VERSION.txt" SWIRL_APP_VERSION)
string(STRIP "${SWIRL_APP_VERSION}" SWIRL_APP_VERSION)
if(NOT SWIRL_APP_VERSION MATCHES "^[0-9]+\\.[0-9]+\\.[0-9]+$")
 message(FATAL_ERROR "src/Swirl.Quick/PRODUCT_VERSION.txt must contain a numeric major.minor.patch version")
endif()
project(Swirl VERSION ${SWIRL_APP_VERSION} LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(SWIRL_TEST_FONT_DIRECTORY "C:/Windows/Fonts" CACHE PATH "Offscreen test font directory")
option(SWIRL_BUILD_UI_TESTS "Build the Qt input-driven overview checks" OFF)
option(SWIRL_BUILD_CORE_TESTS "Build standalone Core/network tests without exposing application UI test entry points" OFF)
option(SWIRL_FONT_TESTS_ONLY "Configure only the independent Qt font tests, without the application or proxy engine" OFF)
option(SWIRL_XRAY_UI_TESTS "Build the isolated JSON import acceptance profile in the real Rust application" OFF)

# Keep the standalone CI and the existing UI suite on the same font targets.
# This path deliberately precedes third_party and all application/core targets.
function(swirl_add_font_tests)
 add_executable(SwirlFontTests tests/FontTests.cpp app/FontManager.h app/FontManager.cpp app/FontAxisPolicy.h app/FontAxisPolicy.cpp app/FontDisplayContext.h app/FontDisplayContext.cpp app/VariableFontPreview.h app/VariableFontPreview.cpp)
 target_include_directories(SwirlFontTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 target_compile_definitions(SwirlFontTests PRIVATE SWIRL_UI_TESTS SWIRL_QML_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/qml")
 # QRhi is Qt's documented texture-upload API, supplied by GuiPrivate.
 # Match the application's dependency so tests exercise the same preview path.
 target_link_libraries(SwirlFontTests PRIVATE Qt6::Quick Qt6::QuickControls2 Qt6::GuiPrivate Qt6::Test)
 add_executable(SwirlFontAxisPolicyTests tests/FontAxisPolicyTests.cpp app/FontAxisPolicy.h app/FontAxisPolicy.cpp)
 target_include_directories(SwirlFontAxisPolicyTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 target_link_libraries(SwirlFontAxisPolicyTests PRIVATE Qt6::Gui Qt6::Test)
 if(MSVC)
  target_compile_options(SwirlFontTests PRIVATE /utf-8)
  target_compile_options(SwirlFontAxisPolicyTests PRIVATE /utf-8)
 endif()
 qt_add_resources(SwirlFontTests harmony_test_fonts PREFIX "/swirl/fonts" BASE "${CMAKE_CURRENT_SOURCE_DIR}/assets/fonts" FILES
  assets/fonts/HarmonyOS_Sans_SC_Regular.ttf assets/fonts/HarmonyOS_Sans_SC_Medium.ttf assets/fonts/HarmonyOS_Sans_SC_Bold.ttf assets/fonts/LICENSE_HarmonyOS_Sans.txt)
 add_test(NAME swirl-font-selection COMMAND SwirlFontTests -o "${CMAKE_CURRENT_BINARY_DIR}/font-selection.xml,xml" -o "-,txt")
 set_tests_properties(swirl-font-selection PROPERTIES LABELS fonts TIMEOUT 30 ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software;QT_QPA_FONTDIR=${SWIRL_TEST_FONT_DIRECTORY}")
 add_test(NAME swirl-font-axis-policy COMMAND SwirlFontAxisPolicyTests -o "${CMAKE_CURRENT_BINARY_DIR}/font-axis-policy.xml,xml" -o "-,txt")
 set_tests_properties(swirl-font-axis-policy PROPERTIES LABELS fonts TIMEOUT 30)
 if(WIN32)
  add_test(NAME swirl-font-native-raster COMMAND SwirlFontTests nativeGlyphsHaveNoColourFringes previewRepeatedAxesReuseResources localSwirlCollectionUsesPhysicalFaces customAxesChangeRealGlyphsAtMixedCoordinates physicalIdentityRejectsMissingAndChangedOutlineTables -o "${CMAKE_CURRENT_BINARY_DIR}/font-native-raster.xml,xml" -o "-,txt")
  set_tests_properties(swirl-font-native-raster PROPERTIES LABELS fonts TIMEOUT 30 RUN_SERIAL TRUE ENVIRONMENT "QT_QPA_PLATFORM=windows;QSG_RHI_BACKEND=d3d11" ENVIRONMENT_MODIFICATION "QT_QUICK_BACKEND=unset:")
 endif()
 file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/font-toolchain.txt"
  "Qt=${Qt6_VERSION}\nCompiler=${CMAKE_CXX_COMPILER_ID}\nCompilerVersion=${CMAKE_CXX_COMPILER_VERSION}\nGenerator=${CMAKE_GENERATOR}\nGeneratorPlatform=${CMAKE_GENERATOR_PLATFORM}\nPointerSize=${CMAKE_SIZEOF_VOID_P}\nCxxStandard=${CMAKE_CXX_STANDARD}\n")
endfunction()

if(SWIRL_FONT_TESTS_ONLY)
 find_package(Qt6 6.9 REQUIRED COMPONENTS Quick QuickControls2 GuiPrivate Test)
 qt_standard_project_setup(REQUIRES 6.8)
 enable_testing()
 swirl_add_font_tests()
 return()
endif()

# The old runtime selector is accepted only as ON for existing build scripts.
# Font-only projects return above and never acquire a proxy runtime dependency.
if(DEFINED SWIRL_USE_RUST_CORE AND NOT SWIRL_USE_RUST_CORE)
 message(FATAL_ERROR "SWIRL_USE_RUST_CORE=OFF is no longer supported; Rust is the only product runtime")
endif()
set(SWIRL_USE_RUST_CORE ON CACHE BOOL "Deprecated: the product always uses Rust Core" FORCE)

find_package(Qt6 6.9 REQUIRED COMPONENTS Quick Qml QuickControls2 Network Svg GuiPrivate ShaderTools)
qt_standard_project_setup(REQUIRES 6.8)
qt_policy(SET QTP0004 NEW)
add_subdirectory(third_party)
add_executable(SwirlScriptRunner tools/ScriptRunner.cpp)
target_link_libraries(SwirlScriptRunner PRIVATE Qt6::Core Qt6::Qml)
target_compile_definitions(SwirlScriptRunner PRIVATE NOMINMAX)
qt_add_executable(Swirl WIN32 main.cpp app/DismissalController.h app/DismissalController.cpp app/SystemDataProvider.cpp app/SystemDataProvider.h app/WindowsBackdrop.cpp app/WindowsBackdrop.h network/CaptureService.cpp network/CaptureService.h app/ModuleDraftStore.cpp app/ModuleDraftStore.h)
execute_process(COMMAND git rev-parse --short HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" OUTPUT_VARIABLE SWIRL_BUILD_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}" OUTPUT_VARIABLE SWIRL_SOURCE_SHA OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT SWIRL_BUILD_REVISION)
 set(SWIRL_BUILD_REVISION "source-archive")
endif()
if(NOT SWIRL_SOURCE_SHA)
 set(SWIRL_SOURCE_SHA "source-archive")
endif()
# These values are consumed only by main.cpp. Keep QML/version updates from
# recompiling unrelated application objects and large embedded font resources.
set_property(SOURCE main.cpp APPEND PROPERTY COMPILE_DEFINITIONS SWIRL_APP_VERSION="${PROJECT_VERSION}")
target_sources(Swirl PRIVATE app/FontManager.h app/FontManager.cpp app/FontAxisPolicy.h app/FontAxisPolicy.cpp)
qt_add_resources(Swirl harmony_fonts PREFIX "/swirl/fonts" BASE "${CMAKE_CURRENT_SOURCE_DIR}/assets/fonts" FILES
 assets/fonts/HarmonyOS_Sans_SC_Regular.ttf assets/fonts/HarmonyOS_Sans_SC_Medium.ttf assets/fonts/HarmonyOS_Sans_SC_Bold.ttf assets/fonts/LICENSE_HarmonyOS_Sans.txt)
add_library(SwirlEngine STATIC
 app/DiagnosticService.h app/DiagnosticService.cpp
 engine/TelemetryService.h engine/TelemetryService.cpp
 engine/NodeTestService.h engine/NodeTestService.cpp
 engine/SystemProxySession.h engine/SystemProxySession.cpp
 engine/SystemProxyState.h engine/SystemProxyState.cpp
 engine/ProxyEngine.h
 engine/EngineController.h engine/EngineController.cpp)
target_sources(SwirlEngine PRIVATE engine/ProxyNode.h engine/ProxyNode.cpp engine/NodeStore.h engine/NodeStore.cpp)
target_sources(SwirlEngine PRIVATE engine/NodeImporter.h engine/NodeImporter.cpp)
target_sources(SwirlEngine PRIVATE engine/XrayJsonBridge.h engine/XrayJsonBridge.cpp engine/NativeNodeBridge.h engine/NativeNodeBridge.cpp)
target_sources(SwirlEngine PRIVATE engine/SubscriptionNormalizer.h engine/SubscriptionNormalizer.cpp)
target_sources(SwirlEngine PRIVATE engine/SwirlProtocolRegistry.h engine/SwirlProtocolRegistry.cpp)
target_sources(SwirlEngine PRIVATE engine/ConnectionDiagnostics.h engine/ConnectionDiagnostics.cpp)
target_sources(SwirlEngine PRIVATE engine/NodeImportService.h engine/NodeImportService.cpp)
target_sources(SwirlEngine PRIVATE network/HttpRequestPolicy.h)
target_sources(SwirlEngine PRIVATE engine/RustCoreEngine.h engine/RustCoreEngine.cpp)
include(cmake/SwirlRustCore.cmake)
swirl_pair_rust_core(SwirlEngine)
swirl_stage_rust_core(Swirl)
target_sources(SwirlEngine PRIVATE engine/RustCoreLibrary.h engine/RustCoreLibrary.cpp)
target_sources(Swirl PRIVATE engine/RustCoreSelfTest.h engine/RustCoreSelfTest.cpp)
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
set(SWIRL_QML_FILES
 qml/controls/SwirlText.qml qml/controls/SwirlFontBinding.qml
 qml/controls/SwirlTextArea.qml qml/controls/SwirlToolTip.qml
 qml/controls/SwirlLinkedDetail.qml
 qml/controls/SwirlNodeTransfer.qml
 qml/components/SwirlFontSettings.qml qml/components/NodeSourceHeader.qml
 qml/components/PolicyHelpers.js qml/components/PolicyTargetPicker.qml
 qml/components/ServicePolicyDialog.qml qml/components/PolicyProbeSettings.qml
 qml/components/PolicyGroupDialog.qml qml/components/ServiceAssignments.qml
 qml/components/SubscriptionRow.qml qml/components/SubscriptionDialog.qml qml/components/ConfigurationReviewDialog.qml
 qml/components/OutboundModeControl.qml
 qml/components/PolicyGroupList.qml qml/components/PolicyFormScroll.qml
 qml/components/SwirlSecondaryWindow.qml
 qml/components/SwirlWindowTitleBar.qml
 qml/controls/RewriteRulesDialog.qml
 qml/components/ReferenceSection.qml qml/components/ReferenceOutline.qml qml/components/ReferenceCheckBox.qml qml/pages/CaptureInspectorPage.qml
 qml/controls/SwirlStatusCapsule.qml qml/controls/SwirlSystemProxyCapsule.qml qml/controls/SwirlScrollBar.qml qml/pages/ProcessesPage.qml
 qml/Main.qml qml/Theme.qml qml/AppState.qml qml/FeatureCatalog.qml qml/SwirlMotion.qml qml/SwirlTransitionRegistry.qml
 qml/controls/SwirlTransitionCoordinator.qml qml/controls/SwirlHeroCard.qml qml/controls/SwirlHeroTitle.qml
 qml/components/SwirlContinuousSurface.qml qml/components/SwirlShellOutline.qml qml/components/SwirlBlurLayer.qml qml/components/SwirlGlassMaterial.qml qml/components/SwirlWindowControls.qml qml/components/SwirlDailyTrafficChart.qml
 qml/controls/SwirlClickLight.qml qml/controls/SwirlActivityIndicator.qml qml/controls/SwirlExpander.qml
 qml/controls/SwirlPressMotion.qml qml/controls/SwirlAnimatedModel.qml qml/controls/SwirlMotionButton.qml qml/controls/SwirlSpring.qml qml/controls/SwirlPageHost.qml
 qml/pages/FeatureHubPage.qml qml/pages/FeatureModulePage.qml qml/components/SwirlBrandIcon.qml
 qml/controls/SwirlPillSurface.qml qml/controls/SwirlIconButton.qml qml/controls/SwirlButton.qml qml/controls/SwirlSegmentedControl.qml qml/controls/SwirlToggle.qml
 qml/controls/SwirlSearchField.qml qml/controls/SwirlTextField.qml
 qml/controls/SwirlComboBox.qml qml/controls/SwirlDialog.qml
 qml/controls/SwirlDataTable.qml qml/controls/SwirlContextMenu.qml
 qml/components/SwirlClearGlassSurface.qml qml/components/SwirlGlassPanel.qml qml/components/SwirlNavigationItem.qml
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
# Resource URLs are shared across branches and test/production builds. Bind the
# disk cache to QML contents even when resource timestamps have not changed.
set(SWIRL_QML_CACHE_INPUT "")
foreach(qml IN LISTS SWIRL_QML_FILES)
 file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${qml}" qml_hash)
 string(APPEND SWIRL_QML_CACHE_INPUT "${qml}:${qml_hash}\n")
 set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${qml}")
endforeach()
string(SHA256 SWIRL_QML_CACHE_HASH "${SWIRL_QML_CACHE_INPUT}")
string(SUBSTRING "${SWIRL_QML_CACHE_HASH}" 0 16 SWIRL_QML_CACHE_REVISION)
set_property(SOURCE main.cpp APPEND PROPERTY COMPILE_DEFINITIONS SWIRL_QML_CACHE_REVISION="${SWIRL_QML_CACHE_REVISION}")
qt_add_qml_module(Swirl
    URI SwirlQuick
    VERSION 1.0
    RESOURCE_PREFIX /qt/qml
    NO_GENERATE_EXTRA_QMLDIRS
    QML_FILES ${SWIRL_QML_FILES}
    SOURCES app/JavascriptHighlighter.h app/JavascriptHighlighter.cpp app/WindowEdge.h app/WindowEdge.cpp app/VariableFontPreview.h app/VariableFontPreview.cpp app/FontDisplayContext.h app/FontDisplayContext.cpp app/NodeViewModel.h app/NodeViewModel.cpp app/NodeSectionModel.h app/NodeSectionModel.cpp
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
qt_add_shaders(Swirl glass_ui PREFIX "/swirl" BASE "${CMAKE_CURRENT_SOURCE_DIR}" FILES shaders/swirl-surface.frag shaders/swirl-blur.frag shaders/swirl-glass.frag shaders/sidebar-shadow.frag shaders/sidebar-transmission.frag)
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
if(SWIRL_XRAY_UI_TESTS)
 if(NOT SWIRL_USE_RUST_CORE)
  message(FATAL_ERROR "The JSON import UI acceptance profile requires the real Rust Core build")
 endif()
 find_package(Qt6 REQUIRED COMPONENTS Test QuickTest)
 target_sources(Swirl PRIVATE tests/XrayUiChecks.h tests/XrayUiChecks.cpp)
 target_compile_definitions(Swirl PRIVATE SWIRL_XRAY_UI_TESTS)
 target_link_libraries(Swirl PRIVATE Qt6::Test Qt6::QuickTest)
endif()
# The full UI profile includes these standalone tests for compatibility. The
# Core-only profile must leave Swirl's sources, resources and definitions intact.
if(SWIRL_BUILD_UI_TESTS OR SWIRL_BUILD_CORE_TESTS)
 enable_testing()
 add_executable(SwirlStoragePathsTests tests/StoragePathsTests.cpp)
 target_link_libraries(SwirlStoragePathsTests PRIVATE Qt6::Core)
 add_test(NAME swirl-storage-paths COMMAND SwirlStoragePathsTests)
 file(COPY "${CMAKE_CURRENT_SOURCE_DIR}/packaging/rules" DESTINATION "${CMAKE_CURRENT_BINARY_DIR}")
 find_package(Qt6 REQUIRED COMPONENTS Test)
 qt_add_executable(SwirlNodeViewModelTests tests/NodeViewModelTests.cpp app/NodeViewModel.h app/NodeViewModel.cpp)
 target_link_libraries(SwirlNodeViewModelTests PRIVATE SwirlEngine Qt6::Qml Qt6::Test)
 target_include_directories(SwirlNodeViewModelTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 add_test(NAME swirl-node-view-model COMMAND SwirlNodeViewModelTests)
 set_tests_properties(swirl-node-view-model PROPERTIES TIMEOUT 60)
 qt_add_executable(SwirlNodeSectionModelTests tests/NodeSectionModelTests.cpp app/NodeSectionModel.h app/NodeSectionModel.cpp app/NodeViewModel.h app/NodeViewModel.cpp)
 target_link_libraries(SwirlNodeSectionModelTests PRIVATE SwirlEngine Qt6::Qml Qt6::Test)
 target_include_directories(SwirlNodeSectionModelTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 add_test(NAME swirl-node-section-model COMMAND SwirlNodeSectionModelTests)
 set_tests_properties(swirl-node-section-model PROPERTIES TIMEOUT 60)
 qt_add_executable(SwirlPolicyConfigurationTests tests/PolicyConfigurationTests.cpp)
 target_link_libraries(SwirlPolicyConfigurationTests PRIVATE SwirlEngine Qt6::Test)
 target_include_directories(SwirlPolicyConfigurationTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 add_test(NAME swirl-policy-configuration COMMAND SwirlPolicyConfigurationTests)
 set_tests_properties(swirl-policy-configuration PROPERTIES TIMEOUT 60)
 qt_add_executable(SwirlCatalogTransactionTests tests/CatalogTransactionTests.cpp)
 target_link_libraries(SwirlCatalogTransactionTests PRIVATE SwirlEngine Qt6::Test)
 target_include_directories(SwirlCatalogTransactionTests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
 add_test(NAME swirl-catalog-transaction COMMAND SwirlCatalogTransactionTests)
 set_tests_properties(swirl-catalog-transaction PROPERTIES TIMEOUT 60)
 if(MSVC)
  target_compile_options(SwirlPolicyConfigurationTests PRIVATE /utf-8)
  target_compile_options(SwirlCatalogTransactionTests PRIVATE /utf-8)
 endif()
 swirl_add_font_tests()
 if(SWIRL_BUILD_UI_TESTS)
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
 endif()
 enable_testing()
 if(SWIRL_USE_RUST_CORE)
  add_executable(SwirlRustCoreTests tests/RustCoreTests.cpp)
  target_link_libraries(SwirlRustCoreTests PRIVATE SwirlEngine Qt6::Test)
  swirl_stage_rust_core(SwirlRustCoreTests)
  include(cmake/RustCoreLibraryTests.cmake)
  swirl_add_rust_library_tests()
  target_compile_definitions(SwirlRustCoreTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
  if(MSVC)
   target_compile_options(SwirlRustCoreTests PRIVATE /utf-8)
  endif()
  # Qt's Windows text logger may use OutputDebugString when the runner has no
  # console. Keep an explicit report so CI can show the actual failed assertion.
  add_test(NAME swirl-rust-qt-integration COMMAND SwirlRustCoreTests
   -o "${CMAKE_CURRENT_BINARY_DIR}/swirl-rust-qt-integration.xml,xml" -o -,txt)
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
 add_executable(SwirlExtensionTests tests/ExtensionTests.cpp)
 if(MSVC)
  target_compile_options(SwirlExtensionTests PRIVATE /utf-8)
 endif()
 target_link_libraries(SwirlExtensionTests PRIVATE SwirlExtensions Qt6::Test)
 add_dependencies(SwirlExtensionTests SwirlScriptRunner)
 add_test(NAME swirl-local-extensions COMMAND SwirlExtensionTests)
 set_tests_properties(swirl-local-extensions PROPERTIES TIMEOUT 60)
 add_executable(SwirlTelemetryTests tests/TelemetryTests.cpp)
 target_link_libraries(SwirlTelemetryTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlTelemetryTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
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
 add_executable(SwirlSystemProxyStateTests tests/SystemProxyStateTests.cpp)
 target_link_libraries(SwirlSystemProxyStateTests PRIVATE SwirlEngine Qt6::Test)
 if(MSVC)
  target_compile_options(SwirlSystemProxyStateTests PRIVATE /utf-8)
 endif()
 # Read-only live observations and a unique temporary registry key only;
 # this does not opt in to changing the user's Internet Settings.
 add_test(NAME swirl-system-proxy-state COMMAND SwirlSystemProxyStateTests)
 set_tests_properties(swirl-system-proxy-state PROPERTIES LABELS security TIMEOUT 30)
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
 add_executable(SwirlNodeTests tests/NodeTests.cpp tests/ControlledNetwork.h)
 target_link_libraries(SwirlNodeTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlNodeTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 if(MSVC)
  target_compile_options(SwirlNodeTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-node-real-chain COMMAND SwirlNodeTests -o node-chain.txt,txt -o node-chain.xml,xml -o -,txt)
 add_executable(SwirlNetworkRegressionTests tests/NetworkRegressionTests.cpp)
 target_link_libraries(SwirlNetworkRegressionTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlNetworkRegressionTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 add_test(NAME swirl-stream-regression COMMAND SwirlNetworkRegressionTests -o stream-regression.txt,txt -o stream-regression.xml,xml -o -,txt)
 set_tests_properties(swirl-stream-regression PROPERTIES TIMEOUT 180)
 add_executable(SwirlImportTests tests/ImportTests.cpp tests/ControlledNetwork.h)
 find_package(Python3 3.9 REQUIRED COMPONENTS Interpreter)
 add_executable(SwirlQtNetworkPolicyTests tests/QtNetworkPolicyTests.cpp)
 target_link_libraries(SwirlQtNetworkPolicyTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlQtNetworkPolicyTests PRIVATE
  SWIRL_TEST_PYTHON="${Python3_EXECUTABLE}"
  SWIRL_TLS_FIXTURE_SCRIPT="${CMAKE_CURRENT_SOURCE_DIR}/tests/qt-network/tls_origin.py")
 if(MSVC)
  target_compile_options(SwirlQtNetworkPolicyTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-qt-network-policy COMMAND SwirlQtNetworkPolicyTests
  -o "${CMAKE_CURRENT_BINARY_DIR}/qt-network-policy.xml,xml" -o -,txt)
 set_tests_properties(swirl-qt-network-policy PROPERTIES LABELS security TIMEOUT 90)
 add_executable(SwirlSubscriptionFormatTests tests/SubscriptionFormatTests.cpp tests/ControlledNetwork.h)
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
 add_test(NAME swirl-subscription-formats COMMAND SwirlSubscriptionFormatTests -o subscription-formats.txt,txt -o subscription-formats.xml,xml -o -,txt)
 set_tests_properties(swirl-subscription-formats PROPERTIES TIMEOUT 180)
 target_link_libraries(SwirlImportTests PRIVATE SwirlEngine Qt6::Test)
 target_compile_definitions(SwirlImportTests PRIVATE SWIRL_FIXTURE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
 if(MSVC)
  target_compile_options(SwirlImportTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-import-subscription COMMAND SwirlImportTests -o import-subscription.txt,txt -o import-subscription.xml,xml -o -,txt)
 set_tests_properties(swirl-import-subscription PROPERTIES TIMEOUT 120)
 add_test(NAME swirl-import-boundaries COMMAND SwirlImportTests sourceGlobalsArePreservedAndCannotBecomeNodeOnlyImports iniCompleteProfileHasClosedExecutionSemantics iniTransportAliasesCannotDowngradeSecurity iniEnvelopeAndWrappedJsonFailClosed typedOptionsAndAliasesCannotOverwriteImportedState legacyLoonAndEquivalentUriAliasesRetainTypedValues completeConfigurationWithoutOwnerDoesNotDiscardGlobals socks5TlsUriAliasesPreserveSecurity uriRealityRequiresAnExplicitSecurityLayerAndCredential tcpUriTransportRequirementsRemainBlockedAfterPersistence vlessUriAuthorityAndPathRequirementsRemainBlocked uriHeaderTypeHasClosedTransportSemantics preUpgradeUriStoreRechecksSourceWithoutRewriting singBoxTlsTypesAndFingerprintIntentArePreserved singBoxTransportShapesAndFieldsCannotDowngrade
  -o "${CMAKE_CURRENT_BINARY_DIR}/swirl-import-boundaries.xml,xml" -o -,txt)
 set_tests_properties(swirl-import-boundaries PROPERTIES TIMEOUT 30)
 set_tests_properties(swirl-node-real-chain PROPERTIES TIMEOUT 180)
 if(SWIRL_BUILD_UI_TESTS)
 target_sources(Swirl PRIVATE tests/EngineUiChecks.cpp tests/EngineUiChecks.h tests/NodeUiChecks.cpp tests/NodeUiChecks.h tests/PolicyUiChecks.cpp tests/PolicyUiChecks.h tests/MotionChecks.cpp tests/MotionChecks.h tests/LiquidGlassChecks.cpp tests/U2Checks.cpp)
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

foreach(runtime_target IN ITEMS SwirlProxyGuard SwirlExtensionTests SwirlTelemetryTests
 SwirlDiagnosticTests SwirlSystemProxyStateTests SwirlSystemProxyTests SwirlAcceptance SwirlNodeTests
 SwirlNetworkRegressionTests SwirlImportTests SwirlSubscriptionFormatTests
 SwirlPrivateSubscriptionInspect SwirlPolicyConfigurationTests SwirlCatalogTransactionTests)
 if(TARGET ${runtime_target})
  swirl_stage_rust_core(${runtime_target})
 endif()
endforeach()
