# Activity five-card rebuild

The overview uses two explicit RowLayout objects: connection status and transfer
in a 5:7 upper row, then sources and a right-hand ColumnLayout in a 7:5 lower row.
The right-hand column contains diagnostics and connections. Width hints on the
layout slots fix each column's minimum, preferred and maximum width to its share
after the 16dp gap; content implicit widths cannot override these proportions.

The 0.2.28 breakpoint was incorrect for the owner's actual window. The existing
expanded sidebar is 208 logical pixels and page padding is 24 on each side. A
1013-logical-pixel window therefore has 757 pixels of activity content, below
the old 780 threshold. The same old binary was reproduced on the owner's native
150% display at 1013 by 672 logical pixels (1520 by 1008 physical pixels after the
window minimum height applies), and it selected one column. This was a layout
condition, not evidence of a stale installer.

Version 0.2.29 uses a 736-logical-pixel content breakpoint. At that threshold,
the 5:7 split has readable widths of 300 and 420 after the gap. At the observed
757-pixel content width, those widths are 308.75 and 432.25. The normal-height
layout budgets 238 pixels for the upper row and 326 for the lower row, fitting
the observed 596-pixel scroll viewport with the 16-pixel row gap and bottom
space. Taller two-column windows approach 38:62. The single column keeps the
compact 238/326/155dp card heights even in a tall window. Shorter viewports retain
these content minimums and scroll vertically. The rate labels, numbers and units share one
baseline; the chart retains a 110dp minimum height. Source summaries keep normal
30dp rows and reserve space for at least five records.

Card instances stay alive across details and responsive reflow. A narrow-state
ParentChange moves each existing card into an ordered ColumnLayout slot instead
of destroying pages or duplicating cards. This retains filters, viewport state
and the cloud-knot instance. Connection status no longer stretches an empty
spacer; node information uses the whole width while the knot is inactive, with
an 80dp knot region reserved only while active or withdrawing.

The neutral canvas, opaque content faces, existing font system, clear floating
sidebar and 14dp shell/sidebar corners remain in use. The background artwork now
uses a limited bottom-left feather composition and a faint top-right echo.
System Proxy, TUN and acknowledged outbound-mode controls share the top toolbar.

All five cards use one reversible container transition. The surface changes
geometry while text and detail layouts retain their normal size. A new segment
starts at the currently drawn rectangle when interrupted or resized; returning
reads the source's current layout and brings an offscreen source into view only
when necessary. Menu dismissal continues to use the existing dismissal stack.

Connection details use the current node, network, exit-IP observation, policy,
profile and core uptime. Missing values remain explicit. The model does not
provide every connection's process identity, device name, protocol or latency,
or gateway/DNS-server addresses. The INTERNET measurement is a complete HTTPS
request; independent diagnostic measurements are not added together. Historical
sampling gaps remain gaps. Process/device rankings do not supply the totals.

Details retain virtualized tables and incremental row identities. Data
projections pause during the outer transition; the overview chart pauses while
details are open. Source-row activation clears the destination search and locates
that stable item. Longer tables scroll horizontally at readable column widths.

The production UI correction is confined to ActivityPage.qml and product version
0.2.29. Test-only CLI wiring and geometry checks cover the new structure; existing
activity tests were updated to the five-card contract without removing their data
checks. The accepted background, floating sidebar, shell structure, and data
models are retained. No Rust Core, TUN, DNS, rule-routing or protocol
implementation changes are included.

## Verification ownership

The owner initially requested runtime testing of 0.2.28 themselves, then
requested correction and direct verification of the observed layout failure.
Build checks, controlled geometry/transition checks and native-display evidence
must be reported separately from broad DPI/refresh, subscription, system-control
and networking acceptance. A source calculation or one screenshot does not
establish those broader outcomes. No tests were removed or disabled in the
source; test-free product compilation follows the existing production profile.

On the owner's 2560 by 1600 Windows display, actual system scaling was changed
through Settings to 100%, 125%, 150%, 175% and 200%, then restored to 150%. No Qt
scale-factor override was used. The focused native Direct3D 11 checks passed at
all five DPRs. They read final live QQuickItem geometry, compare the two width
ratios and stack edges, check text bounds, exercise all five details and ESC,
and reflow while a detail is open. At the screenshot's 150% scale, the 1013 by
672 logical window has 757 logical content pixels and all five cards fit.
Saved 100% and 125% rectangles were also independently checked for viewport fit.

The existing retained-data activity regression passed 143 checks with 600
controlled records. Its memory window now starts after all five populated
detail pages settle: the original 24 MiB bound is unchanged; eight measured
cycles grew by 1,867,776 bytes. The separate initial populated-data cache cost
was 28,852,224 bytes. An earlier measurement incorrectly included that first
cache fill. The interrupted-ESC test also samples synchronously at key dispatch,
because Qt's QWindow key helper processes the event loop after press and release;
its original five-pixel continuity tolerance remains unchanged.

The five-card animation capture contains 228 actual Qt window frames at native
150% scaling and no capture failures. Readback timing and Qt frame delivery do
not establish physical presentation FPS. Real subscriptions, active proxy/TUN,
cross-monitor behavior and long-name/IPv6 data remain separate acceptance work.

## Primary references consulted

- [Qt Popup dismissal and focus](https://doc.qt.io/qt-6/qml-qtquick-controls-popup.html)
- [Qt path animation and current endpoints](https://doc.qt.io/qt-6/qml-qtquick-pathanimation.html)
- [FluentUI for QML](https://github.com/zhuzichu520/FluentUI): mature desktop
  control/navigation reference. Swirl's existing controls and coordinator are
  retained; no external component code was copied.
