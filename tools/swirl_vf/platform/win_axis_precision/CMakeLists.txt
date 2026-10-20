cmake_minimum_required(VERSION 3.24)
project(SwirlWindowsAxisPrecision LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "D1 acceptance requires the actual Windows SDK and runtime")
endif()

find_package(Qt6 6.10.3 EXACT REQUIRED COMPONENTS Core Gui)
add_executable(win_axis_precision_directwrite ../win_axis_precision_directwrite.cpp)
target_compile_features(win_axis_precision_directwrite PRIVATE cxx_std_17)
target_link_libraries(win_axis_precision_directwrite PRIVATE dwrite d2d1 windowscodecs ole32 bcrypt)

add_executable(win_axis_precision_qt ../win_axis_precision_qt.cpp)
target_compile_features(win_axis_precision_qt PRIVATE cxx_std_17)
target_link_libraries(win_axis_precision_qt PRIVATE Qt6::Core Qt6::Gui)

if(MSVC)
  target_compile_options(win_axis_precision_directwrite PRIVATE /W4 /utf-8 /fp:precise)
  target_compile_options(win_axis_precision_qt PRIVATE /W4 /utf-8 /fp:precise)
endif()

file(WRITE "${CMAKE_BINARY_DIR}/d1-toolchain.txt"
  "Qt=${Qt6Core_VERSION}\nCompiler=${CMAKE_CXX_COMPILER_ID}\nCompilerVersion=${CMAKE_CXX_COMPILER_VERSION}\nPointerSize=${CMAKE_SIZEOF_VOID_P}\nWindowsSDK=${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}\n")
