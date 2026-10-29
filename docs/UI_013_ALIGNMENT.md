# 0.1.3 window and activity alignment

Baseline: `0b15f777d564a2edc778b69abb4cf5c74ea376d2`, including its latest floating sidebar transmission and shadow.

The window contour and sidebar now share a 16-DIP radius. The radius stays independent of content zoom; Qt applies screen DPI scaling. Maximized and full-screen windows retain square outer corners. Sidebar position, material, shadow and navigation motion are preserved.

Activity section titles retain their 34-DIP capsules, with symmetric vertical padding and explicitly centered text and chevrons. All three sections leave 10 DIP between the title capsule and the first statistics separator. The today/month selector is vertically centered against the same title row.

The user's follow-up requests the sidebar selection style for all buttons. Shared button and capsule backgrounds now use the same neutral fill without gradients or raised shadows. Standard buttons, icon buttons and combo boxes use pill corners; segmented controls default to rounded corners. Switch thumbs and sidebar selections have no raised shadow. Primary actions retain accent text, destructive actions retain red text, and switches retain their checked-state color. Hover, pressed, focus, disabled and motion behavior remain. Floating menus retain their readable surface fill; window/sidebar elevation and card layout remain in place.

Primary reference consulted before implementation: [Qt's Button implementation](https://github.com/qt/qtdeclarative/blob/dev/src/quickcontrols/material/Button.qml) and the installed Qt 6.10.3 Fusion Button.qml. The existing Qt Controls content/background and padding model is retained; no external code was copied.

Version sequence requested by the user: 0.1.2 baseline, this update 0.1.3, then 0.1.4 and onward. Completed updates must be committed and pushed to GitHub.

Validation: the updated Qt application builds; `swirl-appearance-ui`, `swirl-all-pages` and `swirl-motion` pass after the flat-control changes. Light/dark activity and dark settings captures were inspected at DPR 1.5. Native window-radius checks pass with a 16-DIP/24-physical-pixel contour, including resize, content zoom, maximization, full screen and restore; no bright pixels leaked beyond the tested corners. The appearance check intentionally displays a magenta right-page fixture for 250 ms to detect sidebar contamination. That check is compiled only when UI tests are enabled; production delivery uses `SWIRL_BUILD_UI_TESTS=OFF`.

UI render checks do not establish real proxy or private-node acceptance. Final visual acceptance remains with the user.
