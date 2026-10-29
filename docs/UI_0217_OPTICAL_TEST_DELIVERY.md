# Windows optical cloud-knot adjustment

The user rejected the canonical taskbar raster's visual weight even when its
bounding width matched ChatGPT. A wide mark has less visible area than a round
mark within the same square icon slot; matching width alone is insufficient.

The approved correction keeps the central original coordinates and all vertical
coordinates. Control-point X coordinates below 350 or above 650 tuck inward by
22 percent around those boundaries. Aspect-fit rasterization then enlarges the
central knot and its visible area while retaining a horizontally wide silhouette.
No stroke is added. The original colors, gradients, five ribbon paths, artwork
transform and in-app `assets/brand/swirl-symbol.svg` remain unchanged except for
the explicitly adjusted Windows path coordinates.

All 18 native ICO sizes, EXE resources, runtime QIcon frames and the owned shell
shortcut use the same Windows master. The new `Swirl-brand-0217-optical.ico`
resource path prevents the shell from reusing the previous canonical alias.

Native taskbar screenshots, physical 100/125/150/175/200 percent scale checks,
button interaction and package evidence must be renewed for the final source.
An icon raster or compile pass alone is not runtime acceptance.

The latest delivery instruction is **test only**. Do not push, delete or recreate
main, and do not change its protections or default-branch settings.

The pre-existing Vision inner-TLS HelloRetryRequest limitation is separate from
the UI/icon work. The production inspector deliberately rejects its direct-mode
handoff. Keep the failure evidence and original security assertions; do not
change Rust forwarding or bypass TLS checks to pass this delivery's CI.
