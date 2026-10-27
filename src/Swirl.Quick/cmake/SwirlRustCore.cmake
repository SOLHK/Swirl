# Cargo owns Rust's dependency graph; CMake owns pairing/staging with Qt.
# Keep Cargo incremental, but invoke it on every product build. A stale output
# timestamp must never bypass a changed toolchain, vendored crate or build.rs.
include_guard(GLOBAL)
find_program(SWIRL_CARGO cargo REQUIRED)
find_program(SWIRL_RUSTC rustc REQUIRED)
get_filename_component(SWIRL_QUICK_SOURCE "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
get_filename_component(SWIRL_RUST_SOURCE "${SWIRL_QUICK_SOURCE}/../../core" ABSOLUTE)
get_filename_component(SWIRL_REPOSITORY_ROOT "${SWIRL_RUST_SOURCE}/.." ABSOLUTE)
set(SWIRL_RUST_TARGET "${CMAKE_CURRENT_BINARY_DIR}/rust-target" CACHE PATH "Cargo build cache for the paired Rust runtime")

if(WIN32)
 if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8 OR CMAKE_SYSTEM_PROCESSOR MATCHES "^(ARM|arm|aarch64)")
  message(FATAL_ERROR "Swirl Windows product requires an x64 Qt toolchain")
 endif()
 if(CMAKE_GENERATOR_PLATFORM AND NOT CMAKE_GENERATOR_PLATFORM MATCHES "^[xX]64$")
  message(FATAL_ERROR "Configure the Windows product with -A x64")
 endif()
 if(MSVC)
  set(SWIRL_RUST_TRIPLE "x86_64-pc-windows-msvc")
 elseif(MINGW AND CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  execute_process(COMMAND "${CMAKE_CXX_COMPILER}" -dumpmachine
   OUTPUT_VARIABLE SWIRL_CXX_TARGET OUTPUT_STRIP_TRAILING_WHITESPACE
   RESULT_VARIABLE SWIRL_CXX_TARGET_RESULT)
  if(NOT SWIRL_CXX_TARGET_RESULT EQUAL 0 OR NOT SWIRL_CXX_TARGET STREQUAL "x86_64-w64-mingw32")
   message(FATAL_ERROR "Swirl MinGW product requires the x86_64-w64-mingw32 compiler")
  endif()
  # The U2 Windows UI uses MinGW. Pair it with the GNU Rust target through
  # the same checked C ABI; never load an MSVC DLL from another build tree.
  set(SWIRL_RUST_TRIPLE "x86_64-pc-windows-gnu")
 else()
  message(FATAL_ERROR "Swirl Windows product requires x64 MSVC or x64 GNU MinGW")
 endif()
 set(SWIRL_RUST_LIBRARY_NAME "swirl_api.dll")
else()
 # Used for native integration tests; this does not claim Linux/macOS packaging.
 execute_process(COMMAND "${SWIRL_RUSTC}" -vV
  WORKING_DIRECTORY "${SWIRL_RUST_SOURCE}"
  OUTPUT_VARIABLE SWIRL_RUSTC_VERSION RESULT_VARIABLE SWIRL_RUSTC_RESULT)
 if(NOT SWIRL_RUSTC_RESULT EQUAL 0 OR NOT SWIRL_RUSTC_VERSION MATCHES "host: ([A-Za-z0-9_.-]+)")
  message(FATAL_ERROR "Cannot determine the native Rust target")
 endif()
 set(SWIRL_RUST_TRIPLE "${CMAKE_MATCH_1}")
 if(CMAKE_CROSSCOMPILING)
  message(FATAL_ERROR "Non-Windows Rust/Qt cross compilation is not configured")
 endif()
 if(APPLE)
  set(SWIRL_RUST_LIBRARY_NAME "libswirl_api.dylib")
 else()
  set(SWIRL_RUST_LIBRARY_NAME "libswirl_api.so")
 endif()
endif()
set(SWIRL_RUST_LIBRARY "${SWIRL_RUST_TARGET}/${SWIRL_RUST_TRIPLE}/release/${SWIRL_RUST_LIBRARY_NAME}")

# Reconfigure when existing production inputs change, not just when the glob's
# file list changes. Build scripts, vendored sources and the lockfile are inputs.
file(GLOB_RECURSE SWIRL_RUST_INPUTS CONFIGURE_DEPENDS
 "${SWIRL_RUST_SOURCE}/crates/*.rs" "${SWIRL_RUST_SOURCE}/crates/*.toml"
 "${SWIRL_RUST_SOURCE}/vendor/*.rs" "${SWIRL_RUST_SOURCE}/vendor/*.toml")
list(FILTER SWIRL_RUST_INPUTS EXCLUDE REGEX "/(tests|benches|examples|testdata)/|/[^/]*_tests?\\.rs$|/test\\.rs$")
list(APPEND SWIRL_RUST_INPUTS
 "${SWIRL_RUST_SOURCE}/Cargo.toml" "${SWIRL_RUST_SOURCE}/Cargo.lock"
 "${SWIRL_RUST_SOURCE}/rust-toolchain.toml" "${CMAKE_CURRENT_LIST_FILE}")
foreach(config IN ITEMS "${SWIRL_REPOSITORY_ROOT}/.cargo/config" "${SWIRL_REPOSITORY_ROOT}/.cargo/config.toml"
 "${SWIRL_RUST_SOURCE}/.cargo/config" "${SWIRL_RUST_SOURCE}/.cargo/config.toml")
 if(EXISTS "${config}")
  list(APPEND SWIRL_RUST_INPUTS "${config}")
 endif()
endforeach()
list(SORT SWIRL_RUST_INPUTS)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${SWIRL_RUST_INPUTS})
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${SWIRL_REPOSITORY_ROOT}"
 OUTPUT_VARIABLE SWIRL_SOURCE_SHA OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT SWIRL_SOURCE_SHA MATCHES "^[0-9a-f]+$")
 set(SWIRL_SOURCE_SHA "source-archive")
endif()
# A new commit/checkout must also refresh the EXE and DLL source revision, even
# if its only source changes are outside Rust. Works with normal Git worktrees.
execute_process(COMMAND git symbolic-ref -q HEAD WORKING_DIRECTORY "${SWIRL_REPOSITORY_ROOT}"
 OUTPUT_VARIABLE SWIRL_GIT_REF OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
foreach(git_entry IN ITEMS HEAD "${SWIRL_GIT_REF}" packed-refs)
 if(git_entry)
  execute_process(COMMAND git rev-parse --git-path "${git_entry}"
   WORKING_DIRECTORY "${SWIRL_REPOSITORY_ROOT}"
   OUTPUT_VARIABLE git_path OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
  if(git_path)
   get_filename_component(git_path "${git_path}" ABSOLUTE BASE_DIR "${SWIRL_REPOSITORY_ROOT}")
   if(EXISTS "${git_path}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${git_path}")
   endif()
  endif()
 endif()
endforeach()
set(identity "swirl-cabi-1\n${SWIRL_RUST_TRIPLE}\nrelease\n${SWIRL_SOURCE_SHA}\n")
foreach(input IN LISTS SWIRL_RUST_INPUTS)
 file(SHA256 "${input}" digest)
 file(RELATIVE_PATH relative "${SWIRL_REPOSITORY_ROOT}" "${input}")
 string(APPEND identity "${relative}:${digest}\n")
endforeach()
string(SHA256 SWIRL_RUST_BUILD_ID "${identity}")
set(SWIRL_RUST_LIBRARY "${SWIRL_RUST_LIBRARY}" CACHE INTERNAL "Exact Cargo product library" FORCE)
set(SWIRL_RUST_TRIPLE "${SWIRL_RUST_TRIPLE}" CACHE INTERNAL "Cargo target paired with Qt" FORCE)
set(SWIRL_RUST_BUILD_ID "${SWIRL_RUST_BUILD_ID}" CACHE INTERNAL "Rust/Qt content build identity" FORCE)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/swirl-rust-build.json"
 "{\"abi_version\":1,\"build_id\":\"${SWIRL_RUST_BUILD_ID}\",\"source_sha\":\"${SWIRL_SOURCE_SHA}\",\"target\":\"${SWIRL_RUST_TRIPLE}\"}\n")
# Only the loader and diagnostic identity consumers need to recompile when the
# source revision changes. Target-wide definitions previously invalidated every
# C++ object, including the large embedded font resources, after each commit.
# file(CONFIGURE) preserves the header timestamp when its content is unchanged.
set(SWIRL_BUILD_IDENTITY_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(CONFIGURE OUTPUT "${SWIRL_BUILD_IDENTITY_DIRECTORY}/SwirlBuildIdentity.h"
 CONTENT "#pragma once\n#define SWIRL_RUST_BUILD_ID \"@SWIRL_RUST_BUILD_ID@\"\n#define SWIRL_SOURCE_SHA \"@SWIRL_SOURCE_SHA@\"\n" @ONLY)

add_custom_target(SwirlRustCore
 COMMAND "${CMAKE_COMMAND}" -E env
  "SWIRL_BUILD_ID=${SWIRL_RUST_BUILD_ID}" "SWIRL_SOURCE_SHA=${SWIRL_SOURCE_SHA}"
  "${SWIRL_CARGO}" build --release --locked --lib --target "${SWIRL_RUST_TRIPLE}"
  --manifest-path "${SWIRL_RUST_SOURCE}/Cargo.toml" --target-dir "${SWIRL_RUST_TARGET}" -p swirl-api
 COMMAND "${CMAKE_COMMAND}" "-DSWIRL_LIBRARY=${SWIRL_RUST_LIBRARY}"
  -P "${CMAKE_CURRENT_LIST_DIR}/RequireRustLibrary.cmake"
 BYPRODUCTS "${SWIRL_RUST_LIBRARY}"
 WORKING_DIRECTORY "${SWIRL_RUST_SOURCE}"
 COMMENT "Build the paired Rust Core with Cargo; stale DLL fallback is forbidden"
 VERBATIM USES_TERMINAL)

function(swirl_pair_rust_core target)
 add_dependencies(${target} SwirlRustCore)
 target_compile_definitions(${target} PUBLIC SWIRL_USE_RUST_CORE)
 target_include_directories(${target} PUBLIC "${SWIRL_BUILD_IDENTITY_DIRECTORY}")
endfunction()

function(swirl_stage_rust_core target)
 add_dependencies(${target} SwirlRustCore)
 # This event runs even when a Rust-only change did not relink the executable.
 add_custom_command(TARGET SwirlRustCore POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E make_directory "$<TARGET_FILE_DIR:${target}>"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${SWIRL_RUST_LIBRARY}" "$<TARGET_FILE_DIR:${target}>/${SWIRL_RUST_LIBRARY_NAME}"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${CMAKE_CURRENT_BINARY_DIR}/swirl-rust-build.json" "$<TARGET_FILE_DIR:${target}>/swirl-rust-build.json"
  COMMAND "${CMAKE_COMMAND}" -E copy_directory "${SWIRL_QUICK_SOURCE}/packaging/rules" "$<TARGET_FILE_DIR:${target}>/rules"
  VERBATIM)
endfunction()
