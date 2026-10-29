# Variable-font frame timing, 2026-10-18

This stage adds opt-in, SWIRL_UI_TESTS-only instrumentation. Normal font rendering, animation, axes, metrics, preview surface ownership and application behavior are unchanged. It is independent of the preceding community-links change.

## Method and reproduction

Run an isolated test build with `--font-frame-test --font-frame-output=<local-directory> --preview-page=settings --preview-font-file=<authorized-local-font>`. Use a unique `SWIRL_TEST_ROOT`. Private font binaries and screenshots stay outside Git.

Three repetitions each: static continuous updates, in-process pointer events through the actual HGHT slider, and fractional three-axis changes. Each phase requests 30 warmup and 240 sampled frames. Timestamp Qt's render-thread signals through DirectConnection and steady_clock. Frame-feedback drives the next GUI input; there are no qWait/sleep calls, screenshots, serialization or file writes inside the measured loop. Setup waits and the final capture are outside it.

`frameSwapped` denotes queued presentation, and `afterFrameEnd` denotes submission, not GPU completion or panel scanout. Separately report raster CPU wall time, render-record wall time, GUI driver-queue delay and input-to-queued-presentation latency. The old GUI callback timings included qWait and event delivery, so they cannot establish a 4.17 ms rendering budget. PresentMon was unavailable; no panel latency is inferred.

Primary references: [Qt QQuickWindow signals](https://doc.qt.io/qt-6.10/qquickwindow.html) and [Qt 6.10 threaded render loop source](https://github.com/qt/qtdeclarative/blob/6.10/src/quick/scenegraph/qsgthreadedrenderloop.cpp).

## Local results

Windows 11, 2560x1600, actual 150% / DPR 1.5, D3D11, existing FreeType font engine, unmodified local three-axis TTC. Actual refresh was temporarily changed 120 -> 240 -> 120 Hz with documented ChangeDisplaySettingsExW flags 0, saved complete DEVMODE and an independent restore watchdog. Final 120 Hz / 150% was read back successfully. The original running Swirl process was untouched.

Ranges below are the three per-round medians, milliseconds:

| Actual Hz | Scenario | Queued presentation interval | Four preview lines raster | Input to queued presentation |
|---|---|---|---|---|
| 120 | Static | 8.345-8.347 | No new raster | N/A |
| 120 | HGHT slider | 8.353-8.358 | 5.419-5.429 | 8.304-8.319 |
| 120 | Three axes | 8.386-8.414 | 5.898-5.923 | 8.335-8.373 |
| 240 | Static | 4.171-4.178 | No new raster | N/A |
| 240 | HGHT slider | 8.117-8.202 | 5.509-5.559 | 8.057-8.170 |
| 240 | Three axes | 8.417-8.460 | 5.983-6.032 | 8.349-8.412 |

At 240 Hz slider p95 input latency was 10.017-10.341 ms; three-axis p95 was 10.384-10.665 ms. GUI queue-delay medians were 0.036-0.044 ms. The raster work alone exceeds the 4.167 ms budget: stable 240 fps while changing axes is **not passed**. Test completion is not a performance pass.

All 18 phases completed, real slider values changed, and the page object remained identical. Submitted-frame samples were 239 or 240 per phase; raw data preserves this boundary difference. Each slider phase has two repeated coordinates that need no raster. Other changing inputs without a recorded exact submission were 3 at 120 Hz (one at the final phase boundary) and 1 at 240 Hz. They are excluded from latency statistics, not counted as successful delivery. Every measured three-axis input had an exact recorded submission. Sampled private bytes at phase ends were 219.33-279.10 MiB; this finite test is not proof of an unlimited memory plateau.

## Reading entry and scope change

An optional local `Open-BlindFontReview.ps1` randomizes original/experimental mapping, verifies font hashes and opens an isolated review at 9/10/11/12/13/14/16 pt. Test-only command-line options set the point size and export the actual QFont point size and axes. Eight checks (two local engines, original/experiment, 9/16 pt) verified all four lines' point sizes and default axes. Unprocessed QQuickWindow renders are application artifacts, not physical-screen screenshots.

The user subsequently changed priority: subjective improvement/blind review is now their own judgment and **does not block engineering progress**. Historical acceptance remains 10/12 for the old Swirl rubric; removing this gate is not counted as an extra pass. Font-file benefit remains unproven. The next independent stage checks direct target-size raster edges/corners, broken strokes, unexpected interpolation distortion, clipping, overlap and fallback from small to large sizes and at axis extremes/combinations. Actual display DPI and simulated DPR remain separate.

## Validation and rollback

Qt build passed; selected font regression process exited 0; all-pages smoke passed (12.96 s). Reading entry checks passed 8/8. No font file, system registration, display DPI, proxy, network protocol or subscription logic was changed. No private font resource is committed.

Local evidence: `D:\Codex\PingFangUI-Optimization\reports\DIRECT_FRAME_SUMMARY.json`, `reports\direct-frame-refresh-20261018`, `reports\READING_ENTRY_CHECK.json`, and corresponding unprocessed images under `screenshots`. The optional review launcher remains local. Disable the test flags to use the normal path; revert this stage's commit to remove instrumentation. No system-font rollback is needed.
