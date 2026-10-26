# Settings migration — 2026-10-27

## Interaction phase

`SettingsPage` retains its public `section`, `sections`, `scrollToBottom()` and
`motionTitle` entry points and the font/engine automation object names. The
section directory keeps stationary input geometry. A single `SwirlArcMotion`
retargets the selection presentation from its current position and velocity.

Visited sections retain individual ScrollViews and asynchronous live Loaders.
Each pane uses `SwirlArcMotion` and `SwirlTransitionCoordinator` to carry its
curved enter/exit geometry and reversible reveal. Old and new panes coexist
during travel. The page history supports Escape and Alt+Left; selection is
applied before animation, and no obsolete transition gates new input.

Existing appearance settings, font preview/apply/import/license behavior,
proxy diagnostics, engine actions and errors were extracted without changing
their backend calls. FontBinding's completion fence, deferred Connections and
axes publication are unchanged. The existing page host/cache is unchanged.

The independent Qt 6.12 build and 61-route smoke passed. Native navigation
passed all 13 sections, asynchronous first loading, retained diagnostic/font
draft controls, actual Down/Alt-Left and Window Escape, plus the existing
shared hub/cache/return checks. Native interaction passed 66 checks with no
QML warnings after fixing a visible/moving feedback loop and waiting for the
asynchronous About pane. APEC motion passed 36 checks. The full synthetic-font
memory plateau pressure test remains a separate open baseline issue; this
checkpoint does not claim it passed. No host network setting or user data was
changed, and no subscription was read.

## Visual phase

Prepared after the interaction phase: Theme owns canvas `#FBFCFD`, surface
`#FFFFFF`, navy `#14283F`, secondary `#53667A`, cyan `#007EAA` and separator
`#DDE6ED`. Page code consumes the existing semantic tokens instead of copying
those values. Existing fontManager choice and variable-font behavior remain
the type source; settings rows use 14dp labels/12dp descriptions and 18dp group
heads, with shared page-title tokens above them.

The Settings directory groups personalization, connection, local preferences
and product information. Reading-aligned settings rows use quiet separators
and preserve space around controls. The hub uses one primary general-settings
entry, then parallel resource/configuration columns. The initial uniform-card
idea was rejected because these functions have different priority and density.
Existing unsupported controls remain explicitly unavailable; their display
does not imply execution.

The hub retains all seven `settings-*` IDs and shared title/icon/description/
surface ownership, `openSettings(route, entry)` and `surfaceHidden`. Font and
hub motion-only changes precede their visual drafts. Escape requires the narrow
`handleSectionEscape()` callback from Main's Escape handler because the existing
window event filter consumes Escape before page Keys handlers. Modal dismissal
remains first; the header's route-return contract does not call this callback.

Primary implementation references are the existing Qt 6.12 motion foundation
sources in `APEC_MOTION_FOUNDATION.md`, especially Qt Popup/Menu lifecycle and
the retained Arc/Interaction/Coordinator contracts. No external implementation
or shader was copied for this settings migration.

This phase is not a physical GPU, high-refresh, DPI, private-network or final
visual acceptance claim.
