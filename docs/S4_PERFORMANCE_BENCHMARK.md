# S4 performance measurements

## Initial native baseline

Measured on the user's Windows host with S3's unchanged tests-enabled binary,
Qt 6.10.3, D3D11, 150% DPR, 240 Hz. Raw evidence:
`D:/Codex/outputs/s4/ui-baseline/motion.json`.

| Metric | S3 baseline |
|---|---:|
| Active frame median | 4.1275 ms |
| Active frame P95 | 5.5319 ms |
| Active frame P99 | 62.7856 ms |
| Frames over 50 ms | 8 / 470 |
| Warm frame P95 | 4.9591 ms |
| Working set after navigation | 397,901,824 bytes |
| Repeated-navigation memory increase | 311,296 bytes |
| Cached pages / outstanding grabs | 16 / 0 |
| Idle frames in 650 ms | 1 |

These are actual frame intervals, not click response latency. The retained
motion suite mixes deliberately interrupted navigation and resizing; slow-frame
counts do not by themselves identify a render bottleneck. No claim of a leak or
20% memory reduction is justified by this single measurement.

## Reproducible additional measurements

`SwirlNodeViewModelTests catalogScaleMeasurements` records synchronous insertion,
20 searches, all-node latency refresh while latency sorting is active, and 20
unchanged refreshes for 100, 500, 1,000 and 2,000 synthetic nodes. Set
`SWIRL_NODE_MODEL_REPORT` to an output JSON path. All data is reserved synthetic
public metadata; no private input or real endpoint is used.

`SWIRL_U2_CHECKS=S4 Swirl --motion-test --motion-output=<path>` measures the same
four node sizes on the real Qt event loop, scroll frame intervals, delegate
reuse, selection and navigation dispatch/completion, idle CPU/memory, minimized
CPU/memory, and fixed shell geometry. Dispatch timing measures synchronous event
handling, not input-to-photon latency; completion includes the full animation.

## Model result after batching

Final model run: `D:/Codex/outputs/s4/ui-after/model-final.json` and
`model-final.txt`, six passed / zero failed / zero skipped. CPU is Intel
i7-14650HX, 16 cores / 24 logical processors. Native GPU selection is the Qt
D3D11 backend; the machine has Intel UHD and NVIDIA RTX 5060 Laptop adapters,
so listing both devices does not establish which adapter was selected.

| Nodes | Before all-latency update | After | Before / after notifications |
|---:|---:|---:|---:|
| 100 | 0.7824 ms | 0.3025 ms | 100 / 1 |
| 500 | 4.6252 ms | 1.8479 ms | 500 / 1 |
| 1,000 | 11.0331 ms | 3.9813 ms | 1,000 / 1 |
| 2,000 | 24.4739 ms | 8.4631 ms | 2,000 / 1 |

The 2,000-node update is 65.4% lower in this paired local sample. All runs retain
zero resets. Persistent model indices, latency sort order, one-node changes,
contiguous removals, favorites and filters remain covered. An earlier post-run
during compilation is retained as `model.json`; it is contended and is not used
for the comparison. `model-quiet.json` is an additional consistent quiet sample.

Another avoided cost is catalog reconstruction on unrelated controller status
updates. Forty telemetry/status emissions now cause zero catalog timer wakeups;
a real `nodesChanged` emission still causes a refresh. This was a redundant
O(node count) path on every traffic/uptime update, bypassing S3's precise node
presentation notifications.

## Fresh-process readiness

`tools/Measure-S4Startup.ps1` ran ten interleaved S3/current pairs through the
existing isolated, self-exiting preview path. All twenty completed and rendered
their capture. Evidence: `ui-after/startup/startup.json`.

| Windows message-loop readiness | S3 | S4 candidate |
|---|---:|---:|
| P50, 10 fresh processes | 208.0659 ms | 212.3190 ms |
| P95, 10 fresh processes | 944.8572 ms | 222.5256 ms |

`WaitForInputIdle` is **not** a cold-boot, uncached-disk, first-frame or
input-to-photon measurement. The baseline's first/outlier sample and existing
OS/Qt caches prevent attributing the P95 difference solely to product changes.
Median readiness did not improve. No reboot, cache purge, other-app termination
or system setting change was used.

## Native UI stage result

`ui-after/motion-verified.json`: zero failures; same Windows/Qt/D3D11/DPR/240 Hz
setup as the baseline, with unchanged caches, effects, and animation durations.

| Metric | S3 baseline | S4 candidate |
|---|---:|---:|
| Active frame median | 4.1275 ms | 4.1481 ms |
| Active frame P95 | 5.5319 ms | 5.5787 ms |
| Active frame P99 | 62.7856 ms | 63.1036 ms |
| Frames over 50 ms | 8 / 470 | 8 / 469 |
| Warm frame P95 | 4.9591 ms | 4.8417 ms |
| Working set | 397,901,824 B | 396,935,168 B |
| Revisit working-set increase | 311,296 B | 929,792 B |
| Cached pages / active grabs / idle frames | 16 / 0 / 1 | 16 / 0 / 1 |

**The 20% memory goal was not achieved.** This sample changes working set by
only -0.24%; active-frame tails and long-frame counts did not materially improve.
The measured improvement is in catalog update work and avoided telemetry
refreshes, not a demonstrated global rendering or residency reduction. Retained
pages, font/texture resources and effects remain present; this work does not
claim to have proven which retained resource dominates memory.

`ui-after/stress-final-native.json` exits 0 with 220 checks / zero failures after
rebuilding the corrected fixture and shared-owned frame sampler. Earlier
`stress-verified.json` remains a failed overall run (exit 2 from the incomplete
synthetic address), not replaced by the later success. The corrected scripted
scroll at 100 / 500 / 1,000 / 2,000 rows keeps 28 / 31 / 31 / 31 delegates and
has P95 frame intervals 4.8260 / 5.9379 / 5.4087 / 5.6796 ms; maximum event-loop
gaps were 10.6962 / 11.9516 / 11.3076 / 10.0032 ms. This is programmatic scrolling
with invariant inspection, not an OS input-to-photon test.

Navigation dispatch P95 is 4.7837 ms and completion P95 is 297.8376 ms; node
selection dispatch P95 is 2.7076 ms and completion P95 is 412.9720 ms. These
separate synchronous input handling from full animation completion. They do not
prove the user's visual-response targets by themselves. During the three-second
idle and minimized windows CPU time increased 0 ms each (Windows
counter resolution). A longer loaded/idle soak remains separate acceptance.

`ui-after/stress-final-offscreen.json` exits 0 with 220 checks / zero failures,
establishing the offscreen/software CI correctness path; its timing is not native
GPU evidence. Both corrected stress runs contain the sampler ownership repair
and complete synthetic fields, and retain zero QML warnings. All current runtime evidence is explicitly
stage evidence from the working-tree build, not a final release acceptance.
