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

The stronger concurrent-node regression then exposed a separate Windows handle
ownership defect: raw Winsock reservation sockets were inheritable. A concurrently
launched core could retain another adapter's control and mixed-listener handles
after the parent closed them, so the intended core could not bind its endpoints.
Reservations now use WSASocketW with WSA_FLAG_NO_HANDLE_INHERIT atomically, while
retaining overlapped I/O and exclusive binding. Port selection and system network
settings remain unchanged. The failing-node fixture must reach the actual node
availability check; a startup timeout is no longer accepted as the expected
failure. It failed before this fix and completed in 5.5 seconds after it.
Reference: https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsasocketw

## Expansion completion follow-up

The shared title and surface previously owned separate clocks. The title was
hidden until its clock stopped, then replaced by the live title during cleanup;
its baseline and font weight also differed from some destination titles.
The page host now owns the shared title's progress as well as the boundary.
The real title enters before the shared layer retires, using the destination
typography and an interpolated text baseline. The expanding card's material
also reaches its destination before cleanup. Mid-flight reversal snapshots the
title before resetting progress, preserving its current displayed position.
All original press, expansion, page reveal and reverse animations remain.

Navigation checks freeze each of the nine real expansions at its final animated
value, verify that the live title is already visible, and compare rendered pixels
before and after retirement. These endpoint tests supplement actual interaction
recordings and DPI runs; readback images do not measure physical presentation FPS.

The final continuous expansion keeps the white source-card material as the
destination page's own rounded surface, without a page border or full-page
shadow. It no longer fades that material to a transparent canvas in the middle
of opening. A single linear phase drives smooth spatial curves: the card reaches
its destination first, while its functional content completes a subtle 1.5%
growth and reveal. Press feedback and reversible navigation remain enabled.
The surface type is retained while hidden, so clearing navigation metadata cannot
activate a full-page shadow. A stable clip node and exact endpoint interpolation
avoid a native hinted-text shift during retirement. Resizing retargets the title
from its currently displayed geometry. A cancellable 32 ms terminal commit keeps
the identical final scene present before releasing the shared layer.

Endpoint fixtures now let the actual animation run to completion before holding
its final scene; they no longer visibly jump an early animation to the endpoint.
Moving screenshot readback is opt-in. Passive performance sampling runs 36 warm
forward/reverse transitions with a normal QEventLoop, without screenshots,
expression polling or QTest's sleep-driven wait loop during motion. On the
current 120 Hz Windows 11 display it recorded 1,578 active delivery samples:
p95 8.74 ms, p99 9.12 ms, maximum 19.81 ms; one interval exceeded 1.5 refresh
budgets and none exceeded 2.5. All-delivery p95 including the stationary terminal
commit was 8.81 ms. These are Qt frame delivery observations, not a claim of
physical display presentation FPS. All nine endpoint comparisons changed zero
pixels in this run.

The fresh local suite passed 22 of 23 groups initially. The remaining Overview
capture-toggle check assumed the user's normal port 8899 was free; an owned
exclusive-bind probe confirmed it was occupied (Windows error 10048). The fixture
now obtains its own ephemeral loopback port and passes it through the same page
toggle; the production default remains 8899. Its targeted rerun passed, including
real listener start/stop and all modal/navigation checks. No existing listener or
user application was stopped. First-failure evidence is retained in the report.

## Production animation policy acceptance

The user's 12.mp4 revealed a gap in the preview acceptance: Windows returned
reduced client-area motion while Swirl's own Reduce Motion preference was false.
The previous implicit OR with the Windows preference made every production
duration zero. Animated test fixtures had overridden that policy, so their
successful expansion recordings did not prove the production default.

Swirl now defaults to its own full animation preference. The existing explicit
Reduce Motion control remains, and a separately persisted Follow System Motion
option lets users opt into the operating system's animation preference. No
Windows setting is changed. Standalone navigation no longer overrides the native
policy: it records and checks the actual effective production defaults before
exercising the nine cards. The initial native-policy run recorded systemReduced
true, followSystem false, applicationReduced false, effectiveReduced false and
expandDuration 360; its endpoint comparisons passed. Motion tests additionally
inject reduced system policy with following both off and on, and appearance
tests verify that the explicit preference survives a new process.

Production startup diagnostics record only these policy booleans and duration,
without credentials or user data. Tests-OFF production startup and actual card
input are verified separately from the deterministic test overrides. The earlier
69f3cca preview is superseded by this policy correction.

## Reverse functional-content continuity

Production UI input revealed that the shrinking card and shared title moved
while the outgoing functional page stayed at its final screen position. The
title could therefore cross its own description during the return. The page
host now carries the live body by the same spatial displacement as its card,
without resizing its layout or replacing its controls. A quick reversal or
resize snapshots the body's current presentation offset before retargeting;
the next expanded endpoint restores the normal zero offset.

Nine new regression cases reproduced this defect before the repair, then
verified that the actual page center and card have the same displacement
during return. A return-to-reopen case additionally checks that the live body
does not jump when direction changes and that the same cached page survives.
This is separate from the endpoint pixel comparisons and passive timing data.
