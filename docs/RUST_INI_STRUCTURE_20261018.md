# Native INI document structure and validation boundaries

This stage continues `c5ed84b9e40a147de743826501d04c711321081d` on
`work/core-completion-20261017`, using the new 06:55:48 UTC encrypted Windows
capture. Supplier refresh requests during development and replay were zero.

## Corrected behavior

Previously, a valid proxy section followed by a malformed section header could
still yield executable node candidates: the INI importer skipped every non-node
section without validating its envelope. Section whitespace could also hide the
supported proxy section, and preserved INI configuration sections were reported as
zero because their lossless document representation is a string.

The native importer now validates every INI section header, rejects ambiguous
repeated sections, control characters, empty node assignment names and bounded
section-count/name violations before returning any candidates. It accepts header
whitespace and trailing hash/semicolon comments. The original text remains
preserved, including on errors. Control validation runs before whitespace trimming;
independent review reproduced and led to fixing a boundary-control bypass in the
initial candidate patch. Base64-wrapped INI follows the same checks.

Non-node bodies are retained verbatim. Their client-specific rule, script, rewrite,
DNS and policy grammars are still NOT semantically validated or executable here.
The additive `configuration_sections_unvalidated` report field makes this explicit;
`full_configuration_sections_preserved` now counts these INI sections correctly.
The same unvalidated count is reported for preserved non-node JSON/YAML sections.
`parsed` still means structural/node parsing, not full configuration acceptance.
No unsupported behavior is converted to DIRECT and no protocol/TLS policy changed.

## References and licensing boundary

The official [Loon configuration example](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf)
and [Quantumult X example](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)
were reviewed for section syntax and differing body grammars. Implementation and
synthetic regressions were independently written; no example implementation was
copied, no external source was vendored, and no dependency or license changed.
Duplicate sections remain explicitly unsupported because merge precedence has not
been established across these client dialects. This is not universal INI support.

## Actual local verification

- Four new Rust regressions, including original/Base64 malformed tails, section
  metadata, duplicate/empty assignments and boundary controls. The initial three
  regressions failed before implementation; their failure log is preserved.
- Final fmt/check/strict Clippy and all 136 Rust tests passed; Release built.
- All 11 independent subscription-import tests passed, including SS/Trojan peers.
- Windows capture security suite: 26 cases, 25 passed and one existing privilege
  skip; no supplier endpoints were used.
- All 18 newly cached entries still parse, with 1558 records and 450 TCP candidate
  records including repeated exports. Loon entry 15 now explicitly reports 12
  preserved, unvalidated non-node sections. Full configuration execution is false.
- Rebuilt Qt to Rust integration CTest passed. Exact additional peer and CI results
  are recorded in the machine evidence and subsequent checkpoint.

The first CMake launcher invocation failed because its Python module path was not
set; invoking the existing CMake binary fixed this without installing anything.
An accidentally unfiltered CTest invocation also launched the existing appearance
UI test, which hit its unchanged 45-second timeout. That run was stopped, its log
retained, and only the intended Rust integration test was rerun successfully.
This UI failure remains uninvestigated; visual/UI acceptance is NOT claimed.
Only the test processes under the build directory were stopped; the user's
existing D:\ASwirl application was left running. No QML or UI source changed.
The existing MinGW .drectve warning remains; linking succeeded.

## Next work

The complete product subscription chain still needs an atomic document import.
Current NodeImportService imports only nodes; NodeStore stabilizes UUIDs during
merge, while network configuration is saved separately. A safe next stage must
prepare final node IDs before mapping groups/rules, validate against candidate
nodes, preserve the complete source only in encrypted storage, and commit or
recover both node and network state together. Do not simply call the existing
replaceNetworkConfiguration from the busy import callback: it rejects that state
and does not provide two-file atomicity. Preserve unknown DNS semantics explicitly;
Mihomo respect-rules is not equivalent to Qt respectRules/force_proxy_hosts.

No new provider-node network test, TUN, full application package, or long-duration
performance run was performed by this parser stage. Prior real-node evidence must
retain its original source/environment identity.
## Windows test launch incident and current execution environment

The user supplied a screenshot of `SwirlRustCoreTests.exe` reporting missing
`Qt6Gui.dll`. The screenshot was downloaded to D:\Codex\outputs\IMG_2177.jpeg
and inspected locally. Existing Qt6Gui/Qt6Core/Qt6Test DLLs are version 6.10.3.0;
both the test executable and Qt6Gui.dll are PE x64. They were not missing from
the installed toolchain. The initial unfiltered CTest environment omitted its Qt
runtime bin directory. Earlier targeted reruns used the corrected process-local
PATH and passed; no test was restarted after the user reported the dialog.

The actual unfiltered command was `ctest --test-dir D:\Codex\work\build-rust-qt
--output-on-failure`. Its log is D:\Codex\work\ini-qt-unfiltered-aborted.log:
`swirl-appearance-ui` timed out at 45.01 seconds, then the run entered
`swirl-rust-qt-integration`. The appearance timeout remains unresolved and has
not been attributed to the INI patch. The successful targeted command used
`-R '^swirl-rust-qt-integration$'` with the Qt bin directory on that process PATH;
its separate log is D:\Codex\work\ini-qt-ctest.log (1/1, 6.33 seconds).
Four independent Qt protocol peer suites also passed before the user's report.

D:\Codex\work\swirl-env.ps1 now includes the existing Qt runtime and real CMake
binary directories for the calling process only. The local wrapper
D:\Codex\work\Run-Qt-Rust-Integration.ps1 checks required DLL existence and x64
PE architecture and restricts CTest to that integration test. Its ValidateOnly
preflight passed with test_started=false. No software or DLL was downloaded, no
global PATH was edited, and no currently running user application was terminated.

The current delegated execution is supplied by the desktop application's local
Codex exec-server, connected to the cloud environment. It is not a separately
created visible desktop Codex project task. Exact local state-db lookups found
neither the delegated execution thread nor the parent conversation. Desktop
list_threads/send_message_to_thread calls failed with MCP -32000. No competing
writer/task was created to work around that visibility issue. New module edits
and local test launches were paused to investigate the user-reported environment.
