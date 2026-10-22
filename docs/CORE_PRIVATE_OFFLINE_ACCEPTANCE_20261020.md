# Private offline qualification, 2026-10-20

This stage extends the existing capture analyzer and Qt inspector. It does not
refresh a subscription, start the Rust Runtime, connect to a provider, invoke
Codex, or alter the system proxy. The physical Windows subscription and cache
have not been read in the chat environment. The current count among the earlier
59 VLESS/REALITY nodes is therefore **unknown**; the old zero-candidate result is
not reused.

## Evidence boundaries

`Analyze-CapturedSubscriptions.py` reads an existing capture index and its DPAPI
records, checks both response hashes, and sends each distinct decoded document
to the existing Rust inspector over stdin. Complete originals and private
diagnostics remain in a DPAPI result. That result is reopened and compared after
save. Both outputs must be new, distinct files outside the input cache; an
existing output or path within that cache is refused. Public reports are a
projection of fixed protocol/status/reason enums,
booleans and bounded counts; they do not copy arbitrary inspector fields, source
labels, server names, credentials, keys or free-text diagnostics. Node numbers
are reassigned locally, rather than copied from source identifiers.

`SwirlPrivateSubscriptionInspect` uses the real `NodeImporter`, `NodeStore` and
`SwirlProtocolRegistry::nativeNodeReason` path. In a Rust build the last call uses
the current `RustCoreEngine::configuration` mapper without starting an engine.
Its two modes are:

| Input | Verified operation | Write scope |
| --- | --- | --- |
| DPAPI-encrypted response plus a new store path | Parse, create an encrypted NodeStore, destroy the writer, independently reload, compare node identities and all stored protocol parameters/original configuration, evaluate current native eligibility | New store only; existing output or selection sidecar is refused |
| `--node-store` plus an existing product NodeStore | Actual DPAPI reload, current native eligibility, original URI reparse comparison where available | None; store and selection bytes are checked unchanged |

Reload-added conversion diagnostics are deliberately excluded from the parameter
comparison. They must not be reported as lost parameters. Conversion diagnostics
are exported only through a fixed reason-code lookup; unrecognized text becomes
`UnclassifiedNativeOrImportDiagnostic`.

Both reports keep parse, complete parameter mapping, encrypted reload, native
eligibility, Runtime start, proxy entry, REALITY connection, REALITY
authentication, Vision, Vision Direct, HTTP and HTTPS as separate stages. The
Python capture reload is not a Qt NodeStore reload. An offline candidate is not
network evidence. All connection stages remain `not-tested` by default. The
existing optional Python HTTPS probe is still disabled with `--test-limit 0`;
even when explicitly enabled, it cannot certify Qt execution, REALITY
authentication details, Vision Direct or plain HTTP.

The design reuses the separation between checking a configuration and running
it documented by [Xray's command interface](https://xtls.github.io/en/document/command.html).
No upstream source or full proxy engine was copied. DPAPI processing uses the
existing same-user Windows implementation and clears the returned decryption
buffer; see [Microsoft's CryptUnprotectData contract](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata).

## Tests and pending native execution

Seven portable `EvidenceTests` cover public-field projection, free-text canaries,
failed parsing, unproven success flags, default offline control flow and the
encrypted-result reread requirement, and refusal to overwrite existing files or
write into the input cache. Their pipeline test uses mocked DPAPI I/O
on Linux and is not Windows DPAPI evidence. Linux Qt syntax compilation checks
the C++ source but cannot execute its Windows branch.

The new native test is:

```text
python -m unittest tools.tests.test_subscription_capture.CaptureTests.test_qt_offline_inspector_reloads_and_redacts_actual_dpapi -v
```

It requires Windows and `SWIRL_QT_PRIVATE_INSPECTOR` pointing to the built and
deployed Rust-mode Qt executable. The formal CI step must fail if the executable
or environment variable is absent. The ordinary capture suite runs before that
Qt build and may skip the optional inspector test; that skip is not the formal
result.

The native test uses only synthetic chrome/Vision/headerType=none, TCP-path and
unsupported-fingerprint nodes. It checks actual DPAPI save/reload, candidate
counts and specific rejection reasons, stdout/stderr redaction, unchanged
existing ciphertext and selection sidecar, refusal to reuse output, and failure
on a tampered synthetic ciphertext. A Windows result must be recorded separately
against the exact tested source SHA.

## Prepared physical Windows offline handoff

Use these steps only with the final source/artifacts whose Windows Qt public
acceptance has been checked. They are prepared instructions, not an assertion
that the physical machine has been tested. Use the same Windows account that
encrypted the old cache. Keep every new output under `D:\Codex`; the existing
authorized C-drive cache remains read-only.

From the checked-out repository, create a fresh output directory and use the
matching Rust inspector binary:

```powershell
$out = Join-Path 'D:\Codex' ('Swirl-offline-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
$cache = 'C:\Users\sysfr\Documents\Codex\2026-10-16\new-chat-2\work\private-capture\cache'
$rustInspector = (Resolve-Path 'core\target\release\swirl-inspect.exe').Path
$qtInspector = (Resolve-Path 'build\rust-qt\Release\SwirlPrivateSubscriptionInspect.exe').Path
py -3 tools/Analyze-CapturedSubscriptions.py --cache $cache --inspector $rustInspector --private-output (Join-Path $out 'analysis.dpapi') --report (Join-Path $out 'rust-offline.json') --test-limit 0
if ($LASTEXITCODE) { throw 'Offline Rust analysis failed' }
```

Resolve cached response files from the encrypted capture index in local memory.
For each distinct response, reuse `SubscriptionCapture.py replay` with the Qt
inspector and a fresh `nodes-<ordinal>.dpapi` under `$out`, then run:

```powershell
& $qtInspector --node-store $newStore | Set-Content -Encoding UTF8 $redactedQtReport
if ($LASTEXITCODE) { throw 'Offline Qt reload failed' }
```

Here `$newStore` is the newly created isolated NodeStore and
`$redactedQtReport` is an ordinal-named JSON path under `$out`. An existing
product NodeStore can instead be passed directly to `--node-store`; it will not
be rewritten or selected. A capture record, capture `index.dpapi`, and
`subscriptions.private` are different formats and must not be passed as a
product NodeStore. Do not dump any of them to the console.

Preserve the exact source SHA, binary hashes and process exit codes alongside
the allowlisted reports. Only those reports may leave the machine. Provider
authentication, Vision Direct, real HTTP/HTTPS, A/B switching and the final
Swirl.exe run remain the subsequent physical acceptance task. This offline
stage does not change the frozen 79-item, 6-complete, 10.83% project baseline.
