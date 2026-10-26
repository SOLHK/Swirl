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
