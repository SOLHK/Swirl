function(swirl_add_rust_library_tests)
 add_executable(SwirlRustCoreLibraryTests
  "${SWIRL_QUICK_SOURCE}/tests/RustCoreLibraryTests.cpp"
  "${SWIRL_QUICK_SOURCE}/engine/RustCoreLibrary.cpp")
 target_include_directories(SwirlRustCoreLibraryTests PRIVATE "${SWIRL_QUICK_SOURCE}")
 target_link_libraries(SwirlRustCoreLibraryTests PRIVATE Qt6::Core Qt6::Test)
 swirl_pair_rust_core(SwirlRustCoreLibraryTests)
 swirl_stage_rust_core(SwirlRustCoreLibraryTests)
 foreach(kind RANGE 1 10)
  add_library(SwirlLoaderFixture${kind} SHARED "${SWIRL_QUICK_SOURCE}/tests/RustCoreLibraryTests.cpp")
  target_link_libraries(SwirlLoaderFixture${kind} PRIVATE Qt6::Core)
  target_compile_definitions(SwirlLoaderFixture${kind} PRIVATE
   SWIRL_LOADER_FIXTURE_KIND=${kind} SWIRL_RUST_BUILD_ID="${SWIRL_RUST_BUILD_ID}" SWIRL_SOURCE_SHA="${SWIRL_SOURCE_SHA}")
  set_target_properties(SwirlLoaderFixture${kind} PROPERTIES
   AUTOMOC OFF
   OUTPUT_NAME "swirl_loader_fixture_${kind}"
   LIBRARY_OUTPUT_DIRECTORY "$<TARGET_FILE_DIR:SwirlRustCoreLibraryTests>/loader-fixtures"
   RUNTIME_OUTPUT_DIRECTORY "$<TARGET_FILE_DIR:SwirlRustCoreLibraryTests>/loader-fixtures")
  # A parent project may flatten each configuration into bin/. Those inherited
  # per-configuration properties take precedence over the generic directory,
  # especially for Windows DLLs, which are RUNTIME artifacts. Keep all actual
  # shared fixtures beside the test's expected loader-fixtures directory.
  foreach(configuration IN ITEMS Debug Release RelWithDebInfo MinSizeRel ${CMAKE_CONFIGURATION_TYPES} ${CMAKE_BUILD_TYPE})
   string(TOUPPER "${configuration}" configuration_upper)
   set_target_properties(SwirlLoaderFixture${kind} PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY_${configuration_upper} "$<TARGET_FILE_DIR:SwirlRustCoreLibraryTests>/loader-fixtures"
    RUNTIME_OUTPUT_DIRECTORY_${configuration_upper} "$<TARGET_FILE_DIR:SwirlRustCoreLibraryTests>/loader-fixtures")
  endforeach()
  add_dependencies(SwirlRustCoreLibraryTests SwirlLoaderFixture${kind})
  if(MSVC)
   target_compile_options(SwirlLoaderFixture${kind} PRIVATE /utf-8)
  endif()
 endforeach()
 if(MSVC)
  target_compile_options(SwirlRustCoreLibraryTests PRIVATE /utf-8)
 endif()
 add_test(NAME swirl-rust-library-loader COMMAND SwirlRustCoreLibraryTests
  -o "${CMAKE_CURRENT_BINARY_DIR}/swirl-rust-library-loader.xml,xml" -o -,txt)
 set_tests_properties(swirl-rust-library-loader PROPERTIES TIMEOUT 60
  ENVIRONMENT "QT_FORCE_STDERR_LOGGING=1")
endfunction()
