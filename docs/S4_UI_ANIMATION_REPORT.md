# S4 UI / motion evidence

## Contract and design direction

The S3 shell is the reference: no window/sidebar geometry, contour, clipping,
antialiasing, shadow, size policy, or existing animation is to be replaced.
The content palette remains the existing light canvas `#F8F8F8`, white surface,
dark canvas `#24272C`, dark surface `#292C31`, and existing blue accent. Existing
font selection and native glyph rendering remain authoritative. Content is left
aligned, status is beside its subject, actions remain at the card edge. Changes
must improve truthful state feedback and reuse, not add decorative motion.

Baseline inspection found an already unified `SwirlMotion`, reversible
`SwirlTransitionCoordinator`, dismissal stack, cached route host, and virtualized
node view. Those mechanisms are retained. There is no evidence of a navigation
leak in the initial repeat test: the measured increase was 311,296 bytes.

## Baseline captured before product edits

Native Windows, Qt 6.10.3, D3D11, DPR 1.5, 240 Hz; existing S3 tests build
`D:/Codex/build-swirl-s3-max-20261023/Swirl.exe`.

- `D:/Codex/outputs/s4/ui-baseline/motion.json`: zero failed checks; 16 cached
  pages, zero active grabs, one idle frame.
- `D:/Codex/outputs/s4/ui-baseline/glass/dpi-150`: 124 light/dark captures and
  266 checks, zero failures.
- Initial five-scale script: 125/150/175/200% correct and passing; the requested
  100% run actually used native 150% and is retained as a failed scale check.
- Corrected 100% process environment (`QT_ENABLE_HIGHDPI_SCALING=0`,
  `QT_SCALE_FACTOR=1`) produced DPR 1 and zero failures in
  `glass-dpi100-corrected/report.json`. This changes only the test process.

## Primary references and dependency decision

- [Qt Declarative](https://github.com/qt/qtdeclarative), observed GitHub mirror:
  298 stars, 39,801 commits. The existing application already uses Qt Quick;
  this change introduces no additional runtime dependency. GitHub's rendered
  page did not expose the latest commit timestamp, so maintenance recency is
  not asserted from that page.
- [Kirigami](https://github.com/KDE/kirigami), observed mirror: 325 stars,
  5,693 commits; canonical upstream is KDE Invent. Evaluated for reusable
  controls and state handling; not added because it brings another UI component
  system without solving the measured defect. No source copied.
- [Qt ListView reuse guidance](https://doc.qt.io/qt-6/qml-qtquick-listview.html#reusing-items)
  explicitly requires resetting transient delegate state and stopping pooled
  animations. This is directly relevant to the node latency reuse defect.
- [Qt QCollator](https://doc.qt.io/qt-6/qcollator.html) documents reusable sort
  keys; do not add a cache without a measured need and invalidation contract.

License evaluation: keep the project's existing Qt licensing/distribution
contract; no third-party code is imported by S4 UI work. Kirigami is a reference
only and is neither linked nor distributed.

## Implemented changes

- Node list reuse resets transient latency by node identity and settles pooled
  or hidden delegates. A real value update keeps its smooth interpolation;
  its target is set before restarting, avoiding the previous-value binding
  race. Native checks see intermediate values and the exact final measurement.
- The existing motion singleton also supplies the shared curve, status duration
  and busy cycle. The same reversible clock and press/release mechanisms remain
  in use. The busy glyph uses Qt's render-thread rotation animator; visibility,
  minimization and reduced-motion gates remain intact.
- Success/warning badge text has stronger light/dark contrast and a complete
  accessible status name. Subscription page title uses the established page
  scale, status uses “已更新”, and filtered-empty copy explains search recovery.
  Busy/success state is still derived from the actual importer/store completion.
- Settings identifies the app as Swirl and its internal module as Rust Core.
  No shell geometry, function, material effect or page cache was removed.

## Validation status

All five native scales now pass with exact DPR 1 / 1.25 / 1.5 / 1.75 / 2:
`D:/Codex/outputs/s4/ui-after/glass/dpi-summary.json`. At 150%, 266 checks and
124 light/dark route captures pass; other scales each pass 26 checks and four
captures. Representative 100% activity, 150% dark subscription and 2,000-node
screens were visually reviewed. This does not claim every screenshot received
manual pixel review.

Corrected native synthetic stress `ui-after/stress-final-native.json` exits
**0** with **220 checks / zero failures** after a fresh stage build based on
`658d90d`. It observes 164 / 962 / 712 / 713 reused node identities at the four sizes with
zero cross-node latency interpolation. Same-node values move from 10 through
approximately 17–19 to exactly 90; all selections, Escape returns, shell size
and sidebar checks pass. Two earlier stress artifacts retain harness failures
because QObject ownership traversal missed ListView visual delegates; the
observer now traverses the visual tree. An intermediate run caught the stale
animation-target defect and remains a failure, rather than being overwritten.
The later `stress-verified.json` / `stress-offscreen.json` artifacts also remain
failed overall (exit 2) because their synthetic row omitted the selected detail
address. The complete fixture now supplies address, port and engine label.

Independent review also found a render-thread lifetime race in the new sampler;
the source now captures an owned shared sample state and snapshots under its
mutex. The corrected native result above includes that repair and complete
fixture; final exact-SHA integration is still a separate gate.

Native `--node-self-test` exited zero after real loopback forwarding, protected
subscription import/update/failure, selection, filtered lists, cancellation of
deletion with Escape, and the new true-busy/store-complete assertions.
`ui-after/node-business/` retains success/failure screenshots and 25 business
transition frames; these screenshots were visually reviewed.

The DPI script now also restores absent environment variables by removing them,
instead of coercing null to an empty string. Qt's `qEnvironmentVariableIsSet`
can treat an empty marker as enabled, accidentally selecting glass checks for a
later motion run. The accidentally repeated glass capture is retained in the
directory named `ui-after/motion.json`; it is **not** a motion performance result.

Native `ui-after/motion-verified.json` reports zero failures and exits zero.
Corrected offscreen/software `ui-after/stress-final-offscreen.json` also exits
zero with 220 checks / zero failures. Its diagnostics contain no QML warnings.
The native motion
suite retains reduced-motion policy, rapid interruption, modal dismissal,
keyboard focus, page-cache and grab-lifetime checks. Native node business checks
also exit zero. Final exact-SHA integration must rerun the revised sampler and
the appropriate retained suites after the stage is committed.

Baseline screenshots and synthetic node measurements are not private-
subscription or WAN acceptance. A 20% memory reduction was not achieved; see
the separate performance report for actual values and limits.
