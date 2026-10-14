# Static HTTP/2 dependency, pinned source and checksums in nghttp2/SWIRL-DEPENDENCY.md.
include(CheckIncludeFile)
include(CheckSymbolExists)
set(PACKAGE_VERSION "1.70.0")
set(PACKAGE_VERSION_NUM "0x014600")
if(MSVC)
 set(HINT_NORETURN "__declspec(noreturn)")
 set(ssize_t "ptrdiff_t")
else()
 set(HINT_NORETURN "__attribute__((noreturn))")
endif()
foreach(header IN ITEMS arpa/inet.h fcntl.h inttypes.h limits.h netdb.h netinet/in.h netinet/ip.h pwd.h sys/socket.h sys/time.h syslog.h unistd.h windows.h)
 string(TOUPPER "${header}" name)
 string(REGEX REPLACE "[/.]" "_" name "${name}")
 check_include_file("${header}" "HAVE_${name}")
endforeach()
if(WIN32)
 set(HAVE_GETTICKCOUNT64 1)
else()
 check_symbol_exists(clock_gettime "time.h" HAVE_CLOCK_GETTIME)
 check_symbol_exists(CLOCK_MONOTONIC "time.h" HAVE_DECL_CLOCK_MONOTONIC)
endif()
configure_file(nghttp2/cmakeconfig.h.in generated/config.h)
configure_file(nghttp2/lib/includes/nghttp2/nghttp2ver.h.in generated/nghttp2/nghttp2ver.h @ONLY)
add_library(SwirlHttp2 STATIC
 nghttp2/lib/nghttp2_pq.c
 nghttp2/lib/nghttp2_map.c
 nghttp2/lib/nghttp2_queue.c
 nghttp2/lib/nghttp2_frame.c
 nghttp2/lib/nghttp2_buf.c
 nghttp2/lib/nghttp2_stream.c
 nghttp2/lib/nghttp2_outbound_item.c
 nghttp2/lib/nghttp2_session.c
 nghttp2/lib/nghttp2_submit.c
 nghttp2/lib/nghttp2_helper.c
 nghttp2/lib/nghttp2_alpn.c
 nghttp2/lib/nghttp2_hd.c
 nghttp2/lib/nghttp2_hd_huffman.c
 nghttp2/lib/nghttp2_hd_huffman_data.c
 nghttp2/lib/nghttp2_version.c
 nghttp2/lib/nghttp2_priority_spec.c
 nghttp2/lib/nghttp2_option.c
 nghttp2/lib/nghttp2_callbacks.c
 nghttp2/lib/nghttp2_mem.c
 nghttp2/lib/nghttp2_http.c
 nghttp2/lib/nghttp2_rcbuf.c
 nghttp2/lib/nghttp2_extpri.c
 nghttp2/lib/nghttp2_ratelim.c
 nghttp2/lib/nghttp2_time.c
 nghttp2/lib/nghttp2_debug.c
 nghttp2/lib/sfparse.c
)
set_target_properties(SwirlHttp2 PROPERTIES AUTOMOC OFF C_STANDARD 11)
target_compile_definitions(SwirlHttp2 PRIVATE BUILDING_NGHTTP2 HAVE_CONFIG_H PUBLIC NGHTTP2_STATICLIB)
target_include_directories(SwirlHttp2 PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated" PUBLIC nghttp2/lib/includes "${CMAKE_CURRENT_BINARY_DIR}/generated")
