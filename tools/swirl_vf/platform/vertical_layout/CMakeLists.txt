cmake_minimum_required(VERSION 3.20)
project(SwirlOriginalVerticalLayoutProbe LANGUAGES CXX)

if(NOT WIN32)
    message(FATAL_ERROR "The actual DirectWrite layout probe requires Windows")
endif()

add_executable(directwrite_vertical_layout ../directwrite_vertical_layout.cpp)
target_compile_features(directwrite_vertical_layout PRIVATE cxx_std_17)
target_compile_definitions(directwrite_vertical_layout PRIVATE _WIN32_WINNT=0x0A00 NTDDI_VERSION=0x0A000004)
target_link_libraries(directwrite_vertical_layout PRIVATE dwrite d2d1 bcrypt)
if(MSVC)
    target_compile_options(directwrite_vertical_layout PRIVATE /W4 /EHsc /utf-8)
endif()
