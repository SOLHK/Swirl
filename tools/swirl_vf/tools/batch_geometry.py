#!/usr/bin/env python3
"""Batched HVGL design-space geometry for adaptive variable-font reconstruction.

This accelerates an explicitly experimental interpretation; it is not an Apple
oracle. Source component/path identity is retained for every emitted contour.
Unsupported tangent types remain rejected. No user-axis/avar mapping is guessed.
The production builder must still require independent native geometry evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from hvf import Composite, HVGL, UnsupportedRendering, require


@dataclass(frozen=True)
class ContourSource:
    part_index: int
    tree_part_offset: int
    source_path_index: int
    source_segment_start: int


@dataclass
class GeometryBatch:
    # Each path is (sample, alternating on/off point, xy), without rounding.
    paths: list[np.ndarray]
    sources: list[ContourSource]
    sample_count: int


class BatchGeometry:
    backend = "portable-batched-experimental-unverified"

    def __init__(self, table: HVGL):
        self.table = table

    def render(self, glyph_id: int, design_locations) -> GeometryBatch:
        root = self.table.part(glyph_id)
        locations = np.asarray(design_locations, dtype=np.float64)
        require(locations.ndim == 2 and locations.shape[1] == root.axis_count,
                "design locations must be a sample-by-root-axis matrix")
        count = len(locations)
        require(1 <= count <= 1024, "sample count outside 1..1024")
        require(bool(np.isfinite(locations).all()) and bool((np.abs(locations) <= 1).all()),
                "root design coordinates must be finite and within [-1,1]")
        # Bound intermediate allocations independently of supplied binary sizes.
        require(count * max(root.tree_axes, root.tree_parts * 3) <= 8_000_000,
                "hierarchy batch exceeds intermediate resource limit")
        values = np.zeros((count, root.tree_axes), dtype=np.float64)
        values[:, :root.axis_count] = locations
        translations = np.zeros((count, root.tree_parts, 2), dtype=np.float64)
        rotations = np.zeros((count, root.tree_parts), dtype=np.float64)
        result = GeometryBatch([], [], count)
        active = set()
        point_count = 0

        def transforms(record, target, base, weights):
            if len(record.master_rows):
                target[:, base + 1 + record.master_rows] += record.master_values
            for (row, col), vector in zip(record.extreme_indices, record.extreme_values):
                target[:, base + 1 + int(row)] += weights[:, int(col), None] * vector

        def visit(index, part_base, axis_base, parent_matrix, parent_offset, depth):
            nonlocal point_count
            require(index not in active and depth <= 256, "cyclic or excessive hierarchy depth")
            active.add(index)
            part = self.table.part(index)
            axis_values = values[:, axis_base:axis_base + part.axis_count]
            require(axis_values.shape[1] == part.axis_count, "tree axis range is inconsistent")
            weights = np.zeros((count, part.axis_count * 2), dtype=np.float64)
            weights[:, ::2] = np.maximum(-axis_values, 0)
            weights[:, 1::2] = np.maximum(axis_values, 0)
            angle = rotations[:, part_base]
            cosine, sine = np.cos(angle), np.sin(angle)
            rotation = np.empty((count, 2, 2), dtype=np.float64)
            rotation[:, 0, 0] = cosine; rotation[:, 0, 1] = -sine
            rotation[:, 1, 0] = sine; rotation[:, 1, 1] = cosine
            matrix = np.einsum("nij,njk->nik", parent_matrix, rotation)
            offset = parent_offset + np.einsum("nij,nj->ni", parent_matrix, translations[:, part_base])
            if isinstance(part, Composite):
                descendants = axis_base + part.axis_count
                # Reader validation requires every individual index vector to
                # be strictly increasing, so direct indexed addition is exact.
                if len(part.master_rows):
                    values[:, descendants + part.master_rows] += part.master_values
                for column in range(part.axis_count * 2):
                    start, end = map(int, part.column_starts[column:column + 2])
                    if start != end:
                        values[:, descendants + part.extreme_rows[start:end]] += (
                            weights[:, column, None] * part.extreme_values[start:end])
                transforms(part.translations, translations, part_base, weights)
                transforms(part.rotations, rotations[..., None], part_base, weights)
                for child, part_row, axis_row in part.subparts:
                    visit(child, part_base + 1 + part_row, descendants + axis_row,
                          matrix, offset, depth + 1)
            else:
                unsupported = sorted(set(part.blends) - {0, 1})
                if unsupported:
                    raise UnsupportedRendering(f"part {part.index}: tangent blend types {unsupported} lack validated evaluation")
                require(count * part.master.size <= 8_000_000,
                        "shape batch exceeds coordinate resource limit")
                coordinates = np.broadcast_to(part.master, (count, *part.master.shape)).copy()
                if part.axis_count:
                    coordinates += np.einsum("na,asp->nsp", weights, part.delta)
                start = 0
                for path_index, size in enumerate(part.path_sizes):
                    segment = coordinates[:, start:start + size].copy()
                    kinds = part.blends[start:start + size]
                    source = ContourSource(part.index, part_base, path_index, start)
                    start += size
                    if size < 3:
                        continue  # Explicit rule in Apple's HVGL specification.
                    point_count += count * size * 2
                    require(point_count <= 8_000_000, "path batch exceeds output resource limit")
                    off = segment[:, :, 2:4].copy()
                    for k, kind in enumerate(kinds):
                        if kind == 0:
                            factor = segment[:, k, 0, None]
                            segment[:, k, :2] = (1 - factor) * off[:, k - 1] + factor * off[:, k]
                    points = segment.reshape(count, -1, 2)
                    points = np.einsum("nij,npj->npi", matrix, points) + offset[:, None, :]
                    require(bool(np.isfinite(points).all()), "non-finite evaluated outline")
                    result.paths.append(points)
                    result.sources.append(source)
            active.remove(index)

        visit(glyph_id, 0, 0, np.broadcast_to(np.eye(2), (count, 2, 2)),
              np.zeros((count, 2)), 0)
        return result
