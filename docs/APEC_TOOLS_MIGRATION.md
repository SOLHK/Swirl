# APEC tools and dynamic modules migration

This record covers the **14 owned page source files** below. `FeatureModulePage` is the shared editor for the **32 current `feature-*` routes** in `FeatureCatalog`; it is not 32 independent implementations. The application's 61-route smoke belongs to the integrated run and must not be inferred from this file count.

## Current stage and constraints

The parent-controlled Qt 6.12.0/GCC 15.1 motion-stage build and isolated interaction gates passed before visual migration. All **14 visual replacements are now applied to the real page source files**, after the motion-source SHA-256 guard matched. The visual source is frozen for the next integrated build and runtime/visual verification; the new visual layout is **not yet runtime accepted**. No new QML component, C++/Rust implementation, network service, configuration setting or build target is introduced by this batch.

The implementation uses the existing `SwirlArcMotion`, `SwirlTransitionCoordinator`, `SwirlFlow`, `SwirlAnimatedModel`, shared controls and guarded dialogs. It retains page-host caching and font startup fences. Arc feedback belongs to reading labels/empty states; controls, text editors and tables keep fixed hit regions. List priority changes retain their actual source/target motion. Hidden-page and Reduce Motion settlement use existing primitives. The Inspector expansion observes the whole page only after component completion, avoiding a `visible`/coordinator cycle.

## Per-page changes and verification

| Source page | Motion and real operation | Visual replacement applied | Verification status |
| --- | --- | --- | --- |
| FeatureModulePage | Reversible configuration/entries/information arc; real local draft add, edit, delete, enable-intent and reorder; startup restore completion fence | Shared page header, open form surface, compact priority rows, explicit service-not-connected status; preserves draft load/save/JSON import/export | Motion-stage native operation checks passed; visual rerun pending |
| ExternalToolsPage | Six real source tabs, grouping/search and count arc; no table hit-region motion | Header plus group rail and data workspace; retains capture start/stop, MitM control gate, clear, refresh and proxy-control navigation | Motion-stage route-load smoke passed; operation/visual rerun pending |
| ProfilesPage | Stable incremental saved-profile list and existing guarded editor/dialog lifecycle | Header actions, active profile line, compact table and explicit apply/remove actions | Motion-stage cached navigation passed; visual rerun and save/import/export/apply regression pending |
| ModulesPage | Stable-ID animated model for install/remove/priority moves; real toggle remains engine-state-gated | Priority-ordered compact rows, keyboard-accessible row selection, install action and shared tokens | Motion-stage cached navigation passed; visual rerun and real module mutations pending |
| ScriptsPage | Real worker busy/error/output drives `SwirlFlow`; saved script list updates incrementally | Saved-script workspace and named editor actions; retains JSON input, source, highlighter, result/error and worker execution | Motion-stage Input68 actually saved/ran a local JSON worker script; visual rerun and error/timeout cases pending |
| InspectorPage | Reversible waterfall expansion; filter/selection retained; listens to page visibility after completion | Request workspace and truthful absent-timing state; placeholder HAR/record actions explicitly unavailable | Static parser checked; expansion/filter native check pending |
| CaptureInspectorPage | Actual session filters/selection and request/response tab arc; listening status uses actual provider state | Single capture workspace, compact listening rail, session table and detail reader; preserves stop/clear/HAR export and size/redaction copy | Static parser checked; real capture/HAR regression pending |
| ToolboxPage | Actual measurement state drives flow; custom tool choice arc; execute stays unavailable for unconnected tools | Explicit HTTPS/ICMP/DNS readings, external IP/network type and compact custom tool editor | Static parser checked; controlled measurement check pending; no real-network claim |
| ApiPage | Local tabs actually switch; interface path/method remain local; `implemented=false` | Interface/log/permission-specific empty states and local request draft; send remains unavailable | Motion-stage native local tab assertion passed; visual rerun pending |
| WorkbenchPage | Local feature selection arc and completion-fenced reset; `implemented=false` | Function list with separate per-function local editing buffers, explicit not-connected state | Static parser checked; local selection/buffer check pending |
| AutomationPage | Local task/history/conditions tabs actually switch; `implemented=false` | Trigger/action draft and real-empty task/history surfaces; save/run remain unavailable | Motion-stage native local tab assertion passed; visual rerun pending |
| BreakpointPage | Local request-header/body/query tabs with independent editing buffers; `implemented=false` | Honest empty pause queue and fixed request-draft editor; continue/drop remain unavailable | Static parser checked; local buffer assertion pending |
| MapPage | Local/remote tab arc with separate form buffers; `implemented=false` | Mapping list empty state and local match/target preview; save remains unavailable | Motion-stage native local tab/buffer assertions passed; visual rerun pending |
| ReplayPage | Actual local history selection fills draft only; four independent request-section buffers; `implemented=false` | Request history and fixed local editor, truthful absent response, reversible tab reading feedback; send remains unavailable | Motion-stage native local tab/buffer assertions passed; visual rerun pending |

## Inherited interaction review

All 14 corresponding files in `D:/Codex/work/Swirl-apec-v3-20261027/work/inherited-ui-20261027` were inspected by a function/provider-call inventory and focused source reads. Search/filter interactions for saved profiles, scripts and modules, and the explicit network-type refresh were retained in the applied visual source. Their old visual layout was not copied wholesale. The retained inventory is `work/tools-migration/inherited-interaction-audit.json`. The network refresh is additionally fenced by component completion before observing page visibility.

## Evidence and limits

- Qt 6.12.0 `qmllint` was run against the 14 motion sources. The retained output is `work/tools-migration/motion-lint.txt`; no `Error`, `Unexpected token` or `Syntax error` was found. Existing context-provider/unqualified dynamic bindings and Qt's transform/layout false positives remain warnings. This is not a clean-warning or runtime pass.
- The 14 visual replacements were statically parsed both in the draft directory and after application to the source tree. The retained outputs are `work/tools-migration/visual-drafts-lint.txt` and `work/tools-migration/visual-source-lint.txt`; neither contains parser errors. Dynamic window/context types remain a static-analysis limitation; integrated qmlcachegen/application verification of the visual batch is still required.
- The first integrated compiler run exposed an extra semicolon after a QML object-valued `transform`; the three affected owned pages were corrected, then all 14 owned sources were rescanned. The failed first run remains in the parent's build evidence.
- Parent-controlled native verification must use an existing absolute `SWIRL_TEST_ROOT` and built-in test isolation. This batch did not run another GUI, access private subscriptions, change proxy/TUN/routes/DNS or claim provider/network acceptance.
- Physical GPU/high-refresh/60/120 Hz, all-DPI visual acceptance, screen-reader acceptance and final installer/source identity remain outside the static checks above.

## Motion-stage native evidence (before these tool visual layouts)

- `work/build-pages/core-visual-tools-motion-smoke.log`: 61-route smoke, exit 0, elapsed 13,212 ms; evidence `work/build-pages/evidence-20261027-040943`.
- `work/build-pages/core-visual-input68.log`: native interaction suite, 68 checks / 0 failures, exit 0, elapsed 28,154 ms; evidence `work/build-pages/evidence-20261027-041045`. It actually saved and ran a local JavaScript worker with JSON input.
- `work/build-pages/tool-page-native-result.txt`: exit 0. `work/build-pages/tool-page-native/navigation-report.json`: 308 checks / 0 failures, DPR 1.5, native shell handle unchanged. The tool-specific checks used actual tab input, two real local module entry forms, reorder and unsaved restoration, plus API/Automation local tabs and Map/Replay independent editing buffers while `implemented=false`. The 308 total also contains broader cached-navigation checks; it must not be relabelled as 308 tool-only checks.
- These passes accepted the tool **motion/local interaction** batch. They do not automatically accept the subsequently applied tool visual layouts, physical GPU performance, every DPI or real network services.

## Stable native interaction selectors

`moduleSections`, `moduleSectionMotion`, `moduleAddButton`, `moduleEntryName`, `moduleEntryValue`, `moduleEntryConfirm`, `moduleSaveButton`; `apiSection-<original tab>`, `automationSection-<original tab>`, `mapSection-<original tab>`, `mapDraftMatch`; `replaySection-<original tab>`, `replayDraftEditor`. Applied visual sources retain the same original page state strings and selectors.
