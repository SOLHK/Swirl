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
set(SWIRL_RUST_LIBRARY "" CACHE FILEPATH "Exact-source swirl-api cdylib built with cargo --locked")
if(NOT IS_ABSOLUTE "${SWIRL_RUST_LIBRARY}" OR NOT EXISTS "${SWIRL_RUST_LIBRARY}")
    message(FATAL_ERROR "Build swirl-api first and pass its absolute path as SWIRL_RUST_LIBRARY; no mock or external core is used")
endif()

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
    "${SWIRL_QUICK_SOURCE}/engine/ProxyLatencyProbe.h"
    "${SWIRL_QUICK_SOURCE}/engine/ProxyLatencyProbe.cpp"
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
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreEngine.h"
    "${SWIRL_QUICK_SOURCE}/engine/RustCoreEngine.cpp")
target_include_directories(SwirlXrayProduct PUBLIC "${SWIRL_QUICK_SOURCE}")
target_compile_definitions(SwirlXrayProduct PUBLIC SWIRL_USE_RUST_CORE)
target_link_libraries(SwirlXrayProduct PUBLIC Qt6::Core Qt6::Network Qt6::Gui)
if(WIN32)
    target_compile_definitions(SwirlXrayProduct PUBLIC NOMINMAX)
    target_link_libraries(SwirlXrayProduct PRIVATE crypt32 wininet iphlpapi ws2_32)
endif()
if(MSVC)
    target_compile_options(SwirlXrayProduct PRIVATE /utf-8)
endif()

# Copy on every build, including a Rust-only rebuild with unchanged Qt objects.
# QLibrary resolves libswirl_api.{so,dylib} or swirl_api.dll in the executable dir.
add_custom_target(SwirlXrayRustRuntime ALL
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${SWIRL_RUST_LIBRARY}" "${CMAKE_RUNTIME_OUTPUT_DIRECTORY}"
    DEPENDS "${SWIRL_RUST_LIBRARY}"
    VERBATIM)

function(swirl_add_xray_test target source test_name)
    add_executable(${target} "${SWIRL_QUICK_SOURCE}/tests/${source}")
    target_link_libraries(${target} PRIVATE SwirlXrayProduct Qt6::Test)
    target_compile_definitions(${target} PRIVATE
        SWIRL_FIXTURE_DIR="${SWIRL_QUICK_SOURCE}/tests/fixtures"
        SWIRL_SOURCE_ROOT="${SWIRL_REPOSITORY}")
    if(MSVC)
        target_compile_options(${target} PRIVATE /utf-8)
    endif()
    add_dependencies(${target} SwirlXrayRustRuntime)
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
# D1 precedes the storage stage. Once its source is committed, the same build
# automatically runs the real DPAPI roundtrip on Windows and fails closed tests
# on other platforms; CI verifies the required Windows test is actually present.
if(EXISTS "${SWIRL_QUICK_SOURCE}/tests/XrayStoreTests.cpp")
    swirl_add_xray_test(SwirlXrayStoreTests XrayStoreTests.cpp swirl-xray-store)
endif()
if(EXISTS "${SWIRL_QUICK_SOURCE}/tests/XrayRuntimeTests.cpp")
    swirl_add_xray_test(SwirlXrayRuntimeTests XrayRuntimeTests.cpp swirl-xray-runtime)
endif()
if(EXISTS "${SWIRL_QUICK_SOURCE}/tests/XrayCatalogTests.cpp")
    swirl_add_xray_test(SwirlXrayCatalogTests XrayCatalogTests.cpp swirl-xray-catalog)
endif()

execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${SWIRL_REPOSITORY}"
    OUTPUT_VARIABLE SWIRL_SOURCE_SHA OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/xray-toolchain.txt"
    "Source=${SWIRL_SOURCE_SHA}\nQt=${Qt6_VERSION}\nCompiler=${CMAKE_CXX_COMPILER_ID}\nCompilerVersion=${CMAKE_CXX_COMPILER_VERSION}\nSystem=${CMAKE_SYSTEM_NAME}\nArchitecture=${CMAKE_SYSTEM_PROCESSOR}\nRustLibrary=${SWIRL_RUST_LIBRARY}\n")
