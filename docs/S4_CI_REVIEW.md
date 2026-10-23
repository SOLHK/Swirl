# S4 CI change review

| Severity | Findings introduced by S4 |
|---|---:|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 1 |

Scope: S4 mobile compilation workflow and the changed native, fixture, source-guard and Windows packaging workflow paths. This is not a claim that all historical workflows were hardened.

- Triggers are fixed branch `push` and manual dispatch; no privileged PR-target/workflow-run trigger or fork checkout is introduced. Tokens are read-only and checkout credentials are not persisted in the changed S4 execution paths.
- Script expressions use fixed matrices, source SHA and runner/workspace paths, not issue/PR text. Target names enter shell via environment variables. No new secret is used, printed or embedded in artifacts.
- Existing third-party Qt/MSVC/Go actions remain pinned to exact commits; native peer archives retain locked hashes and executable identities. The new checkout action is SHA-pinned. Low finding: several existing first-party `actions/*` references and the new upload step use version tags, not immutable SHAs. This is a retained supply-chain hardening opportunity, not an introduced write-token path.
- Final package assembly verifies the complete manifest after smoke and saves diagnostics outside the payload. Test failures retain their failed status. In particular the original strict VMess and public TLS jobs still fail rather than using `continue-on-error`, skipped assertions or 204-as-closure substitutions.
- The OpenHarmony job names its limited crates and records `network_permissions_verified=false` and `device_networking_verified=false`. Android/iOS jobs check full workspace libraries with the appropriate native SDK environment; none claims a mobile system adapter is implemented.
- YAML syntax was parsed locally across all 45 workflow files. Actual runner execution, compiler success and package generation remain separate validation results linked to their exact commit.

The historical S3 whole-UI source guard is retained. S4's guard preserves the same baseline hashes for 100 unchanged files, including window/sidebar implementations and geometry, while allowing eight named model/content/motion files authorized by the S4 task. Runtime geometry, input and five-DPI checks remain mandatory; source hashing is not visual acceptance.
