cmake_minimum_required(VERSION 3.25)
project(SwirlQuick VERSION 0.1 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.8 REQUIRED COMPONENTS Quick Qml QuickControls2)
qt_standard_project_setup(REQUIRES 6.8)
qt_policy(SET QTP0004 NEW)
qt_add_executable(SwirlQuick WIN32 main.cpp demo/DemoDataProvider.cpp demo/DemoDataProvider.h app/WindowsBackdrop.cpp app/WindowsBackdrop.h)
set_source_files_properties(qml/Main.qml PROPERTIES QT_RESOURCE_ALIAS Main.qml)
set_source_files_properties(qml/Theme.qml PROPERTIES QT_RESOURCE_ALIAS Theme.qml QT_QML_SINGLETON_TYPE TRUE)
set_source_files_properties(qml/AppState.qml PROPERTIES QT_RESOURCE_ALIAS AppState.qml QT_QML_SINGLETON_TYPE TRUE)
qt_add_qml_module(SwirlQuick URI SwirlQuick VERSION 1.0 RESOURCE_PREFIX /qt/qml QML_FILES
 qml/Main.qml qml/Theme.qml qml/AppState.qml
 qml/controls/SwirlButton.qml qml/controls/SwirlToggle.qml
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
)
set(SWIRL_ASSET_PATH "${CMAKE_CURRENT_SOURCE_DIR}/../../AdShield/Assets")
qt_add_resources(SwirlQuick brand PREFIX "/swirl" BASE "${SWIRL_ASSET_PATH}" FILES "${SWIRL_ASSET_PATH}/swirl-256.png")
target_link_libraries(SwirlQuick PRIVATE Qt6::Quick Qt6::Qml Qt6::QuickControls2)
if(WIN32)
 target_link_libraries(SwirlQuick PRIVATE dwmapi)
endif()
