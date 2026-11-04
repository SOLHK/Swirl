# D2 scoped Qt DLL repair validation

Continuation from verified D1 HEAD `6d4d692d82b3c55bb52592faff3cef12ec91076f`.
The user's follow-up requests the repair. This checkpoint applies the existing
one-function patch only in a disposable pinned Qt checkout and rebuilds QtGui;
no Swirl production file, font, backend choice or other branch is changed.

The new dedicated workflow runs Windows Server 2022 and 2025. It first builds
unmodified Qt 6.10.3 from `7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4`, then
applies the hash-verified proposal and incrementally rebuilds the same tree with
the same compiler and options. The private Core/Gui prefix is never deployed
into a production SDK. Build flags and both DLL identities are recorded.

Both builds execute the unchanged D1 harness, including DirectWrite, Qt Native,
FreeType, private/installed modes, reversed order and installation cleanup.
The baseline must retain exactly the four known FreeType outline failures;
the patched DLL must pass all 16 original processes and the unchanged analyzer.
Each build also executes 48 D2 CONTROL processes (576 offset observations).
No application-side transform guard is used on either side. All patched public
path queries must equal the complete cold path exactly. State, advances,
sampled cache entries, raw pixels and decoded PNGs must agree across builds.

Local validation: 37 unchanged D1 tests, 19 D2 identity tests, and 13 new
fail-closed tests passed. Windows rebuilt-DLL outcomes are PENDING at this
source checkpoint; neither the earlier diagnostic success nor Linux parser
tests certify this build. Original SDK CI and failed artifacts remain intact.

Scope limits: this is a focused source-built Qt Core/Gui validation, not a
reproducible rebuild of every official SDK component. The small upstream patch
is not a production deployment; Qt Quick UI, performance, Windows 11 and an
original qualified TTC remain NOT_RUN. Results and exact CI identities will be
recorded after inspecting the new native evidence.
