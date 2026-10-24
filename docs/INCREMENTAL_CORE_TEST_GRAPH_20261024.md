# Keep standalone network tests separate from application UI exposure

## Measured baseline

The same-source benchmark at `5abf999c2a72ec58ed94d359d6bad6e791ade33b`,
[run 40091514412](https://github.com/SOLHK/Swirl/actions/runs/40091514412),
reduced the candidate script from 628.026 seconds in attempt 1 to 426.294
seconds in attempt 2 (32.12%). Focused test compilation fell from 137.432 to
6.121 seconds. Test execution remained 109.510 versus 109.268 seconds;
18/18 engine objects were reused and the no-change rebuild took 0.650 seconds.
These are the existing cache improvement, not a result of the change below.

The [attempt 2 Windows job](https://github.com/SOLHK/Swirl/actions/runs/40091514412/attempts/2)
(`120867815759`, Qt 6.11.3/MSVC) restored the exact compiler cache. Production
nevertheless took about 191 seconds and regenerated 95 QML source caches plus
their loader, then recompiled 96 cache objects and one type-registration object.
The remaining ordinary UI objects were already reused. Cargo checks took
2.83 seconds for the focused build and 0.31 seconds for production.

## Cause and change

The candidate previously configured `SWIRL_BUILD_UI_TESTS=ON` to obtain its
standalone test executables, then changed it to OFF for production. ON also
added sources, Qt Test, application test definitions and `material_tests.qrc`
to the Swirl application target. QML cache commands depend on those resources
and generated type information. Merely changing the configuration invalidated
95 QML generation commands even though the test-enabled application was never
built.

`SWIRL_BUILD_CORE_TESTS` now creates the independent test executables while
leaving Swirl's application sources, resources and compile definitions at
their production values. The historical UI option still includes the same
standalone tests and application UI checks. The candidate configures Core
tests ON, UI and Xray application test entry points OFF, and keeps that one
graph through testing and production. No second production configure is needed.

The selected 12 test suites, or 13 with disposable system-proxy recovery,
remain unchanged. Shared-object hashes/timestamps, tested DLL identity,
no-change rebuild, package startup, real controlled HTTP/SOCKS5/CONNECT
roundtrips, installer lifecycle and exact final inventory checks remain required.
The existing staging guard still rejects an application with UI tests enabled;
standalone test executables are not added to the package inventory.

No QML, animation, DPI, compiler optimization level or compressor was changed.
Full Rust regression and Windows packaging continue in parallel in CI.

## Validation and cost

`scripts/tests/Test-CMakeCoreProfile.py` uses a separate configure-only Ninja
directory. It compares the real production and Core-only application compilation
and QML generation commands, checks the selected test registrations and absent
application UI entry points, verifies that the historical UI profile still
registers its checks, then restores Core-only mode. It does not compile or
execute the application. This scratch graph never touches the product graph.

Local modified-source validation (Qt 6.10.3/MinGW, based on `4fa690d`): all 129
application compilation commands and all 96 QML generation commands were
identical between production and Core-only profiles, including after the UI
profile was exercised. The full UI profile retained all ten application test
registrations. Disposable mode retained all 13 candidate test registrations;
no system setting was mutated by this graph-only check. Warm validation took
13.470 seconds. This is local graph evidence, not an MSVC build speedup claim.

The candidate records this check separately as
`validate-standalone-production-graph`, preserving configuration logs, command
lists, hashes and source cleanliness in its evidence artifact. CI must report
its actual cost; a cold scratch configure may cost more than the local warm
check. No additional cache reuse state machine was added for this small check.
Final exact-source compilation, runtime tests and packaging are verified by CI.

Package-policy regression passed 31 path assertions, 16 staging cases (including
Core ON allowed and UI ON rejected), and 14 final-manifest scenarios.

Primary references: [Qt QML module build integration](https://doc.qt.io/qt-6/qt-add-qml-module.html)
describes resource, cache and type-information generation on the backing target;
[CMake test registration](https://cmake.org/cmake/help/latest/command/add_test.html)
allows tests to be registered as separate executables. The changed Ninja
commands and hosted job logs above establish this repository's invalidation.
