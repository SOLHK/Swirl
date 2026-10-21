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
font bytes, raw original payloads, plans or private logs. Original CI is
pending at this source checkpoint; installed-control success is not substituted.

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

C1's reviewed packer/binary checker is prepared as a separate selected patch,
not included in this first source-input checkpoint. Its synthetic-only engine
is not enabled for original data by changing a marker. No original glyph
model/face or Apple-derived Swirl-VF.ttc is generated here. Windows11 and
actual Qt/Swirl remain NOT_RUN.

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
