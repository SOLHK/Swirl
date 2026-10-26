# Swirl 3.0 — flowing knot design direction

2026-10-27. This is Swirl's independent design specification and implementation
plan, not an official APEC visual identity manual. Official observations and
their dates are recorded separately in `APEC_2026_VISUAL_RESEARCH.md`.

## Product and visual premise

Swirl is a desktop network tool. A user must immediately find the proxy master
switch, the effective policy/exit, connection failures and source update state.
Its distinguishing visual device is the original interwoven cloud-knot. The
redesign keeps that identity and uses its flowing paths to connect navigation,
connection state and brand motion. Quiet information surfaces surround this
device; gradients do not become generic card or button backgrounds.

The 2026-10-27 brief supersedes the historical fixed 14dp contours and Activity
two-over-three arrangement. It preserves actual capabilities, data, routing,
receipt-gated configuration mutations, interruption handling and font loading.

## Proposed shared tokens (next implementation stage)

| Role | Light | Dark | Purpose |
| --- | --- | --- | --- |
| Canvas | `#FBFCFD` | `#101D2D` | Neutral near-white / navy workspace |
| Surface | `#FFFFFF` | `#182A40` | Content and dialogs |
| Primary text | `#14283F` | `#EDF5FC` | Stable navy hierarchy |
| Secondary text | `#53667A` | `#B4C7D9` | Supporting information |
| Interactive accent | `#007EAA` | `#55C8E6` | Focus, primary action, active navigation |
| Separator | `#DDE6ED` | `#344B63` | Only at real information boundaries |

Brand colour is separately controlled: orange `#F5A04D`, red `#D93962`,
blue `#285DD3`, cyan `#099DC2`, green `#3CAA79`. These are Swirl-selected
values, not sampled or official APEC colour codes. Red in the logo never
replaces a labelled error state. Brand gradients use unequal stops per path;
their transition vectors and local intermediate colours are in the SVG master.

Keep the existing real fontManager/variable-font controls and async startup
fence. Initial desktop type scale: 12 supporting, 14 body, 18 section, 26 page
title, 28–36 key metrics. Use tabular figures where the selected font supports
them. Titles and content align left. Verify every semantic foreground against
its actual material, including disabled and high-contrast states.

Initial geometry to validate in Qt: 4dp base grid, 12dp shell inset, 184dp
expanded navigation width, 52dp collapsed navigation, 40dp navigation row,
20dp floating navigation radius, 22dp window radius, 10dp controls, 14–18dp
content grouping. These are proposed measurements, not already-validated UI.
Do not encode every group as a card. Responsive reflow, text scaling and all
100/125/150/175/200% DPI cases determine final values.

## Brand implementation in this stage

`assets/brand/swirl-symbol.svg` is the editable master. Five cubic contours
preserve the four inward curls, diagonal crossing and open negative spaces of
the existing Swirl knot. Long sweeps use broad tangents; hook tips close with
rounded curves. There are no bird silhouettes, feather arrays or APEC text.

Each part carries a deliberately directed colour passage: warm left/inner
curl; cyan-to-blue crown; blue-to-cyan forward crossing; cyan-to-green return;
teal inner return. The separation between crossings carries depth without
adding a white outline. Small icons retain the same silhouette. Native raster
verification must inspect the 16–256px frames, not just the large master.

`tools/Generate-BrandAssets.py` produces light/dark transparent marks, two
neutral icon tiles and two monochrome high-contrast marks. `--check` verifies
that the exports match the editable source. QML's brand component switches to
the monochrome assets for increased contrast. The existing Qt SVG → ICO →
Windows resource → NSIS chain remains the single native icon path. The old
tracked ICO is regenerated with that same chain before brand delivery.

Static SVG previews are design evidence only. Application load, installer
identity and native raster results are separate validation records.

## Material contract for the Astra Ultra stage

The sidebar will be an independent floating navigation surface. Study Apple's
[materials guidance](https://developer.apple.com/design/human-interface-guidelines/materials)
and keep control text readable over the actual backdrop. A translucent white
Rectangle alone does not meet this contract.

Keep Windows APIs inside the platform adapter. Distinguish native DWM desktop
backdrop from an application-content sample: a QML blur is only allowed to
claim the latter. Prototype a bounded sidebar-sized source with a combined
blur/tint pass, a low-amplitude normal-based edge refraction and a directional
rim response. Clamp texture sampling to safe bounds. Limit highlights to the
interaction edge; do not draw a uniform white border. Retain the existing
analytic shadow and its cache where it still matches the new geometry.

Use [Qt MultiEffect](https://doc.qt.io/qt-6/qml-qtquick-effects-multieffect.html)
for supported combined effects; use independently written, build-time QSB
shaders for refraction/path flow. [ShaderEffect](https://doc.qt.io/qt-6/qml-qtquick-shadereffect.html)
does not render with the software scenegraph backend, so a software-only pass
cannot accept this material. Opaque/high-contrast/reduced-transparency fallbacks
must remain legible and functional and be described as fallbacks.

The official [Qt Quick Effect Maker source](https://github.com/qt/qtquickeffectmaker)
was examined as tooling context. No third-party glass shader or web CSS was
copied or added. Qt remains the existing rendering dependency; preserve its
installed module notices and existing distribution obligations. Module licensing
must be checked per installed module, not inferred from one repository file.

## Motion contract for the Astra Ultra stage

Motion is designed with each component, not added after page layout. Preserve
the existing retargetable page host, caches, return context and transition
generation fencing. Reuse `SwirlMotion` and the registry instead of starting a
parallel animation framework.

| Interaction | Initial timing | Spatial meaning |
| --- | --- | --- |
| Press / release | 70 / 140ms | Contact and recovery, no large shrinking |
| Hover / focus | 110 / 150ms | Local light response, keyboard equivalent |
| Navigation selection | 240ms | Continuous retarget from current position |
| Page enter / return | 300 / 240ms | Small curved trajectory, preserve origin |
| Sheet open / close | 280 / 180ms | Expand from invoking control |
| Group expand | 320ms | Reveal content in reading order |
| Row mutation | 180ms, 24ms stagger | Explain change without delaying input |
| Connection success | 520ms, one shot | Sweep through knot only after receipt |

These are Swirl tuning proposals, not official APEC animation timings. Use
normalised arc length for path progression and colour phase; do not slide a
whole rectangular gradient back and forth. The new brand path IDs provide
stable visual segments. Stagger long sweeps by phase, not arbitrary per-row
delays. Blend from current presentation during interruption. A second action
must not wait for an obsolete first animation to finish.

Connection/probe/update animations are driven by real pending/success/failure
state. A click is not connection success. Idle connected state settles;
continuous motion is restricted to genuine pending activity. Stop offscreen
work. Reduced motion retains clear state feedback and navigation meaning.
Do not cap the product at 60Hz or remove animations to claim performance.

## Full-page coverage and information architecture

The source inventory finds 31 page files plus dynamic FeatureCatalog routes;
the latter must also be covered. Check shared controls first, then every route,
all settings subpanes, context menus, import dialogs, empty/error/loading
states, keyboard focus and Escape/back behaviour.

Activity should place the single authoritative proxy switch and effective
network/exit state first, followed by traffic and active connections. INTERNET
probe duration remains distinct from node outbound connection time. Never
relabel a whole HTTPS request as network RTT. Keep upload, download, totals,
latency, core status and shortcuts discoverable.

Nodes remain a resource library: browsing or row selection does not change the
runtime exit. Policies show the effective route, precedence and transaction
receipt. Subscription refresh updates owned nodes and does not execute foreign
rules/scripts. Retain cancellation, provenance, explicit destructive actions
and persistent error context while redesigning their presentation.

## Execution and model checkpoints

1. Astra Max: official visual study and source baseline; then editable Logo and
   native icon integration. Qt 6.12 upgrade is a supporting requirement from
   the user's follow-up, not evidence that the whole UI is rebuilt.
2. Notify the user to switch to Astra Ultra before the floating glass and
   global Design System implementation. Do not switch the parent chat silently.
3. Notify the user to switch to GPT-6.1 Sol Ultra for all QML page migration.
   Each page uses motion primitives designed from step 2.
4. Notify the user to switch to Astra Ultra for global motion integration,
   shader refinement and measured performance work.
5. Notify the user to switch to Astra Max for final integration/review.

Each verified stage is committed and pushed separately to
`work/swirl-apec-v3-20261027`; main/test and other development trees remain
untouched. A stage package is not a completed Swirl 3.0 release. Physical GPU,
60/120/high-refresh, all DPI visual acceptance and private-network acceptance
must have independent evidence or remain explicitly unverified.
