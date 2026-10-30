# Activity five-card rebuild

The overview now gives connection status and transfer a 5:7 upper row, then
sources and the two stacked auxiliary cards a 7:5 lower row. Card instances stay
alive across details so filters, viewport state and the cloud-knot weave survive
navigation. Logical minimum heights preserve readable content and allow vertical
scrolling; content narrower than 780 logical pixels becomes a single column.

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

The scope is QML, UI resources and product version 0.2.28. No Rust Core, TUN,
DNS, rule-routing or protocol implementation changes are included.

## Verification ownership

The owner requested that all runtime testing be performed by them. Build and
static source/packaging checks are separate from runtime acceptance. Screenshots,
recordings, actual DPI/refresh performance, real subscriptions and system-control
behavior must not be reported as passed without owner-run evidence. No tests
were removed or disabled in the source; test-free product compilation follows
the existing production profile.

## Primary references consulted

- [Qt Popup dismissal and focus](https://doc.qt.io/qt-6/qml-qtquick-controls-popup.html)
- [Qt path animation and current endpoints](https://doc.qt.io/qt-6/qml-qtquick-pathanimation.html)
- [FluentUI for QML](https://github.com/zhuzichu520/FluentUI): mature desktop
  control/navigation reference. Swirl's existing controls and coordinator are
  retained; no external component code was copied.
