# Swirl UI V2 skills audit — 2026-10-24

Scope: stage 1 read-only source audit. No Swirl source edits; no package/framework dependency added.

## UI UX Pro Max

- Existing project skill: `D:/Codex/work/Swirl-ui-v2-20261024/.agents/skills/ui-ux-pro-max/SKILL.md` (same content as the 0.2.3 source checkout).
- Existing file Git blob: `b31974d1afba697bc685a74f0fb6e904e9614d73`; SHA-256: `E5BAF9400D4347E5ED3EB1F6B99CD0B9BA545B8B0E507AABB2B87397BBF73EA1`.
- Last repository change to this file: `a325e8663547bf674e7836dcba0f17375f9e251e`.
- Official upstream inspected: [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/d14efff8ed1faa4187f004f79926f428c8074ec7), current main SHA `d14efff8ed1faa4187f004f79926f428c8074ec7` at audit time. Current official SKILL.md uses separate references; the existing project copy is not byte-identical. No replacement or duplicate installation performed.
- Read the complete existing SKILL.md. Executed its local search tool with `rapid animation interruption --domain ux -n 3`. The first result is Cancellable State Transitions: semantic selection state must be set independently of animation completion; rapid changes replace prior motion safely. Remaining results cover avoiding decorative infinite loops and honoring reduced motion.
- Applicable: keyboard/focus and Esc behavior; useful accessible names; semantic theme tokens; compact sortable/virtualized lists; persistent search/navigation state; asynchronous feedback; progressive disclosure; interruption-safe transitions.
- Boundaries: there is no Qt stack in its 22-stack table. React/GSAP/HTML examples, mobile touch/safe-area sizes and CSS APIs do not authorize a different framework or override current desktop geometry. Apply semantic UX principles using existing Qt controls.

## Motion Design

- Official source: [LottieFiles/motion-design-skill](https://github.com/LottieFiles/motion-design-skill/tree/f9a8a041b85185ee4881b3471d3415e939aac772/skills/motion-design).
- Fixed source SHA: `f9a8a041b85185ee4881b3471d3415e939aac772`; declared skill version 1.0.0; MIT license.
- Installed with the existing skill-installer helper to `D:/Codex/skills/motion-design`, avoiding C-drive payload storage. Installer temporary files were directed to `D:/Codex/tmp/swirl-ui-v2-skills-audit`.
- SKILL.md SHA-256: `8729ECBC7E5736C1295BAAA8BA0384BB4B1AAC9CF91B83FCDC64D9548A57BB19`.
- Read the complete SKILL.md plus `director/context-adaptation.md` and `reference/quality-checklist.md`.
- Applicable: functional intent; consistent duration/easing tokens; entrance deceleration and exit acceleration; subtle spatial/scale feedback; shorter exits; bounded stagger; reduced-motion alternatives; actual frame-time measurement.
- Boundaries: the instruction to always add three motion layers and ambient effects conflicts with the user's preference against expensive ornament and the existing focused product UI. Do not add ambient animation to satisfy a count. Browser-oriented GPU/element-budget claims are guidance, not Qt performance evidence. Do not lengthen the existing responsive page transition to 400–600 ms merely to match a table. Do not introduce Lottie/web frameworks for native QML motion.
- Availability: installed payload is readable now at the absolute path above. This custom D-drive destination is not the current automatic global skill-discovery directory; record the path in the stage handoff rather than claiming it has been globally registered or making an unsolicited copy.

## Applied to the current baseline

`src/Swirl.Quick/qml/SwirlMotion.qml` already centralizes motion tokens, spring parameters, OS/manual reduced-motion policy and popup trigger origin. Existing values include press 80 ms, release 140 ms, selection 220 ms, page 190 ms, dialog 220 ms and exit 160 ms. Phase 2 should reuse this singleton and audit consuming components for interruption and focus behavior, instead of replacing it with a new animation system. These source observations do not establish measured 60 FPS.

Python used successfully for the local search and installer: `C:/Users/sysfr/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`. The `python` command resolves to a Windows Store placeholder; no Python installation was needed.

Hallmark and Qt AI Skills are already installed and are audited by the parent agent; they were not duplicated by this subtask.
