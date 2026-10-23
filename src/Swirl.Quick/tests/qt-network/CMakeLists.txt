cmake_minimum_required(VERSION 3.25)
project(SwirlQtNetworkPolicyTests LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.9 REQUIRED COMPONENTS Core Gui Network Test)
if(NOT SWIRL_TEST_PYTHON)
 find_package(Python3 3.9 REQUIRED COMPONENTS Interpreter)
 set(SWIRL_TEST_PYTHON "${Python3_EXECUTABLE}")
endif()
enable_testing()

get_filename_component(SWIRL_QUICK_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
include("${SWIRL_QUICK_SOURCE}/cmake/SwirlRustCore.cmake")
# Compile the real downloader and parser. No Rust runtime is started by these
# tests, and the existing application callback observes parsed nodes without
# pretending that non-Windows hosts implement the Windows DPAPI store.
add_executable(SwirlQtNetworkPolicyTests
 "${SWIRL_QUICK_SOURCE}/tests/QtNetworkPolicyTests.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/NodeImportService.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/NodeImportService.h"
 "${SWIRL_QUICK_SOURCE}/engine/NodeStore.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/NodeStore.h"
 "${SWIRL_QUICK_SOURCE}/engine/NodeImporter.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/SubscriptionNormalizer.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/ProxyNode.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/SwirlProtocolRegistry.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/XrayJsonBridge.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/RustCoreEngine.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/RustCoreLibrary.cpp"
 "${SWIRL_QUICK_SOURCE}/engine/ProxyEngine.h")
target_include_directories(SwirlQtNetworkPolicyTests PRIVATE "${SWIRL_QUICK_SOURCE}")
target_compile_definitions(SwirlQtNetworkPolicyTests PRIVATE
 SWIRL_USE_RUST_CORE
 SWIRL_TEST_PYTHON="${SWIRL_TEST_PYTHON}"
 SWIRL_TLS_FIXTURE_SCRIPT="${CMAKE_CURRENT_LIST_DIR}/tls_origin.py")
target_link_libraries(SwirlQtNetworkPolicyTests PRIVATE Qt6::Core Qt6::Gui Qt6::Network Qt6::Test)
swirl_pair_rust_core(SwirlQtNetworkPolicyTests)
swirl_stage_rust_core(SwirlQtNetworkPolicyTests)
if(WIN32)
 target_compile_definitions(SwirlQtNetworkPolicyTests PRIVATE NOMINMAX)
 target_link_libraries(SwirlQtNetworkPolicyTests PRIVATE crypt32)
endif()
if(MSVC)
 target_compile_options(SwirlQtNetworkPolicyTests PRIVATE /utf-8)
endif()
add_test(NAME swirl-qt-network-policy COMMAND SwirlQtNetworkPolicyTests
 -o "${CMAKE_CURRENT_BINARY_DIR}/qt-network-policy.xml,xml" -o -,txt)
set_tests_properties(swirl-qt-network-policy PROPERTIES TIMEOUT 90)
