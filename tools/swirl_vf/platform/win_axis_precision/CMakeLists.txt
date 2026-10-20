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
target_sources(win_axis_precision_qt PRIVATE ../../../../src/Swirl.Quick/app/FontAxisPolicy.cpp)
target_compile_features(win_axis_precision_qt PRIVATE cxx_std_17)
target_link_libraries(win_axis_precision_qt PRIVATE Qt6::Core Qt6::Gui)

if(MSVC)
  target_compile_options(win_axis_precision_directwrite PRIVATE /W4 /utf-8 /fp:precise)
  target_compile_options(win_axis_precision_qt PRIVATE /W4 /utf-8 /fp:precise)
endif()

file(WRITE "${CMAKE_BINARY_DIR}/d1-toolchain.txt"
  "Qt=${Qt6Core_VERSION}\nCompiler=${CMAKE_CXX_COMPILER_ID}\nCompilerVersion=${CMAKE_CXX_COMPILER_VERSION}\nCompilerPath=${CMAKE_CXX_COMPILER}\nPointerSize=${CMAKE_SIZEOF_VOID_P}\nWindowsSDK=${CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION}\nCMakeVersion=${CMAKE_VERSION}\nGenerator=${CMAKE_GENERATOR}\nGeneratorInstance=${CMAKE_GENERATOR_INSTANCE}\nPlatformToolset=${CMAKE_VS_PLATFORM_TOOLSET}\n")

# Opt-in only AFTER the unchanged D1 harness has completed. Never link the
# private ABI intervention into the primary probe or a production executable.
if(DEFINED ENV{D2_QTBASE_SOURCE} AND DEFINED ENV{D2_PREPARED})
  if(QT_FEATURE_system_freetype OR NOT TARGET Qt6::GuiPrivate)
    message(FATAL_ERROR "D2 requires the pinned SDK's bundled FreeType and private headers")
  endif()
  enable_language(C)
  file(TO_CMAKE_PATH "$ENV{D2_QTBASE_SOURCE}" d2_qt)
  file(TO_CMAKE_PATH "$ENV{D2_PREPARED}" d2_prepared)
  add_executable(win_axis_precision_d2 EXCLUDE_FROM_ALL d2_probe.cpp "${d2_prepared}/d2_ft_access.c")
  target_sources(win_axis_precision_d2 PRIVATE ../../../../src/Swirl.Quick/app/FontAxisPolicy.cpp)
  target_include_directories(win_axis_precision_d2 PRIVATE "${d2_prepared}" "${d2_qt}/src/3rdparty/freetype/include")
  target_compile_definitions(win_axis_precision_d2 PRIVATE FT2_BUILD_LIBRARY)
  target_compile_features(win_axis_precision_d2 PRIVATE cxx_std_17)
  target_link_libraries(win_axis_precision_d2 PRIVATE Qt6::GuiPrivate)
  if(MSVC)
    target_compile_options(win_axis_precision_d2 PRIVATE /W4 /utf-8 /fp:precise)
  endif()
endif()
