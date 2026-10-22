# Rust GUI rule-mode connection preflight

The normal Windows product loads a saved `Proxy/routingMode` value. Its
default legacy value is `rule`, which asks for the smart rule library when
no native document routing profile is active. The current Rust product does
not execute that library. Node selection and isolated node
probes validate with `global` routing, so a supported node could be selected
and probed while the later live connection failed with a combined error.

The live connection now validates the exact candidate session before it
starts or stops the Rust engine. A blocked session can retain the user's new
node selection but leaves the saved routing mode, existing engine, and Windows
system proxy unchanged. The
error identifies the unsupported setting. The user can explicitly choose
**代理 → 策略 → 全局代理** in the existing interface and connect again. This
does not turn on the Windows system proxy or imply independent internet access.

Independent implementation references consulted before the change:

- [sing-box checks a candidate before reloading](https://github.com/SagerNet/sing-box/blob/testing/cmd/sing-box/cmd_run.go#L187-L199).
- [Mihomo reports provider node parse errors instead of silently skipping them](https://github.com/MetaCubeX/mihomo/blob/Meta/adapter/provider/provider.go#L416-L427).

The Windows Qt regression uses a synthetic SOCKS5 peer and isolated test
storage. It verifies that saved rule mode is preserved and opens no listener,
then explicitly selects global mode and completes an HTTP request through the
in-process Rust proxy. It also checks separate messages for compatibility,
TUN, LAN, and metered settings. A successful local fixture is not a private
provider or Mihomo-independent internet acceptance result.
