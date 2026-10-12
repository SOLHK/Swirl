# Phase three: current-user proxy, routing and restrained motion

This change starts at merged PR #11 (`a83d2b2`) on `test`. It retains the
DPAPI node/subscription store, protocol options, native Qt Quick interface,
capture service and HDR renderer. It does not alter `main`.

## Windows proxy ownership

The overview switch queries and updates the current user's **WinINET LAN**
configuration through `INTERNET_OPTION_PER_CONNECTION_OPTION`. It snapshots
the flags, proxy server, bypass list and PAC URL. WinHTTP, OS DNS, routes, TUN,
VPN processes and other proxy applications are untouched.

Enable requires the owned Mihomo process, authenticated API and a successful
connection to its actual mixed port. Unknown node health is labelled separately
from a successful real node probe. A listener or healthy API does not establish
that a browser or video works.

Before writing settings, Swirl atomically stores a DPAPI-encrypted recovery
journal and starts `SwirlProxyGuard.exe`. The guard acknowledges readiness before
the settings are changed. It monitors both the GUI and engine process identities,
including Windows creation timestamps to handle PID reuse.

Normal shutdown, explicit disable, engine failure and abrupt process termination
restore the captured settings **only when all current settings still equal the
ones written by Swirl**. A later external change relinquishes ownership. Session
IDs and a file lock prevent an older guard from restoring a newer session's
settings. A stale encrypted record can also be recovered on next launch.

The live switch polls Windows every 500 ms. Policy restrictions, unavailable
listeners, failed guardian startup, settings mismatches and recovery failures are
reported. No other proxy software is stopped. This is LAN/current-user proxy
management; separate dial-up/VPN connection-specific WinINET settings are outside
the scope of this version.

## Real routing

The three choices correspond to authenticated Mihomo `/configs` updates and are
confirmed by a subsequent configuration read. They are independent of system
proxy ownership. Offline mode preference persists; in-flight mode changes disable
the selector. Failed updates stop the engine rather than claim a changed exit.

Rule mode prioritizes:

1. Loopback, private, link-local and local domains: DIRECT.
2. Google, YouTube and their listed resource/video domains: SWIRL.
3. The bundled China domain/IP MRS providers: DIRECT.
4. Everything else: SWIRL.

The SWIRL select group contains the saved nodes. The built-in GLOBAL group is
explicitly constrained to SWIRL so global mode follows the same chosen node.
Direct mode uses Mihomo's direct outbound. Necessary local bypasses are retained
in Windows system proxy configuration.

China providers are pinned to MetaCubeX/meta-rules-dat commit
`83c8208bdfae92b1caaa29745f51f233b6f1847e`, with GPL-3.0 notices and SHA-256 hashes
in `packaging/rules`. Startup verifies and copies both providers into the private
session directory. Missing or changed data fails visibly; no empty-rule fallback
or runtime geo download is used. Provider updates arrive with application updates.

Internal Mihomo DNS resolves foreign domains through DoH via SWIRL. Node bootstrap
and domestic direct DNS use the existing system resolver. This internal resolver
does not change Windows DNS or install a DNS listener.

The rules page displays the actual generated order. The connections page polls
the authenticated engine for active flows, including target, rule, byte counts
and named outbound chain. Credentials and API secrets are not exposed to QML.
Unavailable latency, rule-hit counters and unimplemented export/termination
actions remain explicitly unavailable.

## UI and icon changes

Page transitions use a 180 ms crossfade with at most six logical pixels of
vertical travel. Cached page trees preserve input, drafts and scroll positions.
Rapid clicks retire older outgoing pages; reduced motion settles immediately.
Card navigation no longer waits for a texture grab or expands a shared image.
Sidebar selection and button springs remain native Qt animations.

Popup closure now walks guarded QPointers: closing a popup can synchronously
destroy descendants, making the former raw traversal unsafe. This fixes the
offscreen animation-test crash during navigation after dialog dismissal.

The executable and installer use the existing plate-free knot mark SVG, with
transparent multi-size ICO frames and a larger 88% maximum canvas occupancy.
The installed window uses the same ICO. A new Swirl-specific icon filename updates
its own installed shortcuts without clearing global caches. AppUserModelID remains
`SOLHK.Swirl.Desktop`. Existing pins targeting a different old installation may
still need the user's repinning; unrelated shortcuts are not modified.
The installer also stamps that AppUserModelID on its own desktop/start-menu
links using a guarded helper. It verifies the link's existing target before
updating the icon/property and notifies Explorer for that item only.

The antialiased one-physical-pixel window contour has stronger theme-aware
contrast. Radius, desktop acrylic material and HDR composition are retained;
maximized windows suppress the decorative contour.

## Validation boundaries

Automated transport fixtures remain controlled data. They are not public-network
acceptance. `SwirlAcceptance` is a local-only test driver, built only with test
support, which loads an encrypted **copy** under the current Windows account. It
is not installed. Private subscriptions/configuration files must never enter CI,
Git or artifacts.

The opt-in `SwirlSystemProxyTests` exercises real current-user WinINET changes,
normal restoration, external edits and abrupt owner/engine death. It is excluded
from normal CTest/CI unless explicitly enabled to avoid changing unrelated runners.
Normal CTest covers engine, node, import, UI, motion, page and HTTP capture checks.

Rendered DPR tests use per-process Qt scale overrides; they do not change the
user's Windows display settings. They verify the native GPU rendering path at
100%, 125%, 150% and 200%, not physical multi-monitor changes or HDR display output.

Public browser acceptance requires visible Google home/search pages and actual
YouTube playback advancing continuously for at least 30 seconds, together with
matching engine flows. HTTP success, a video-page title or an API health read is
not sufficient. Outstanding browser-tool limitations must remain explicit in
the delivery report; this PR does not claim that those checks passed.
