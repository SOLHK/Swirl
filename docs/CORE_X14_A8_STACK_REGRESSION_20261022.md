# X1.4-A8: Windows Hysteria2 stack regression

## Recovered source and retained failures

The designated branch was still at `b6fba1827b0136c50123dab41fa4cb1c79a9ebce`.
Its parent is A7 `de115093691ff00371b6e8313e4f1bb832c1fa3a`.
The previous workspace was copied into a separate checkout; its uncommitted
files and other development branches were not changed.

- [A7 run 39793316607](https://github.com/SOLHK/Swirl/actions/runs/39793316607):
  Windows Hysteria2 ran 17 methods with 14 failures and `0xC00000FD`.
- [b6 run 39801982069](https://github.com/SOLHK/Swirl/actions/runs/39801982069):
  the outer `Box::pin` was insufficient. Windows still ran 17 methods with 13
  failures, including the same stack overflow. The imported HTTPUpgrade wrong
  UUID rejection also raised Winsock 10053 instead of `ConnectionResetError`.

## Production correction

`swirl-protocol/src/lib.rs::connect_selected` now performs the original common
validation, then dispatches Hysteria2 and TUIC directly into their owned boxed
connector futures. Ordinary stream protocols use `connect_stream_selected`.
QUIC no longer enters the large TCP/TLS/REALITY dispatch poll frame.

Boxing a future bounds its inline state but does not move its synchronous
`poll()` stack frames onto the heap. On this unoptimized Linux build, the old
mixed dispatch poll frame reserves about 291 KB. The split dispatcher reserves
about 37 KB and never calls the ordinary-stream poll path for QUIC. These are
build-specific observations, not ABI size guarantees or a throughput benchmark.

Shared transport conflict, TLS validation, failure codes and connection budgets
remain in place. One owned box is selected per public connection; no detached
task, new queue, retry, unbounded allocation, thread stack setting, linker stack
setting, TLS relaxation or alternate proxy core was introduced. Dropping the
future still drops the exact protocol owners in the caller's runtime.

Primary references reviewed before implementation:

- [Rust Box::pin](https://doc.rust-lang.org/std/boxed/struct.Box.html#method.pin)
- [Tokio runtime future boxing](https://github.com/tokio-rs/tokio/blob/master/tokio/src/runtime/runtime.rs)
- [Quinn connection ownership and drop](https://github.com/quinn-rs/quinn/blob/main/quinn/src/connection.rs)
- [Hysteria2 official protocol](https://v2.hysteria.network/docs/developers/Protocol/)

The HTTPUpgrade negative test now recognizes `ConnectionAbortedError` as well
as `ConnectionResetError`. This applies only to rejection cases. Received
application bytes, timeout, or any independent-origin request still fail.
Successful-response and clean-close assertions are unchanged. See
[Microsoft WSAECONNABORTED](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)
and [Python connection exceptions](https://docs.python.org/3/library/exceptions.html#ConnectionAbortedError).

## Reproduction and permanent regression

The same unchanged `hysteria2-client` example was built from A7, b6 and the split
fix using Rust 1.99.1, unoptimized dev profile, debug info off. The pinned
Hysteria v2.13.0 server was SHA256-verified; all origins were independent local
TCP/UDP services, and all credentials were disposable synthetic values.

| Measured main-thread stack limit | A7 TCP / wrong password | b6 TCP / wrong password | Split TCP / wrong password | UDP |
|---|---|---|---|---|
| 1,048,576 bytes | overflow / overflow | overflow / overflow | clean 64 KiB echo / explicit auth rejection | all three pass 3072-byte echo |
| 786,432 bytes | overflow / overflow | overflow / overflow | clean 64 KiB echo / explicit auth rejection | all three pass |
| 655,360 bytes and below | overflow | overflow | overflow in unchanged standalone driver | overflow |

The last row is retained: this work does not claim arbitrary tiny-stack support.
The earlier window's Linux b6 success was not substituted for the fresh failing
reproduction in this build.

`native_client_stack.py` creates a fresh launcher, sets both actual
`RLIMIT_STACK` values to 1 MiB, records them, and execs the unchanged client.
It avoids `preexec_fn` in the multithreaded Python fixture. The permanent Linux
CI gate runs all original 17 methods this way, including 4 MiB bidirectional
data, QUIC/TLS/password authentication, UDP fragmentation/DNS, TLS/pin failures,
normal close, restart/reconnect, IPv6 and concurrent connections. No test data,
timeout or authentication assertion was reduced. `run_hysteria2_official.py`
requires exactly the original 17 methods, no failures/errors and zero skips.

The additional lifecycle driver uses one current-thread Tokio runtime and
checks cleanup before process exit:

1. Poll the public connection until pending with live QUIC tasks, then drop it.
   TLS/authentication completion is deliberately not claimed for this phase.
2. Authenticate against the real server, exchange 4096 bytes, then cancel an
   owned stream read. Its QUIC/H3 tasks must return to the zero-task baseline.
3. Reconnect in that same runtime, exchange 65536 bytes, complete normal EOF,
   and again require zero live tasks. The independent target must observe two
   closed connections and exactly 69632 bytes.

Both default-stack and measured 1 MiB lifecycle tests passed locally. The
original standalone main remains unchanged; increasing a thread stack is not
the fix.

## Local commands and observed results

Executed in `core` with `--locked` (the populated cache also allowed `--offline`):

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --workspace --lib --bins --examples --locked
```

All gates passed; workspace tests reported **640 passed, 0 failed, 0 ignored**,
including the doctest. Public inline futures measured 216/224/224 bytes for
ordinary/explicit-transport/stream-UDP entry points, guarded by a 1024-byte
ceiling. This size guard complements the actual constrained-stack network test.

```text
HY2_CONSTRAINED_STACK=1 python tools/tests/run_hysteria2_official.py
python -m unittest -v test_hysteria2_lifecycle
HY2_CONSTRAINED_STACK=1 python -m unittest -v test_hysteria2_lifecycle
python -m unittest -v test_imported_transports_xray
```

Local results: original HY2 **17/17, zero skips** at 1 MiB; lifecycle **1/1** at
each stack setting; imported transports **5/5**, including all 12 negative
transport/SNI/UUID combinations with zero independent-origin requests. The
Linux results do not substitute for Windows execution of Winsock 10053.

Source hashes, executable hashes, actual stack observations, failure receipts
and lifecycle counters are in [the local evidence](evidence/x14-a8/).
Final Windows/macOS/Linux conclusions must be read from the six completed jobs
on the fix commit in [the native protocol workflow](../.github/workflows/rust-native-protocols.yml).
Queued/running jobs and older commits are not accepted as final-SHA evidence.

## Scope of acceptance

The original 17 methods include explicit negative probes for the pinned
server's half-close behavior and 4096-byte UDP reply limit. Passing those
methods records those limitations; it does not convert them into supported
features. This is Core and dynamic C ABI interoperability against controlled
official servers. Public suppliers, weak-network/long-duration performance,
physical Windows GUI, system-proxy ownership and TUN product acceptance are
separate. See [the Qt handoff](CORE_X14_A8_QT_HANDOFF_20261022.md).
