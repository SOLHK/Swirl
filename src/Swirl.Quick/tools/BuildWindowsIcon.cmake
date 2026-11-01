set(ENV{PATH} "${SWIRL_QT_BINARY_DIR};$ENV{PATH}")
get_filename_component(icon_working_directory "${SWIRL_ICON_BUILDER}" DIRECTORY)
message(STATUS "Generating Windows ICO with ${SWIRL_ICON_BUILDER} using Qt ${SWIRL_QT_BINARY_DIR}")
execute_process(
 COMMAND "${SWIRL_ICON_BUILDER}" "${SWIRL_ICON_SOURCE}" "${SWIRL_ICON_OUTPUT}"
 WORKING_DIRECTORY "${icon_working_directory}"
 RESULT_VARIABLE icon_result
 OUTPUT_VARIABLE icon_stdout
 ERROR_VARIABLE icon_stderr
 TIMEOUT 60
)
if(NOT icon_result STREQUAL "0")
 message(FATAL_ERROR "SwirlIconBuilder failed (${icon_result})\n${icon_stdout}${icon_stderr}")
endif()
