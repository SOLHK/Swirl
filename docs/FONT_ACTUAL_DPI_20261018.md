# Actual Windows DPI validation and retained failures — 2026-10-18

The user manually changed Windows scaling on one display. The tested application build was `669f425537868589fe1e7e7798ea241d092aef16`; no application rebuild occurred between these actual-scale stages. Resolution stayed2560x1600 and refresh stayed120Hz. Each stage checked documented Windows effective-DPI/scale readings and the isolated Qt window DPR, with no Qt scale environment override. The existing installed application and original local font were unchanged.

| Actual Windows scale | Effective DPI / Qt DPR | Representative pixel cases | Settings captures | Additional findings |
| --- | --- | --- | --- | --- |
|125%|120 /1.25|9 passed,0 failed; max delta0|2/2|First parent-translation alignment assertion failed;3 isolated rechecks passed. Original failure retained, cause unproven.|
|100%|96 /1.0|9 passed,0 failed; max delta0|2/2|Translation, scale restoration and idle checks passed.|
|175%|168 /1.75|9 passed,0 failed; max delta0|2/2|Translation, scale restoration and idle checks passed.|
|200%|192 /2.0|8 passed,1 failed|2/2|72pt maximum-axis case had one channel delta3 above tolerance2. Parent-translation assertion also failed. Scale restoration and idle checks passed.|
|150% restored|144 /1.5|One minimal restoration sample passed, delta0|2/2|Actual2560x1600/120Hz restoration verified before and after the check.|

The nine representatives cover9/16/72pt, true axis boundaries, a half-physical-pixel placement, and the11/12pt thin/narrow/tall overshoot cases. Large samples use bounded viewport tiles. Each settings capture used1100x700 logical pixels and its recorded pixel dimensions matched the actual DPR. These are new isolated windows at each actual Windows scale, not proof of a single live window changing DPI or a cross-monitor transition. App renders are not physical-panel sharpness measurements.

## Retained failures and low-cost diagnosis

At actual200%, the failing72pt case used wght900, wdth120 and HGHT1000. In tile0 at physical window pixel(60,721), the live RGB values were(102,102,102), whereas the independently painted reference was105. The channel tolerance remains2. This failure was neither removed nor cleared by rerunning the actual-scale stage.

A test-only diagnostic build subsequently saved the preview's unmodified native raster and observed afterAnimating timing. Four bounded runs were performed with the real system restored to150%: simulatedDPR1.25 with seven contextual cases, simulatedDPR2 with seven contextual cases, simulatedDPR2 with only the failing case, and actualDPR1.5 with that case. The twoDPR2 runs reproduced the same pixel and values. Live window output matched the preview's native raster exactly (maximum delta0), including gray102 at the failing pixel. Native raster versus independent reference retained the one-pixel delta3. Thus the reproduced discrepancy already exists at raster/reference drawing, rather than being introduced by scene graph composition. Its precise rasterization/translation/reference cause remains unresolved; this evidence does not establish a font-outline defect or justify changing the font or tolerance.

The two historical parent-translation failures also remain unresolved. They observed alignment after a fixed25ms wait, without recording whether an afterAnimating pass had happened. The four instrumented runs all aligned successfully; one first pass arrived at24.5491ms and was observed at25.0613ms. Another nominal25ms wait actually returned at34.2013ms. This shows synchronization risk and narrow timing margin, but does not prove the cause of the historical failures. No production timing/rendering behavior was changed to force a pass.

At the user's quota stop, instrumentation source, patch and runnable test binary were preserved locally. Only those uncommitted instrumentation edits were removed from the repository; the public application source remains unchanged. All raw first-failure logs, captures, native-raster diagnostics and rechecks remain available locally. No full matrix, performance optimization or new font modification was started.

## Handoff and boundaries

The retained runnable review application remains the previously verified669f425 build. Its two CI workflows completed successfully. This report is a separate documentation-only commit; it must not inherit that commit's CI status. New CI can be inspected separately without delaying the local result.

Private evidence is under the local font-optimization directory: `reports/manual-system-dpi-20261018/` (per-scale results, restoration and pixel coordinates), `reports/font-layer-diagnostics-20261018/runs.json`, and the corresponding raw `screenshots/` directories. The diagnostic patch and frozen test binary are retained separately. No font binary, glyph bitmap, screenshot, private path or machine identity is attached to this public report.

Outstanding: identify the raster/reference delta3 cause; obtain decisive frame-synchronized evidence for the historical translation assertions; validate a single live-window DPI transition/cross-screen behavior if needed. Stable240fps axis updates remains unpassed from the earlier measurement stage. Historical acceptance percentages and the independent core-progress figure are unchanged. System fonts, registry mappings, the installed app, proxy protocols and subscriptions were not changed.
