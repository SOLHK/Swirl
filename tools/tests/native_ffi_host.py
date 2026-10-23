#!/usr/bin/env python3
"""Bounded JSON test host that actually loads Swirl's exported C ABI.

Configuration arrives only on stdin. This is a ctypes caller of the Rust
dynamic library, not Controller.dispatch, a proxy implementation, or Qt.
Every successfully started handle is stopped before the process exits.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys


CAPACITY = 1024 * 1024
GUARD = 32


class FfiHostError(RuntimeError):
    """Only fixed, credential-free codes may cross this host boundary."""


class NativeHost:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.library_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        # extern "C" is cdecl, including on Windows; do not use WinDLL/stdcall.
        self.library = ctypes.CDLL(str(self.path))
        self.version = self.library.swirl_core_abi_version
        self.version.argtypes = []
        self.version.restype = ctypes.c_uint32
        self.abi_version = int(self.version())
        if self.abi_version != 1:
            raise FfiHostError("FfiHostAbiVersion")
        pointer_bytes = ctypes.sizeof(ctypes.c_void_p)
        if ctypes.sizeof(ctypes.c_size_t) != pointer_bytes or ctypes.sizeof(ctypes.c_ssize_t) != pointer_bytes:
            raise FfiHostError("FfiHostIntegerWidth")
        self.export = self.library.swirl_core_command
        byte_pointer = ctypes.POINTER(ctypes.c_uint8)
        self.export.argtypes = [byte_pointer, ctypes.c_size_t, byte_pointer, ctypes.c_size_t]
        self.export.restype = ctypes.c_ssize_t
        self.calls = 0
        self.handle = None
        self.started = self.stopped = 0
        self.commands = {}
        self.boundaries = self.check_boundaries()
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.library_hash:
            raise FfiHostError("FfiHostLibraryChanged")

    def raw(self, data, *, input_null=False, output_null=False, output_capacity=CAPACITY):
        # Even rejected ABI calls receive initialized, nonoverlapping allocations
        # covering their declared lengths. There is no unsafe pointer probe.
        source = (ctypes.c_uint8 * max(1, len(data))).from_buffer_copy(data or b"\0")
        destination = (ctypes.c_uint8 * (CAPACITY + GUARD))()
        ctypes.memset(destination, 0xA5, ctypes.sizeof(destination))
        self.calls += 1
        written = int(self.export(None if input_null else source, len(data),
                                  None if output_null else destination, output_capacity))
        if written > output_capacity or written > CAPACITY:
            raise FfiHostError("FfiHostOutputLength")
        unchanged_at = max(0, written)
        if bytes(destination[unchanged_at:]) != b"\xa5" * (CAPACITY + GUARD - unchanged_at):
            raise FfiHostError("FfiHostOutputCanary")
        return written, bytes(destination[:max(0, written)])

    def invoke(self, data):
        if not 0 < len(data) <= CAPACITY:
            raise FfiHostError("FfiHostInputSize")
        written, output = self.raw(data)
        if not 0 < written <= CAPACITY:
            raise FfiHostError("FfiHostCommandReturn")
        try:
            result = json.loads(output.decode("utf-8"))
        except (UnicodeError, ValueError):
            raise FfiHostError("FfiHostOutputJson") from None
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise FfiHostError("FfiHostOutputShape")
        return result

    def check_boundaries(self):
        result = {}
        query = b'{"op":"snapshot","handle":0}'
        cases = (
            ("null_input_rejected", query, {"input_null": True}),
            ("null_output_rejected", query, {"output_null": True}),
            ("empty_input_rejected", b"", {}),
            ("input_over_1mib_rejected", b" " * (CAPACITY + 1), {}),
            ("output_below_1mib_rejected", query, {"output_capacity": CAPACITY - 1}),
        )
        for name, data, options in cases:
            written, _ = self.raw(data, **options)
            if written != -1:
                raise FfiHostError("FfiHostBoundaryRejection")
            result[name] = True
        if self.invoke(query + b" " * (CAPACITY - len(query))) != {"ok": False, "error": "UnknownHandle"}:
            raise FfiHostError("FfiHostMaximumInput")
        result["input_exactly_1mib_accepted"] = True
        for name, data in (
            ("invalid_utf8_rejected", b"\xff"),
            ("unknown_private_field_redacted",
             b'{"op":"snapshot","handle":0,"password":"synthetic-ffi-private-value"}'),
        ):
            if self.invoke(data) != {"ok": False, "error": "CommandInvalidOrUnsupported"}:
                raise FfiHostError("FfiHostBoundaryJson")
            result[name] = True
        result["output_capacity_1mib_and_canary"] = True
        return result

    def identity(self):
        return {"ok": True, "control_boundary": "exported_c_abi_dynamic_library",
                "library_file": self.path.name, "library_sha256": self.library_hash,
                "abi_version": self.abi_version, "usize_bytes": ctypes.sizeof(ctypes.c_size_t),
                "isize_bytes": ctypes.sizeof(ctypes.c_ssize_t),
                "input_capacity": CAPACITY, "output_capacity": CAPACITY,
                "buffer_boundaries": self.boundaries, "ffi_command_calls": self.calls,
                "command_counts": dict(self.commands), "handles_started": self.started,
                "handles_stopped": self.stopped, "active_handles": int(self.handle is not None)}

    def command(self, value):
        if not isinstance(value, dict) or not isinstance(value.get("op"), str):
            return {"ok": False, "error": "FfiHostInputShape"}
        if value == {"op": "host_identity"}:
            return self.identity()
        if "handle" in value:
            return {"ok": False, "error": "FfiHostExplicitHandle"}
        operation = {"status": "snapshot", "select_node": "select"}.get(value["op"], value["op"])
        if operation not in {"start", "stop", "snapshot", "select", "select_group", "configure",
                             "probe_start", "probe_status", "probe_cancel"}:
            return {"ok": False, "error": "FfiHostOperation"}
        command = {**value, "op": operation}
        if operation == "start":
            if self.handle is not None:
                return {"ok": False, "error": "CoreAlreadyStarted"}
        elif self.handle is None:
            return {"ok": False, "error": "CoreMissing"}
        else:
            command["handle"] = self.handle
        result = self.invoke(json.dumps(command, separators=(",", ":")).encode("utf-8"))
        self.commands[operation] = self.commands.get(operation, 0) + 1
        if result["ok"] and operation == "start":
            handle = result.get("handle")
            if type(handle) is not int or not 0 < handle < 2**64 or not isinstance(result.get("status"), dict):
                raise FfiHostError("FfiHostStartShape")
            self.handle = handle
            self.started += 1
        elif result["ok"] and operation == "stop":
            self.handle = None
            self.stopped += 1
        # Preserve the actual exported function's response, including its handle.
        # Configure/select need not manufacture transport-runtime's extra status.
        return result

    def close(self):
        if self.handle is not None and not self.command({"op": "stop"})["ok"]:
            raise FfiHostError("FfiHostStop")


def main():
    host = None
    exit_code = 0
    try:
        host = NativeHost(os.environ["SWIRL_NATIVE_LIBRARY"])
        while line := sys.stdin.buffer.readline(CAPACITY + 2):
            data = line[:-1] if line.endswith(b"\n") else line
            if len(data) > CAPACITY:
                raise FfiHostError("FfiHostInputSize")
            try:
                value = json.loads(data.decode("utf-8"))
            except (UnicodeError, ValueError):
                result = {"ok": False, "error": "FfiHostInputJson"}
            else:
                result = host.command(value)
            print(json.dumps(result, separators=(",", ":")), flush=True)
    except Exception as error:
        # Never print exception text or stdin; loader/parser messages may contain
        # paths, private JSON, or credentials supplied by callers.
        code = str(error) if isinstance(error, FfiHostError) else "FfiHostFailure"
        print(code, file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        if host is not None:
            try:
                host.close()
            except Exception:
                print("FfiHostStop", file=sys.stderr, flush=True)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
