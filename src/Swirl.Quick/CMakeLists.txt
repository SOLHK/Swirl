cmake_minimum_required(VERSION 3.25)
project(Swirl VERSION 0.1 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.8 REQUIRED COMPONENTS Quick Qml QuickControls2)
qt_standard_project_setup(REQUIRES 6.8)
qt_policy(SET QTP0004 NEW)
qt_add_executable(Swirl WIN32 main.cpp demo/DemoDataProvider.cpp demo/DemoDataProvider.h app/WindowsBackdrop.cpp app/WindowsBackdrop.h)
set(SWIRL_QML_FILES
 qml/Main.qml qml/Theme.qml qml/AppState.qml
 qml/controls/SwirlButton.qml qml/controls/SwirlSegmentedControl.qml qml/controls/SwirlToggle.qml
 qml/controls/SwirlSearchField.qml qml/controls/SwirlTextField.qml
 qml/controls/SwirlComboBox.qml qml/controls/SwirlDialog.qml
 qml/controls/SwirlDataTable.qml qml/controls/SwirlContextMenu.qml
 qml/components/SwirlGlassPanel.qml qml/components/SwirlNavigationItem.qml
 qml/components/SwirlSidebar.qml qml/components/SwirlTrafficChart.qml
 qml/components/SwirlMetricCard.qml qml/components/SwirlStatusBadge.qml
 qml/components/SwirlInspectorPanel.qml qml/components/SwirlEmptyState.qml
 qml/components/SwirlIcon.qml
 qml/pages/OverviewPage.qml qml/pages/ConnectionsPage.qml
 qml/pages/ProxiesPage.qml qml/pages/InspectorPage.qml
 qml/pages/ScriptsPage.qml qml/pages/SettingsPage.qml
 qml/pages/WorkbenchPage.qml qml/pages/ToolboxPage.qml
 qml/pages/DashboardPage.qml qml/pages/DNSPage.qml
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
set_source_files_properties(qml/Theme.qml qml/AppState.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)
qt_add_qml_module(Swirl
    URI SwirlQuick
    VERSION 1.0
    RESOURCE_PREFIX /qt/qml
    NO_GENERATE_EXTRA_QMLDIRS
    QML_FILES ${SWIRL_QML_FILES}
    SOURCES app/JavascriptHighlighter.h app/JavascriptHighlighter.cpp
)
set(SWIRL_ASSET_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../AdShield/Assets")
qt_add_resources(Swirl brand PREFIX "/swirl" BASE "${SWIRL_ASSET_PATH}" FILES "${SWIRL_ASSET_PATH}/swirl-256.png")
target_include_directories(Swirl PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/app")
target_link_libraries(Swirl PRIVATE Qt6::Quick Qt6::Qml Qt6::QuickControls2)
if(WIN32)
 target_link_libraries(Swirl PRIVATE dwmapi)
endif()
