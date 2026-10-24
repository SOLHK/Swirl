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

Primary references: [Cargo incremental profiles](https://doc.rust-lang.org/cargo/reference/profiles.html#incremental),
[CMake content-stable generated files](https://cmake.org/cmake/help/latest/command/file.html#configure),
and [the pinned Actions cache implementation](https://github.com/actions/cache/tree/0057852bfaa89a56745cba8c7296529d2fc39830).
The cache implementation requires separate restore/save steps for explicit
save conditions; a failed downstream check must not be described as successful
because compiler artifacts were reusable.
