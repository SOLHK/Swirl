# Historical installer cleanup defect and regression

This directory records a diagnosis of the **historical 24af5838 package**, not
acceptance of the current branch. The Windows runner used source checkout
`ceafbef537b9f9f30a0bc13b1dc24f7ff16addfd` for that historical package and the
diagnostic script from `ae083d7f0dc73c5d34802d872d124a34fb4e465d`. The original
envelope preserves both identities and explicitly sets `diagnostic_only: true`
and `current_source_acceptance: false`.

## Executed evidence

- Historical package build: <https://github.com/SOLHK/Swirl/actions/runs/41475106009>
- Strict historical lifecycle reproduction: <https://github.com/SOLHK/Swirl/actions/runs/41486232873>
- Diagnostic artifact: `13160614838`, archive SHA-256
  `b529aa04986ad10b1e8c29c6c4552a52ec6e9fa834843d7c4ff416ed608a32b5`.
- Original NSIS artifact: `13160021695`; production directory artifact:
  `13160625395`.
- Actual `Swirl-Setup.exe` SHA-256:
  `082c6e60ffa968d0e6d3d8766a055e7dc49b5a6263de1f66c74352218b6ea84b`.
- Actual package manifest SHA-256:
  `95e57c627ba3948422075ea22b731dc3bb77e386719e91cbf2450fb6a0758003`.

The actual isolated installer exited 0, installed all 1,519 manifest files with
matching hashes, and ran the installed Rust HTTP/CONNECT/SOCKS5 roundtrips,
Qt/OpenSSL self-test and all 61 UI routes successfully. The actual uninstaller
also exited 0, but the strict test correctly failed because its installation
directory remained. No owned process remained, no process was forcibly killed,
and the user's registry and shortcuts were unchanged. The test subsequently
cleaned its unique disposable fixture after preserving these reports.

`installed-layout.json` is the complete original installed tree. Its ten empty
leaf directories were created by Qt deployment. `uninstall-remainder.json`
records exactly 17 directories and **zero files** after the real uninstaller:
the empty subtrees and their ancestors. The original uninstall executable was
removed successfully.

## Root cause

The package manifest owned files only. NSIS `File /r` also emitted directory
creation commands for empty QML directories. The maintenance helper only
pruned ancestors of removed, owned files, so directories that never contained
an owned file were outside its cleanup plan. The final nonrecursive `RMDir`
could not remove the resulting tree.

`inspect-historical-nsis-directories.py` independently decodes the original
installer's bounded LZMA instruction header after checking the exact installer
and manifest hashes. It finds 11 directory creation commands without any
manifest file descendants. Those paths and their ancestors exactly predict
the 17 entries observed on Windows, as recorded in
`historical-installer-root-cause.json`. Seven-Zip's ordinary NSIS file listing
omits these directory creation commands, so extracting only the listed files
does not reproduce the installed directory tree.

The repair removes empty directories only from a newly created staging tree.
The real installer's strict acceptance check now compares all files and all
manifest-derived ancestor directories. The production uninstaller's protection
for unknown or modified user files and directories remains in place.

## Reproduction

Download the two historical artifacts from the run above. Inspect the pinned
installer without executing it:

```sh
python inspect-historical-nsis-directories.py /path/to/Swirl-Setup.exe /path/to/package-manifest.json
```

Exercise the exact current validator and its fixed historical negative control
against generated fixture files:

```powershell
pwsh -NoProfile -File docs/evidence/windows-proxy-compat-20261102/resume-20261103/installer-cleanup/Test-InstallerInventoryRegression.ps1 -RepositoryRoot .
```

`inventory-regression.json` records 11 passing checks. The old validator accepts
the observed empty QML directory shape; the corrected validator rejects it,
then accepts the same fixture after normalization. These local checks do not
execute NSIS and do not replace the latest full Windows production workflow.

Windows 11 Codex Desktop A/B: **NOT_RUN**. Ordinary nonisolated user installation:
**NOT_RUN**. The historical CI execution used an isolated directory on a
disposable Windows runner.
