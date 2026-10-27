# APEC redesign baseline — 2026-10-27

Remote repository: https://github.com/SOLHK/Swirl . The connector branch API
and a fresh Git fetch agreed on `work/swirl-3-20261026` at
`80955a98ef225fb799acb190967e8da4f41e719d`. Remote main was older at
`87409c0bf9c957ef113f84c176c5a1529c27b9df`; it is not the working integration
baseline. The fresh independent clone is on `work/swirl-apec-v3-20261027`.

The preceding development directory contains 48 tracked modifications and four
untracked files (three settings subpanes and a TUN status document). Those
changes are not assumed to be reviewed or accepted. All 52 files were copied
with a SHA256 manifest into local ignored `work/inherited-ui-20261027`. The
old worktree/index/branch were not modified. Review and deliberately integrate
the snapshot in the full-page stage, including its new settings QML files;
do not copy only a tracked diff or discard working transitions.

The committed native control foundation is already present (`dad8405`). The
baseline includes 31 QML page files, shared components/controls and dynamic
FeatureCatalog routes. Existing Qt 6.10.3 code has font async initialization
fencing, retargetable page navigation, native shadow caching, transactional
policy/subscription operations and Windows-adapter isolation. Preserve those
functional foundations while replacing the visual language.

The old icon consists of five polygonal filled paths; the new brand work
preserves its multi-curl knot identity and existing native ICO/NSIS wiring.
The source and material inventory is a read-only finding, not a test pass.

The user subsequently required the latest Qt. Qt's official release page and
SDK manifests establish **6.12.0** as the newest stable release inspected on
2026-10-27. The new project requires Qt >=6.12; CI pins the verified 6.12.0 SDK
for reproducibility. Future upgrades should re-check the official stable
channel, pin the resulting version and repeat relevant compatibility tests.
No old build cache is reconfigured to point at the new source tree.

Sources: [Qt 6.12 release](https://www.qt.io/blog/qt-6.12-released),
[official downloads](https://download.qt.io/official_releases/qt/6.12/).
