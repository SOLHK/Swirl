# Font system CI and Windows handoff

## Scope and source identity

`font-system-windows.yml` responds to font/QML changes on
`work/core-completion-20261017` and checks out the triggering **commit SHA**, not a
moving branch tip. It never writes a branch, edits an App, uses private
subscription archives, or reads a private font. It also declares a manual trigger
on that same branch; `build_full_application=false` omits only the extra full
application compilation, not the font test targets. The initial execution uses
the development-branch push. GitHub's manual-run UI depends on default-branch
workflow registration, so a Run workflow button is not promised while this file
exists only on the development branch. No main-branch change is made to expose
that button; API dispatch availability must be verified after the first run.

The implementation is independent Swirl code. The dependency installation
follows the existing repository's `jurplel/install-qt-action@v4` convention. The
corresponding references are:

- [Qt 6.10 Windows supported configurations](https://doc.qt.io/qt-6.10/windows.html).
- [install-qt-action's documented MSVC 2022 architecture](https://github.com/jurplel/install-qt-action/tree/v4).
- [Qt 6.10.3 offscreen platform source](https://github.com/qt/qtbase/blob/v6.10.3/src/plugins/platforms/offscreen/qoffscreenintegration.cpp).
- [Qt 6.10.3 XML test result writer](https://github.com/qt/qtbase/blob/v6.10.3/src/testlib/qxmltestlogger.cpp).
- [GitHub Actions standard runner billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
  and [usage limits](https://docs.github.com/en/actions/reference/limits).

## Independent build before application dependencies

The CMake option `SWIRL_FONT_TESTS_ONLY=ON` creates `SwirlFontTests` and
`SwirlFontAxisPolicyTests` then returns before the HTTP/2, proxy engine, shader,
launcher, or complete application targets are configured. The standalone path
needs Qt Quick, Quick Controls 2 and Test. Both this path and the existing
`SWIRL_BUILD_UI_TESTS` path call the same font-target registration function. There
is no second copy of the test implementation and no modified pixel tolerance.

The hosted job uses Qt **6.10.3** `win64_msvc2022_64`, the **Visual Studio 17 2022**
CMake generator and **x64**. Before compilation it checks both the SDK's reported
version and CMake's actual Qt version, compiler ID and pointer size. It saves the
actual compiler version, language standard and generator in `font-toolchain.txt`.
MinGW packages are not combined with MSVC objects.

Each push then attempts a separate complete `Swirl` application compilation with
the existing `SWIRL_BUILD_UI_TESTS=ON` option. This compiles the existing
`FontUiChecks.h` and `FontFrameChecks.h` code paths, including setup of the advanced
manual-mode control. The build explicitly selects only `--target Swirl`; it does
not build every unrelated test target or run CTest in that application directory.
A font test failure remains a failure even if that compile succeeds. This extra
build does not run the application, change its core choice or exercise live
network/proxy settings. Compiling the private-font UI/240 Hz test code does not
count as executing those tests.
An unavailable external dependency is a real failed configure/build step, with
its original log retained. No installer or runnable package is published by this
font verification job.

## Test sources, executed cases and skips

The job executes the checked-in original `generate_font_metadata_fixtures.py`
with pinned fontTools **4.61.1**. Its simple triangle outlines create the static,
variable metadata, altered range and CFF fixtures from scratch; it does not read
or derive glyphs from user fonts. The generator also supplies original multi-axis
outlines for public automatic/manual mode integration checks. Only the separate CFF fixture is put in the
offscreen font-search directory, giving the persistence test an alternative
family. The same-family static/variable/range fixtures are kept out of that
directory, so the metadata replacement test controls registration order itself.

`SwirlFontTests` uses the existing bundled HarmonyOS Sans resources and license.
`SWIRL_TEST_TTC` and `SWIRL_FONT_EVIDENCE` are explicitly empty in this public
workflow. A user's PingFang TTC is never downloaded, generated, committed, or
uploaded. The existing private-font cases consequently report **SKIP**. In
particular, their absence is not a raster-quality pass.

The CTest targets also write native Qt XML reports. The summary parser reads each
Qt `Incident` rather than equating the CTest process exit code with all cases
passing. It excludes lifecycle callbacks from case counts, preserves skipped
case names/reasons, fails on missing/truncated reports and requires these public
checks to actually pass:

| Gate | Required execution |
| --- | --- |
| Font selection | Default family and settings persistence; unchanged imported bytes; malformed file rejection |
| Synthetic font metadata | Same-family registration replacement/range change; original CFF import and raster |
| Independent axis policy | Every registered policy case; a skip fails this gate |
| Public font integration | Automatic/manual profiles, independent-process restart, legacy migration, real multi-axis glyph/fallback rendering, and bounded caches |
| Actual QML and preview integration | Existing controls and live mode/family updates, display-context lifetime, font-resource invalidation, and idle raster stability |
| Windows native raster | `nativeGlyphsHaveNoColourFringes`; a skip fails this gate |

The offscreen selection/QML suite explicitly uses Qt Quick's software backend,
as an offscreen integration check. The separate Windows native raster target
unsets that override and runs the Windows/D3D11 path; software offscreen results
are not evidence of D3D11 glyph quality.

The full FontTests executable still executes all registered cases. Existing
private render matrices and pixel tolerance **2** remain unchanged. No private
font test is removed, weakened, or reclassified as a passing case. Parser
regressions verify that missing reports, private skips, required synthetic skips,
skipped policy cases and failed lifecycle callbacks retain distinct outcomes.
The existing private/child/native-only cases are explicitly listed: any new
public test that unexpectedly skips also fails the report gate. The current
automatic-font integration cases are required by name, so an accidentally
unregistered QML or restart slot cannot disappear from an otherwise green report.

## Evidence and limits

The artifact contains only explicitly listed build logs, CTest/QTest XML,
individual-case JSON, compiler details, step outcomes and exact SHA/run identity.
It does not contain fonts, user settings, subscription data, credentials,
screenshots of private content, source snapshots of unrelated modules, or an
application binary. Retention is seven days; the new job disables the Qt cache
and uses a 40-minute timeout with two-way compile parallelism. It uses the
standard `windows-2022` public runner, not a paid larger runner. The job is
disabled if the repository becomes private so that it cannot silently start
using paid private-repository minutes. Account-wide usage/budget settings are
not changed, and storage usage remains subject to GitHub's existing account
limits.

The native check requests **D3D11 WARP** on the hosted Windows VM, using Swirl's
existing FreeType platform setup. Qt's scene graph diagnostic log records the
actual selected backend. This validates a Windows Qt render path on the runner;
it is not a physical Windows 11 monitor or GPU test. The evidence explicitly
sets `physicalDpiVerified=false` and `refresh240HzVerified=false`. A successful
hosted job cannot certify actual Windows scale changes, cross-monitor transitions,
glyph clarity on the user's display, frame pacing, or stable 240 fps.

## Existing App write authority

The existing `.github/workflows/core-development.yml` uses
`actions/create-github-app-token@v3` with the already configured `SWIRL_APP_ID`
and `SWIRL_APP_PRIVATE_KEY`, explicitly requests `contents: write` and
`workflows: write`, and checks out/pushes the permitted development branch using
that token. The repository's development handoff records the successful workflow
commit [`a60c446`](https://github.com/SOLHK/Swirl/commit/a60c446fdb54c10753c2d367752c4e0275a89922)
and [associated App run](https://github.com/SOLHK/Swirl/actions/runs/39029146435).

That existing job only stages `.github/workflows/rust-core.yml`. Its updater
also explicitly allows only that existing Rust workflow. Those restrictions
are not altered or bypassed by the font CI. Adding this new workflow therefore
requires an available connection with workflow write permission; a past App
success is evidence of that App's authority, not proof that every connector or
local Git credential has the same permission. The font workflow itself needs
only repository read permission and no secrets.

## Real Windows continuation

Keep the user's checkout, build directories and test reports under `D:\Codex`.
Cloud workspace writes and GitHub commits do not save files onto that drive.
After a successful build and test result for the exact intended SHA:

1. Use the current development checkout/build on the Windows machine and confirm
   that the executable's revision matches the tested commit. A GitHub run's green
   status applies only to its recorded SHA.
2. Run the existing local-only font tests with the user's own TTC present only on
   that machine. Keep the original glyph pixel tolerance and preserve failures.
3. Test real Windows scaling and movement between monitors, font/theme changes,
   navigation to cached pages, inputs, menus, popups and restoration after restart.
4. Repeat the existing real display frame measurement at 60 Hz and 240 Hz. Record
   display settings, present intervals and CPU/GPU behavior; do not treat the
   hosted WARP run or a `QT_SCALE_FACTOR` simulation as this acceptance.

This document describes the implemented execution contract. Actual compile/test
successes and failures must be read from the run for each exact SHA; merely
checking in this workflow does not establish that it ran.
