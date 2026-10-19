/*
 * Swirl-VF: local Apple HVF outline oracle.
 * Independent implementation against Apple's documented public C API.
 * No Apple font data or third-party converter source is included.
 *
 * Build on a Mac with an SDK exposing <hvf/Scaler.h>:
 *   xcrun clang -std=c11 -O2 -Wall -Wextra -Werror
 *     -mmacosx-version-min=15.4 hvf_oracle.c -lhvf -o hvf_oracle
 *
 * Usage: hvf_oracle INPUT FACE COORDS START COUNT [parts]
 * COORDS: comma-separated normalized DESIGN coordinates, in fvar order.
 * COUNT=0 means all remaining maxp glyphs (or all parts with `parts`).
 * This deliberately does NOT interpret avar, synthesize metrics, or claim
 * equivalence with CoreText's user-coordinate behavior.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#if !defined(__APPLE__)
int main(void) {
    fputs("{\"record\":\"summary\",\"status\":\"NOT_RUN\","
          "\"reason\":\"Apple HVF runtime requires macOS\"}\n", stdout);
    return 77;
}
#else
#include <hvf/Scaler.h>

typedef struct { const unsigned char *bytes; size_t size; } Span;
typedef struct {
    FILE *out;
    unsigned long events, parts_begun, parts_ended, paths_begun, paths_ended;
    unsigned long moves, lines, quads, cubics, closes;
    int failed;
} Output;

static int within(Span s, size_t offset, size_t count) {
    return offset <= s.size && count <= s.size - offset;
}
static uint16_t be16(const unsigned char *p) {
    return (uint16_t)(((uint16_t)p[0] << 8) | p[1]);
}
static uint32_t be32(const unsigned char *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}
static uint16_t le16(const unsigned char *p) {
    return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}
static int parse_size(const char *arg, size_t *out) {
    char *end = NULL;
    errno = 0;
    if (!arg[0] || arg[0] == '-') return 0;
    unsigned long long n = strtoull(arg, &end, 10);
    if (errno || *end || n > SIZE_MAX) return 0;
    *out = (size_t)n;
    return 1;
}
static int find_table(Span file, size_t sfnt, const char tag[4], Span *out) {
    *out = (Span){ NULL, 0 };
    if (!within(file, sfnt, 12)) return -1;
    unsigned count = be16(file.bytes + sfnt + 4);
    if (!within(file, sfnt + 12, (size_t)count * 16)) return -1;
    for (unsigned i = 0; i < count; ++i) {
        const unsigned char *r = file.bytes + sfnt + 12 + 16 * i;
        if (memcmp(r, tag, 4)) continue;
        if (out->bytes) return -1; /* Ambiguous duplicate table tag. */
        size_t offset = be32(r + 8), length = be32(r + 12);
        if (!within(file, offset, length)) return -1;
        *out = (Span){ file.bytes + offset, length };
    }
    return out->bytes ? 1 : 0;
}
static void separator(Output *out) {
    if (out->events++) fputc(',', out->out);
}
static void xy(Output *out, HVFPoint p) {
    if (!isfinite(p.x) || !isfinite(p.y)) {
        fputs("null,null", out->out);
        out->failed = 1;
    } else {
        fprintf(out->out, "%.17g,%.17g", (double)p.x, (double)p.y);
    }
}
static HVFPartRenderAction emit(HVFPartRenderInstruction instruction,
                                const HVFPartRenderParameters *params,
                                void *data) {
    Output *out = data;
    separator(out);
    switch (instruction) {
    case HVFPartRenderInstructionBeginPart:
        if (!params) { out->failed = 1; fputs("[\"missing_params\"]", out->out); break; }
        fprintf(out->out, "[\"begin_part\",%zu]", (size_t)params->beginPart.partInfo.partId);
        ++out->parts_begun;
        break;
    case HVFPartRenderInstructionEndPart:
        if (!params) { out->failed = 1; fputs("[\"missing_params\"]", out->out); break; }
        fprintf(out->out, "[\"end_part\",%zu]", (size_t)params->endPart.partInfo.partId);
        ++out->parts_ended;
        break;
    case HVFPartRenderInstructionBeginPath:
        fputs("[\"begin_path\"]", out->out); ++out->paths_begun; break;
    case HVFPartRenderInstructionEndPath:
        fputs("[\"end_path\"]", out->out); ++out->paths_ended; break;
    case HVFPartRenderInstructionClosePath:
        fputs("[\"close\"]", out->out); ++out->closes; break;
    case HVFPartRenderInstructionStop:
        fputs("[\"stop\"]", out->out); break;
    case HVFPartRenderInstructionAddPoint:
    case HVFPartRenderInstructionAddLine:
        if (!params) { out->failed = 1; fputs("[\"missing_params\"]", out->out); break; }
        fputs(instruction == HVFPartRenderInstructionAddPoint ? "[\"move\"," : "[\"line\",", out->out);
        xy(out, params->addPoint.pt); fputc(']', out->out);
        if (instruction == HVFPartRenderInstructionAddPoint) ++out->moves; else ++out->lines;
        break;
    case HVFPartRenderInstructionAddQuad:
        if (!params) { out->failed = 1; fputs("[\"missing_params\"]", out->out); break; }
        fputs("[\"quad\",", out->out); xy(out, params->addQuad.offpt);
        fputc(',', out->out); xy(out, params->addQuad.onpt); fputc(']', out->out);
        ++out->quads;
        break;
    case HVFPartRenderInstructionAddCubic:
        if (!params) { out->failed = 1; fputs("[\"missing_params\"]", out->out); break; }
        fputs("[\"cubic\",", out->out); xy(out, params->addCubic.cp1);
        fputc(',', out->out); xy(out, params->addCubic.cp2);
        fputc(',', out->out); xy(out, params->addCubic.onpt); fputc(']', out->out);
        ++out->cubics;
        break;
    default:
        fprintf(out->out, "[\"unsupported_instruction\",%u]", (unsigned)instruction);
        out->failed = 1;
    }
    if (ferror(out->out)) out->failed = 1;
    return out->failed ? HVFPartRenderActionStop : HVFPartRenderActionContinue;
}
static int fail(const char *message) {
    fprintf(stderr, "hvf_oracle: %s\n", message);
    return 2;
}

static int extract(int argc, char **argv) {
    if (argc < 6 || argc > 7) return fail("usage: INPUT FACE DESIGN_COORDS START COUNT [parts]");
    if (argc == 7 && strcmp(argv[6], "parts")) return fail("last argument must be parts");
    size_t face = 0, start = 0, requested = 0;
    if (!parse_size(argv[2], &face) || !parse_size(argv[4], &start) ||
        !parse_size(argv[5], &requested)) return fail("invalid nonnegative index/count");
    FILE *in = fopen(argv[1], "rb");
    if (!in) return fail("cannot open input");
    if (fseeko(in, 0, SEEK_END)) { fclose(in); return fail("cannot seek input"); }
    off_t end = ftello(in);
    if (end <= 0 || (uint64_t)end > UINT32_MAX || fseeko(in, 0, SEEK_SET)) {
        fclose(in); return fail("input is empty, too large, or not seekable");
    }
    size_t file_size = (size_t)end;
    unsigned char *bytes = malloc(file_size);
    if (!bytes) { fclose(in); return fail("out of memory"); }
    if (fread(bytes, 1, file_size, in) != file_size) {
        free(bytes); fclose(in); return fail("short read");
    }
    fclose(in);
    int result = 2, opened = 0;
    void *storage = NULL, *aligned_hvgl = NULL, *aligned_hvpm = NULL;
    HVFAxisValue *coords = NULL;
    HVFPartRenderer *renderer = NULL;
    Span file = { bytes, file_size };
    Span hvgl = {0}, hvpm = {0}, maxp = {0}, fvar = {0};
    size_t sfnt = 0, faces = 1;
    if (within(file, 0, 12) && !memcmp(bytes, "ttcf", 4)) {
        faces = be32(bytes + 8);
        if (!faces || !within(file, 12, faces * 4) || face >= faces) {
            fail("invalid TTC face directory/index"); goto done;
        }
        sfnt = be32(bytes + 12 + face * 4);
    } else if (face) { fail("single font only has face 0"); goto done; }
    if (!within(file, sfnt, 12) ||
        find_table(file, sfnt, "hvgl", &hvgl) != 1 || hvgl.size < 24 ||
        find_table(file, sfnt, "hvpm", &hvpm) < 0 ||
        find_table(file, sfnt, "maxp", &maxp) != 1 || maxp.size < 6 ||
        find_table(file, sfnt, "fvar", &fvar) != 1 || fvar.size < 16) {
        fail("malformed or missing required table"); goto done;
    }
    unsigned axis_count = be16(fvar.bytes + 8), axis_size = be16(fvar.bytes + 10);
    size_t axis_offset = be16(fvar.bytes + 4);
    if (!axis_count || axis_count > 64 || axis_size < 20 ||
        !within(fvar, axis_offset, (size_t)axis_size * axis_count)) {
        fail("invalid fvar axis directory"); goto done;
    }
    coords = calloc(axis_count, sizeof(*coords));
    if (!coords) { fail("out of memory"); goto done; }
    const char *text = argv[3];
    for (unsigned i = 0; i < axis_count; ++i) {
        char *next = NULL;
        errno = 0;
        coords[i] = strtod(text, &next);
        if (next == text || errno || !isfinite(coords[i]) || coords[i] < -1.0 || coords[i] > 1.0 ||
            (i + 1 < axis_count ? *next != ',' : *next != '\0')) {
            fail("coordinates must match fvar axis count and lie in [-1,1]"); goto done;
        }
        text = next + (i + 1 < axis_count);
    }
    /* malloc provides the required double alignment even if TTC table offsets do not. */
    aligned_hvgl = malloc(hvgl.size);
    aligned_hvpm = hvpm.size ? malloc(hvpm.size) : NULL;
    size_t storage_size = HVF_part_renderer_storage_size();
    storage = storage_size ? calloc(1, storage_size) : NULL;
    if (!aligned_hvgl || (hvpm.size && !aligned_hvpm) || !storage) {
        fail("renderer/table allocation failed"); goto done;
    }
    memcpy(aligned_hvgl, hvgl.bytes, hvgl.size);
    if (hvpm.size) memcpy(aligned_hvpm, hvpm.bytes, hvpm.size);
    if (HVF_open_part_renderer(aligned_hvgl, hvgl.size, aligned_hvpm, hvpm.size, storage, storage_size)) {
        fail("Apple HVF rejected the tables"); goto done;
    }
    opened = 1;
    renderer = (HVFPartRenderer *)storage;
    size_t total_parts = HVF_part_count(renderer);
    uint32_t visible_parts = HVF_glyph_count(renderer);
    uint16_t maxp_glyphs = be16(maxp.bytes + 4);
    size_t available = argc == 7 ? total_parts : maxp_glyphs;
    if (maxp_glyphs > visible_parts || start >= available ||
        (requested && requested > available - start)) {
        fail("requested range exceeds available glyphs/parts"); goto done;
    }
    size_t count = requested ? requested : available - start;
    HVFLibraryVersion library_version = HVF_library_version();
    HVFTableVersion supported_version = HVF_table_version(renderer);
    printf("{\"record\":\"header\",\"schema\":1,\"engine\":\"Apple HVF\","
           "\"coordinate_space\":\"normalized_design_after_avar\","
           "\"input_bytes\":%zu,\"face_index\":%zu,\"face_count\":%zu,"
           "\"maxp_glyphs\":%u,\"hvf_visible_parts\":%u,\"hvf_total_parts\":%zu,"
           "\"hvgl_bytes\":%zu,\"hvpm_bytes\":%zu,\"hvgl_version\":[%u,%u],"
           "\"renderer_table_version\":[%u,%u],\"library_version\":[%u,%u,%u],"
           "\"start\":%zu,\"count\":%zu,\"fvar_axis_tags\":[",
           file_size, face, faces, (unsigned)maxp_glyphs, visible_parts, total_parts,
           hvgl.size, hvpm.size, (unsigned)le16(hvgl.bytes), (unsigned)le16(hvgl.bytes + 2),
           (unsigned)supported_version.major, (unsigned)supported_version.minor,
           (unsigned)library_version.major, (unsigned)library_version.minor, (unsigned)library_version.patch,
           start, count);
    for (unsigned i = 0; i < axis_count; ++i) {
        if (i) fputc(',', stdout);
        const unsigned char *tag = fvar.bytes + axis_offset + axis_size * i;
        printf("\"\\u%04x\\u%04x\\u%04x\\u%04x\"", tag[0], tag[1], tag[2], tag[3]);
    }
    fputs("],\"normalized_coords\":[", stdout);
    for (unsigned i = 0; i < axis_count; ++i) printf("%s%.17g", i ? "," : "", (double)coords[i]);
    fputs("],\"metrics\":\"NOT_EXTRACTED\",\"user_axis_mapping\":\"NOT_TESTED\"}\n", stdout);
    size_t failed = 0, rendered = 0;
    for (size_t part = start; part < start + count; ++part) {
        int code = HVF_set_render_part(renderer, part);
        int part_axes = code ? -1 : HVF_render_part_axis_count(renderer);
        unsigned applied = 0;
        if (!code && (part_axes < 0 || part_axes > (int)axis_count)) code = -1;
        if (!code) {
            for (int axis = 0; axis < part_axes; ++axis) {
                code = HVF_set_axis_value(renderer, axis, coords[axis]);
                if (code) break;
                ++applied;
            }
        }
        printf("{\"record\":\"outline\",\"part_index\":%zu,\"part_axis_count\":%d,"
               "\"applied_axis_count\":%u,\"events\":[", part, part_axes, applied);
        Output output = { .out = stdout };
        if (!code) code = HVF_render_current_part(renderer, emit, &output);
        int ok = code == 0 && !output.failed;
        printf("],\"status\":\"%s\",\"native_code\":%d,\"counters\":{"
               "\"events\":%lu,\"parts_begun\":%lu,\"parts_ended\":%lu,"
               "\"paths_begun\":%lu,\"paths_ended\":%lu,\"moves\":%lu,"
               "\"lines\":%lu,\"quads\":%lu,\"cubics\":%lu,\"closes\":%lu}}\n",
               ok ? "OK" : "FAILED", code, output.events, output.parts_begun, output.parts_ended,
               output.paths_begun, output.paths_ended, output.moves, output.lines,
               output.quads, output.cubics, output.closes);
        if (ok) ++rendered; else ++failed;
        if (ferror(stdout)) { fail("output write failure"); goto done; }
    }
    printf("{\"record\":\"summary\",\"status\":\"%s\",\"rendered\":%zu,"
           "\"failed\":%zu,\"preservation_verdict\":\"NOT_EVALUATED\"}\n",
           failed ? "FAILED" : "EXTRACTED", rendered, failed);
    result = failed ? 1 : 0;
done:
    if (opened && HVF_close_part_renderer(renderer)) result = fail("renderer cleanup failed");
    free(storage); free(aligned_hvgl); free(aligned_hvpm); free(coords); free(bytes);
    return result;
}

int main(int argc, char **argv) {
    if (__builtin_available(macOS 15.4, *)) return extract(argc, argv);
    fputs("{\"record\":\"summary\",\"status\":\"NOT_RUN\","
          "\"reason\":\"Apple HVF C API unavailable on this macOS version\"}\n", stdout);
    return 77;
}
#endif
