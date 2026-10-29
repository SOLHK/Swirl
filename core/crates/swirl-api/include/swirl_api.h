#ifndef SWIRL_API_H
#define SWIRL_API_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Independent, offline import ABI. This never starts a proxy or accesses files,
 * URLs, DNS, or system configuration. Success responses contain credentials and
 * must stay private. Only diagnostic codes/paths are safe to display in errors.
 *
 * Input is UTF-8 Xray/V2Ray JSON, at most 4 MiB. The caller keeps both regions
 * valid for the call, with no input mutation or overlapping writable output.
 * A NULL input is permitted only with input_len == 0 (an ordinary parse error).
 *
 * Query with output == NULL and output_capacity == 0. The positive return is
 * the exact response size, without a trailing NUL. Allocate that many bytes and
 * repeat with identical input. An undersized output returns the required size
 * without writing any bytes. Output capacity may not exceed 64 MiB.
 *
 * Negative results: -1 invalid buffer/size, -2 caught panic, -3 internal error,
 * -4 response exceeds the bounded output limit. JSON syntax/validation errors
 * have a positive response size and return {"schema":1,"ok":false,...}.
 *
 * Independent calls may run concurrently. No import state or input is cached.
 * This is a projection boundary, not an assertion of actual network success.
 */
intptr_t swirl_import_xray_v1(const uint8_t *input, size_t input_len,
                            uint8_t *output, size_t output_capacity);

/* Same offline buffer/ownership contract. Input (at most 1 MiB) must contain
 * exactly {"proxies":[one_complete_normalized_node]}. Every supplied option is
 * validated by the authoritative Rust subscription inspector. A successful
 * response contains private native_outbound data; it is not network evidence.
 */
intptr_t swirl_import_node_v1(const uint8_t *input, size_t input_len,
                            uint8_t *output, size_t output_capacity);

/* Offline strict profile projection. Input (at most 4 MiB) is
 * {"format":"clash"|"ini"|"sing-box","configuration":{...}}. The normalized profile
 * excludes nodes, which are validated independently before one atomic save.
 * Same bounded query/write contract as the other import functions. */
intptr_t swirl_import_profile_v1(const uint8_t *input, size_t input_len,
                               uint8_t *output, size_t output_capacity);

uint32_t swirl_core_abi_version(void);
/* UTF-8 JSON: abi_version, build_id, source_sha, package_version, target.
 * Returns bytes excluding NUL, -1 for a null/short buffer, -2 for caught panic.
 * A 4096-byte buffer is sufficient. No configuration or credentials are included. */
intptr_t swirl_core_build_info(uint8_t *output, size_t output_capacity);
/* Existing lifecycle ABI: output_capacity must be at least 1 MiB; serialize
 * lifecycle calls and stop all handles before unloading the shared library. */
intptr_t swirl_core_command(const uint8_t *input, size_t input_len,
                           uint8_t *output, size_t output_capacity);

#ifdef __cplusplus
}
#endif

#endif
