"""Bounded, independent reader for Apple's published HVGL 3.1 / HVPM 1.

The binary reader implements the published storage format.  The experimental
renderer is deliberately a separate class: parsing success is not evidence of
CoreText-equivalent rendering. Isolated Type-2 tangent projection is an
explicitly enabled experimental path with separate native evidence; unsupported
tangent types remain errors rather than being treated as ordinary corners.

References (retrieved 2026-10-19):
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html
https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvpm.html
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import math
import struct
from typing import Union

import numpy as np


class FormatError(ValueError):
    pass


class UnsupportedRendering(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise FormatError(message)


class Reader:
    def __init__(self, data: bytes, start=0, end=None):
        self.data = data
        self.start = start
        self.end = len(data) if end is None else end
        require(0 <= self.start <= self.end <= len(data), "invalid byte range")

    def range(self, offset: int, length: int) -> int:
        require(offset >= self.start and length >= 0 and offset + length <= self.end,
                f"out-of-bounds read at {offset}, length {length}, range {self.start}:{self.end}")
        return offset

    def unpack(self, fmt: str, offset: int):
        self.range(offset, struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, offset)

    def array(self, dtype: str, count: int, offset: int, *, finite=False):
        dt = np.dtype(dtype)
        self.range(offset, count * dt.itemsize)
        out = np.frombuffer(self.data, dt, count, offset)
        if finite:
            require(bool(np.isfinite(out).all()), f"non-finite value at {offset}")
        return out


@dataclass(frozen=True)
class Shape:
    index: int
    axis_count: int
    path_sizes: tuple[int, ...]
    blends: tuple[int, ...]
    master: np.ndarray
    delta: np.ndarray

    @property
    def tree_parts(self):
        return 1

    @property
    def tree_axes(self):
        return self.axis_count


@dataclass(frozen=True)
class SparseTransforms:
    master_rows: np.ndarray
    master_values: np.ndarray
    extreme_indices: np.ndarray
    extreme_values: np.ndarray


@dataclass(frozen=True)
class Composite:
    index: int
    axis_count: int
    tree_parts: int
    tree_axes: int
    maximum_extrema: int
    subparts: tuple[tuple[int, int, int], ...]
    column_starts: np.ndarray
    master_rows: np.ndarray
    master_values: np.ndarray
    extreme_rows: np.ndarray
    extreme_values: np.ndarray
    translations: SparseTransforms
    rotations: SparseTransforms


Part = Union[Shape, Composite]


class PartMap:
    def __init__(self, data: bytes | None = None):
        self.ranges: list[tuple[int, int, int]] = []
        if data is not None:
            r = Reader(data)
            version, flags, offset = r.unpack("<HHI", 0)
            require(version == 1 and flags == 0, "unsupported HVPM version or flags")
            require(offset >= 8 and offset % 4 == 0, "bad HVPM range offset")
            count, = r.unpack("<I", offset)
            r.range(offset + 4, count * 12)
            previous_end = -1
            for i in range(count):
                a, b, destination = r.unpack("<III", offset + 4 + i * 12)
                require(previous_end < a <= b, "overlapping, unsorted or empty HVPM range")
                require(destination + b - a <= 0xFFFFFFFF, "HVPM destination overflows uint32")
                self.ranges.append((a, b, destination))
                previous_end = b
        self.starts = [a for a, _, _ in self.ranges]

    def map(self, index: int) -> int:
        i = bisect_right(self.starts, index) - 1
        if i >= 0:
            a, b, destination = self.ranges[i]
            if index <= b:
                return index - a + destination
        return index


class HVGL:
    def __init__(self, data: bytes, hvpm: bytes | None = None):
        self.data = data
        self.reader = Reader(data)
        major, minor, flags, count, offset, glyphs, unused = self.reader.unpack("<HHIIIII", 0)
        require((major, minor) == (3, 1), f"unsupported HVGL version {major}.{minor}")
        require(flags == 0 and unused == 0, "unsupported HVGL flags/reserved field")
        require(0 <= glyphs <= count <= 1_000_000, "invalid or excessive HVGL part count")
        require(offset >= 24 and offset % 8 == 0, "unaligned HVGL part index")
        offsets = self.reader.array("<u4", count + 1, offset).astype(np.uint64)
        require(bool((offsets[1:] >= offsets[:-1]).all()), "nonmonotonic part offsets")
        require(int(offsets[0]) >= (count + 1) * 4, "part data overlaps part index")
        require(int(offsets[-1]) + offset <= len(data), "part index exceeds HVGL table")
        self.major, self.minor = major, minor
        self.part_count, self.glyph_count = count, glyphs
        self.index_offset = offset
        self.offsets = offsets + offset  # The stored base is the index, NOT the table.
        self.part_map = PartMap(hvpm)
        self._cache: dict[int, Part] = {}
        for a, b, destination in self.part_map.ranges:
            require(b < count and destination + b - a < count, "HVPM part outside HVGL")

    def part(self, index: int, *, remap=True) -> Part:
        require(0 <= index < self.part_count, f"bad part index {index}")
        if remap:
            index = self.part_map.map(index)
        if index not in self._cache:
            self._cache[index] = self._parse_part(index)
        return self._cache[index]

    def _parse_part(self, index: int) -> Part:
        start, end = int(self.offsets[index]), int(self.offsets[index + 1])
        r = Reader(self.data, start, end)
        flags, axes = r.unpack("<HH", start)
        require(flags in (0, 1), f"unsupported flags {flags} in part {index}")
        if flags == 0:
            require(start % 8 == 0, f"unaligned shape {index}")
            _, _, paths, segments = r.unpack("<HHHH", start)
            path_sizes = tuple(int(x) for x in r.array("<u2", paths, start + 8))
            require(sum(path_sizes) == segments, f"path/segment count mismatch in shape {index}")
            blends = tuple(int(x) for x in r.array("u1", segments, start + 8 + 2 * paths))
            require(all(x <= 4 for x in blends), f"unknown blend in shape {index}")
            m_offset = (start + 8 + 2 * paths + segments + 7) & ~7
            # Empty shapes have no Float64 payload and need not contain extra padding.
            if segments == 0:
                m_offset = min(m_offset, end)
            master = r.array("<f8", 4 * segments, m_offset, finite=True).reshape(segments, 4)
            delta = r.array("<f8", 8 * axes * segments, m_offset + 32 * segments,
                            finite=True).reshape(2 * axes, segments, 4)
            return Shape(index, axes, path_sizes, blends, master, delta)
        require(start % 4 == 0, f"unaligned composite {index}")
        h = r.unpack("<18H", start)
        (_, axes, subcount, tree_parts, tree_axes, max_extrema,
         m_axes, e_axes, m_trans, m_rot, e_trans, e_rot, *offsets) = h
        require(tree_parts >= 1 + subcount and tree_axes >= axes,
                f"invalid tree counts in composite {index}")
        require(max_extrema >= axes * 2, f"bad maximum extrema in composite {index}")
        p_sub, p_col, p_ma, p_ea, p_trans, p_rot = (start + 4 * x for x in offsets)
        for p in (p_sub, p_col, p_ma, p_ea, p_trans, p_rot):
            require(p >= start + 36 and p <= end, f"bad section offset in composite {index}")
        r.range(p_sub, subcount * 8)
        subparts = tuple(r.unpack("<IHH", p_sub + 8 * i) for i in range(subcount))
        for child, part_row, axis_row in subparts:
            require(child < self.part_count and part_row < tree_parts - 1,
                    f"invalid subpart reference in composite {index}")
            require(axis_row <= tree_axes - axes, f"bad subpart axis offset in composite {index}")
        cols = r.array("<u2", 2 * axes + 1, p_col)
        p_rows = p_col + (2 * axes + 1) * 2
        mr = r.array("<u2", m_axes, p_rows)
        er = r.array("<u2", e_axes, p_rows + m_axes * 2)
        require(int(cols[0]) == 0 and int(cols[-1]) == e_axes,
                f"CSC sentinel mismatch in composite {index}")
        require(bool((cols[1:] >= cols[:-1]).all()), f"unsorted CSC columns in composite {index}")
        self._check_rows(mr, tree_axes - axes, f"master axes in part {index}")
        for col in range(2 * axes):
            self._check_rows(er[int(cols[col]):int(cols[col + 1])], tree_axes - axes,
                             f"extremum axes in part {index}, column {col}")
        mv = r.array("<f4", m_axes, p_ma, finite=True)
        ev = r.array("<f4", e_axes, p_ea, finite=True)
        trans = self._transforms(r, p_trans, m_trans, e_trans, tree_parts - 1, axes, 2, index)
        rot = self._transforms(r, p_rot, m_rot, e_rot, tree_parts - 1, axes, 1, index)
        return Composite(index, axes, tree_parts, tree_axes, max_extrema,
                         subparts, cols, mr, mv, er, ev, trans, rot)

    @staticmethod
    def _check_rows(rows, size, label):
        require(bool((rows < size).all()), f"row outside structure tree: {label}")
        require(bool((rows[1:] > rows[:-1]).all()), f"duplicate or unsorted rows: {label}")

    def _transforms(self, r, offset, masters, extremes, rows, axes, components, index):
        mv = r.array("<f4", masters * components, offset, finite=True).reshape(masters, components)
        p = offset + masters * components * 4
        ev = r.array("<f4", extremes * components, p, finite=True).reshape(extremes, components)
        p += extremes * components * 4
        ei = r.array("<u2", extremes * 2, p).reshape(extremes, 2)
        mr = r.array("<u2", masters, p + extremes * 4)
        self._check_rows(mr, rows, f"transform masters part {index}")
        require(bool((ei[:, 0] < rows).all()) and bool((ei[:, 1] < axes * 2).all()),
                f"transform index outside tree in part {index}")
        keys = ei[:, 0].astype(np.uint64) * (axes * 2 + 1) + ei[:, 1]
        require(bool((keys[1:] > keys[:-1]).all()), f"unsorted transform indices in part {index}")
        return SparseTransforms(mr, mv, ei, ev)

    def validate(self) -> dict:
        """Decode every part, validate the DAG and all depth-first row offsets."""
        kinds, blend_counts, axis_counts = Counter(), Counter(), Counter()
        active_rotations = []
        for i in range(self.part_count):
            p = self.part(i, remap=False)
            kinds[type(p).__name__] += 1
            axis_counts[f"{type(p).__name__}:{p.axis_count}"] += 1
            if isinstance(p, Shape):
                blend_counts.update(p.blends)
            elif bool(np.any(p.rotations.extreme_values)):
                active_rotations.append(i)

        visiting: set[int] = set()
        depths = {}

        @lru_cache(maxsize=None)
        def walk(index):
            require(index not in visiting, f"cyclic part structure at {index}")
            visiting.add(index)
            p = self.part(index)
            count, axes, mx, depth = 1, p.axis_count, p.axis_count * 2, 1
            if isinstance(p, Composite):
                for child, part_row, axis_row in p.subparts:
                    require(part_row == count - 1 and axis_row == axes - p.axis_count,
                            f"incorrect depth-first offsets in composite {index}")
                    cp, ca, cm, cd = walk(child)
                    count += cp
                    axes += ca
                    mx, depth = max(mx, cm), max(depth, cd + 1)
                require((count, axes, mx) == (p.tree_parts, p.tree_axes, p.maximum_extrema),
                        f"structure header mismatch in composite {index}: computed {count, axes, mx}")
            visiting.remove(index)
            depths[index] = depth
            return count, axes, mx, depth

        for i in range(self.part_count):
            walk(i)
        for a, b, dst in self.part_map.ranges:
            for original in range(a, b + 1):
                o, s = self.part(original, remap=False), self.part(dst + original - a, remap=False)
                require(type(o) is type(s) and o.axis_count == s.axis_count,
                        f"incompatible HVPM replacement for part {original}")
                require(o.tree_parts == s.tree_parts and o.tree_axes == s.tree_axes,
                        f"incompatible HVPM structure for part {original}")
                # Every descendant is checked, including equal aggregate-count trees.
                self._validate_mapping_structure(o, s, set())
        return {"version": [self.major, self.minor], "part_count": self.part_count,
                "glyph_count": self.glyph_count, "kinds": dict(kinds),
                "blend_counts": dict(blend_counts), "axis_counts": dict(axis_counts),
                "max_tree_depth": max(depths.values(), default=0),
                "parts_with_rotation_variations": active_rotations,
                "binary_and_structure_validation": "PASS",
                "apple_render_equivalence": "NOT_TESTED"}

    def _validate_mapping_structure(self, original, substitute, seen):
        pair = original.index, substitute.index
        if pair in seen:
            return
        seen.add(pair)
        require(type(original) is type(substitute) and original.axis_count == substitute.axis_count,
                f"incompatible remapped descendant {pair}")
        if isinstance(original, Composite):
            require(len(original.subparts) == len(substitute.subparts), f"remapped child count {pair}")
            for oc, sc in zip(original.subparts, substitute.subparts):
                self._validate_mapping_structure(self.part(oc[0], remap=False),
                                                 self.part(sc[0], remap=False), seen)


def extrema(values):
    """Negative/positive extremum support weights, in stored column order."""
    a = np.asarray(values, dtype=float)
    require(bool(np.isfinite(a).all()), "non-finite axis coordinate")
    result = np.zeros(len(a) * 2)
    result[::2] = np.maximum(-a, 0)
    result[1::2] = np.maximum(a, 0)
    return result


class ExperimentalRenderer:
    """Research evaluator; NEVER a release/Apple-equivalence oracle.

    Axis deltas are additive. Descendant transforms compose in traversal order:
    a deeper composite rotates an inherited translation before adding its own.
    This was checked against independent native synthetic fixtures. The complete
    source still requires native comparison. Type 2 is an explicit opt-in to the
    separately tested projection rule; Types 3/4 remain unsupported.
    """
    backend = "portable-experimental-unverified"

    def __init__(self, table: HVGL, *, isolated_tangents: bool = False):
        self.table = table
        self.isolated_tangents = isolated_tangents

    def render(self, glyph_id: int, design_location) -> list[np.ndarray]:
        root = self.table.part(glyph_id)
        require(len(design_location) == root.axis_count, "axis count mismatch")
        require(all(math.isfinite(x) and -1 <= x <= 1 for x in design_location),
                "root design coordinates must be within [-1,1]")
        values = np.zeros(root.tree_axes)
        values[:root.axis_count] = design_location
        translations = np.zeros((root.tree_parts, 2))
        rotations = np.zeros(root.tree_parts)
        paths = []
        active = set()

        def compose_transforms(part, part_base, weights):
            # Native experiments distinguish master/extremum composition and
            # rotation-centre interpolation from additive R/T parameters.
            from transform_geometry import blend_transform_rows
            for row, delta in blend_transform_rows(part, weights).items():
                target = part_base + 1 + row
                co, si = math.cos(delta[2]), math.sin(delta[2])
                x, y = translations[target]
                translations[target] = (co*x - si*y + delta[0],
                                        si*x + co*y + delta[1])
                rotations[target] += delta[2]

        def visit(index, part_base, axis_base, parent_matrix):
            if index in active:
                raise FormatError("cycle while rendering")
            active.add(index)
            p = self.table.part(index)
            weights = extrema(values[axis_base:axis_base + p.axis_count])
            angle = rotations[part_base]
            co, si = math.cos(angle), math.sin(angle)
            transform = np.array([[co, -si, translations[part_base, 0]],
                                  [si, co, translations[part_base, 1]], [0, 0, 1]])
            matrix = parent_matrix @ transform
            if isinstance(p, Composite):
                desc = axis_base + p.axis_count
                np.add.at(values, desc + p.master_rows, p.master_values)
                for col in range(p.axis_count * 2):
                    a, b = int(p.column_starts[col]), int(p.column_starts[col + 1])
                    if weights[col] and a != b:
                        np.add.at(values, desc + p.extreme_rows[a:b], p.extreme_values[a:b] * weights[col])
                compose_transforms(p, part_base, weights)
                for child, part_row, axis_row in p.subparts:
                    visit(child, part_base + 1 + part_row, desc + axis_row, matrix)
            else:
                supported = {0, 1, 2} if self.isolated_tangents else {0, 1}
                unsupported = sorted(set(p.blends) - supported)
                if unsupported:
                    raise UnsupportedRendering(f"part {p.index}: tangent blend types {unsupported} need Apple oracle")
                if p.axis_count:
                    coords = p.master + np.tensordot(weights, p.delta, axes=(0, 0))
                else:
                    coords = p.master.copy()
                pos = 0
                for size in p.path_sizes:
                    segment = coords[pos:pos + size].copy()
                    types = p.blends[pos:pos + size]
                    pos += size
                    if size < 3:  # specified by Apple, not a heuristic simplification
                        continue
                    if self.isolated_tangents:
                        from tangent_geometry import resolve_path, TangentGeometryError
                        try:
                            points = resolve_path(segment, types)
                        except TangentGeometryError as error:
                            raise UnsupportedRendering(f"part {p.index}: {error}") from error
                    else:
                        off = segment[:, 2:4].copy()
                        for k, kind in enumerate(types):
                            if kind == 0:
                                parallel = np.clip(segment[k, 0], 0.0, 1.0)
                                segment[k, :2] = (1 - parallel) * off[k - 1] + parallel * off[k]
                        points = segment.reshape(-1, 2)
                    homogeneous = np.column_stack((points, np.ones(len(points))))
                    transformed = (homogeneous @ matrix.T)[:, :2]
                    require(bool(np.isfinite(transformed).all()), "non-finite rendered coordinate")
                    paths.append(transformed)
            active.remove(index)

        visit(glyph_id, 0, 0, np.eye(3))
        return paths
