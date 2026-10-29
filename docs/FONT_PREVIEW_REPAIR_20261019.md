# Font preview resource reuse and axis delivery

## Source and acceptance boundary

The supplied `PRO_HANDOFF.md` and `FINAL_FONT_WINDOWS_ACCEPTANCE.md` were read
before changes. The supplied source snapshot identifies
`5adcfcf158a4eb99f56e78d0997af5dbc25bd3d0`. The clean development branch fetched
for this work was `work/core-completion-20261017` at
`a7e872d0f046dcd66614704555cd0b569ac4a7a4`; its two additional commits changed
documentation only. The affected application and test code matched the snapshot.

The attached Windows failures are retained, not reclassified as new passes:

* At 200% scale, the last-minus-third-last of eight repeated-coordinate rounds
  was **27.8359375 MiB**, above the existing exclusive **16 MiB** threshold.
* Eight rounds of 180 repeated coordinates, 1024 distinct coordinates, the
  1 GiB private-byte budget, and the three rounds of four frame phases remain.
* The original 240 Hz three-axis `queuedPresentIntervalMs` p95 was
  **54.852–57.431 ms**. This is not input-to-present latency. The corresponding
  `inputToQueuedPresentMs` p95 was **13.3503–13.9557 ms**, and
  `driverQueueDelayMs` p95 was **46.4065–47.4255 ms**.
* `frameSwapped` records queued presentation, not GPU completion or physical
  display output. The six-second phase timeout is unchanged.

The supplied evidence ZIP contains two occurrences each of the UI and frame
report filenames. They were extracted separately with their original entry
offsets and SHA-256 values. One frame report has twelve phases, the other nine;
the incomplete report is not promoted to a complete acceptance run. Original
evidence and private font files are delivered separately and are not committed.

## Problems and changes

### A preview update waited twice

`SwirlFontBinding` already coalesces a complete axis map with
`Qt.callLater(refreshAxes)`. Its delayed Binding then queued the same result
again. Preview bindings now publish that complete map when `refreshAxes` runs
(`delayed: !preview`). Ordinary text and layout keep their existing timing.

A deterministic probe using the production binding, Theme and FontManager
submitted 48 three-axis updates. Previously none of the 48 maps was visible at
the end of the first callback; now all 48 are visible. Both versions eventually
produced 48 exact maps, 48 font changes, and zero partial maps. The regression in
`qmlLiveAutomaticFonts` checks the production callback, not a replacement binding.

### Each raster revision allocated and retired textures

The old preview created a fresh QImage and QSGTexture for every revision. Its
ownership was correct; that observation alone does not prove a C++ leak.
Repeated GPU allocation/retirement is a plausible contributor to the Windows
high-water growth because backend resource release may wait for in-flight work.

The preview now reuses its QImage when dimensions match and the image is unique.
If an upload still owns a shared copy, it detaches before painting. A small
QSGTexture implementation uses `commitTextureOperations` to upload the latest
image into a retained QRhiTexture. Size or QRhi changes allocate a new resource.
The node owns its texture on the scene-graph thread; no global axis cache is added.
Software rendering retains Qt's image texture factory path.

Clearing text or setting width to zero releases the old image and node; restoring
content allocates again. Only actual invalidations schedule polish. Original
font requests, raster bounds, DPR mapping, premultiplied alpha, and Linear texture
filtering are preserved. Test-only atomic counters record real buffer replacement
or detachment and texture creation.

QRhi has documented APIs but limited compatibility guarantees. The standalone
font tests now find and link the same `Qt6::GuiPrivate` dependency already used by
the full application. Build with matching Qt headers/libraries; this is not a
claim of stable QRhi ABI across Qt releases.

### The test viewport could exceed the 200% work area

`FontTestViewport.h` uses the actual screen available geometry and native frame
margins, both in logical coordinates. It respects application minimum sizes,
records requested and actual geometry, and fails setup if the frame cannot fit.
The frame benchmark scrolls the existing viewport during setup so the pointer
slider and all four preview lines are visible through clipping ancestors. It
does not change display scale, refresh rate, the UI layout, or measured inputs.

Windows private-byte query failure now fails memory gates instead of silently
passing. Unsupported platforms explicitly report unavailable measurement.
Frame reports add unrepresented input IDs and a driver-origin-to-queued-present
span while retaining the existing fields. Its start is the preceding frame
feedback callback, not a physical input event.

## Local validation

Qt **6.10.3**, GCC **13.3**, Linux Release, offscreen/software:

* Baseline: 2/2 CTest processes, **50 individual cases passed, 9 skipped**.
* Patched: 2/2 CTest processes, **51 individual cases passed, 9 skipped**.
  Lifecycle callbacks are excluded. Skips remain skips.
* The new preview test checks A→B→A pixels, full three-axis coalescing, idle
  stability, buffer reuse, clear/restore, width-zero/restore, and destruction.
  Its GPU allocation assertion executes only on an RHI backend.
* A separate QRhi Null probe executed 32 same-size changes with one buffer and
  one texture creation; clear/restore and resizing caused the expected new
  allocations. Null validates code paths and lifetime, not GPU pixels or memory.
* A four-line DPR=2 CPU probe with the original private TTC did not reproduce
  the Windows growth. Last-three-round growth was 0 bytes before and 65,536
  bytes after. It did not establish CPU acceleration and excludes QML/GPU.
* The first patched full suite exposed an early test snapshot: the new width
  fixture family had arrived while its old five-axis map was still pending.
  Setup now waits for the correct two-axis map and wght=400 before snapshotting.
  The original complete-QFont equality and zero-change assertions remain.
  The failed XML/log and diagnostic axis values are preserved separately.

The Windows workflow on this development branch compiles the exact triggering
source, exercises D3D11 WARP and the standalone tests, then builds the full app.
The native-raster invocation now also runs `previewRepeatedAxesReuseResources`;
when Windows/D3D11 is requested the test requires that actual graphics API, so
the texture-reuse branch cannot silently be replaced by software-only checks.
Its result must be read from the actual run; the Linux results above do not
predeclare its outcome.

## Still required on the user's Windows hardware

Run original and experimental fonts in isolated application font directories,
with source identities recorded. Retest the original 200% memory gate, 1024 new
coordinates, native raster tolerances, same-window physical DPI transitions,
and 60/120/240 Hz three-round/four-phase traces. Keep the foreground failure and
all original evidence. Record process private bytes and GPU memory alongside
trace fields; do not derive physical refresh or photon latency from frameSwapped.
For a performance A/B, give the baseline the same viewport-only setup adjustment
and verify equal actual dimensions. A smaller viewport is not evidence that the
allocation or queue change improved performance.

The independent font-binary deliverable is explicitly experimental. The real
installed older PingFang file was not available in the cloud workspace. Only the
uploaded PingFang and its experimental copies are glyph comparison sources;
neither a different typeface nor an unverified same-name download substitutes for
the installed old font. Its collection script and binary evidence are separate.

## Primary implementation references

The approaches were reviewed before implementation; Swirl's changes were
independently written and do not copy Qt's implementation.

* [Qt 6.10.3 QSGPlainTexture](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/scenegraph/util/qsgplaintexture.cpp)
* [Qt 6.10.3 QSGDefaultPainterNode](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/scenegraph/util/qsgdefaultpainternode.cpp)
* [Qt 6.10.3 QSGSimpleTextureNode](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/scenegraph/util/qsgsimpletexturenode.cpp)
* [Qt 6.10.3 Binding](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/qmlmeta/types/qqmlbind.cpp)
* [QRhi lifetime and compatibility](https://doc.qt.io/qt-6.10/qrhi.html)
* [QSGTexture upload contract](https://doc.qt.io/qt-6.10/qsgtexture.html#commitTextureOperations)
* [Binding.delayed](https://doc.qt.io/qt-6.10/qml-qtqml-binding.html#delayed-prop)
* [Qt.callLater](https://doc.qt.io/qt-6.10/qml-qtqml-qt.html#callLater-method)
