# Subscription source semantics and document target isolation

Continue on `work/core-completion-20261017`. This stage follows implementation `ed2f87fb56f704b365a392b691bd138995273867`; its exact three-platform CI [39109242589](https://github.com/SOLHK/Swirl/actions/runs/39109242589) and core validation [39109242588](https://github.com/SOLHK/Swirl/actions/runs/39109242588) finished successfully. That CI did not cover the rule-alias defect described below. Current follow-up source is identified by the implementation commit and source hashes in the companion evidence/checkpoint after validation.

## Corrected behavior

Qt adapters previously discarded INI sections outside the node list and sing-box root fields/policy outbounds. They now retain the source document/object in the parser result, label its dialect, and reject application when that whole profile has no executable mapping. This is in-memory preservation followed by atomic rejection; it is not a new persistent archive for rejected GUI inputs and does not claim full INI body grammar validation. Pure node exports remain supported. Existing authorized encrypted capture files are unchanged.

The INI envelope now validates section syntax, duplicate sections, limits, missing sections and control characters. UTF-8 must be complete and valid before trimming. JSON duplicate-key validation applies to sing-box even through Base64, STATUS and BOM wrapping. Repeated BOM is rejected. The existing YAML parser's single-document API silently ignored later documents; the adapter now parses the complete stream and requires exactly one document. Legal single-document YAML flow arrays remain accepted.

Independent parent review found `MATCH,SWIRL` in an imported Clash document could use Swirl's global selected-node alias, potentially from another subscription. A cross-subscription regression reproduced acceptance before the fix (`normalizer-policy-red.log`: 1 failure). Import transactions now allow rule targets only from their own declared groups or explicit DIRECT/REJECT. The existing native rule editor's SWIRL meaning is unchanged and remains tested. Foreign IDs/names, GLOBAL and SWIRL are rejected without changing encrypted bytes, selected node or network settings.

The first executable Clash profile still requires an explicit terminal MATCH and disallows unsupported root globals/DNS. This is a bounded profile, not complete subscription compatibility. No new proxy protocol, TUN path or provider-network acceptance is claimed.

## References and review

Behavior references: [sing-box configuration structure](https://sing-box.sagernet.org/configuration/), [official Quantumult X sample](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf), [official Surge guide](https://manual.nssurge.com/book/understanding-surge/en/), and the vendored fkYAML `deserialize_docs` API. These sources distinguish global semantics from outbound nodes; no implementation was copied and no dependency was added. Surge and Quantumult X documentation are treated as proprietary reference material. The existing fkYAML 0.5.0 MIT dependency/license is retained; no third-party proxy engine is invoked.

The [sing-box repository license](https://github.com/SagerNet/sing-box#license) states GPL v3-or-later and an additional naming/association restriction. Only configuration behavior was studied; no source was imported.

Read-only independent review found the truncated UTF-8, double-BOM and multi-document paths; all received targeted fixes and regressions. The reviewer did not run tests. Parent review found the rule alias issue; root reproduced and fixed it. Final test counts and hashes are in the companion evidence after the executable checks finish.

## Subscription status and remaining scope

See [18-entry matrix](SUBSCRIPTION_18_ENTRY_MATRIX_20261018.md). The new capture has 18 parsed entries, 1558 records including duplicates, and zero new real-node attempts. It contains three protocol types, not six: SS 720, Trojan 720 and VLESS 118. The two VLESS exports share one acquisition URL and contain the same 59 records.

Historical strict HTTPS success belongs to manifest entry 7 (Shadowrocket label; immutable old remote #9) and entry 15 (Loon old local cache), three sample records each. Historical cache enumeration 8 is not manifest entry 8. These are not a claim of six independent servers or new-window success.

The parent reported automatic approval review rejected a newly requested real-node sampling action pending clearer scope approval. No new real-node request is made in this stage. Offline analysis, source changes and isolated synthetic peers continue. Supplier refresh remains prohibited after the original cutoff.

The 79-item acceptance denominator and six accepted items remain unchanged; 10.83% is the declared weighted acceptance figure, not code completion. Protocols already implemented but lacking all acceptance gates remain partial, not unimplemented.

Next: verify this follow-up's exact CI; implement explicit DNS query-family policy before attempting the researched limited Clash DNS profile. Do not map Mihomo respect-rules to Qt force_proxy_hosts or ignore bootstrap/hosts/IPv6 differences. Preserve the fail-closed DNS boundary until independent peer and transactional tests support it.

## Final local checks before implementation commit

- Native Windows application and Qt test targets built using the existing Qt 6.10.3/MinGW toolchain.
- Native Qt: 37 passed, 0 failed, 5 external-peer hooks skipped in the standalone run.
- Four independent local-peer suites passed: SS/Loon SS, VLESS, SOCKS4/4a and VLESS WebSocket; these supply the skipped hooks.
- New native parser-boundary target: 5 passed including setup/cleanup; CTest native+boundary 2/2 passed in 9.31 seconds.
- Compatibility import regression selection: 13 passed, 0 failed.
- Development helper checks: 18 passed, 1 existing symlink-privilege skip; no security checks or timeouts relaxed.
- `git diff --check` passed. The parent-reported selected-alias defect's original failing log is retained.
- All generated artifacts and test settings reside under D:/Codex. No drivers, proxy settings, user installation or provider endpoints were changed. The preceding stage's appearance/storage tests are prior evidence, not rerun claims for this stage.

Exact final logs use `normalizer-acceptance-*` and `normalizer-peer-*` under D:/Codex/work. CI for this implementation must be checked after its push; ed2f87f's green CI is not its result.

## Final implementation and exact CI

Implementation: `fbef3993e9decc68c8be93a17551536ea9013fd8`. [Rust Core 39110589656](https://github.com/SOLHK/Swirl/actions/runs/39110589656) succeeded on Windows, Linux and macOS; [core validation 39110589665](https://github.com/SOLHK/Swirl/actions/runs/39110589665) also succeeded. Windows includes the added native import-boundary CTest plus native Qt/storage and four independent Qt protocol-peer suites. This confirms this implementation's checks, not all-protocol or real-corpus acceptance.

[Verified evidence](evidence/RUST_SUBSCRIPTION_BOUNDARIES_20261018_VERIFIED.json) binds the exact source, local binary/log hashes, original red regression, CI jobs and final offline replay. [Replay evidence](evidence/SUBSCRIPTION_18_ENTRY_REPLAY_FBEF399.json) binds all18 cached entries to the same source's Rust tree and inspector binary; default redacted output only, no provider/node requests, no plaintext files. All18 counts match the prior report.

A transient Windows exec transport disconnect recovered before any further mutation. The interrupted command never started. Source hashes remained correct and no orphan build/test process remained; the user's existing Swirl process was left untouched.
