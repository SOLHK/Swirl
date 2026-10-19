# Swirl Core emergency recovery checkpoint — 2026-10-20 (Asia/Singapore)

This checkpoint is committed immediately at the user's request to protect the continuation context against chat interruptions. It does **not** claim an unverified CI run or additional executable changes. Work is restricted to `work/core-completion-20261017`. Never force-push or touch main/test or unrelated font/UI files.

## Last verified pushed code

- **S5 current source**: `0416fe09fce4f4d5599c5a859842331f7783ebb3` — `test(core): verify proxy-path TLS shutdown and require the App inspector`; parent `b98850c3caaec7874f7e8c5a95866bbc4741df36` (concurrent font work preserved).
- S4: `a066f7d4c8acb96f5d6a46cee5700b2590328b64` — reserve actual fixture sockets, strengthen independent TLS close check.
- S3: `41555465b72fd59d42bc473f0d097c93e210c240` — reject unsupported node choices even in explicit DIRECT mode, protect SNI aliases.
- S2: `593e7cddc360cf7f51d9fdc988e6cf8fd99aea96` — node/route product wiring; independent HTTP/HTTPS/echo origins and A/B proxy tests; Windows Qt/DPAPI suite added.
- S1: `292df3ba9763414947ec9b5dffa7886c45a00879` — strict subscription-field boundaries and persisted config tests.

Review `docs/CORE_SUBSCRIPTION_PRODUCT_CHAIN_20261019.md`, `docs/CONTINUE_DEVELOPMENT.md`, and `docs/SELF_DEVELOPMENT_PROGRESS.md` for exact commands, source scopes, initial failure evidence, and previous CI links. These files are more authoritative than transient chat progress messages.

## Current technical state and unfinished acceptance

1. S5's Qt HTTPS test client now initiates close through the **actual Qt HttpProxy → Rust → independent proxy → HTTPS target** path and requires authenticated TLS EOF, unwrap and raw EOF; bare TCP truncation must fail. The portable suite retains server-initiated shutdown. The current committed S5 message reports four local proxy-path diagnostics, eight portable tests, 45 CI guards and nine SOCKS4 cases passing, with an explicit Windows Qt hook skip. These local results **do not prove** Windows C++/DPAPI product tests or the full app build on S5.
2. App peer step now exports and preflights the previously built Inspector so SOCKS4 subscription coverage can actually run. Verify that step in *exact source* App CI.
3. Preserve historical failures as failures: S1 Linux dual-stack port collision and Windows SS bind error; S2/S3 Windows independent-origin HTTPS shutdown; S4 Windows four SSLEOFError closures and skipped downstream app build. S4 Linux/macOS/App succeeded, **not** evidence of S5 success. See source docs for run IDs and raw artifacts.
4. Synthetic subscription paths, selected outbound snapshot, A/B switch, ordered routing, DIRECT/REJECT and fail-closed behavior have executable test coverage. Do not conflate the portable JSON host with Windows Qt NodeStore/DPAPI and actual product use.
5. The separately authorized live subscription was privately inspected: 59 VLESS/REALITY entries, 55 also declaring Vision. The production combined async REALITY/Vision path, DirectReady and socket/TLS ownership transfer are still blocked; **no provider connection has been proven**. Never write subscription URLs, tokens or node secrets to Git, CI logs or this document.
6. Official frozen acceptance stays **79 items / 6 fully accepted / 10.83% weighted**. No change to the numerator without complete frozen item evidence.

## Recovery order (highest priority)

1. Read current remote HEAD and CI for exact S5 SHA `0416fe09fce4f4d5599c5a859842331f7783ebb3`; collect Linux, macOS, Windows and App statuses, raw logs and run URLs. CI for earlier SHA does not validate S5.
2. If Windows `ProductQtIntegration` fails, inspect each stage of the real HttpProxy → Rust TLS close exchange and fix **without disabling certificate validation, origin close checks or no-DIRECT-fallback**.
3. Require successful Windows Qt/DPAPI product suite followed by **full native Windows application** build, and all applicable Rust/independent peer jobs. Preserve skips separately.
4. Retest actual subscriber parameter retention and fail-closed behavior; do not claim the provider's REALITY/Vision nodes are executable. Continue to improve protocol-independent product chain before adding protocols.
5. Commit small verified changes frequently to the **same development branch**, with no forced updates, preserving concurrent font work. Append exact source SHA / run URL / outcomes to `docs/CONTINUE_DEVELOPMENT.md` and `docs/SELF_DEVELOPMENT_PROGRESS.md`.

## Session boundary honesty

This checkpoint captures only GitHub-pushed source and reproducible handoff context. No local working copy from a previous transient runtime is available here, so uncommitted private scratch/source cannot be asserted to have been pushed. Do not treat this documentation-only commit as a new executable acceptance.
