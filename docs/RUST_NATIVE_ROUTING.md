# Rust native routing integration

The existing Qt rule editor now feeds executable rules to Swirl Rust when
`SWIRL_USE_RUST_CORE=ON`. No QML, layout, styling or system proxy settings change.

## Executed subset

| Existing rule | Rust matcher | Behavior |
|---|---|---|
| DOMAIN | domain | Case-insensitive exact host |
| DOMAIN-SUFFIX | domain_suffix | Exact domain or label-bounded suffix |
| DOMAIN-KEYWORD | domain_keyword | Case-insensitive ASCII substring |
| IP-CIDR / IP-CIDR6 | cidr | IPv4 / IPv6 destination network |
| SRC-IP-CIDR | source_cidr | Accepted TCP peer / validated UDP client IP |
| DST-PORT | destination_port | One destination port, 1–65535 |
| MATCH | match | Unconditional rule at its original position |

Rules execute from top to bottom. Supported policies are DIRECT, REJECT,
SWIRL (the selected node), and validated manual select groups. The unmatched default remains the selected node.
Qt generates collision-free IDs for its explicit direct/reject exits. Unsupported
unselected imported nodes remain stored but are not activated.

Rule mode executes custom rules. Global and direct modes keep stored rules but
do not execute them. Switching back to rule mode validates the entire active rule
list before an atomic update. Even unsupported rules below MATCH are rejected;
they are not silently lost. Running rule rows are supplied through the existing
engine interface. Hit counts remain unavailable, displayed as “—”.

Process rules, rule providers/MRS/GeoIP, automatic smart routing, automatic policy groups,
port ranges, regex and logical expressions are not implemented here. Active
unsupported rules fail with their index. Existing smart-routing sessions remain
blocked in the Rust preview until their provider semantics are implemented.

## Manual policy groups

The existing group editor's `select` groups map to typed Rust selectors. Members
must be concrete supported nodes, DIRECT or REJECT. The first ordered member is
selected on startup; an explicitly supplied `default-selected` must name a member.
The unchanged editor has no separate live group-member selection control. Its
global node buttons continue to change SWIRL, not every custom group.

The local Rust control API provides
`{"op":"select_group","handle":1,"id":"group-id","member":"node-id"}`.
It atomically changes only that selector for new connections. Snapshots report
selector IDs and their selected members. Existing streams/UDP associations keep
their original plan. Invalid groups or members do not advance the generation or
mutate the plan. Node selection now also holds the same write lock throughout
its read/modify/commit to avoid lost concurrent selector changes.

The mapper validates every declared group and member in rule mode. Duplicate
names/members, missing nodes, nested groups, unsupported protocols, arbitrary
extra fields, non-member defaults and automatic group types fail explicitly.
Inactive groups remain stored in global/direct mode. Limits are 128 selectors,
512 members per selector and 512 total executable nodes (Qt reserves two slots
for built-in policies). There is no fallback, retry/replay, group health probing,
load balancing or imported group nesting. A failed selected member stays failed.

The editor unconditionally stores its default health URL and 300-second interval
on manual groups too. Only these exact defaults or absent values are accepted as
inactive metadata; no request is scheduled. Other health-check settings are
rejected rather than silently accepted. This is a narrow manual-selector subset,
not full select-group compatibility including health-check side effects.

Qt loopback tests route through authenticated member B while global selection is
A, then verify global mode uses A and a failed B never falls back. Rust and the
independent Python API peer test live selection, old TCP survival, invalid-member
rollback and no implicit DIRECT; UDP tests retain the old selector snapshot.

## DNS and connection lifetime

IP rules from Qt trigger bounded system DNS only when an unresolved destination
actually reaches a resolving CIDR rule. An earlier domain/port/final match never
does this lookup. An explicit `no-resolve` suffix skips unresolved names; it can
use an address obtained by an earlier resolving rule. The second matching pass
does not let earlier no-resolve rules consume a later rule's DNS result.

The first resolver address is used for matching and pinned for the actual dial
or proxy request. Another DNS address is not retried under that address's policy,
and the upstream does not independently re-resolve that target. HTTP Host and
application TLS bytes remain untouched. This favors deterministic routing over
multi-address availability; Happy Eyeballs and policy-aware address retries are
not implemented. A failed route lookup fails the TCP request or drops/counts the
UDP datagram, without falling through to another policy.

For compatibility with earlier schema-1 Swirl IR, a raw `cidr` matcher missing
`resolve` retains literal-IP-only behavior. The Qt mapper explicitly writes
`resolve: true` unless `no-resolve` was supplied. All unknown matcher fields,
including fields on the final matcher, fail validation.

Existing TCP connections and UDP associations retain immutable configuration
snapshots. New connections use a successfully committed mode/selection/rule
update. UDP rules use the existing four-task preparation bound. Unsupported
UDP exits drop rather than falling through to another node or DIRECT; this is an
explicit Swirl limitation, not a claim of complete Mihomo rule compatibility.

## Evidence and scope

Rust tests cover matching order, suffix boundaries, lazy DNS, no-resolve ordering,
mixed DNS answers, source/port matching, unknown fields, TCP rule updates with an
open stream and UDP port routing. Qt loopback tests verify rule/global/direct
mode changes, actual direct/selected-node forwarding, rejection without target
access, mode rollback on invalid rules and rule-row presentation. An independent
Python VLESS peer verifies that a resolving rule sends the chosen IP upstream.

The Windows legacy node UI test also checks per-request origin exit counts.
It no longer assumes the compatibility probe's historical two connections when
the isolated probe uses a native engine. DIRECT and the other exit must remain
unused; success alone is insufficient.

CI now includes native Rust and independent protocol peers on Linux and macOS,
in addition to Windows Rust/Qt. Job configuration alone is not evidence of a pass;
consult the run for the delivered commit. Mobile targets and desktop UI on those
platforms are not validated by these jobs. No private subscription is used by CI.

Rule terminology and no-resolve reference:
https://wiki.metacubex.one/en/config/rules/ . This documents an implemented subset;
it does not claim complete provider, process, DNS or policy-group compatibility.
Manual-group terminology: https://wiki.metacubex.one/en/config/proxy-groups/select/ .
