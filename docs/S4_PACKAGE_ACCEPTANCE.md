# S4 package staging and disposable installer acceptance

Recorded 2026-10-24 Asia/Shanghai. The real NSIS installer and uninstaller were
compiled and executed against synthetic payloads in one unique D-drive test
directory. **28/28 lifecycle and safety checks passed.** This verifies installer
mechanics and file preservation; it is not an installed Swirl application test,
final release-package verification, or private-subscription acceptance.

## Changes and ownership rules

- Finalization validates source identity, exact inventory and every recorded
  SHA256 after the smoke launch. The specifically allowed smoke diagnostic is
  moved outside the payload and retained as evidence. Unexpected files, changed
  hashes and mismatched source identities fail validation.
- Payload roots, manifest files, output paths and their ancestors are checked
  for reparse points before they are read or written. Evidence/include paths
  cannot point back into the payload through a junction.
- NSIS embeds the verified manifest and fixed maintenance scripts into its
  temporary plugin directory. It invokes the system Windows PowerShell by its
  explicit path, hidden, with literal quoted arguments, and checks its exit
  status. No downloaded script or old uninstaller participates.
- Upgrade validates and saves prior ownership before copying. It verifies the
  new vendor files before removing obsolete files declared by the old manifest.
  Obsolete files with modified bytes and files absent from the ownership
  manifest are preserved. Paths present in the new vendor manifest are updated
  as normal application files.
- Uninstall deletes only files from its embedded manifest whose bytes still
  match the recorded hash. Modified files and user-added files are retained;
  directory removal is nonrecursive and only removes empty directories. The
  former recursive deletion of the complete application directory is gone.
- Before planning any deletion, uninstall requires the installed manifest to
  exist and match its embedded manifest byte-for-byte. A saved V1 uninstaller
  therefore refuses an upgraded V2 installation, including shared vendor files
  whose contents happen to be identical in both versions.
- Unknown legacy ownership preserves extra files. A malformed known ownership
  manifest fails before cleanup; there is no destructive fallback. Legacy extra
  vendor files may therefore remain and are not presented as exact cleanup.
- Isolated validation requires the exact destination
  `$env:SWIRL_ISOLATED_INSTALL_ROOT\install`, beneath `D:\Codex\tmp\s4`, with
  canonical-path and ancestor-link checks. Nonempty unmarked directories are
  refused. Uninstall requires an installation ownership marker.

Actual execution caught two additional defects: NSIS's original path operation
returned an empty result for the fresh destination, and the 32-bit system
PowerShell inherited a module path without `Get-FileHash`. Canonicalization now
uses bounded `GetFullPathNameW`; maintenance hashes files with the framework
SHA256 streaming API. These are Windows packaging details outside Rust Core.

## Executed checks

The installer installed version 0.0.1 of a synthetic, non-executed payload,
upgraded it to 0.0.2 with a changed file inventory, and uninstalled it. The
synthetic `data/subscriptions.dpapi` and `user.txt` remained byte-identical.
Registry values and existing Desktop/Start Menu shortcuts were snapshotted and
compared without modifying them. No installed Swirl executable was launched,
stopped, replaced or removed; no real encrypted subscription was opened.

| Check group | Actual result |
|---|---|
| Real NSIS lifecycle and safety regression | **28 passed / 0 failed**, exit 0 |
| Package filename policy | **31 assertions passed** |
| Release CMake cache/staging checks | **14 cases passed** |
| Exact final-manifest regression | **14 scenarios passed** |
| Real product binary / final MSVC installer / signed delivery | Not executed by this fixture |
| Complete rollback following an interrupted or partially failed copy | Not implemented or claimed by this change |

The 28 checks cover initial installation, two payload manifests, smoke evidence
retention, exact file inventories and hashes, removal of obsolete vendor files,
upgrade/uninstall user-file retention, modified vendor-file preservation,
malformed old ownership rejected before deletion, post-copy hash rejection,
unmarked directories, missing ownership, wrong expected root, traversal to a
different child, destination links, payload/output junctions, stale-uninstaller
refusal with every V2/user/marker byte retained, and unchanged user integration.
The full named list is in the evidence JSON.

Raw local evidence:

- `D:/Codex/outputs/s4/package-lifecycle/installer-lifecycle-d31784b84ea6469ea37bfed925d1afc6.json`
- `D:/Codex/outputs/s4/package-lifecycle-stale-after.log`
- `D:/Codex/outputs/s4/package-policy-final.log`
- Fixture and compiled installers retained at
  `D:/Codex/tmp/s4/installer-lifecycle-d31784b84ea6469ea37bfed925d1afc6`.

The [committed evidence index](evidence/S4_PACKAGE_ACCEPTANCE_20261024.json)
contains the source-file hashes, source base
`658d90d566cb61ff5dc7f908e8b8a88f0e52dd30`, NSIS hash, 28 outcomes and raw-log
hashes. Package code was uncommitted during this run; those exact file hashes
identify the tested state. Earlier failed disposable runs remain in the raw
directory, including fresh-path refusal and the system PowerShell module issue.
The stale-uninstaller regression first reproduced the defect: the old
uninstaller returned success and removed matching shared files and V2 ownership
markers. Its failing report is
`installer-lifecycle-cdf6c9b191ee4dcb841c9e3895e9f252.json`. After the manifest
identity guard, it exits 2 without changing any installed byte; the ordinary V2
uninstaller then succeeds and retains the synthetic user files.

## Repeat locally or on Windows CI

```powershell
& scripts/tests/Test-S4InstallerLifecycle.ps1 `
  -Nsis '<absolute path to makensis.exe>' `
  -Icon '<current build>/brand/Swirl.ico' `
  -EvidenceRoot '<runner temporary directory>/s4-package-lifecycle'
& scripts/tests/Test-RustProductPackagePolicy.ps1
```

The lifecycle script requires Windows with a writable D: drive and creates its
own unique `D:\Codex\tmp\s4` fixture. It sets/restores the exact isolated-root
environment variable. Passing the NSIS path, current build icon and evidence
directory removes the local defaults' S3-cache assumptions; no S3 binary or
environment setup is required. Run after the current build icon and NSIS are
available. It deliberately retains disposable artifacts instead of performing
a broad directory cleanup.

Before delivery, rerun against the final integrated source and verify the real
MSVC EXE/DLL source identity, final portable/NSIS contents and installed product.
This fixture's synthetic file verification cannot substitute for those gates.
