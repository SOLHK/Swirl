# Swirl Core X1.1 verified baseline

Base `bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29` from `work/subscription-import-20261021`. The network fixes (`b8aa4f6`) and rule routing (`b6dce3a`) are ancestors. `work/core-completion-20261017` has diverged with separate monitoring work. Independent worktree; no changes to main or parallel branches.

Linux x86_64, Rust 1.99.1: `cargo fmt --all -- --check`, `cargo check --workspace --locked`, `cargo clippy --workspace --all-targets --locked -- -D warnings`, and `cargo test --workspace --locked` passed. 359 Rust tests and one doctest passed; zero failures. This does not establish Qt, Windows, macOS, public-node or VMess interoperability acceptance.

The baseline contains native VLESS/REALITY/Vision, Trojan, Shadowsocks AEAD, SOCKS and HTTP CONNECT connectors. Xray JSON conversion is limited; VMess has no native outbound variant. gRPC/H2/XHTTP must not be silently converted to TCP. Full Xray global configuration is not executable.

References: Xray-core `92ccc939aaf4f8965f369cf0b142e005aeaa11d5` (MPL-2.0); V2Fly core (MIT); sing-box `dfb80349bf5779ec0a3f834c9ec2794345bff8f0` (GPL-3.0-or-later, inspected only). No implementation was copied. No relevant installed Rust-specific engineering skill was found. Existing repository development contract was applied.
