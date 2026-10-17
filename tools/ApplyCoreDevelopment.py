"""Apply the reviewed Rust CI gates using the existing scoped GitHub App job.

The only writable file is .github/workflows/rust-core.yml. The update enables
its existing jobs on this development branch, adds the already implemented
DoH, SOCKS4, WebSocket and automatic-policy peer suites, and runs fixed public-network
checks with an evidence artifact on Linux. The current stage adds negative DNS
and isolated native-outbound probe and connection-stage regressions alongside the existing SOCKS4
and WS Qt forwarding peers. It does not change permissions, secrets,
existing actions, release jobs, pull-request triggers or any product source.

Run ``python tools/ApplyCoreDevelopment.py --check`` to run the safety tests and
review the exact diff without writing. With no arguments, writes are restricted
to this repository's existing development workflow and push ref. The caller
already owns committing and pushing the change through its GitHub App token.
"""

import argparse
from collections.abc import Mapping
import difflib
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPOSITORY = "SOLHK/Swirl"
DEVELOPMENT_REF = "refs/heads/work/core-completion-20261017"
WORKFLOW = Path(".github/workflows/rust-core.yml")
CALLER_WORKFLOW = (
    f"{REPOSITORY}/.github/workflows/core-development.yml@{DEVELOPMENT_REF}"
)
WINDOWS_STATUS_GUARD = "          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n"
ADDITIONAL_TESTS = (
    "test_dns_https.py",
    "test_socks4.py",
    "test_websocket_transport.py",
    "test_core_development.py",
)
POLICY_TEST = "test_policy_groups.py"
DNS_PROBE_TESTS = ("test_dns_negative.py", "test_native_probe.py", "test_connection_stages.py")
QT_PEER_TESTS = (
    "test_socks4.py Socks4Integration.test_qt_imported_socks4_and_4a_data_path",
    "test_websocket_transport.py WebSocketTransportTests.test_qt_vless_websocket_data_path",
)
PUBLIC_PROBE = Path("tools/Verify-PublicRustCore.py")
PUBLIC_VALIDATION_STEPS = """      - name: Native public HTTPS and DoH verification
        if: runner.os == 'Linux'
        run: python ../tools/Verify-PublicRustCore.py --harness target/release/swirl-api --output ../CORE_PUBLIC_NETWORK.json
      - name: Preserve public network evidence
        if: always() && runner.os == 'Linux'
        uses: actions/upload-artifact@v4
        with:
          name: Swirl-Core-Public-Network
          path: CORE_PUBLIC_NETWORK.json
          retention-days: 7
"""


def _replace_checked(source: str, before: str, after: str, label: str,
                     intermediate: str | None = None) -> str:
    """Accept only an exact reviewed historical or final block, once."""
    historical = (before,) if intermediate is None else (before, intermediate)
    previous = sum(source.count(block) for block in historical)
    updated = source.count(after)
    if previous == 1 and updated == 0:
        original = next(block for block in historical if source.count(block) == 1)
        return source.replace(original, after, 1)
    if previous == 0 and updated == 1:
        return source
    raise ValueError(f"Rust CI {label} has drifted or is ambiguous; review required")


def _previous_workflow(source: str) -> str:
    """Return a bounded, idempotent update; validate all blocks before any write."""
    stage_counts = (
        source.count(f"          python ../tools/tests/{POLICY_TEST}\n"),
        source.count('          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n'),
        *(source.count(f"          python tools/tests/{test}\n") for test in QT_PEER_TESTS),
    )
    if stage_counts not in ((0, 0, 0, 0), (2, 1, 1, 1)):
        raise ValueError("Rust CI policy/Qt stage is only partially present; review required")
    source = _replace_checked(
        source,
        "  push:\n    branches: [test, main]\n",
        "  push:\n    branches: [test, main, work/core-completion-20261017]\n",
        "push branch list",
    )
    anchor = "          python ../tools/tests/test_dns_tls.py\n"
    portable_tail = "  windows-rust:\n"
    portable_tests = "".join(
        f"          python ../tools/tests/{name}\n" for name in ADDITIONAL_TESTS
    )
    source = _replace_checked(
        source,
        anchor + portable_tail,
        anchor + portable_tests + f"          python ../tools/tests/{POLICY_TEST}\n" + PUBLIC_VALIDATION_STEPS + portable_tail,
        "portable peer menu",
        intermediate=anchor + portable_tests + PUBLIC_VALIDATION_STEPS + portable_tail,
    )
    windows_tail = "          python ../tools/tests/test_subscription_capture.py\n"
    windows_tests = "".join(
        f"          python ../tools/tests/{name}\n" + WINDOWS_STATUS_GUARD
        for name in ADDITIONAL_TESTS
    )
    source = _replace_checked(
        source,
        anchor + WINDOWS_STATUS_GUARD + windows_tail,
        anchor + WINDOWS_STATUS_GUARD + windows_tests + f"          python ../tools/tests/{POLICY_TEST}\n" + WINDOWS_STATUS_GUARD + windows_tail,
        "Windows peer menu",
        intermediate=anchor + WINDOWS_STATUS_GUARD + windows_tests + windows_tail,
    )
    portable_environment = '          export SWIRL_RUST_HARNESS="$PWD/target/release/swirl-api"\n'
    first_test = '          python ../tools/tests/test_rust_core.py\n'
    source = _replace_checked(
        source,
        portable_environment + first_test,
        portable_environment + '          export SWIRL_RUST_INSPECTOR="$PWD/target/release/swirl-inspect"\n' + first_test,
        "portable inspector identity",
    )
    # The currently reviewed workflow ends with this exact Qt command. Requiring
    # the entire tail prevents partially added/duplicated commands being accepted.
    qt_anchor = "          python tools/tests/test_rust_core.py RustCoreIntegration.test_vless_qt_data_path\n"
    qt_after = qt_anchor + WINDOWS_STATUS_GUARD + "".join(
        f"          python tools/tests/{test}\n" + WINDOWS_STATUS_GUARD for test in QT_PEER_TESTS
    )
    if source.count(qt_anchor) != 1:
        raise ValueError("Rust CI Qt peer menu has drifted or is ambiguous; review required")
    if source.endswith(qt_after):
        return source
    if source.endswith(qt_anchor):
        return source[:-len(qt_anchor)] + qt_after
    raise ValueError("Rust CI Qt peer menu has drifted or is ambiguous; review required")


def updated_workflow(source: str) -> str:
    """Extend only the two reviewed test menus; reject partial/duplicate additions."""
    policy = f"          python ../tools/tests/{POLICY_TEST}\n"
    portable = policy + PUBLIC_VALIDATION_STEPS
    windows = policy + WINDOWS_STATUS_GUARD + "          python ../tools/tests/test_subscription_capture.py\n"
    added_portable = "".join(f"          python ../tools/tests/{name}\n" for name in DNS_PROBE_TESTS)
    added_windows = "".join(f"          python ../tools/tests/{name}\n" + WINDOWS_STATUS_GUARD for name in DNS_PROBE_TESTS)
    portable_after = policy + added_portable + PUBLIC_VALIDATION_STEPS
    windows_after = policy + WINDOWS_STATUS_GUARD + added_windows + "          python ../tools/tests/test_subscription_capture.py\n"
    counts = tuple(source.count(f"          python ../tools/tests/{name}\n") for name in DNS_PROBE_TESTS)
    if counts == (2, 2, 2):
        if source.count(portable_after) != 1 or source.count(windows_after) != 1:
            raise ValueError("Rust CI DNS/probe menus have drifted; review required")
        source = source.replace(portable_after, portable, 1).replace(windows_after, windows, 1)
    elif counts == (2, 2, 0):
        # The verified DNS stage predates the connection-stage peer suite.
        command = "          python ../tools/tests/test_connection_stages.py\n"
        old_portable = portable_after.replace(command, "")
        old_windows = windows_after.replace(command + WINDOWS_STATUS_GUARD, "")
        if source.count(old_portable) != 1 or source.count(old_windows) != 1:
            raise ValueError("Rust CI previous DNS/probe menus have drifted; review required")
        source = source.replace(old_portable, portable, 1).replace(old_windows, windows, 1)
    elif counts != (0, 0, 0):
        raise ValueError("Rust CI DNS/probe stage is only partially present; review required")
    source = _previous_workflow(source)
    source = _replace_checked(source, portable, portable_after, "portable DNS/probe menu")
    return _replace_checked(source, windows, windows_after, "Windows DNS/probe menu")


def validate_context(environment: Mapping[str, str]) -> None:
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": DEVELOPMENT_REF,
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_WORKFLOW_REF": CALLER_WORKFLOW,
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            # Do not print environment values: this helper never reads tokens.
            raise ValueError(f"Workflow writes are disabled in this {name} context")


def prepare_update(repository: Path) -> tuple[Path, str, str]:
    repository = repository.resolve()
    path = repository / WORKFLOW
    if path.is_symlink() or path.resolve() != path:
        raise ValueError("Rust CI target must be a regular file within the repository")
    if not path.is_file():
        raise ValueError("The existing Rust CI workflow is required")
    # Git checkouts may use CRLF on Windows. Both styles represent the same
    # workflow; writes still occur only in the existing Linux App job.
    before = path.read_text(encoding="utf-8")
    after = updated_workflow(before)
    for name in (*ADDITIONAL_TESTS, POLICY_TEST, *DNS_PROBE_TESTS):
        if not (repository / "tools/tests" / name).is_file():
            raise ValueError(f"Required CI suite is missing: {name}")
    if not (repository / PUBLIC_PROBE).is_file():
        raise ValueError("The required native public-network verification script is missing")
    return path, before, after


def apply_update(repository: Path, environment: Mapping[str, str]) -> bool:
    validate_context(environment)
    path, before, after = prepare_update(repository)
    if before == after:
        return False
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".rust-core-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(after.encode("utf-8"))
        temporary_path.chmod(path.stat().st_mode)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Run safety tests and show the diff without writes"
    )
    options = parser.parse_args()
    repository = Path(__file__).resolve().parent.parent
    if not options.check:
        validate_context(os.environ)
    # This is an explicit, mandatory gate in the existing App job; a missing or
    # failing safety suite prevents any workflow mutation or automatic commit.
    subprocess.run(
        [sys.executable, str(repository / "tools/tests/test_core_development.py")],
        cwd=repository,
        check=True,
    )
    _, before, after = prepare_update(repository)
    print(f"Reviewed workflow: {WORKFLOW.as_posix()}", flush=True)
    print(f"Before SHA-256: {hashlib.sha256(before.encode()).hexdigest()}", flush=True)
    print(f"After SHA-256:  {hashlib.sha256(after.encode()).hexdigest()}", flush=True)
    if options.check:
        sys.stdout.writelines(
            difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile=WORKFLOW.as_posix(), tofile=WORKFLOW.as_posix(),
            )
        )
    else:
        changed = apply_update(repository, os.environ)
        print("Applied reviewed Rust CI update" if changed else "Rust CI gates already current")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Core development validation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
