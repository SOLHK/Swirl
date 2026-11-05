"""Conservative point-identity matching for TrueType contour models.

This module deliberately matches only geometrically identical encoded point rings.
It does not infer correspondence between different shapes or interpolate unmatched
points. Ambiguous contour assignments are rejected rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


class PointIdentityError(ValueError):
    """Base class for unsafe or unverifiable point correspondence."""


class InvalidOutlineError(PointIdentityError):
    """The contour representation is malformed."""


class UnmatchedContourError(PointIdentityError):
    """No exact point-ring correspondence exists."""


class AmbiguousPointIdentityError(PointIdentityError):
    """More than one valid correspondence exists."""


@dataclass(frozen=True, order=True)
class OutlinePoint:
    x: int
    y: int
    on_curve: bool


@dataclass(frozen=True)
class Outline:
    points: tuple[OutlinePoint, ...]
    contour_ends: tuple[int, ...]

    @classmethod
    def from_contours(cls, contours: Iterable[Iterable[OutlinePoint]]) -> "Outline":
        points: list[OutlinePoint] = []
        ends: list[int] = []
        for contour in contours:
            ring = tuple(contour)
            if not ring:
                raise InvalidOutlineError("empty_contour_has_no_point_identity")
            if not all(isinstance(p, OutlinePoint) for p in ring):
                raise InvalidOutlineError("invalid_point_record")
            points.extend(ring)
            ends.append(len(points) - 1)
        return cls(tuple(points), tuple(ends))

    def contours(self) -> tuple[tuple[OutlinePoint, ...], ...]:
        if not self.contour_ends:
            if self.points:
                raise InvalidOutlineError("points_without_contours")
            return ()
        if any(not isinstance(e, int) for e in self.contour_ends):
            raise InvalidOutlineError("non_integer_contour_end")
        if tuple(sorted(self.contour_ends)) != self.contour_ends:
            raise InvalidOutlineError("contour_ends_not_monotonic")
        if self.contour_ends[-1] != len(self.points) - 1:
            raise InvalidOutlineError("contour_end_point_count_mismatch")
        start = 0
        result = []
        for end in self.contour_ends:
            if end < start:
                raise InvalidOutlineError("empty_or_overlapping_contour")
            result.append(self.points[start:end + 1])
            start = end + 1
        return tuple(result)


def _ring_mappings(source: Sequence[OutlinePoint],
                   target: Sequence[OutlinePoint]) -> tuple[tuple[int, ...], ...]:
    """Return target-local-index -> source-local-index maps for exact rings."""
    if len(source) != len(target) or not source:
        return ()
    n = len(source)
    maps: set[tuple[int, ...]] = set()
    for reverse in (False, True):
        ordered = tuple(reversed(source)) if reverse else tuple(source)
        for shift in range(n):
            rotated = ordered[shift:] + ordered[:shift]
            if rotated == tuple(target):
                # rotated[j] came from source index below; recover by value-position,
                # not equality search (duplicate points are common in real outlines).
                if reverse:
                    mapping = tuple((n - 1 - ((j + shift) % n)) for j in range(n))
                else:
                    mapping = tuple((j + shift) % n for j in range(n))
                maps.add(mapping)
    return tuple(sorted(maps))


def match_point_identity(source: Outline, target: Outline) -> tuple[int, ...]:
    """Map every target point index to its source index, or fail closed.

    Exact ring matching permits contour permutation and cyclic start-point changes.
    Reversed winding is allowed only when the encoded point/flag ring itself matches.
    If duplicate/symmetric contours make identity non-unique, no arbitrary assignment
    is selected. Phantom points are not part of Outline and must be handled separately.
    """
    src_contours, dst_contours = source.contours(), target.contours()
    if len(src_contours) != len(dst_contours):
        raise UnmatchedContourError("contour_count_mismatch")
    candidates: list[list[tuple[int, tuple[int, ...]]]] = []
    for dst in dst_contours:
        options = []
        for si, src in enumerate(src_contours):
            for mapping in _ring_mappings(src, dst):
                options.append((si, mapping))
        if not options:
            raise UnmatchedContourError("no_exact_contour_identity")
        candidates.append(options)

    solutions: list[tuple[int, ...]] = []

    def search(di: int, used: set[int], mapping: list[int]) -> None:
        if len(solutions) > 1:
            return
        if di == len(dst_contours):
            solutions.append(tuple(mapping))
            return
        dst_start = sum(len(c) for c in dst_contours[:di])
        for si, local_map in candidates[di]:
            if si in used:
                continue
            src_start = sum(len(c) for c in src_contours[:si])
            search(di + 1, used | {si},
                   mapping + [src_start + idx for idx in local_map])

    search(0, set(), [])
    if not solutions:
        raise UnmatchedContourError("contour_assignment_not_bijective")
    if len(solutions) != 1:
        raise AmbiguousPointIdentityError("non_unique_contour_or_point_identity")
    return solutions[0]
