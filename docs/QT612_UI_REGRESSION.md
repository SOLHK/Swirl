# Qt 6.12 native UI regression — incremental candidate

2026-10-27. Native local validation uses the new Qt 6.12.0/GCC 15.1.0 build,
isolated settings and per-instance test OS adapters. These are controlled UI
and loopback tests, not private subscriptions or physical-refresh acceptance.

The first candidate built successfully and loaded all **61 routes**. Its
initial interaction/navigation/node failures exposed stale test assumptions:

- A new routing rule requires an explicit policy selection. The old input test
  filled only the pattern and clicked the disabled save button, then attempted
  navigation behind the still-open modal. The updated test asserts that saving
  is disabled, selects DIRECT through the actual menu, waits for the real
  configuration result and verifies modal closure. Product defaults are not
  changed. Two stable object names identify the existing dialog and selector.
- The native control foundation now follows the OS reduced-motion preference.
  Navigation checks now verify that contract before explicitly controlling the
  test's motion policy. Debounced search and asynchronous font controls are
  awaited by their actual state rather than fixed delays.
- A policy receipt precedes the exit animation. Node input checks now wait for
  the picker to close and choose a visible cached delegate; they retain all
  actual routing and loopback assertions.

The NavigationChecks/NodeUiChecks fixes were reviewed and inherited from the
preserved prior work snapshot. The rest of the earlier page redesign snapshot
remains pending deliberate page-stage integration. Copying a snapshot preserved
old mtimes, so those test translation units were explicitly rebuilt before
accepting their new results; an intermediate stale-object navigation result is
not counted as a retest of the corrections.

Local results after the corresponding rebuilds:

| Suite | Result |
| --- | --- |
| All-page startup smoke | Passed, 61 routes |
| Mouse/keyboard interaction | Passed, 66 checks |
| Navigation | Passed |
| Node UI and controlled routing | Passed |
| Policy UI and transaction lifecycle | Passed |
| Existing motion regression | Passed |

These tests validate retained functionality and the Qt upgrade. They do not
constitute implementation or acceptance of the new Swirl 3.0 Motion System.

The optional font UI run first exited before testing because it lacked its
required variable-font fixture. A synthetic fixture was then generated with
the existing project tool, without reading user fonts. The actual synthetic
run failed its repeated-coordinate memory-plateau check and emitted FreeType
font-engine warnings. This result remains open for diagnosis; no threshold
was relaxed and no font/animation feature was disabled to hide it. Other font
unit/native CI results must be read independently when available.

Installer notice versions are updated from the installed SDK's SBOM: Qt
6.12.0 and bundled FreeType 2.14.3. The old Effect Maker version remains only
as historical development-tool attribution, not the shipped Qt runtime.

## Additional Qt test-runtime checks

Qt 6.12 `windeployqt` deploys the native Windows QPA plugin by default. The
isolated offscreen test executable initially failed to initialize its platform;
plugin-loader diagnostics identified the absent `qoffscreen.dll`. CI's test
runtime now explicitly includes that plugin and verifies its presence. The
separate production deployment remains native Windows.

The source-based font integration fixture also combined its TextArea skin's
bound pixel size with a point size, which Qt reports as conflicting units. It
now explicitly replaces the complete default font with a point-sized font;
the existing point/pixel, optical-axis, live-binding and native-rendering
assertions are unchanged. With the complete platform runtime, the font
selection and axis-policy CTest suites pass. The selection XML records 34 test
functions, zero failures and nine native/private-fixture skips in the offscreen
run; these skipped cases are not accepted by that result.

## Capture backend diagnostic checkpoint

The MSVC CI run `40388157088` passed its 30 CTests and Overview input checks,
then failed the separate deployed application's TLS capture positive control
with an issuer-certificate error. Installer steps were consequently skipped.
This is an unresolved deployment/runtime regression, not a delivered package.

The integrated Qt 6.12.0 local MinGW executable passed all 78 capture checks
with both explicit Schannel (Windows 10.0.29695) and OpenSSL (runtime 3.6.4)
backends. These are controlled loopback results on the local Windows host;
they do not establish the Windows Server CI result or private-network support.

Test builds now report the active TLS backend and the positive control's
certificate errors. `SWIRL_CAPTURE_TEST_TLS_BACKEND` selects a backend only
for `--capture-self-test`, before TLS initialization. Production builds and
certificate/hostname verification are unchanged. No system trust or proxy
configuration was modified.
