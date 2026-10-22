# Swirl-VF 2026-10-20: strict geometry triage checkpoint

This checkpoint preserves the latest concurrent Rust Core work; only Swirl-VF files change.

Original font, verified privately (never committed): 61,473,880 bytes;
SHA-256 `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`;
32 faces with 47,102 GIDs each.

Exact-source macOS baseline: [run 39296798626](https://github.com/SOLHK/Swirl/actions/runs/39296798626),
font commit `8b22ce6064d5de2c39a1d125208710c4c87037d3`.
Original comparison: 910/1088 pass and 178/1088 fail at strict 1/32 FUnit.
Failing GIDs and counts: 6 (33), 7 (33), 104 (33), 170 (33),
3262 (33), 19177 (13). Their respective maximum errors (FUnit)
are 160.5310, 223.9368, 190.2167, 11.8759, 2.1464, 19.5183.

The original cyclic-contour comparator already handles shifted starts.
The default-axis-only successes in five GIDs concentrate suspicion on
varying composite rotation/translation composition and local axis propagation;
a Type-0 factor interpolation edge is also a hypothesis. Neither is a
confirmed root cause until independently authored native macOS tests prove it.

`platform/triage_source_projection.py` extracts a non-outline summary from
the existing exact-source native JSON. Use it in a private workspace with
`python tools/swirl_vf/platform/triage_source_projection.py source-projection.json --output triage.json`.
The 1/32 FUnit tolerance and original test selector remain unaltered.

**Acceptance gate remains RED**: original 178 failures, CoreText metric gate,
true avar coordinate mapping, all 32 face and three-axis gvar/HVAR/VORG
reconstruction, Windows 11/DirectWrite and Qt real-font validation are
unresolved. No final `Swirl-VF.ttc` exists. This checkpoint does not imply a
new native run or repaired production algorithm. It introduces no copyrighted
outlines or fonts into GitHub.
