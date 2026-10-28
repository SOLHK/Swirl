"""Verify that a Windows EXE embeds all 18 frames of its generated Swirl ICO.

Read-only binary inspection using Python's standard library. This verifies the
resource chain; actual taskbar appearance and display DPI still need native QA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

EXPECTED_SIZES = [16, 20, 24, 28, 30, 32, 36, 40, 42, 48, 56, 60, 64, 72, 80, 96, 128, 256]


def unpack(data, fmt, offset):
    if offset < 0 or offset + struct.calcsize(fmt) > len(data):
        raise ValueError(f"Truncated binary structure at {offset}")
    return struct.unpack_from(fmt, data, offset)


def read_ico(data):
    if unpack(data, "<HHH", 0) != (0, 1, len(EXPECTED_SIZES)):
        raise ValueError("Swirl ICO must contain exactly 18 icon frames")
    frames = []
    for index, size in enumerate(EXPECTED_SIZES):
        width, height, colors, reserved, planes, depth, length, offset = unpack(data, "<BBBBHHII", 6 + 16 * index)
        metadata = (width or 256, height or 256, colors, reserved, planes, depth, length)
        dib_length = 40 + size * size * 4 + ((size + 31) // 32) * 4 * size
        if metadata != (size, size, 0, 0, 1, 32, dib_length):
            raise ValueError(f"ICO frame {index} is not the expected {size}px BGRA DIB")
        if offset < 6 + 16 * len(EXPECTED_SIZES) or offset + length > len(data):
            raise ValueError("ICO frame points outside its payload")
        payload = data[offset:offset + length]
        if unpack(payload, "<IiiHHI", 0) != (40, size, 2 * size, 1, 32, 0):
            raise ValueError(f"Invalid {size}px ICO DIB header")
        frames.append((metadata, payload))
    return frames


def read_pe_icons(data):
    if data[:2] != b"MZ":
        raise ValueError("Not a PE executable")
    pe, = unpack(data, "<I", 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Missing PE signature")
    machine, count, _, _, _, optional_size, _ = unpack(data, "<HHIIIHH", pe + 4)
    optional = pe + 24
    if machine != 0x8664 or unpack(data, "<H", optional)[0] != 0x20B:
        raise ValueError("Expected x64 PE32+ executable")
    resource_rva, resource_length = unpack(data, "<II", optional + 112 + 16)
    sections = [unpack(data, "<IIII", optional + optional_size + 40 * index + 8) for index in range(count)]

    def file_offset(rva, length):
        for _, address, raw_size, raw in sections:
            if address <= rva and rva + length <= address + raw_size:
                offset = raw + rva - address
                if offset + length <= len(data):
                    return offset
        raise ValueError(f"Resource RVA {rva:#x} has no complete file-backed section")

    base = file_offset(resource_rva, resource_length)
    resources = []

    def visit(relative, path):
        if len(path) >= 3:
            raise ValueError("Unexpected PE resource directory depth")
        directory = base + relative
        named, ids = unpack(data, "<HH", directory + 12)
        for index in range(named + ids):
            key, target = unpack(data, "<II", directory + 16 + 8 * index)
            entry_path = path + [key]
            if target & 0x80000000:
                visit(target & 0x7FFFFFFF, entry_path)
            else:
                rva, length, _, _ = unpack(data, "<IIII", base + target)
                offset = file_offset(rva, length)
                resources.append((entry_path, data[offset:offset + length]))

    visit(0, [])
    return ([(path, blob) for path, blob in resources if path[0] == 14],
            [(path, blob) for path, blob in resources if path[0] == 3])


def verify(ico, executable):
    frames = read_ico(ico)
    groups, icons = read_pe_icons(executable)
    if len(groups) != 1 or len(icons) != len(frames):
        raise ValueError("Expected one RT_GROUP_ICON and exactly 18 RT_ICON resources")
    path, group = groups[0]
    if len(path) != 3 or unpack(group, "<HHH", 0) != (0, 1, len(frames)) or len(group) != 6 + 14 * len(frames):
        raise ValueError("Invalid EXE RT_GROUP_ICON header")
    results = []
    for index, (metadata, payload) in enumerate(frames):
        width, height, colors, reserved, planes, depth, length, resource_id = unpack(group, "<BBBBHHIH", 6 + 14 * index)
        actual = (width or 256, height or 256, colors, reserved, planes, depth, length)
        candidates = [blob for icon_path, blob in icons if icon_path == [3, resource_id, path[2]]]
        results.append({"size": EXPECTED_SIZES[index], "resource_id": resource_id,
                        "group_metadata_matches": actual == metadata,
                        "rt_icon_bytes_match_ico": len(candidates) == 1 and candidates[0] == payload})
    return {"success": all(row["group_metadata_matches"] and row["rt_icon_bytes_match_ico"] for row in results),
            "frame_count": len(frames), "group_resource_path": path, "frames": results,
            "ico_sha256": hashlib.sha256(ico).hexdigest(), "exe_sha256": hashlib.sha256(executable).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ico", required=True, type=Path)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    try:
        report = verify(options.ico.read_bytes(), options.exe.read_bytes())
    except (OSError, ValueError) as error:
        report = {"success": False, "failure": str(error)}
    report.update({"ico": str(options.ico.resolve()), "exe": str(options.exe.resolve()),
                   "scope": "Exact ICO/EXE resource equality; native taskbar and physical DPI acceptance are separate"})
    if options.output:
        options.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
