# X1.2-B: retained macOS CI failure and independent relay close repair

## Observed failure

Source: `4606b6df484cd0504014b9bdac6cb237a813c9b3`.

[Full Rust run 39719250362](https://github.com/SOLHK/Swirl/actions/runs/39719250362):
Windows job `119628646906` and Linux job `119628646664` succeeded. macOS job
[`119628647017`](https://github.com/SOLHK/Swirl/actions/runs/39719250362/job/119628647017)
passed fmt, workspace check, clippy, workspace tests and independent protocol
peers, then failed `Subscription to native proxy and target`.

The first failure was `ProductChainIntegration.test_large_fragmented_concurrent_halfclose_and_cancel`.
The retained traceback identifies the independent Python SS relay A, line 306:
`wire.shutdown(socket.SHUT_WR)` raised macOS `OSError` / errno 57 (`ENOTCONN`).
The fixture's `close` assertion at line 351 correctly surfaced the error.
There were nine selected tests: seven passed, one failed and the separate
Windows Qt/DPAPI test was explicitly skipped on macOS.

The subscription result artifact was successfully uploaded. Seven later upload
steps failed because the earlier required failure had skipped their producer
steps and their paths did not exist. These are secondary missing-file errors,
not seven additional protocol failures. The upload conditions and strict
`if-no-files-found: error` settings are unchanged.

The fixture file predates B1 (latest preceding file commit `19afd34fca898615d89796cb8d158b4be17ff2e9`).
This test uses the existing subscription inspector path and independent relay;
B1 did not introduce or modify that shutdown call.

## Minimal repair and negative controls

After the complete upstream stream has reached EOF, the relay sends its final
TCP write shutdown. Darwin may already have completed peer close. The fixture
records this state only for `ENOTCONN` (or Windows `WSAENOTCONN` 10057), then
joins the upload thread and requires its independently observed EOF as well.
An unverified upload EOF remains a fixture assertion failure. Other shutdown
errors remain errors. No production Rust code, timeout, payload assertion,
authentication check, cancellation requirement or upload gate is weakened.

Reference semantics were checked against Apple's primary
[shutdown(2) manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/shutdown.2.html).
The implementation is independent; no upstream implementation was copied.

Four added fixture tests use real authenticated loopback sockets and a separate
echo origin. Every exchange checks payload bytes, exact upload/download counts,
trailing response after half-close and final EOF. Controlled shutdown error
injection reproduces the completed-close race and verifies that EBADF/EIO and
ENOTCONN without a verified upload EOF still fail.

Before the repair the positive ENOTCONN regression failed with the same fixture
boundary (Linux errno 107 represents the same symbolic error); after the repair
all four self-checks passed:

```text
python tools/tests/test_product_subscription_chain.py RelayHalfCloseChecks -v
Ran 4 tests
OK
```

The original six-concurrent-stream, 256 KiB + 17 byte, half-close and active
cancellation test remains intact. A new exact-source macOS Actions run is
required to claim the original CI failure resolved. These Linux fixture checks
do not substitute for macOS, Windows Qt, private-provider or physical-device
acceptance.

## Follow-up: exercise actual SS encryption and reject record truncation

Review requested coverage of the original SS relay, beyond the shared HTTP
fixture path. Inspection established that the old `SsStream.recv` already
translated **all** `Reader.chunk` EOF exceptions to an empty read. Legal SS
record-boundary EOF therefore did set `upload_eof`; it was not falsely rejected
by the first repair. The broader translation did expose a separate flaw:
truncated encrypted headers, payloads and authentication tags also looked like
normal EOF.

The independent Python `Reader.chunk` now offers an explicit
`allow_boundary_eof` option. The default retains its prior EOF-exception
contract. The opt-in returns `None` only when zero bytes of the next encrypted
length have arrived. EOF inside its encrypted length, payload or tag still
raises. The product fixture records a partial upload record and fails its
existing final assertion, regardless of whether write shutdown succeeds.

Three added test methods exercise actual bidirectional SS encryption with
AES-128-GCM, AES-256-GCM and ChaCha20-Poly1305, including authenticated empty
records. All three legal boundary-close cases passed even before this follow-up.
Five injected truncations (1/17-byte encrypted headers, and 18/19/54-byte partial
records) demonstrably failed the new rejection tests before the fix; all are
now rejected without releasing their incomplete plaintext to the origin.
The exact payload, origin payload, byte counts, TAIL and final EOF assertions
remain mandatory. Final fixture result:

```text
python tools/tests/test_product_subscription_chain.py RelayHalfCloseChecks -v
Ran 7 tests
OK
```

These remain Linux real-socket fixture results. A real Rust harness/full
platform workflow result must be reported separately, without relabeling these
fixture controls as Rust or provider-network acceptance.
