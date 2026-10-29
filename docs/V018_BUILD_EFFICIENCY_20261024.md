# Incremental Windows network candidates

The network repair branch uses `.github/workflows/v018-network-candidate.yml`
and `scripts/build-network-candidate.ps1`. The full historical S4/0.1.7
workflows remain available with their original assertions. A focused candidate
does not turn the retained public TLS/VMess closure failures into passes and
does not establish private subscription, Codex account, TUN or DPI acceptance.

## Measured previous delivery

The timestamped Windows log for [run 40075766405](https://github.com/SOLHK/Swirl/actions/runs/40075766405)
at `fad05a72070b5770708cf64af57936bc9f0e64a1`, job `120818641310`, shows:

| Phase | Seconds |
|---|---:|
| Configure the test CMake tree | 33.528 |
| Build system proxy test and shared engine (cold Rust included) | 305.172 |
| Build test-enabled application and remaining regression binaries | 899.593 |
| Configure a separate production CMake tree | 16.691 |
| Build the separate production application | 684.640 |

These durations are intervals between workflow group-start timestamps and
include small step transition overhead. They are not compiler-only times.
The Rust compiler itself reported `3m 06s` for the initial Release library;
later Cargo checks reported `0.24–0.44s`. The Qt SDK cache hit, but no Cargo
or CMake artifact cache was configured. The final public network gate failed;
its failure is retained.

Local existing logs independently show dependencies were already reused:
`build-fad05a7.log` reported a 14.02-second Rust API rebuild, and subsequent
unchanged library checks took 0.46 and 0.49 seconds. That same catalog-only
commit changed global C++ identity definitions and scheduled 371 further
actions. The recorded object durations included 48.545 seconds for embedded
font resources and 21.720 seconds for `main.cpp`. These local and hosted
measurements use different toolchains and must not be directly compared.

## What changed

- A generated identity header is included only by code that consumes the
  build/source identity. Every commit still refreshes the loader's expected
  source SHA and Rust build digest, without invalidating unrelated C++ objects.
- The application version and QML cache revision are source-specific
  definitions on `main.cpp`, their sole consumer. A QML cache revision change
  must still refresh the startup cache namespace, while unchanged font/resource
  objects no longer inherit that unrelated definition. The first transition
  from old target-wide flags changes existing compile commands once; a cache
  restore during that transition is not evidence that no objects recompiled.
  Local CMake compile-command inspection found exactly one consumer of each
  definition (`main.cpp`) and neither definition on all ten generated resource
  compilation units. This validates dependency scope and quoting; it is not a
  measured runtime or end-to-end build speedup.
- One Ninja tree builds focused C++ tests, runs them, switches the application's
  test exposure OFF, and builds the production application once. The shared
  engine objects are reused; the script requires unchanged hashes **and**
  timestamps. No test-enabled application is packaged.
- Cargo incremental compilation is enabled. Cargo dependency/target and Ninja
  caches use OS, compiler, SDK, CMake, workspace path and lockfile identities.
  Checkout timestamps are restored only for current tracked regular files
  whose SHA-256 still matches the saved input manifest. Changed bytes retain
  new timestamps, and Ninja/Cargo retain command/dependency invalidation.
- Required loader, import, node, stream, telemetry, diagnostic, proxy-state,
  TLS policy and launcher suites run before production staging. Actual proxy
  mutation/recovery runs only on disposable GitHub-hosted Windows runners.
  Portable Rust safety/regression runs in parallel on Linux.
- Production EXE/DLL identities and DLL hashes must match the tested runtime.
  Clean-directory HTTP, SOCKS5 and HTTPS CONNECT roundtrips, startup, installer
  lifecycle and exact final package inventory/hash checks remain required.

## Reading the evidence

Each candidate saves `evidence/build-timings.json`, per-phase logs, JUnit
results and final manifest verification. `restored_*_cache` records observed
on-disk state; the Actions cache restore log records the actual cache hit or
prefix match. `source_timestamps_restored_by_content` counts verified input
reuse. `engine_objects` counts unchanged tested objects retained by production.
The final no-change rebuild must contain no source compilation or relink.
Successful compiler outputs can be cached even if a subsequent test,
environment check or package step fails. `compiler_cache_ready` records only
compilation, and never changes the failed candidate status. Every later run
still executes all selected tests and source/identity/package checks.

Do not calculate a speedup until a successful candidate supplies actual after
timings. The first run may have cold caches; later hits and misses must be
reported separately. No build or Cargo target is deleted by this workflow.

## First successful network candidate

[Run 40084235219](https://github.com/SOLHK/Swirl/actions/runs/40084235219)
at `a28258e16ebd6e45e63f802b12f262f2293bf4b0` passed both jobs and produced
artifact `12557125151`. Its Windows build/package script took 640.284 seconds:
235.008 seconds compiling focused tests, 187.635 seconds building production,
and 0.509 seconds for a no-change rebuild with no source compilation/relink.
All 18 tested engine objects were reused in production. Thirteen focused
CTest suites passed, including disposable system-proxy recovery; the final
1509-file inventory and every hash were verified.

The first Windows compiler cache was cold (`restored_cmake_cache=false`,
`restored_cargo_cache=false`); Cargo still reused the freshly built dependencies
within the job, reporting 0.37 and 0.20 seconds for subsequent library checks.
An Actions compiler-cache restore hit has not yet been established by this
run. The earlier 42m44s Windows job includes setup and a broader historical
test scope, so it must not be equated with this 10m40s script interval.
The historical separate production build took 684.640 seconds; the observed
new production phase is 187.635 seconds, with shared-object reuse explicitly
measured. This is delivery evidence across commits, not a same-source benchmark.

Primary references: [Cargo incremental profiles](https://doc.rust-lang.org/cargo/reference/profiles.html#incremental),
[CMake content-stable generated files](https://cmake.org/cmake/help/latest/command/file.html#configure),
and [the pinned Actions cache implementation](https://github.com/actions/cache/tree/0057852bfaa89a56745cba8c7296529d2fc39830).
The cache implementation requires separate restore/save steps for explicit
save conditions; a failed downstream check must not be described as successful
because compiler artifacts were reusable.
