# Original startup: the private-copy control also returns no descriptors

Native run [39405669524](https://github.com/SOLHK/Swirl/actions/runs/39405669524)
tested **ac8e750bbcd174b5d1ba38214c646e5c55203ded**. Both Python and
apple-startup finished **success**. This is complete startup diagnosis, with
**zero glyph requests, zero metric records and zero reconstructed original
faces**. It does not change the earlier strict metric failures.

Python ran 592 tests: 585 passed and 7 optional HarfBuzz tests skipped. All six
audit tests passed. The suite includes all 144 new B1 test methods, including
20 startup protocol and isolation tests. The independent Swift probe compiled
and ran on macOS 27.0.1 arm64, build 26A434.

## Four independent source-bound processes

| Input | Descriptor API | Descriptors | Bound physical faces | Source URL checks | Direct VORG observation |
| --- | --- | ---: | ---: | --- | --- |
| System original | NON_NIL | 268 | 32/32 | All descriptor/font URLs match | Present on 268/268 fonts |
| Byte-identical private copy | **NIL** | 0 | 0/32 | No CTFont to inspect | **Not observed** |
| Private directory-only no-VORG copy | **NIL** | 0 | 0/32 | No CTFont to inspect | **Not observed** |
| System original repeat | NON_NIL | 268 | 32/32 | All descriptor/font URLs match | Present on 268/268 fonts |

Both private variants use the same temporary pathname, written in sequence,
with a fresh native process for every condition. The byte-identical copy has
the same SHA-256 and 61,473,880-byte length as the system source. Its 672 source
table identities also match. The directory-only variant preserves all 640
retained table identities. No source font, variant font or original glyph
outline is published, and all private temporary files were deleted.

The refusal is now located **at CTFontManagerCreateFontDescriptorsFromURL
returning nil**, before CTFont creation, retained-table verification or a VORG
table query. The earlier generic startup error did not reveal this boundary.

Because the unchanged private copy fails in the same way, the no-VORG refusal
cannot establish a VORG-removal cause. The evidence classification is:

```text
PRIVATE_LOCATION_LOAD_OR_BINDING_BLOCKED_VORG_CAUSALITY_UNKNOWN
```

This records a difference between the system original and a relocated copy
under this unregistered-URL loading procedure. It does not isolate pathname,
extended attributes, system trust, caches or a specific Apple protection
mechanism. API nil gives no such reason.

There is no CTFont for either private variant. Therefore their missing VORG
observations must not be described as CTFontCopyTable(VORG) returning nil.
Nor can the experiment claim any original no-VORG metric changes.

## Source identities, repeat and direct VORG evidence

Both system-original raw stdout files have exactly 62,119,485 bytes and are
byte-for-byte identical, SHA-256:

```text
4ff4c15e15d041ddec18419b202652b3e0207f49fff1cef4332098bee03d44fb
```

Each of the 268 descriptors matches exactly one physical source face, with all
retained table hashes, UPEM and glyph count agreeing. Every physical face is
covered without ambiguity. Descriptor counts are not face counts: faces 0–19
have nine descriptors each, 20–23 have six each, and 24–31 have eight each.

All bound descriptor and CTFont source URLs agree with the original URL.
Every startup font size is 12 and every matrix is the identity. The requested
startup size remains 0, as in the production descriptor path.

Direct VORG queries on all 268 system-source CTFonts return eight bytes, with
SHA-256:

```text
6be1f4f55c357a9a8d2ebbcea9e90766c45f6acb9b546d11dc4c576213b0d506
```

That is a table-presence observation; no glyph or metric observation follows it.

The independent archive audit recomputed 180,096 descriptor/face/table
comparisons and 1,876 binary64 size/matrix values in the first system report.
Byte-exact A/A identity verifies the corresponding repeated report. The total
360,192 comparison checks and 3,752 binary64 startup values must not be counted
as glyph or metric samples. Across the four source reports, 2,656 expected
source-table records are independently checked.

## Evidence

- [Native job log](startup/native-job-118571033968.log)
- [Python job log](startup/python-job-118570866640.log)
- [Structured summary](startup/summary.json)
- [Provenance and file hashes](startup/provenance.json)
- [Complete raw artifact](archives/original-startup-12256826076.zip)

The archive was actually downloaded and matched to the GitHub artifact digest;
all eight ZIP member CRCs were verified, with no font payload files or unsafe
member paths. It is 4,962,862 bytes, SHA-256:

```text
f145e3dab64c738e39bb0f33e489f8d8cd0514def296607fe8aa66e27780da6e
```

## Consequence for the original metric investigation

A valid original-font VORG ablation needs a loading procedure that first binds
an unchanged private copy to all 32 physical faces. That prerequisite is not
met by this URL procedure. Repeating the same private-copy metric sampling
would produce no additional VORG evidence.

The last actual original metric check remains 24/60 unique vertical-X failures,
repeated exactly as 48/120 records. The synthetic 849/850 gate is unchanged.
A complete startup diagnosis does not establish a production repair.
