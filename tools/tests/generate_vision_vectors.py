#!/usr/bin/env python3
"""Independent, public synthetic Vision wire vectors; never imports Rust code."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "core/crates/swirl-protocol/tests/fixtures"
)
UUID = bytes.fromhex("00112233445566778899aabbccddeeff")


def frame_vectors() -> str:
    # Each direction starts with UUID; subsequent frame headers do not repeat it.
    cases = [
        ("first_empty_continue", True, 0, b"", b""),
        ("first_padding_only", True, 0, b"", bytes.fromhex("55aaff")),
        ("first_continue", True, 0, b"hello", bytes.fromhex("deadbeef")),
        ("first_end", True, 1, b"protected", bytes.fromhex("010203")),
        ("first_direct_request", True, 2, bytes.fromhex("1703030003616263"), b"\x00\xff"),
        ("first_empty_end", True, 1, b"", b""),
        ("later_empty_continue", False, 0, b"", b""),
        ("later_continue", False, 0, bytes.fromhex("001602ffff"), b"\x7e"),
        ("later_end", False, 1, b"tail", b""),
        ("later_direct_request", False, 2, b"opaque", b"\xa5\x5a"),
    ]
    lines = [
        "# Public synthetic Vision framing vectors v1.",
        "# UUID: 00112233445566778899aabbccddeeff",
        "# name|first (1/0)|command|content hex|padding hex|wire hex",
    ]
    for name, first, command, content, padding in cases:
        wire = (UUID if first else b"") + struct.pack(
            "!BHH", command, len(content), len(padding)
        ) + content + padding
        lines.append(
            f"{name}|{int(first)}|{command}|{content.hex()}|{padding.hex()}|{wire.hex()}"
        )
    return "\n".join(lines) + "\n"


def varint(value: int) -> bytes:
    result = bytearray()
    while value >= 0x80:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result)


def flow_vectors() -> str:
    lines = [
        "# Public synthetic VLESS v0 request Addons vectors v1.",
        "# name|flow kind|flow text|complete length-prefixed Addons hex",
    ]
    for name, kind, flow in [
        ("missing", "none", ""),
        ("empty", "some", ""),
        ("vision", "some", "xtls-rprx-vision"),
    ]:
        # Protobuf field 1, length-delimited (wire type 2), followed by its bytes.
        encoded = flow.encode("utf-8")
        addons = varint((1 << 3) | 2) + varint(len(encoded)) + encoded if flow else b""
        assert len(addons) <= 255
        wire = bytes([len(addons)]) + addons
        lines.append(f"{name}|{kind}|{flow}|{wire.hex()}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = {
        FIXTURES / "vision-v1.txt": frame_vectors(),
        FIXTURES / "flow-v1.txt": flow_vectors(),
    }
    for path, contents in expected.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents.encode("ascii"))
        elif not path.is_file() or path.read_bytes() != contents.encode("ascii"):
            raise SystemExit(f"fixture differs: {path.name}; review before using --write")
    print("Vision vectors: 10 frame and 3 flow cases " + ("written" if args.write else "match"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
