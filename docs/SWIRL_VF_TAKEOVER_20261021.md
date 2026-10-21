# A3/B1/C1 takeover — isolated source-input repair

## Branch and preserved histories

The user authorized a new isolated integration experiment because D1 contains
many independent commits. New branch `work/vf-takeover-abc-20261021`, worktree
`~/Swirl-worktrees/vf-takeover-abc`, starts at exact fetched D1 HEAD
`54e579f1b46ee75187069d40b9ec626b3cc980d5`. PR23 remains draft/unmerged and
its branch is not modified. No A3/B1/C1/integration branch is merged or written.

Fetched tips: A3 `66594e9d32a33c1d216319e2dccd2f35c7e47a4a`, B1
`7902cdb7b449a56939346263df54a692c22d8337`, C1
`c0fe6c47f1a4a0854fcbbde7c9f08b791b44123e`, integration
`f87b6f98eb7018c4a5e86f281fe707764565ce58`. Their latest handoffs, sources,
regressions and terminal native CI were read. API rechecks confirm A3 run
39407084146/source6d6a7b5 success, B1 startup run39405669524/sourceac8e750
success, and C1 continuation39404296030/source75628e3 success. These are
prior, scoped results; they do not establish production mapping or metrics.

## P0 actual defect and repair

The old production V2 adapter treats T(T(x)) as a candidate equivalent source
instance and requires its complete glyph payload to equal x. A3 already
proved that this proposition is false for repeatable original inputs: the
readback dictionary can be identical while the actual geometry differs. That
is an invalid prerequisite for sampling the source function at x, regardless
of whether a later target can represent that function.

The new explicitly named `CoreTextExactOriginalRequestReplayV1` backend freezes
and submits x twice without replacing any coordinate. It checks the complete
raw reported dictionary and every non-envelope native payload field, including
unknown fields and numeric signed-zero bits, exactly for every requested GID.
Original source requests, metrics, paths and readback values are unchanged.
The old V2 default, comparisons and all its tests are retained.

The native transport and launcher are reused with one fixed, explicit second
contract; no duplicate converter or generic plugin framework is introduced.
The source contract retains `axis_observations_only=true`, no axis-equivalence
backend, strict echo failures, and all source/target mapping acceptance flags
false. Production `NativeOracle` accepts it only after independently checking
the complete original physical-face/table identity, exact fixed policy, four
code/native dependency hashes and runtime. Every returned GID carries a checked
request bit pattern, full ordered batch GID list, unchanged payload/readback
replay evidence and recomputed strict diagnostics. Final summary/EOF/exit and
strict-diagnostic totals are also independently checked. Missing, downgraded,
forged or mismatched proofs remain blocked.

This repairs source-input sampling. It does not restore exact user-axis echo,
infer hidden CoreText design q, accept a global user-to-design mapping, relax
any 1e-6/1e-5/1/32 threshold, or bless an unrepresentable target font. Existing
serialization, metric-origin and independent holdout gates remain mandatory.

## Actual local native evidence

The unchanged Swift extractor compiled in this new worktree on actual macOS26.3
/25D125. The local exact user original cannot be loaded by CoreText, as already
proven in D1; it was not replaced or patched. A distinctly labelled installed
system-font control is used here: SHA256
`7ea432196657d83d2675521224be420f9aeb0d7e9def7da6cb2b4c364d8e0983`,
32faces/47098GIDs. It is not the original39d42acd source.

The new bounded driver reuses D2's **384 original requests verbatim**, now with
glyph5/19177 payload checks, plus seven A3/default/decimal controls and seven
predeclared T2 diagnostic controls. There are **391 labelled original requests,
390 unique face/coordinate originals**. Across forward/reverse processes:
**796 verified batches,1592 internal native requests,3184 glyph records,796
exact opposite-order payload pairs**. All384 D2 source requests pass unchanged
source replay while their strict echo result remains **288pass/96fail**.

On the seven diagnostic controls, re-evaluating the old V2 gate offline on
actual measured original/T2 records gives four passes, two payload failures
and one replay-readback instability. These old failures are not relabelled
as passes. Numeric coordinate bits bind the submitted request and unchanged
Swift constructor, not CoreText private internal q.

Safe aggregate: [source control](evidence/SWIRL_VF_TAKEOVER_SOURCE_CONTROL_20261021.json).
All plans, raw native payloads, font identities and stderr stay in ignored
`build/vf-takeover-private/`. An initial pilot correctly refused a launcher
after a concurrent development edit changed its dependency hash; no native
observation was counted. It was retained privately and rerun in a fresh
directory after source freeze.

New source-backend12 tests and production-consumer4 tests pass. Legacy V2
25/25 tests pass. The first consumer test-double had no fileno and failed
before production validation; its fixture was corrected and all16 new tests
then passed. Full source-stage regression is recorded at the source checkpoint.

The dedicated read-only CI workflow runs the exact original39d42acd on the
existing macOS27 runner and uploads **only summary.json**. It never exports
font bytes, raw original payloads, plans or private logs. Source checkpoint
`dbff131cd04784e11a9f1c043ffec6b201040bf1` passed portable and original-source
jobs in [run39546531075](https://github.com/SOLHK/Swirl/actions/runs/39546531075).
Actual original macOS27.0.1/26A434 reproduced all3184 glyph records and796
opposite-order pairs, with all384 D2 requests replayable and the original
288pass/96fail strict result unchanged. The GID5 collision pair retained its
0.5474853515625 advance difference. This is original evidence, separate from
the installed control. Safe aggregate:
[original replay](evidence/SWIRL_VF_TAKEOVER_ORIGINAL_REPLAY_20261021.json).

Primary references reviewed before implementation: A3's prereadback handoff
and immutable native evidence at66594e9; project's existing verified-axis
transport; [HarfBuzz CoreText](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-coretext.cc)
(MIT) and [fontTools4.61.1 TTFont](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/ttFont.py)
(MIT). Existing APIs/design were reused; no upstream implementation copied.

## B1/P2 boundary

The B1 audit again confirms raw vertical advance and origin signs match
HarfBuzz's CoreText backend. Original fixedX500 at width800/1200 differs from
DirectWrite's current-width-half convention400/600; VORG supplies Y only.
The849/850 case is a separate synthetic native behavior, not the measured
original height. No valid API correction or font-only X representation was
found; all strict failures remain. A delivery-contract question is pending
about explicit Qt/Swirl layout compensation versus low-level native API
equality. No dependent relaxation or compensating source edit is made.

C1's reviewed packer/binary checker is integrated as a separate selected patch;
its synthetic-only reconstruction engine is not imported or enabled for Apple
data. No original glyph model/face or Apple-derived Swirl-VF.ttc is generated.
Windows11 and actual Qt/Swirl remain NOT_RUN.

## Reviewed production boundary and actual C1 fix

A follow-up independent review found a missing explicit distinction at the
build entry point: accepting source replay in NativeOracle could otherwise
allow the old approximate reconstruction to proceed without an accepted target
mapping contract. The production entry now rejects source-request-only metadata
before sampling, both on the first session and later resumed sessions. The
diagnostic NativeOracle remains usable. Two regressions prove no new sample,
checkpoint or final font is created, and a previously verified face survives a
later rejected session. Existing complete analytic reconstruction remains valid.
This closes the boundary rather than relying on current unrelated metric failures
to prevent publication. Source replay alone never authorizes target construction.

The existing production TTC serializer now calls the exact reviewed C1 packer
and independent binary verifier, preserving its per-face/table comparison,
native finalization, source rehash and final no-replace publication. C1's own
`production_accepted=false` marker remains packaging scope only. All three C1
modules are bound into resumable checkpoint recipe hashes. Provenance and exact
source blobs are in [selected reuse](SWIRL_VF_C1_REUSE_20261021.md).

An actual on-disk padding corruption reproduces the old false pass: all three
face model gates and the table-byte gate pass before and after the mutation.
The new raw checker rejects `serialization:ttc_nonzero_padding`, no native
finalization/publication occurs, and typed safe failure context is retained.
The old face-order corruption test still changes actual candidate bytes and
fails the same name gate; its injection now uses the actual packer callback.
Changing any selected packer/verifier code hash rejects an old checkpoint
without modifying its manifest.

Actual macOS26.3 native control reconstructs two authored faces through the new
packer:58requests/174glyph records, zero observed source/candidate outline,
table metric and bound discrepancy under the existing1-unit comparator.
The separate strict raw API gate still fails849versus850 at unchanged1/32;
table-metric reconstruction does not relabel that raw API failure. Static
default/fractional instances also pass their existing checks. Fonts are temporary
and removed by the existing native driver.

An additional authored32-face/7GID control was packed locally:53896bytes,
672table references/300unique tables/372shared references, all source table
bytes preserved except required head checksum adjustment. FontTools and the
independent binary checker pass; HarfBuzz14.6.0 ran64directional shaping smoke
cases/192glyph records. File remains private at
`build/vf-takeover-private/c1-synthetic/c1-control.ttc`; it is explicitly authored
test data, not a PingFang conversion or delivery font. Safe aggregate:
[C1 local](evidence/SWIRL_VF_TAKEOVER_C1_LOCAL_20261021.json).

Full second-stage suite: **703 discovered =696passed +7platform skips**,34.485s;
audit6/6. This includes all60selected C1 tests, the new production padding and
checkpoint hash regressions, two source-only production-boundary tests and all
old source/strict-axis tests. New Windows2022 CI packages the authored32-face
control through this same C1 code and runs existing DirectWrite probing/raster
capture; results pending at this checkpoint. No Apple font or derived font is
uploaded by any job. Windows11 installation and actual Qt/Swirl are NOT_RUN.

## Reproduction

Use the existing D1 venv read-only, with new output directories in this worktree:

```sh
/Users/mac430/Swirl-worktrees/vf-macos-windows-d1/build/vf-d1-private/venv/bin/python -m unittest discover -s tools/swirl_vf/tests -p 'test_source_request*.py' -v
```

`platform/probe_source_request_replay.py SOURCE --binary NATIVE --output FRESH
--expected-sha256 EXACT --source-kind original` is the exact-original command;
CI binds the unchanged system original path and SHA39d42acd explicitly.

Source-input checkpoint regression finished: **639 discovered =632passed +7
platform skips**,31.464s; audit6/6. This count includes16 new source/consumer
tests and excludes the60 not-yet-committed C1 packaging tests. The full original
strict V2 regression stays intact. No raw original axis or metric failure is
relabeled as an acceptance pass.
