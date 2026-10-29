"""Run the unchanged native client with a measured 1 MiB Linux main-stack limit.

Use a fresh Python process followed by exec, rather than preexec_fn from the
multithreaded official-server fixture. No thread or linker stack is enlarged.
"""
import json
import os
from pathlib import Path
import sys

STACK_BYTES = 1024 * 1024
MARKER = "SWIRL_TEST_STACK="


def client_command(binary):
    if os.environ.get("HY2_CONSTRAINED_STACK") != "1":
        return [str(binary)]
    if sys.platform != "linux":
        raise RuntimeError("ConstrainedStackRequiresLinux")
    return [sys.executable, str(Path(__file__).resolve()), str(binary)]


def stack_receipt(stderr):
    values = [json.loads(line[len(MARKER):]) for line in stderr.splitlines()
              if line.startswith(MARKER)]
    if os.environ.get("HY2_CONSTRAINED_STACK") == "1":
        if len(values) != 1 or values[0] != {
                "soft_bytes": STACK_BYTES, "hard_bytes": STACK_BYTES}:
            raise AssertionError("ConstrainedStackNotMeasured")
        return values[0]
    if values:
        raise AssertionError("UnexpectedStackOverride")
    return None


if __name__ == "__main__":
    if sys.platform != "linux" or len(sys.argv) != 2:
        raise SystemExit("usage: native_client_stack.py CLIENT (Linux only)")
    import resource
    binary = str(Path(sys.argv[1]).resolve(strict=True))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_STACK, (STACK_BYTES, STACK_BYTES))
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    print(MARKER + json.dumps({"soft_bytes": soft, "hard_bytes": hard}),
          file=sys.stderr, flush=True)
    os.execv(binary, [binary])
