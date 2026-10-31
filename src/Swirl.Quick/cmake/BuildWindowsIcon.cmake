# Build-time rasterization must not depend on a native desktop/QPA session.
# This script is a separate process; its environment never changes Swirl, the
# build's other tools, or the native Windows UI acceptance tests.
foreach(required IN ITEMS SWIRL_ICON_BUILDER SWIRL_ICON_PLATFORM_PLUGIN SWIRL_ICON_SOURCE SWIRL_ICON_OUTPUT)
 if(NOT DEFINED ${required} OR "${${required}}" STREQUAL "")
  message(FATAL_ERROR "Missing required icon build input: ${required}")
 endif()
endforeach()
if(NOT EXISTS "${SWIRL_ICON_BUILDER}" OR NOT EXISTS "${SWIRL_ICON_SOURCE}"
   OR NOT EXISTS "${SWIRL_ICON_PLATFORM_PLUGIN}")
 message(FATAL_ERROR "The built icon tool, selected SDK offscreen plugin or canonical SVG is missing")
endif()

# Other test targets deploy Qt DLLs into the shared output directory before
# this tool runs. A deployed QtCore/qt.conf changes default plugin discovery;
# windeployqt does not include offscreen unless explicitly requested. Resolve
# the build-only platform plugin from the same CMake-imported SDK/configuration,
# rather than depending on whichever deployment happened to run first.
get_filename_component(icon_platform_directory "${SWIRL_ICON_PLATFORM_PLUGIN}" DIRECTORY)
get_filename_component(icon_plugin_root "${icon_platform_directory}" DIRECTORY)
set(ENV{QT_QPA_PLATFORM} "offscreen")
set(ENV{QT_QPA_PLATFORM_PLUGIN_PATH} "${icon_platform_directory}")
set(ENV{QT_PLUGIN_PATH} "${icon_plugin_root}")
set(ENV{QT_DEBUG_PLUGINS} "1")
set(ENV{QT_FORCE_STDERR_LOGGING} "1")
message(STATUS "Generate canonical Windows ICO with headless Qt; tool deadline: 60 seconds")
message(STATUS "Icon platform plugin from selected Qt SDK: ${SWIRL_ICON_PLATFORM_PLUGIN}")
execute_process(
 COMMAND "${SWIRL_ICON_BUILDER}" "${SWIRL_ICON_SOURCE}" "${SWIRL_ICON_OUTPUT}"
 RESULT_VARIABLE icon_result
 OUTPUT_VARIABLE icon_stdout
 ERROR_VARIABLE icon_stderr
 ECHO_OUTPUT_VARIABLE
 ECHO_ERROR_VARIABLE
 TIMEOUT 60)
if(NOT "${icon_result}" STREQUAL "0")
 # A failed or timed-out tool must not leave a generated file that a later
 # incremental build could mistake for a successful output.
 file(REMOVE "${SWIRL_ICON_OUTPUT}")
 message(FATAL_ERROR "Canonical Windows ICO generation failed: ${icon_result}\n${icon_stdout}\n${icon_stderr}")
endif()
if(NOT EXISTS "${SWIRL_ICON_OUTPUT}")
 message(FATAL_ERROR "The icon tool returned success without its generated ICO")
endif()
file(SIZE "${SWIRL_ICON_OUTPUT}" icon_size)
if(icon_size LESS 22)
 file(REMOVE "${SWIRL_ICON_OUTPUT}")
 message(FATAL_ERROR "The generated ICO has no complete directory entry")
endif()
message(STATUS "Canonical Windows ICO generation completed (${icon_size} bytes)")
