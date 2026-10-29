# Swirl 0.2.14 — Activity and native icon feedback

The user's 2026-10-28 screenshots show version 0.2.14. This update applies the
feedback to the integrated redesign source instead of restoring that older binary.
The user explicitly requested retaining version 0.2.14, superseding the earlier
3.0.0/3.0.1 numbering. The package filename and exact source SHA distinguish this
updated build from the previous 0.2.14 installer.

## References and decisions

The implementation first inspected mature open-source examples:

- [Qt Quick Layouts](https://github.com/qt/qtdeclarative/blob/6.12/examples/quick/layouts/layouts.qml): negotiate minimum, preferred and available sizes.
- [KDE Union/Kirigami Card](https://github.com/KDE/union/blob/master/src/output/kirigami/AbstractCard.qml): a card owns its background surface independently of scene decoration.
- [Microsoft icon construction](https://github.com/MicrosoftDocs/windows-dev-docs/blob/docs/hub/apps/design/iconography/app-icon-construction.md): provide native size frames for different shell scales.
- [WindowsAppSDK taskbar icon discussion](https://github.com/microsoft/WindowsAppSDK/issues/2730): distinguish window icons from shell shortcut/pinned-icon behavior.

Only the design and API principles were used; Swirl's implementation was written
independently with its existing components.

## Resulting behavior

The Activity page's old 620-DIP breakpoint stacked the layout at normal window
width. Fixed card heights and a separate heading then forced vertical scrolling.
The page now distributes its available height across a two-column reading grid
at supported window sizes. The large body heading is removed; the sidebar entry
remains. Transfer, diagnostics, traffic sources and connections remain visible,
including their filters, metrics and detail actions. Longer source data uses its
own bounded list. Full error messages remain available in a dialog.

The top-right policy shortcut is replaced by one focusable caption/value field
labelled **策略** in the status card. Pointer and keyboard activation navigate to
the actual policy page. The field feedback and shared title use Swirl's existing
bounded wing curve; the route still supports interruption and returning.

One continuous vector decoration now spans the whole application scene. Existing
opaque cards occlude it; uncovered workspace carries the curve. High contrast
and the transparency setting retain their existing behavior. No desktop image
is captured or used as the backdrop.

## Native icon

Read-only inspection of the installed Swirl window confirmed that its 24-pixel
small and 48-pixel large icon matched the existing SVG rasterization. There was
no stale alternate image in that chain. The mark is naturally wider than tall;
changing that ratio would distort it.

The updated runtime/ICO pipeline removes the extra inset and supplies 15 matching
frames, including 30, 36, 60, 72, 80 and 96 pixels. The SVG master and all curves
remain unchanged.

| Frame | Solid alpha bounds before → after | Alpha coverage increase |
| --- | --- | ---: |
| 24 px | 22×18 → 24×18 | 8.94% |
| 36 px | 34×26 → 36×28 | 8.54% |
| 48 px | 46×34 → 48×36 | 8.52% |

All 15 ICO frames match the runtime pixels and masks. An expanded-canvas render
found no alpha outside any frame, confirming that the proportional enlargement
does not crop the curves. A hidden Qt window returned the new small/large icons.
The user's running instance and Windows icon cache were not modified. Actual
pinned taskbar appearance remains part of installed-package visual acceptance.

## Validation

The first 0.2.14 Qt 6.12.0/GCC 15.1 incremental build passed. Native CTest checks
`swirl-appearance-ui` (10.31 s), `swirl-motion` (28.30 s), and `swirl-apec-glass`
(2.64 s) passed. The viewport assertions cover 760×672, 914×672 and 1100×760 DIP
with three populated traffic-source rows and no outer scrolling. Pointer and
keyboard policy navigation and the shared curved title passed. The glass checks
confirm decoration reaches the right workspace and opaque cards conceal it.
Representative light/dark screenshots were inspected.

Native window tint opacity is reduced by four percentage points, to 90% in light
mode and 88% in dark mode, for slightly more desktop visibility through the system
material. Text and opaque cards keep their opacity. The existing opaque fallback
still applies when Windows cannot supply native material or transparency is off.

The final versioned build, populated-layout assertions and CI/package identity
are recorded with the delivered 0.2.14 artifact. These UI checks do not establish
private-provider networking, physical refresh performance or all-DPI acceptance.

## Sidebar continuity and five-colour wings

The follow-up screenshot exposed an actual compositing mismatch: the sidebar
unpremultiplied the sampled translucent window background, tinted it white, and
returned opaque pixels. This brightened the sidebar relative to the workspace.
The window now owns the base material once. A shared vector wing scene is sampled
by the sidebar and displayed outside the matching glass contour. Both paths retain
premultiplied alpha. Refraction and blur return to zero at the edge, preserving
the trajectory across the boundary while the inset lens bends it gently.

The curves use five tapered vanes with orange, red, blue, cyan and green. The
official APEC emblem and glass posters were re-inspected; the shape is independently
drawn, with visible tips inside the viewport. Existing cards continue to occlude it.
The additional full-workspace texture is at logical resolution; the glass blur
remains bounded to the panel and stops while hidden or minimized.

Reference: [Qt 6.12 ShaderEffect examples](https://github.com/qt/qtdeclarative/blob/6.12/examples/quick/shadereffects/shadereffects.qml).
The source-sampling and separate blur-pass principles were inspected before coding.

A native Hero run also exposed missing QML member storage during cold subscription
page creation. Qt documents the GC/deferred-deletion failure class in
[QTBUG-148459 fix](https://github.com/qt/qtdeclarative/commit/c89b2cf16d3184513d6de4cd07482cde90f7f586).
Nonvisual font and popup helpers are now held by explicit typed owner properties,
outside replaceable popup content lists. The navigation test collects garbage
during a cold route, while retaining async incubation and the warning failure gate.

Final local feedback validation: appearance 10.24 s, motion 28.24 s, glass 2.62 s
and Hero 71.92 s passed. Hero includes 102 checks plus 276 navigation checks,
with no missing-member, TypeError, ReferenceError or FreeType diagnostics.
The preceding APEC motion check passed in 14.52 s. New alpha tests verify that
the sidebar leaves the shared base visible and preserves a translucent source.
Earlier failed runs remain in the local evidence archive; obsolete opaque-pane
assertions were replaced with checks of the new shared-base contract.

## Astra material refinement and outstanding font stress

The next refinement gives each of the five vanes unequal thickness, transparent
body gradients, denser curved folds and narrow reflection ridges. Glass feedback
uses surface-space distance, keeping its light round through sidebar resizing;
pointer/focus glints can reach every edge without brightening the entire rim.
No new timer, texture or sample pass is introduced by this refinement.

Commit `24fce41` passed full Windows CI `40636576944`; its verified 0.2.14 installer
has SHA-256 `a4affdcbe5473efc6aac02f41158fad5a1200ac20a678bb501fc24137fa8eb29`.
That package predates the subsequent material refinement.

Additional synthetic-font stress must not be reported as clean: 37 assertions
passed, but logs retained 7,746 FreeType creation warnings. An A/B run restoring
the prior anonymous font-helper ownership still produced 7,503 warnings; the
older 2026-10-27 log also contains 7,761. The historical zero-warning claim in
APEC_PERFORMANCE_INTEGRATION.md has been corrected. Qt font debug identifies
failed system fallback families (including Tahoma, SimSun and Arial), while the
synthetic axis stress is running. The root cause remains unresolved. A debug run
also failed an assertion and is retained separately; it is not clean acceptance.
These observations do not invalidate the passing regular UI/GC lifecycle checks,
and those checks do not establish warning-free extreme variable-font rendering.

The Astra refinement passed native appearance (11.38 s), APEC motion (14.49 s)
and glass checks (2.84 s, including right-edge glint locality). Four light/dark
previews at 760, 914 and 1100 DIP were inspected. The debug font run's three
failed assertions concerned dynamic control discovery, HGHT update and retained
page identity; normal non-debug runs passed those assertions but retained FT
warnings. This remains a diagnostic limitation, not a clean font-stress result.
