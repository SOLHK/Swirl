#!/usr/bin/env python3
"""Build the locked official Xray/REALITY peer; every failure is fatal.

This build-only fixture never fetches subscriptions and is not a product
dependency. All protocol code comes from the unmodified, verified upstream
checkout. The small Go entry point is Swirl's loopback test instrumentation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tools" / "tests" / "xray_peer"


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock_path = FIXTURE / "lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 1,
        "status": "building",
        "started_unix": int(time.time()),
        "platform": platform.platform(),
        "lock_sha256": sha256(lock_path),
        "helper_source_sha256": sha256(FIXTURE / "main.go"),
        "xray": lock["xray"],
        "reality": lock["reality"],
    }
    env = os.environ.copy()
    # No implicit toolchain substitution, private-module exceptions or checksum
    # bypass. Public Go checksum verification remains enabled for every module.
    env.update({"GOTOOLCHAIN": "local", "GOFLAGS": "", "GOWORK": "off",
                "GOPROXY": "https://proxy.golang.org", "GOSUMDB": "sum.golang.org",
                "GONOSUMDB": "", "GONOPROXY": "", "GOPRIVATE": "", "CGO_ENABLED": "0"})
    for key, name in (("GOCACHE", "go-build-cache"), ("GOMODCACHE", "go-module-cache")):
        if not env.get(key):
            env[key] = str(output / name)
    with (output / "build.log").open("w", encoding="utf-8", newline="\n") as log:
        def run(command: list[str], cwd: Path = ROOT, timeout: int = 900) -> str:
            log.write(json.dumps({"cwd": str(cwd), "argv": command}) + "\n")
            log.flush()
            try:
                result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                        encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as error:
                partial = error.stdout or b""
                if isinstance(partial, bytes):
                    partial = partial.decode("utf-8", errors="replace")
                log.write(partial + "\nCOMMAND TIMED OUT\n")
                log.flush()
                raise
            log.write(result.stdout)
            log.write(f"\nexit_code={result.returncode}\n")
            log.flush()
            if result.returncode:
                raise RuntimeError(f"command failed ({result.returncode}): {command[0]} {command[1]}; see build.log")
            return result.stdout.strip()

        def verified_source(source: Path) -> None:
            identity = lock["xray"]
            if run(["git", "rev-parse", "HEAD"], source) != identity["commit"]:
                raise RuntimeError("Xray commit mismatch")
            if run(["git", "rev-parse", "HEAD^{tree}"], source) != identity["tree"]:
                raise RuntimeError("Xray tree mismatch")
            if run(["git", "remote", "get-url", "origin"], source) != identity["repository"]:
                raise RuntimeError("Xray source is not from the locked official remote")
            if run(["git", "status", "--porcelain", "--untracked-files=all"], source):
                raise RuntimeError("Xray checkout must be completely unmodified")
            for name, field in (("go.mod", "go_mod_sha256"), ("go.sum", "go_sum_sha256")):
                if sha256(source / name) != identity[field]:
                    raise RuntimeError(f"locked Xray {name} checksum mismatch")

        try:
            manifest["swirl_source_commit"] = run(["git", "rev-parse", "HEAD"])
            manifest["swirl_worktree_status"] = run(["git", "status", "--porcelain", "--untracked-files=all"])
            actual_go = run([args.go, "env", "GOVERSION"])
            if actual_go != lock["go_version"]:
                raise RuntimeError(f"expected {lock['go_version']}, found {actual_go}")
            manifest["go_version"] = actual_go
            run([args.go, "version"])
            source = args.source.resolve() if args.source else output / "upstream"
            if not source.exists():
                source.mkdir(parents=True)
                run(["git", "init", "--quiet"], source)
                run(["git", "remote", "add", "origin", lock["xray"]["repository"]], source)
                run(["git", "-c", "core.autocrlf=false", "fetch", "--depth", "1", "origin",
                     lock["xray"]["commit"]], source)
                run(["git", "-c", "core.autocrlf=false", "checkout", "--detach", "FETCH_HEAD"], source)
            verified_source(source)
            # Download against upstream's original lock, then compare the exact
            # REALITY module identity before compiling any executable.
            run([args.go, "mod", "download"], source)
            reality = json.loads(run([args.go, "mod", "download", "-json",
                                      lock["reality"]["module"]], source))
            for field, expected in (("Path", "module"), ("Version", "version"),
                                    ("Sum", "sum"), ("GoModSum", "go_mod_sum")):
                if reality.get(field) != lock["reality"][expected]:
                    raise RuntimeError(f"REALITY {field} identity mismatch")
            run([args.go, "mod", "verify"], source)
            run([args.go, "list", "-m", "-json", "all"], source)
            extension = ".exe" if os.name == "nt" else ""
            xray = output / ("xray" + extension)
            peer = output / ("reality-peer" + extension)
            xray_command = [args.go, "build", "-mod=readonly", "-trimpath", "-buildvcs=true"]
            run([*xray_command, "-o", str(xray), "./main"], source)
            ldflags = (f"-X main.xrayCommit={lock['xray']['commit']} "
                       f"-X main.realityVersion={lock['reality']['version']}")
            manifest["helper_source_sha256"] = sha256(FIXTURE / "main.go")
            peer_command = [args.go, "build", "-mod=readonly", "-trimpath", "-buildvcs=false", "-ldflags", ldflags]
            run([*peer_command, "-o", str(peer), str(FIXTURE / "main.go")], source)
            if sha256(FIXTURE / "main.go") != manifest["helper_source_sha256"] or sha256(lock_path) != manifest["lock_sha256"]:
                raise RuntimeError("peer source or lock changed during its build")
            manifest["binaries"] = {}
            for name, path in (("xray", xray), ("reality_peer", peer)):
                version_info = run([args.go, "version", "-m", str(path)])
                (output / f"{name}-go-version.txt").write_text(version_info + "\n", encoding="utf-8")
                if lock["reality"]["version"] not in version_info or lock["reality"]["sum"] not in version_info:
                    raise RuntimeError(f"{name} binary omitted the locked REALITY build identity")
                if name == "xray" and (f"vcs.revision={lock['xray']['commit']}" not in version_info or "vcs.modified=false" not in version_info):
                    raise RuntimeError("Xray executable VCS build identity mismatch")
                manifest["binaries"][name] = {"file": path.name, "sha256": sha256(path)}
            manifest["xray_version_output"] = run([str(xray), "version"])
            manifest["peer_version_output"] = json.loads(run([str(peer), "--version"]))
            if (manifest["peer_version_output"].get("xray_commit") != lock["xray"]["commit"] or
                manifest["peer_version_output"].get("reality_version") != lock["reality"]["version"] or
                manifest["peer_version_output"].get("go_version") != actual_go):
                raise RuntimeError("helper executable Xray identity mismatch")
            # Re-run both builds to distinct output paths with identical fixed
            # inputs/flags. Cache reuse is allowed; equality is actually checked
            # rather than inferred from the flags. The duplicate is temporary.
            manifest["reproducible_rebuild"] = {}
            for name, command, entry in (("xray", xray_command, "./main"),
                                         ("reality_peer", peer_command, str(FIXTURE / "main.go"))):
                repeated = output / ("repeated-" + manifest["binaries"][name]["file"])
                try:
                    run([*command, "-o", str(repeated), entry], source)
                    digest = sha256(repeated)
                    expected = manifest["binaries"][name]["sha256"]
                    manifest["reproducible_rebuild"][name] = {"first_sha256": expected, "repeated_sha256": digest, "matches": digest == expected}
                    if digest != expected:
                        raise RuntimeError(f"{name} repeated build differs from original")
                finally:
                    repeated.unlink(missing_ok=True)
            if sha256(FIXTURE / "main.go") != manifest["helper_source_sha256"]:
                raise RuntimeError("helper source changed during repeated builds")
            # Builds cannot rewrite the imported source or the original module
            # lock. A cache corruption check also runs after both compilations.
            verified_source(source)
            run([args.go, "mod", "verify"], source)
            manifest["status"] = "success"
        except BaseException as error:
            manifest["status"] = "failure"
            manifest["error"] = str(error)
            log.write(f"BUILD FAILED: {error}\n")
            raise
        finally:
            manifest["finished_unix"] = int(time.time())
            (output / "build-manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "success", "manifest": str(output / "build-manifest.json")}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--go", default="go", help="Go executable; must match the locked version")
    parser.add_argument("--source", type=Path, help="Existing clean official checkout at the locked SHA")
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
