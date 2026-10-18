# Existing rule editor: preserve native routing semantics

## Baseline and verified defect

This stage follows font implementation `dfae05d07f84694d12223c9fcd4eddd199373dc1`
and its documentation-only successor `a6c2cd9863348b9f1d591c179f43ad58c88f871d`
on `work/core-completion-20261017`. The user requested continuing Swirl Core
after the font work. No default engine selection, UI layout, system proxy,
subscription source or private cache is changed.

The native adapter already accepts destination CIDR rules with `no-resolve`,
but `EngineController` read the last comma-separated field as the policy. For
`IP-CIDR,198.51.100.0/24,route,no-resolve`, its offline table displayed
`no-resolve`, and group deletion missed the real reference to `route`.
The existing editor also rewrote every non-MATCH rule as three fields,
discarding this option. Its native save path could persist unsupported
PROCESS-NAME rules before the native engine rejected them at startup.
These defects were established by tracing the current production paths;
there was no claim of having run the old Windows binary to reproduce them.

## Implementation

- Read the policy from the MATCH target field or the ordinary rule target
  field, independently of trailing options. Trim surrounding field whitespace
  for interpretation without rewriting unchanged stored strings.
- Preserve existing trailing options on a same-kind edit, including transitions
  between IPv4 and IPv6 destination CIDR kinds. Reject a type change that would
  silently discard a hidden option; the previous rule remains stored.
- Validate the entire candidate native rule/group configuration using the
  existing native validator. Unsupported native PROCESS-NAME, malformed domains
  and wrong CIDR address families fail before persistence.
- Persist a candidate through the existing DPAPI/QSaveFile snapshot before
  publishing it in `m_options`. A failed file commit leaves the old configuration
  visible even to synchronous `optionsChanged` observers.
- Route rule/group addition, editing and removal through that same small
  commit helper. No-op edits do not rewrite the encrypted file.
- Keep the compatibility build's PROCESS-NAME support and preserved modifiers.
  This stage does not claim that Rust gained process rules or the `src` modifier.

The existing UI and the native engine's rule matching implementation remain
unchanged. This is a product configuration integrity fix, not another routing
engine or a complete-profile compatibility milestone.

## Independent references

Read before implementation:

- [Mihomo's documented no-resolve and src semantics](https://wiki.metacubex.one/en/config/rules/#no-resolve).
- [Mihomo rule parser at 88dcbf7f1614a67c3b36b848ee3592dfa92ada36](https://github.com/MetaCubeX/mihomo/blob/88dcbf7f1614a67c3b36b848ee3592dfa92ada36/rules/parser.go),
  which separates the target from additional parameters.

Swirl's helper, candidate commit path and tests were independently written;
no third-party implementation was copied and no dependency was added.

## Verification at source submission

Actual cloud checks: Qt **6.10.3** moc for both Qt test files succeeded;
GCC **13.3.0** C++23 syntax compilation succeeded for the native and compatibility
controller variants and both complete test translation units. All four compiler
logs contained no diagnostics. `git diff --check` passed. These are Linux source
checks, not Windows DPAPI execution; the CMake Windows-only packaging gate was
not removed or bypassed.

Three new slots are registered in the existing `SwirlRustCoreTests`:

| Slot | Required behavior |
| --- | --- |
| `controllerRuleEditsPreserveNoResolve` | Offline fields, no-op byte preservation, edited CIDRs, controller restart, then a real local route distinguishing literal-IP DIRECT from unresolved-domain SOCKS5 forwarding. |
| `controllerRuleReferencesPreventGroupDeletion` | IPv4/IPv6 CIDR modifiers, MATCH and whitespace cannot hide a group reference; removal becomes possible after its referring rule is removed. |
| `controllerRuleValidationAndPersistenceAreAtomic` | Unsupported/malformed native rules and actual file-commit failure retain the old memory state, observer snapshots and encrypted bytes. |

The existing compatibility `networkPreferencesValidateAndPersist` slot also
checks that PROCESS-NAME stays editable and existing `no-resolve,src` modifiers
survive an edit. Public loopback fixtures and temporary stores supply these
tests; no private subscription or font is required.

Windows execution is performed by the existing `swirl-rust-qt-integration` and
`swirl-native-dns-compatibility-guard` CI targets after this source commit is
pushed. Its exact run, commit and result must be recorded after completion;
the earlier green font/Core baseline cannot stand in for these new tests.
The fixed whole-goal acceptance score and complete private-profile acceptance
remain unchanged; no real-node test was performed in this stage.
