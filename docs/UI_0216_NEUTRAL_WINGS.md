# Swirl 0.2.16 — neutral surfaces and feather motion

Source baseline: `39a1b91`, isolated branch
`work/swirl-0216-neutral-wings-20261028`. This iteration retains the requested
0.2.16 version, current information architecture and existing Rust Core.

## Implementation

`Theme.qml` owns the light `#F7F7F8` canvas / white cards and dark `#121212`
canvas / `#1D1D1F` cards. Controls, separators, charts, disabled labels and
navigation use semantic neutral tokens. Accent and feather pigments remain
separate from background materials. The shared `SwirlGlassPanel` supplies
card borders, analytic shadows and interactive hover/press/focus feedback.
The seven Settings entry cards use that same surface.

`SwirlWingAnimation` renders each of the existing four small / five large
closed vector feather paths independently. Each contour has a staggered root
reveal and fold transform; no raster image or whole-wing opacity animation
stands in for feather growth. `SwirlProxyWingMotion` owns one reversible clock
for Activity, Policy and the proxy capsule, bound to the actual
`owned && enabled && processAlive` state. Nominal full travel is 1900 ms open
and 1200 ms close. A Qt SmoothedAnimation behavior preserves the current frame
and velocity on reversal. Zero progress hides the entire small wing.

The workspace owns the large wing across all routes. Its first presented frame
starts a 120 ms visible delay followed by a 2600 ms feather sequence. Navigation
and theme changes retain its progress; minimizing pauses it. Once complete,
there is no decorative animation clock. Reduced motion settles the relevant
state, and increased contrast suppresses decorative artwork.

The floating sidebar retains its dimensions and 14 DIP contour. Its live
application-scene sampling uses a 2.2 DIP blur, 1.6 DIP rim refraction and
native-resolution sampling capped at DPR 2. Removed pigment desaturation,
white color lifting and blue rim colors. Fine neutral rim lighting remains;
no solid panel or added white glass overlay replaces the sampling. This is
application-scene glass, not desktop capture.

The light background wing uses 0.30 opacity and dark uses 0.28 so uncovered
Overview text remains readable. Small proxy feathers retain their own full
color. No Rust protocol, routing, importer or proxy ownership logic changed.

## Reproduction and evidence

Use Qt 6.12.0 with its matching GCC 15.1.0 MinGW kit and the paired Windows GNU
Rust target. Use a new CMake build directory for this checkout. Configure
`SWIRL_BUILD_UI_TESTS=ON` for QA; configure a separate production directory with
that option and `SWIRL_BUILD_CORE_TESTS` both OFF for packaging.

Focused QA entry points are `swirl-appearance-ui`, `swirl-all-pages`,
`swirl-apec-motion`, `swirl-apec-glass`, `Swirl --policy-self-test` and navigation.
Native glass checks assert each feather stage, full close, visible startup,
page continuity, resting pixels, material transmission, interactive cards and
the expected DPR through `SWIRL_EXPECTED_DPR`. Their settled page captures
cover Activity, Overview, Settings and Policy in both themes. These are
controlled render/interaction checks, not physical mixed-monitor or refresh
acceptance. Test results and package hashes are recorded in the delivery
report; a listed entry point alone is not a pass.

The retained critical network/security gates cover configuration/catalog
transactions, import trust boundaries, OS-proxy state, Qt network security
policy and Rust/Qt loopback integration. Host system proxy, TUN, routes, DNS
and private subscriptions must remain untouched. Independent-peer skips and
setup failures are retained in evidence. Private-provider and Codex Desktop
end-to-end acceptance remain separate.

Primary references consulted, without copying third-party implementation:
[KDE Kirigami](https://github.com/KDE/kirigami),
[Qt Shape](https://doc.qt.io/qt-6/qml-qtquick-shapes-shape.html),
[Qt SmoothedAnimation](https://doc.qt.io/qt-6/qml-qtquick-smoothedanimation.html),
[Qt Window frameSwapped](https://doc.qt.io/qt-6/qml-qtquick-window.html#frameSwapped-signal),
and [Qt Quick performance](https://doc.qt.io/qt-6/qtquick-performance.html).
