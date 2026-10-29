# Swirl 0.1.8: source-less legacy catalog repair

## Reproduction and root cause

A read-only, in-memory inspection of the affected Windows DPAPI catalog found
zero subscriptions and 180 nodes. All 180 had empty subscription ID, import
origin and format, with no original configuration or provider alias. Only these
aggregate facts were retained; no node names, endpoints, credentials or decrypted
catalog were exported, and the user's catalog was not modified.

The 0.1.7 migration predicate recognized orphan subscription IDs, an explicit
`subscription` import origin, or an empty origin with a nonempty format. It missed
records that had lost **both** origin and format. The public model consequently
mislabelled them as manual, and the confirmed legacy cleanup skipped them. The
old regression fixture always supplied `subscription`, so it missed this case.

## Correction

A node with a current subscription ID remains owned by that subscription. An
orphan ID is pending review. Without an ID, only an explicitly recorded manual
creation or user import (`manual`, `manual-import`, `text`, `clipboard`, `file`,
`url`) establishes a user-managed node. Empty or unrecognized provenance is
pending review, regardless of format. Detection never rewrites or removes data.

The existing explicit cleanup transaction now includes fully source-less legacy
records. Its confirmation warns that old manually created records may also lack
provenance. Known manual entries/imports and current subscription nodes remain.
The result reports the number removed and the actual remaining count. Selection
and policy-reference cleanup continue through the shared atomic persistence
path. Starting the application alone never deletes uncertain user data.

After upgrading, the affected catalog should show 180 historical unassigned
nodes. The user can review them and confirm cleanup; the old confirmation is
not silently reused to authorize a broader deletion in a new version.

## Regression scope

Real Windows DPAPI fixtures reproduce 180 records with empty fields and with
missing fields, zero subscriptions, a selected legacy node, and optional
explicit manual/text/clipboard/file/URL imports. Tests check classification,
unchanged ciphertext during detection, confirmed 180-to-zero cleanup, known-user
node preservation, cleared selection, persistence/reload, and a no-op repeated
cleanup that leaves ciphertext unchanged. Data is synthetic; this tests the
production catalog lifecycle, not private provider networking.

Local Windows Qt 6.10.3 regression passed all 11 selected CTest suites,
including 48 subscription cases. Portable boundary checks passed 7 tests;
the OpenHarmony subscription/platform target compiled successfully. Common
Rust sources/dependencies are unchanged. The initial new fixture incorrectly
used the original ciphertext's selection sidecar after replacing the fixture;
it was corrected to store selection in the new snapshot, preserving the
production digest binding instead of weakening it.

The product patch version is 0.1.8. Existing public TLS orderly-close failures
and unverified private-provider/Codex acceptance from the 0.1.7 report are not
resolved or reclassified by this catalog fix.

## Primary design reference

[v2rayN ConfigHandler](https://github.com/2dust/v2rayN/blob/57f17d5939e88c8e643ab49b90869d637765e75a/v2rayN/ServiceLib/Handler/ConfigHandler.cs)
uses a persisted subscription ID for associated-server deletion in
`DeleteSubItem` / `RemoveServersViaSubid`. This supports keeping ownership and
user-managed entries explicit. Swirl's conservative legacy classification and
DPAPI transaction are independently implemented; no upstream source was copied.
