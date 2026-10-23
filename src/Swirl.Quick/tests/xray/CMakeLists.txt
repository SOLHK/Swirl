cmake_minimum_required(VERSION 3.25)
project(SwirlXrayProductTests LANGUAGES CXX)

# The product importer is tested independently of Quick, fonts and retained
# compatibility engines. These are the actual production sources and Rust ABI.
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.9 REQUIRED COMPONENTS Core Network Gui Test)
enable_testing()

get_filename_component(SWIRL_QUICK_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
get_filename_component(SWIRL_REPOSITORY "${SWIRL_QUICK_SOURCE}/../.." ABSOLUTE)
include("${SWIRL_QUICK_SOURCE}/cmake/SwirlRustCore.cmake")

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/bin")
foreach(configuration IN ITEMS DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${configuration} "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}")
endforeach()

add_library(SwirlXrayProduct STATIC
    "${SWIRL_QUICK_SOURCE}/engine/ProxyEngine.h"
    "${SWIRL_QUICK_SOURCE}/engine/EngineController.h"
    "${SWIRL_QUICK_SOURCE}/engine/EngineController.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/NodeTestService.h"
    "${SWIRL_QUICK_SOURCE}/engine/NodeTestService.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/TelemetryService.h"
    "${SWIRL_QUICK_SOURCE}/engine/TelemetryService.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/SystemProxySession.h"
    "${SWIRL_QUICK_SOURCE}/engine/SystemProxySession.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/ConnectionDiagnostics.h"
    "${SWIRL_QUICK_SOURCE}/engine/ConnectionDiagnostics.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/ProxyNode.h"
    "${SWIRL_QUICK_SOURCE}/engine/ProxyNode.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/NodeImporter.h"
    "${SWIRL_QUICK_SOURCE}/engine/NodeImporter.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/SubscriptionNormalizer.h"
    "${SWIRL_QUICK_SOURCE}/engine/SubscriptionNormalizer.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/NodeStore.h"
    "${SWIRL_QUICK_SOURCE}/engine/NodeStore.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/NodeImportService.h"
    "${SWIRL_QUICK_SOURCE}/engine/NodeImportService.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/SwirlProtocolRegistry.h"
    "${SWIRL_QUICK_SOURCE}/engine/SwirlProtocolRegistry.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/XrayJsonBridge.h"
    "${SWIRL_QUICK_SOURCE}/engine/XrayJsonBridge.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreLibrary.h"
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreLibrary.cpp"
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreEngine.h"
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreEngine.cpp")
target_include_directories(SwirlXrayProduct PUBLIC "${SWIRL_QUICK_SOURCE}")
swirl_pair_rust_core(SwirlXrayProduct)
target_link_libraries(SwirlXrayProduct PUBLIC Qt6::Core Qt6::Network Qt6::Gui)
if(WIN32)
    target_compile_definitions(SwirlXrayProduct PUBLIC NOMINMAX)
    target_link_libraries(SwirlXrayProduct PRIVATE crypt32 wininet iphlpapi ws2_32)
endif()
if(MSVC)
    target_compile_options(SwirlXrayProduct PRIVATE /utf-8)
endif()

# All executables stage the same content-paired library and verified rules.
function(swirl_add_xray_test target source test_name)
    add_executable(${target} "${SWIRL_QUICK_SOURCE}/tests/${source}")
    target_link_libraries(${target} PRIVATE SwirlXrayProduct Qt6::Test)
    target_compile_definitions(${target} PRIVATE
        SWIRL_FIXTURE_DIR="${SWIRL_QUICK_SOURCE}/tests/fixtures"
        SWIRL_SOURCE_ROOT="${SWIRL_REPOSITORY}")
    if(MSVC)
        target_compile_options(${target} PRIVATE /utf-8)
    endif()
    swirl_stage_rust_core(${target})
    file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/${test_name}-state")
    add_test(NAME ${test_name} COMMAND ${target}
        -o "${CMAKE_CURRENT_BINARY_DIR}/${test_name}.xml,xml" -o "-,txt")
    set_tests_properties(${test_name} PROPERTIES
        TIMEOUT 180
        LABELS "xray;qt;rust-ffi"
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_FORCE_STDERR_LOGGING=1;SWIRL_TEST_ROOT=${CMAKE_CURRENT_BINARY_DIR}/${test_name}-state")
endfunction()

swirl_add_xray_test(SwirlXrayImportTests XrayImportTests.cpp swirl-xray-import)
swirl_add_xray_test(SwirlXrayDownloadTests XrayDownloadTests.cpp swirl-xray-download)
# The complete product chain must not silently lose coverage if a test source
# is removed or renamed. Windows executes DPAPI; other platforms fail closed.
swirl_add_xray_test(SwirlXrayStoreTests XrayStoreTests.cpp swirl-xray-store)
swirl_add_xray_test(SwirlXrayRuntimeTests XrayRuntimeTests.cpp swirl-xray-runtime)
swirl_add_xray_test(SwirlXrayCatalogTests XrayCatalogTests.cpp swirl-xray-catalog)

execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${SWIRL_REPOSITORY}"
    OUTPUT_VARIABLE SWIRL_SOURCE_SHA OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/xray-toolchain.txt"
    "Source=${SWIRL_SOURCE_SHA}\nQt=${Qt6_VERSION}\nCompiler=${CMAKE_CXX_COMPILER_ID}\nCompilerVersion=${CMAKE_CXX_COMPILER_VERSION}\nSystem=${CMAKE_SYSTEM_NAME}\nArchitecture=${CMAKE_SYSTEM_PROCESSOR}\nRustLibrary=${SWIRL_RUST_LIBRARY}\n")

include("${SWIRL_QUICK_SOURCE}/cmake/RustCoreLibraryTests.cmake")
swirl_add_rust_library_tests()
