# Activity system proxy action

The user's 2026-10-24 follow-up changes the Activity toolbar capsule from node-page navigation to a direct system proxy switch. The existing toolbar placement, window/sidebar contours and sizing constraints are retained. The frozen Main.qml guard authorizes only the exact capsule replacement, not arbitrary edits to the window.

`SwirlSystemProxyCapsule` displays **开启系统代理** or **关闭系统代理** from the observed Windows setting. Pending work disables repeated requests. Read/operation errors remain visible through the warning state and detail. Clicking invokes `EngineController::toggleSystemProxy()` and does not change the current route.

Enabling reuses the established Rust engine selection/configuration, healthy runtime and actual loopback-listener checks before the Windows adapter writes settings. A stopped engine starts the saved selected node first. An absent usable node remains an error; it does not silently become DIRECT or open the node page.

The explicit off action first releases Swirl's recovery lease, then sets Windows to direct mode and disables manual proxy, PAC and automatic detection. Observation includes all three modes. This also works when another application configured the current proxy. It leaves the Rust runtime intact. Ordinary application exit, disconnect and the Settings page's release action retain their original snapshot-restoration behavior.

Local motion tests inject a controller only into the real capsule and exercise enable, disable, busy, error and unchanged-route behavior. They assert that the real host proxy snapshot is unchanged. Appearance tests observe the actual host status without clicking the live switch.

Actual Windows setting mutation tests run only in the explicitly opted-in disposable CI step (`SWIRL_SYSTEM_PROXY_TEST=1`). The new tests cover external manual/PAC settings, PAC-only and automatic-detection observation, Swirl-owned takeover, explicit off, journal removal and release-after-off. The real UI test also starts the saved node from a stopped runtime, verifies actual settings and stays on Activity. Existing recovery/abrupt-exit tests remain. These tests are not run on the user's current Clash/network configuration. Current-stage GUI and final CI outcomes are recorded with their corresponding source SHA in the delivery evidence.
