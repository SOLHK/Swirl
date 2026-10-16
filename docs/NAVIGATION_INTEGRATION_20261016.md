# Windows navigation and unified material

The nine More cards previously called `Main.openSettings`, which owned a
separate native settings shell, title bar, content host and transition window.
Even after reducing that path to one settings HWND, it remained independent
of the main sidebar and navigation history.

All nine cards now enter the existing main `SwirlPageHost` through
`AppState`. General, Appearance and Fonts have distinct cached routes; DNS,
Modules, Profiles, Scripts, Subscriptions and Nodes reuse their complete
existing pages. There is no settings Window, settings backdrop controller,
secondary title bar or cross-window reparenting. Back and Alt+Left use the
same history. The hub, forms, filters and list viewport remain mounted in
their cached page instances. Navigation never calls a proxy start/stop or
node-selection operation.

Card press feedback, shared title travel, surface expansion, reverse motion,
route cross-fades and node inspector morphs remain enabled. Cold construction
keeps the previous live page visible. The host also exposes the preparation
interval as pending so the next transition cannot settle before layout and
animation are ready. Mid-flight reversal snapshots the displayed geometry
inside its handler; resize retargets the same live surface.

The pressed card now grows above its original hub into the main content
region. Its icon, description and shared title travel with the expansion;
the functional page is revealed inside that moving boundary while retaining
its final layout size. The single existing motion clock drives the boundary,
content and reverse transition. This reveal clip is part of the animation,
not a workaround for overflowing page layout. Back returns focus to the card.

The gray moving layer came from changing the hidden source card color to
transparent black and then interpolating its mutable QColor value. Source
handoff now changes opacity only, and the transition clones the original RGB
before hiding that source. Only alpha changes as the surface joins the shared
window material. The expanding surface has neither an extra shadow nor a
square page border; ordinary internal cards retain their existing styling.
The hub's decorative full-width header divider is removed. Its back control
appears only near the completed expansion, reads "返回", and is absent on
the hub; it no longer overlaps a still-visible "设置" card page.
The source card keeps the regular white content material in the light theme
instead of replacing it with the blue hover fill. Hover feedback moves to the
existing rounded border with the same color transition duration; press and
expansion motion stay enabled. The navigation fixture checks all RGB channels
against the normal card material throughout the expanding surface's lifetime.

The visible material seam came from a sidebar-only native blur surface and a
different workspace tint, followed by a gradient used to soften their boundary.
There is now one full-shell live compositor blur and one uniform QML tint.
The sidebar has no separate material and the gradient has been removed.
Cards retain their existing opaque material, radius and shadows. Text is
drawn normally, without a window-wide blur texture or desktop screenshots.
Windows transparency, contrast and power policies retain the explicit opaque
or alpha fallback. The optional native blur policy remains capability-dependent.

DNS no longer paints its former dialog-specific gray background. It uses the
existing card material and switches its option columns to vertical stacking
when the main content becomes narrow. Nodes keep their virtualized table and
existing adaptive list/detail layout.

## Validation

The navigation fixture clicks every card twice, checks the unchanged main
native handle, absence of new QQuickWindows, live page coverage, expansion
and reverse geometry, cached page identity, DNS drafts, node search and scroll
state, virtualized row count, minimum-width layout and resource cleanup.
The node UI integration additionally traverses all settings routes while a
real controlled Mihomo connection is running, checking its PID, API health
and selected node after each navigation.

Native desktop material checks compare the sidebar and workspace against the
same red/blue background and sample both sides of the old seam. The pre-final
run passed 67 checks: sidebar delta 95, workspace delta 96, and 81 intermediate
pixels in the controlled blur-edge profile. These are compositor pixel tests,
not a claimed macOS material implementation.

Final test results and commit/CI status are recorded in the delivered report.
The complete local CTest run exercised 22 groups: 20 passed initially. The
remaining two were repaired and passed on targeted rerun: the native stream
assertion now waits for the published final telemetry snapshot, and Overview
input checks validate the new main-window routes and modal ownership rather
than requiring the removed settings HWND. The latter passed 61 checks.
Earlier independent-settings-window reports describe superseded architecture.
The previous task's desktop OAuth and long-lived remote-control checks remain
separate from this navigation acceptance; no desktop authentication was restarted.

## Windows startup readiness follow-up

The navigation release passed its complete Windows CI, but two parallel staging
runs of the same tree exposed intermittent Mihomo readiness failures in node,
native compatibility and subscription tests. Startup was waiting for the
steady health interval (normally two seconds) before its first authenticated
API check. The native fixture also supplied a three-second native handshake
budget to the real three-stage Mihomo compatibility launch.

The adapter now probes when the engine process starts and uses a bounded
200 ms cadence only until authenticated API/config and mixed-listener readiness
are verified. It then restores the configured health interval. The original
total startup deadline, process ownership, authentication and forwarding rules
remain unchanged. A deterministic fixture initially stalls the API while the
steady interval exceeds the entire startup deadline: it failed before this
change and passes after it. Compatibility-only fixtures now give the real
engine a 15-second launch budget matching their existing readiness waits;
native handshake deadline tests retain their explicitly short bounds. API
failure diagnostics include the numeric network error without raw endpoints.
