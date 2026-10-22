#ifndef SWIRL_API_H
#define SWIRL_API_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ABI 1 uses caller-owned buffers only. No Rust allocation crosses the ABI. */
uint32_t swirl_core_abi_version(void);

/* UTF-8 JSON: abi_version, build_id, source_sha, package_version, target.
 * Returns the byte count, excluding NUL (no terminator is written), -1 for a
 * null/short buffer, or -2 for an internally caught panic. A 4096-byte buffer
 * is sufficient. No runtime configuration or credentials are included. */
intptr_t swirl_core_build_info(uint8_t *output, size_t output_capacity);

/* input and output must not overlap. output_capacity must be >= 1048576.
 * Stop all handles before unloading. The implementation catches Rust panics. */
intptr_t swirl_core_command(const uint8_t *input, size_t input_len,
                            uint8_t *output, size_t output_capacity);

#ifdef __cplusplus
}
#endif
#endif
