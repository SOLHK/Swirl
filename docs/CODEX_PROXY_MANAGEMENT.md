# Codex system-proxy compatibility management

`tools/SwirlCodexManage.py` requires Python 3.11+ on Windows. It is a local
management utility, not part of the Rust forwarding path. It reuses the DPAPI
helper in `SubscriptionCapture.py`; keep both files together.

```powershell
py -3 SwirlCodexManage.py check
py -3 SwirlCodexManage.py apply --journal C:\path\private\codex-change.dpapi --allow-write
py -3 SwirlCodexManage.py rollback --journal C:\path\private\codex-change.dpapi --allow-write
```

Use `--codex <absolute CLI executable>` or PATH discovery, and optionally
`--home <directory>`; otherwise CODEX_HOME takes precedence over the default
user `.codex` folder. The tool verifies CLI identity and `features list` support
at runtime rather than assuming every version knows `respect_system_proxy`.
The check reports saved and effective CLI state separately, current-user AppX
desktop version, execution identity and loopback system-proxy port when detected.
It does not claim system-proxy ownership or prove a running desktop's overridden
configuration, remote-control handshake or phone operation.

Apply uses `codex features enable respect_system_proxy` after explicit write
authorization and an encrypted pre-change journal. Already-enabled settings are
left alone. It verifies saved/effective state and checks that unrelated TOML
values are unchanged. No account token file is accessed; config contents and
CLI stderr are not printed. Journals may contain config secrets and remain local
DPAPI ciphertext. CLI failures or unexpected changes retain the journal.

Rollback restores the exact old bytes only if current bytes still match the
recorded post-change digest. Any later edit refuses rollback; it never overwrites
later user changes with an old backup. A newly created config is removed only
under this same identity check. Cooperative Swirl mutations use an exclusive
home lock. Other tools/editors do not participate in that lock; do not edit the
file concurrently with a mutation. Interrupted locks/journals remain for inspection
rather than automatically guessing recovery ownership.

No process is killed or restarted, no permanent environment variable is written,
and no proxy/DNS/TUN or unrelated application setting is changed. Existing Codex
sessions may need a normal user-controlled restart to reload configuration.

Validation: Windows DPAPI tests cover preservation, idempotence, authorization,
later edits, unexpected CLI changes, failures, unsupported flags and journal
ownership. An opt-in test uses the installed CLI against a temporary CODEX_HOME
and verifies apply/rollback without touching the real home. Set
`SWIRL_CODEX_CLI_TEST` to the actual CLI path to run it. The real user home was
checked read-only and already had the feature enabled.

Sources: [official configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic)
and [CLI commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli).
The feature's availability and current state are established by the installed CLI;
the public feature table is not treated as an exhaustive list of internal flags.
