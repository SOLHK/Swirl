# Minimal 849/850 reproduction from the completed B1 experiment

This reduces the already measured stage-1 cases to two self-authored fonts,
two coordinates per font and their independent reverse processes. It is not
a new experiment or an additional native pass. Each font has three glyphs;
the measured rectangle is GID 2. No Apple font is needed.

Run from the repository root on macOS, with Python's fonttools dependency
installed. The output directory must be new. This preserves the full four
native channels, raw binary64 values, exact source-table identity and reverse
replay. No source metric is replaced.

```bash
python - <<'PY'
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/swirl_vf/platform").resolve()))
from fontTools.ttLib import TTFont
from b1_metric_fixture import build_fixture
from b1_metric_discriminator import load_native_json, validate_raw, verify_replay, measured

out = Path("build/b1-minimal-849-850").resolve()
out.mkdir(parents=True, exist_ok=False)
binary = out / "probe"
subprocess.run([
    "xcrun", "swiftc", "-O",
    "tools/swirl_vf/platform/b1_metric_probe.swift",
    "-o", str(binary),
], check=True)

results = []
for upem in (1000, 1024):
    font_path = out / f"upem{upem}.ttf"
    font = build_fixture(upem, "gvar")
    font.save(font_path)
    font.close()
    with TTFont(font_path, recalcTimestamp=False) as font:
        entry = {
            "upem": upem,
            "sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
            "table_sha256": {
                str(tag): hashlib.sha256(font.reader[tag]).hexdigest()
                for tag in font.reader.keys()
            },
        }
    requests = [
        {"id": "minimum", "axes": {"WDTH": 0, "HGHT": -1}, "point_size": upem},
        {"id": "default", "axes": {"WDTH": 0, "HGHT": 0}, "point_size": upem},
    ]
    native = []
    for order, ordered in (("forward", requests), ("reverse", list(reversed(requests)))):
        request_path = out / f"upem{upem}-{order}-requests.json"
        report_path = out / f"upem{upem}-{order}-raw.json"
        request_path.write_text(json.dumps(ordered) + "\n")
        subprocess.run([
            str(binary), "--font", str(font_path),
            "--requests", str(request_path), "--output", str(report_path),
        ], check=True)
        report = load_native_json(report_path.read_bytes())
        validate_raw(report, entry, ordered)
        native.append(report)
    assert verify_replay(*native) == 2
    for row in native[0]["observations"]:
        expected = 850 if row["id"] == "minimum" else 1000
        quantity = measured(row["direct_advances"]["vertical_vector"][0], upem, row["point_size"])
        results.append({"upem": upem, "case": row["id"], "expected_design_units": expected,
                        "quantity": quantity,
                        "strict_error": abs(quantity["design_units"] - expected),
                        "strict_pass": abs(quantity["design_units"] - expected) <= 1/32})
(out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))
raise SystemExit(0 if all(row["strict_pass"] for row in results) else 1)
PY
```

On the completed macOS 27.0.1 B1 run, the corresponding observations were:

| UPEM | Default | Minimum | Minimum expected | Strict minimum result |
| ---: | ---: | ---: | ---: | --- |
| 1000 | 1000 | 849 | 850 | FAIL |
| 1024 | 1000 | 850 | 850 | PASS for this one scalar |

The reduction deliberately exits 1 when the observed discrepancy remains.
A different OS result must be preserved and investigated; the historical
expectation is not a substitute for newly measured values.

See [STAGE1_RESULTS.md](STAGE1_RESULTS.md) for the actual completed native run,
and [FOLLOWUP_RESULTS.md](FOLLOWUP_RESULTS.md) for the independently frozen
550 fixture-coordinate observations that distinguish metric sources and
reject a universal minus-one explanation. Passing the UPEM 1024 endpoint does
not establish precision at fractional coordinates or acceptance of any Apple
original.
