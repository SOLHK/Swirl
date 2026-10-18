# INI profile import, forwarding and atomic updates (2026-10-18)

The Qt product can now execute a closed complete INI profile containing `[Proxy]`, manual `select` groups in `[Proxy Group]`, and ordered `DOMAIN`, `DOMAIN-SUFFIX`, `DOMAIN-KEYWORD` rules ending in an explicit `FINAL`. The normalizer preserves the source document (with the existing outer-whitespace normalization) separately from the validated execution mapping. Importing the node catalog, rules, group IDs and original profile uses the existing single DPAPI/QSaveFile transaction. Unsupported sections or fields never become a node-only import.

A downloaded synthetic INI subscription now runs through Qt into the Rust data path. Independent local SOCKS5 exits verify group B is used despite global node A selection, DOMAIN localhost is rejected without forwarding, a successful download through an active Rust proxy cannot replace active state, a reordered refresh retains B, deletion switches to remaining A, and rename/reload reaches A with a new identity. Invalid profiles, HTTP failures and over-budget rules preserve the previous catalog and configuration; negative profile cases preserve ciphertext byte for byte. Existing write-failure/stale-plan regressions remain in the full suite.

For a new manual group Swirl uses its first declared member. Refreshing the same provider and same group retains the previous still-valid choice; an explicit source default takes priority. Another provider cannot inherit that choice. A removed member falls back to the first declared remaining member. A rename creates a new ID; an unchanged source/name/protocol retains its ID. These are stated Swirl semantics, not a claim to reproduce another client's saved UI state.

The accompanying transport fix closes a reproduced INI security bug: `transport=reality` without its required public key is rejected instead of becoming ordinary TLS. REALITY with a key retains its marker and remains unexecutable until the native protocol is implemented. TCP/WS/obfs aliases use a shared conflict check independent of field order; contradictory TLS/REALITY security modes fail closed. The execution test includes a valid plain-TLS configuration control and proves no connection starts for REALITY. This does not claim a successful TLS or REALITY handshake.

## Validation

- Full Windows application build passed. Qt/Rust integration: 43 passed, 0 failed, 5 external-peer hooks skipped in the standalone suite.
- Native and compatibility import-boundary suites both passed. Independent WebSocket/WSS tests: 11 passed; independent Shadowsocks/Loon tests: 9 passed (including their Qt hooks).
- Development guards: 19 run, 1 pre-existing Windows symlink-permission skip. Native code-page execution avoids an observed UTF-8 decode exception from a Windows command; original diagnostic log is retained.
- Initial missing INI execution and REALITY downgrade were both reproduced by failing tests before fixes. Subsequent test failures (source outer whitespace, synthetic UUID misuse, redundant default selection) were diagnosed and fixed without removing assertions, raising timeouts or weakening safety.
- Exact prior implementation `5f1fd1347ba4f82854e3f773f90e093c3074ce40` has successful Windows/Linux/macOS Rust CI39114652890 and implementation CI39114652905; `SUBSCRIPTION_TYPED_OPTIONS_20261018_VERIFIED.json` binds its source hashes. This does not count as CI for the current patch.

Structured current-source/log hashes: `evidence/INI_PROFILE_TRANSACTION_20261018.json`. Current implementation commit/CI will be bound after push. Local static review: `D:/Codex/outputs/INI_PROFILE_REVIEW_20261018.md`; review is not a test run.

## Remaining scope

General/DNS sections, remote rules, automatic INI groups, IP/process rules in this INI subset, full Quantumult X and sing-box profile semantics remain rejected. Only document-declared groups and explicit DIRECT/REJECT are rule targets. Qt's existing 1000-rule cap is unchanged. This stage does not claim all client formats or the 18 real cached complete profiles pass; the existing 0/18 complete-profile acceptance and 10.83% weighted overall acceptance remain unchanged. No supplier refresh or real-node connection occurred in this stage. The Rust standalone inspector has not gained this Qt product profile mapping.

The new authorized unlimited source remains safely captured: one request, HTTP200, 59 VLESS/TCP/REALITY nodes, 55 requiring Vision. Native REALITY is the immediate next protocol task. Independent R0 authentication and R1 key-exchange work remains isolated until TLS transcript, authenticated certificate/Finished, fingerprint semantics, independent peer interoperability and product integration are proven. Never drop REALITY/Vision to get a successful connection. The old 08:25 window is definitively 0 requests/0 new saves and must not be retried.

## Sources and continuation

The mapping was independently implemented against the existing Swirl validators and the Loon manual's [manual groups](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/policygroup.md), [domain rules](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/domain_rule.md) and [FINAL rule](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/final_rule.md). No converter/proxy implementation was copied and no dependency was added to Swirl in this stage.

Continue on `work/core-completion-20261017`, single source writer. First bind this implementation's exact CI, then continue REALITY TLS integration and independent interoperability for the actual new-source requirements; preserve fail-closed product capability until tested. Font work is queued separately in `D:/Codex/outputs/QUEUED_FONT_TASK.md` for after subscription work; it has not started.
