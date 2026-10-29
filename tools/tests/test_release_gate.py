"""Fast source-level validation of the guarded promotion workflow."""
from pathlib import Path
import re
import textwrap

GATE = Path(__file__).resolve().parents[2] / ".github/workflows/guard-production-release.yml"

def main():
    source = GATE.read_text(encoding="utf-8")
    assert ("\\" + "$" + "{{") not in source, "Actions expressions must not be escaped"
    for value in ("production-gate:", "SOURCE_BRANCH:", "LABEL_PRESENT:",
                  "CANDIDATE_SHA:", "RELEASE_OWNER:", "issues/{pr}/events?",
                  "current == sha", '"release-approved"',
                  '"Build Swirl Qt Quick UI (Preview)"',
                  '"Swirl Rust Core"', '"Validate Qt-only source tree"',
                  '"Qt HTTP client security"', 'latest["updated_at"]',
                  'max(completed_at)'):
        assert value in source, f"Missing release control: {value}"
    assert source.count("$" + "{{") == 10, "Unexpected GitHub workflow expressions"
    program = re.search(r"^          python - <<'PY'\n(.*?)^          PY$", source, re.M | re.S)
    assert program, "Missing bounded inline release-verification program"
    compile(textwrap.dedent(program.group(1)), str(GATE), "exec")
    assert "workflow_dispatch" not in source, "Manual dispatch must not produce a misleading production gate"
    print("Production gate expressions and inline Python syntax validated.")

if __name__ == "__main__":
    main()
