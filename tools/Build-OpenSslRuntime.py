#!/usr/bin/env python3
"""Build the pinned OpenSSL 3.5 LTS Windows runtime, never borrow host SSL DLLs.

Use a matching compiler/Perl/make environment. VC-WIN64A requires native Windows
Perl, NASM and an x64 Visual Studio developer environment. mingw64 requires a
matching MSYS/Cygwin Perl/make/sh and native x64 MinGW compiler; assembly uses GAS.
Only bin/, licenses/ and openssl-runtime.json are deployable. Sources, compiler
logs and download caches live in the separate sibling <output>-build directory.
The receipt is build evidence/file integrity, not an independent attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

LOCK = Path(__file__).with_name("openssl-runtime.lock.json")
FILES = ("bin/libssl-3-x64.dll", "bin/libcrypto-3-x64.dll",
         "licenses/LICENSE.txt", "licenses/NOTICE.txt")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def safe_file(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not parts or "\\" in relative or ":" in relative or relative.startswith("/")
            or any(part in ("", ".", "..") or part.rstrip(" .") != part
                   or re.search(r'[<>"|?*]', part)
                   or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
                   for part in relative.split("/"))):
        raise ValueError("Unsafe relative file path")
    path = root.joinpath(*parts)
    current = path
    while current != root.parent:
        if current.is_symlink() or (current.exists() and linked(current)):
            raise ValueError("Linked runtime/source paths are forbidden")
        current = current.parent
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes selected root")
    return path


def extract_source(archive: Path, destination: Path, root_name: str) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    seen, total = set(), 0
    with tarfile.open(archive, "r:gz") as source:
        for index, member in enumerate(source):
            if index >= 50000 or not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported archive member")
            name = member.name.rstrip("/") if member.isdir() else member.name
            path = safe_file(destination, name)
            if PurePosixPath(name).parts[0] != root_name or name.casefold() in seen:
                raise ValueError("Unexpected archive root or duplicate member")
            seen.add(name.casefold())
            total += member.size
            if member.size < 0 or total > 1024 * 1024 * 1024:
                raise ValueError("Source archive exceeds its size bound")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, path.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
    return destination / root_name


def pe_machine(path: Path) -> int:
    with path.open("rb") as stream:
        header = stream.read(4096)
    if len(header) < 64 or header[:2] != b"MZ":
        raise ValueError("Runtime is not a PE image")
    offset = struct.unpack_from("<I", header, 60)[0]
    if offset < 64 or offset + 26 > len(header) or header[offset:offset + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    if not struct.unpack_from("<H", header, offset + 22)[0] & 0x2000:
        raise ValueError("Runtime PE is not a DLL")
    if struct.unpack_from("<H", header, offset + 24)[0] != 0x20B:
        raise ValueError("Runtime PE is not PE32+")
    return struct.unpack_from("<H", header, offset + 4)[0]


def notice(lock) -> bytes:
    return ("OpenSSL " + lock["version"] + " runtime built from unmodified official source.\n"
            "OpenSSL project: https://openssl-library.org/\n"
            "Licensed under Apache-2.0; see the unchanged upstream LICENSE.txt.\n"
            "Source: " + lock["source"]["url"] + "\n"
            "Source SHA256: " + lock["source"]["sha256"] + "\n"
            "This provenance notice is written by Swirl, not an upstream NOTICE file.\n"
            "The upstream release archive contains LICENSE.txt and no top-level NOTICE.\n").encode("utf-8")


def probe_runtime(root: Path) -> dict:
    # A fresh isolated process cannot inherit an already loaded ambient libssl.
    # LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR resolves libssl's libcrypto beside it.
    code = r'''
import ctypes,json,os,sys
from pathlib import Path
p=Path(sys.argv[1]).resolve()
with os.add_dll_directory(str(p)):
    crypto=ctypes.CDLL(str(p/"libcrypto-3-x64.dll"),winmode=0x1100)
    ssl=ctypes.CDLL(str(p/"libssl-3-x64.dll"),winmode=0x1100)
    crypto.OpenSSL_version.argtypes=[ctypes.c_int]
    crypto.OpenSSL_version.restype=ctypes.c_char_p
    ssl.TLS_client_method.restype=ctypes.c_void_p
    ssl.SSL_CTX_new.argtypes=[ctypes.c_void_p]
    ssl.SSL_CTX_new.restype=ctypes.c_void_p
    ssl.SSL_CTX_free.argtypes=[ctypes.c_void_p]
    ctx=ssl.SSL_CTX_new(ssl.TLS_client_method())
    ok=bool(ctx)
    if ctx: ssl.SSL_CTX_free(ctx)
    print(json.dumps({"version":crypto.OpenSSL_version(0).decode("ascii"),"tls_context_created":ok}))
'''
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("OPENSSL_", "SSL_CERT_"))}
    env.update(OPENSSL_CONF="NUL", OPENSSL_MODULES=str(root / "bin"),
               OPENSSL_ENGINES=str(root / "bin"),
               PATH=str(root / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"))
    result = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(root / "bin")],
                            env=env, capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)


def runtime_cache_key(lock: dict, target: str, toolchain: dict) -> str:
    identity = {"source_sha256": lock["source"]["sha256"], "recipe_sha256": sha256(Path(__file__)),
                "lock_sha256": sha256(LOCK), "target": target, "toolchain": toolchain}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def validate_runtime(root: Path, lock: dict, target: str, cache_key: str | None = None) -> dict:
    if root.is_symlink() or (root.exists() and linked(root)):
        raise ValueError("Deployable runtime root must not be linked")
    if {path.name for path in root.iterdir()} != {"bin", "licenses", "openssl-runtime.json"}:
        raise ValueError("Unexpected file in deployable runtime root")
    for directory, names in (("bin", {"libssl-3-x64.dll", "libcrypto-3-x64.dll"}),
                             ("licenses", {"LICENSE.txt", "NOTICE.txt"})):
        folder = safe_file(root, directory)
        if not folder.is_dir() or {path.name for path in folder.iterdir()} != names:
            raise ValueError("Unexpected or missing deployable runtime file")
    receipt = read_json(safe_file(root, "openssl-runtime.json"))
    fields = {"schema_version", "status", "version", "target", "source", "signature_verified",
              "recipe_sha256", "lock_sha256", "cache_key", "toolchain", "configure_options", "runtime_probe", "files"}
    if (not isinstance(receipt, dict) or set(receipt) != fields
            or type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != 1
            or receipt.get("status") != "success"
            or receipt.get("version") != lock["version"] or receipt.get("target") != target
            or receipt.get("source") != lock["source"]
            or receipt.get("recipe_sha256") != sha256(Path(__file__))
            or receipt.get("lock_sha256") != sha256(LOCK)
            or receipt.get("signature_verified") is not False
            or receipt.get("configure_options") != [target, "shared", "no-tests"]
            or (cache_key is not None and receipt.get("cache_key") != cache_key)):
        raise ValueError("Runtime source/recipe/target/cache identity mismatch")
    toolchain = receipt.get("toolchain")
    expected_tools = {"compiler", "make", "assembler", "perl"} | ({"shell"} if target == "mingw64" else set())
    if not isinstance(toolchain, dict) or set(toolchain) != expected_tools:
        raise ValueError("Runtime toolchain identity is missing")
    for record in toolchain.values():
        if (not isinstance(record, dict) or set(record) != {"file", "sha256", "version"}
                or not isinstance(record["file"], str) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", record["file"])
                or not isinstance(record["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])
                or not isinstance(record["version"], str) or not 1 <= len(record["version"]) <= 1024):
            raise ValueError("Runtime toolchain receipt is not portable")
    if receipt.get("cache_key") != runtime_cache_key(lock, target, toolchain):
        raise ValueError("Runtime cache identity differs from its inputs")
    files = receipt.get("files")
    if not isinstance(files, dict) or set(files) != set(FILES):
        raise ValueError("Runtime receipt file set differs")
    for relative in FILES:
        path = safe_file(root, relative)
        if not path.is_file() or files[relative] != {"sha256": sha256(path), "size": path.stat().st_size}:
            raise ValueError("Runtime/license file changed after build: " + relative)
        if relative.endswith(".dll") and pe_machine(path) != 0x8664:
            raise ValueError("Runtime DLL architecture must be x64")
    if sha256(root / "licenses/LICENSE.txt") != lock["license_sha256"]:
        raise ValueError("Upstream license was changed")
    if (root / "licenses/NOTICE.txt").read_bytes() != notice(lock):
        raise ValueError("Runtime provenance notice differs")
    observed = probe_runtime(root)
    if (not observed.get("tls_context_created") or not observed.get("version", "").startswith("OpenSSL " + lock["version"] + " ")
            or observed != receipt.get("runtime_probe")):
        raise ValueError("Actual runtime version/TLS initialization mismatch")
    return receipt


def download_source(lock: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    source = lock["source"]
    path = safe_file(folder, source["root_directory"] + ".tar.gz")
    if not path.exists():
        temporary = safe_file(folder, path.name + ".part")
        if not source["url"].startswith("https://"):
            raise ValueError("Source URL must be HTTPS")
        with urlopen(source["url"], timeout=120) as response, temporary.open("wb") as output:
            if not response.url.startswith("https://"):
                raise ValueError("Source download left HTTPS")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise ValueError("Source download exceeds its size bound")
                output.write(chunk)
        if sha256(temporary) != source["sha256"]:
            raise ValueError("Official source archive SHA256 mismatch")
        temporary.replace(path)
    if sha256(path) != source["sha256"]:
        raise ValueError("Cached source archive SHA256 mismatch")
    return path


def tool(name: str, env_name: str | None = None) -> Path:
    selected = os.environ.get(env_name) if env_name else None
    selected = selected or shutil.which(name)
    if not selected or not Path(selected).is_file():
        raise RuntimeError("Required build tool missing: " + name)
    return Path(selected).resolve()


def build(args) -> dict:
    if os.name != "nt":
        raise RuntimeError("This runtime recipe requires Windows")
    lock = read_json(LOCK)
    output = args.output.absolute()
    if output.exists() and linked(output):
        raise ValueError("Output must not be a linked directory")
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    work = output.with_name(output.name + "-build")
    work.mkdir(parents=True, exist_ok=True)
    if linked(work):
        raise ValueError("Build directory must not be linked")
    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C")
    for name in ("CFLAGS", "CPPFLAGS", "LDFLAGS", "CL", "_CL_", "LINK", "_LINK_", "CROSS_COMPILE"):
        env.pop(name, None)
    with (work / "build.log").open("a", encoding="utf-8") as log:
        def run(argv, cwd=work, timeout=1800, allowed=(0,)):
            log.write(json.dumps([str(item) for item in argv]) + "\n"); log.flush()
            result = subprocess.run([str(item) for item in argv], cwd=cwd, env=env,
                                    text=True, encoding="utf-8", errors="replace",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            log.write(result.stdout + "\nexit_code=" + str(result.returncode) + "\n"); log.flush()
            if result.returncode not in allowed:
                raise RuntimeError("Build command failed; see " + str(work / "build.log"))
            return result.stdout.strip()
        perl = tool("perl", "PERL")
        perl_version = run([perl, "-e", 'print "$^O $^V"'])
        tools = {"perl": {"file": perl.name, "sha256": sha256(perl), "version": perl_version}}
        if args.target == "VC-WIN64A":
            if not perl_version.startswith("MSWin32 ") or os.environ.get("VSCMD_ARG_TGT_ARCH") not in ("x64", "amd64"):
                raise RuntimeError("VC-WIN64A requires native Windows Perl and an x64 MSVC developer environment")
            compiler, make, assembler = tool("cl"), tool("nmake"), tool("nasm")
            compiler_version = run([compiler], allowed=(0, 2)).splitlines()[0]
            make_version = run([make, "/?"], allowed=(0, 1)).splitlines()[0]
            assembler_version = run([assembler, "-v"])
            make_args = [make, "/nologo", "build_libs"]
        else:
            posix_platform = perl_version.split()[0]
            if posix_platform not in ("msys", "cygwin"):
                raise RuntimeError("mingw64 requires MSYS/Cygwin Perl; native Strawberry Perl is only for VC-WIN64A")
            compiler, make, assembler = tool("gcc", "CC"), tool("make", "MAKE"), tool("as")
            if run([compiler, "-dumpmachine"]) != "x86_64-w64-mingw32":
                raise RuntimeError("mingw64 requires the x86_64-w64-mingw32 compiler")
            shell = tool("sh")
            shell_output = run([shell, "--version"])
            if shell.parent != perl.parent or make.parent != perl.parent or posix_platform not in shell_output.lower():
                raise RuntimeError("mingw64 Perl/make/sh must use the same POSIX tool directory/platform")
            tools["shell"] = {"file": shell.name, "sha256": sha256(shell), "version": shell_output.splitlines()[0]}
            compiler_version = run([compiler, "-dumpfullversion"])
            make_output = run([make, "--version"])
            if posix_platform not in make_output.lower():
                raise RuntimeError("mingw64 requires matching POSIX GNU make, not native mingw32-make")
            make_version = make_output.splitlines()[0]
            assembler_output = run([assembler, "--version"])
            if "x86_64-w64-mingw32" not in assembler_output:
                raise RuntimeError("mingw64 requires the matching x64 GNU assembler")
            assembler_version = assembler_output.splitlines()[0]
            make_args = [make, "-j", str(args.parallel), "SHELL=" + str(shell).replace("\\", "/"), "build_libs"]
        for name, path, version in (("compiler", compiler, compiler_version), ("make", make, make_version), ("assembler", assembler, assembler_version)):
            tools[name] = {"file": path.name, "sha256": sha256(path), "version": version}
        env["PATH"] = os.pathsep.join(dict.fromkeys(str(path.parent) for path in
                                                    (compiler, make, assembler, perl))) + os.pathsep + env.get("PATH", "")
        cache_key = runtime_cache_key(lock, args.target, tools)
        if safe_file(output, "openssl-runtime.json").exists():
            return validate_runtime(output, lock, args.target, cache_key)
        archive = download_source(lock, work / "archives")
        build_root = Path(tempfile.mkdtemp(prefix=cache_key[:12] + "-", dir=work))
        source = extract_source(archive, build_root / "source", lock["source"]["root_directory"])
        if sha256(source / "LICENSE.txt") != lock["license_sha256"]:
            raise ValueError("Source license differs from locked upstream license")
        build_dir = build_root / "compile"; build_dir.mkdir()
        env["CC"] = compiler.name
        env["PERL"] = str(perl).replace("\\", "/")
        run([perl, (source / "Configure").as_posix(), args.target, "shared", "no-tests",
             "--prefix=C:/Swirl-OpenSSL", "--openssldir=C:/Swirl-OpenSSL/ssl"], build_dir)
        disabled = run([perl, "-I.", "-Mconfigdata", "-e",
                        'print join("\n", sort keys %configdata::disabled)'], build_dir).splitlines()
        if "asm" in disabled:
            raise RuntimeError("OpenSSL assembly must remain enabled")
        run(make_args, build_dir)
        for relative in FILES:
            path = safe_file(output, relative); path.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith("bin/"):
                shutil.copyfile(build_dir / Path(relative).name, path)
            elif relative.endswith("LICENSE.txt"):
                shutil.copyfile(source / "LICENSE.txt", path)
            else:
                path.write_bytes(notice(lock))
        for relative in FILES[:2]:
            if pe_machine(output / relative) != 0x8664:
                raise ValueError("Built runtime is not an x64 Windows DLL")
        observed = probe_runtime(output)
        if not observed.get("tls_context_created") or not observed.get("version", "").startswith("OpenSSL " + lock["version"] + " "):
            raise ValueError("Built runtime version or TLS initialization failed")
        receipt = {"schema_version": 1, "status": "success", "version": lock["version"],
                   "target": args.target, "source": lock["source"], "signature_verified": False,
                   "recipe_sha256": sha256(Path(__file__)), "lock_sha256": sha256(LOCK),
                   "cache_key": cache_key, "toolchain": tools,
                   "configure_options": [args.target, "shared", "no-tests"],
                   "runtime_probe": observed,
                   "files": {name: {"sha256": sha256(output / name), "size": (output / name).stat().st_size} for name in FILES}}
        safe_file(output, "openssl-runtime.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return validate_runtime(output, lock, args.target, cache_key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=("VC-WIN64A", "mingw64"), required=True)
    parser.add_argument("--parallel", type=int, default=min(os.cpu_count() or 1, 8),
                        help="GNU make job count; MSVC nmake builds serially")
    parser.add_argument("--verify-only", action="store_true",
                        help="Validate a deployable receipt/runtime without downloading or looking up build tools")
    args = parser.parse_args()
    if not 1 <= args.parallel <= 64:
        parser.error("--parallel must be between 1 and 64")
    try:
        receipt = (validate_runtime(args.output.absolute(), read_json(LOCK), args.target)
                   if args.verify_only else build(args))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({"status": "success", "root": str(args.output.resolve()),
                      "receipt": str(args.output.resolve() / "openssl-runtime.json"),
                      "version": receipt["version"], "target": receipt["target"], "cache_key": receipt["cache_key"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
