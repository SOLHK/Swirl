# v0.1.9 automatic profile scope and restricted INI mapping

The user's October 24 follow-up confirms that node-only Surge, Loon and Quantumult X subscriptions now connect. Those node conversions are retained. A node document must not replace the user's DNS, rules or groups with empty defaults. An unsupported complete profile may yield an explicitly reduced nodes-only result only after the entire document passes an independent safety audit; the first reported projection error is not a safety verdict.

## Primary references consulted

- [Surge managed profiles](https://manual.nssurge.com/profile/managed-profile.html): embedded update URL, interval and strictness.
- [Surfboard managed config](https://getsurfboard.com/docs/profile-format/managed_config/): header position and client-specific update restrictions.
- [Surge general settings](https://manual.nssurge.com/profile/general.html) and [Loon general settings](https://nsloon.app/en/docs/General/): DNS transports, connectivity checks and host-network options have distinct meanings.
- [Quantumult X's upstream sample](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf): local server tags, static policies, filters, resolver flags, concurrent system DNS and encrypted-resolver precedence.
- [Surge automatic groups](https://manual.nssurge.com/policy-groups/url-test.html): scoring and refresh semantics differ from the current native engine. They are not silently mapped to a different strategy.

These are schema/behavior references. No private provider content or source implementation was copied.

## Applied and preserved data

Portable Rust validates the complete original INI document. Surge/Loon/Surfboard local nodes, explicit supported DNS/hosts, manual groups and supported rules retain the previous projection. Quantumult X now has a separate grammar: `[server_local]` tags, `[policy] static`, `[filter_local]` host/suffix/keyword/IP/final rules, `[dns] no-ipv6/no-system/server/doh-server/address`. Its built-in `proxy` becomes a manual group containing only this document's local nodes, never an unrelated saved node or DIRECT.

Only explicit declared plain resolvers with `no-system` can replace Quantumult X DNS. Without it, Quantumult X concurrently adds current-network resolvers, which the native projection cannot reproduce. DoH suppresses unbound plaintext resolvers according to the upstream format; those resolvers are not a plaintext fallback. Bootstrap, certificate validation and source transport checks remain strict. Unsupported domain-reject DNS synthesis, automatic scoring, domain-conditioned/SSID-conditioned DNS, dynamic resources, scripts and other unmatched semantics are not represented as successful complete-profile execution.

Managed headers and selected client-only settings are validated and retained in the encrypted original. The returned `importMetadata` contains fixed flags and fixed key names; it contains no embedded URL, token or setting value. `managedConfig` records `embeddedUrlPreserved=true`, `embeddedUrlApplied=false`, the declared interval and strictness. `preservedGeneral` lists supported cosmetic/connectivity settings that were preserved rather than applied. `restrictions` requires a visible explanation in the shell. Swirl's existing subscription source and update schedule remain the controlling policy; the document cannot redirect updates or silently replace that schedule.

## Automatic nodes-only safety boundary

`profile::has_profile_semantics()` classifies active network instructions. `profile::node_only_fallback_allowed()` separately audits the entire bounded document, including content after an otherwise recoverable error. All unknown capabilities default to unsafe for automatic reduction. Script/MITM content, local files, controller/listener requests, routing/interface mutation, remote include sections and unclassified options cannot hide behind a prior unsupported rule or general setting. An empty dangerous section has no active content; no operation is created from it.

The Qt shell must keep DNS/rules/groups unchanged for nodes-only results, display an explicit reduction reason, and commit the validated nodes atomically. Successful parsing, complete-profile projection, controlled peer forwarding and private-provider/Codex acceptance remain separate evidence. Actual browser, Codex and private provider checks are assigned to the user.

## Focused verification

The portable tests cover exact QX rule/group/DNS output, no accidental plaintext fallback from DoH, node-only output containing no DNS/rules/groups, private-value absence from metadata/errors, malformed managed headers, later dangerous sections following earlier unsupported settings, and closed handling of unknown host capabilities. Run `cargo test -p swirl-subscription --locked --lib` and `cargo clippy -p swirl-subscription --locked --all-targets -- -D warnings` using the configured concrete stable toolchain. Qt controlled-peer tests are separate delivery evidence.
