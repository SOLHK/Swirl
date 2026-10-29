"""Analytic synthetic fixtures; no original/derivative Apple font data."""
import struct
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hvf import HVGL, PartMap, Shape, FormatError, UnsupportedRendering, ExperimentalRenderer


def shape(axes=1, blends=(1, 1, 1), *, parallel=False):
    values = [0, 0, 50, 0, 100, 0, 100, 50, 0, 100, 0, 50]
    if parallel:
        values[0:2] = [0.25, 0]
    header = struct.pack("<5H", 0, axes, 1, 3, 3) + bytes(blends)
    header += b"\0" * (-len(header) % 8)
    delta = [0.0] * (axes * 2 * 12)
    if axes:
        for i in range(0, 12, 2):
            delta[i], delta[12 + i] = -10, 20
        if parallel:
            delta[0], delta[12] = 0, 0
    return header + struct.pack("<12d", *values) + struct.pack("<" + str(len(delta)) + "d", *delta)


def composite(child=1, *, master=0.25, positive=0.5, rotation=0.0):
    # One child with one axis. A master translation applies to that child.
    header_size = 36
    sub = struct.pack("<IHH", child, 0, 0)
    cols_rows = struct.pack("<5H", 0, 0, 1, 0, 0) + b"\0\0"
    master_data = struct.pack("<f", master)
    extreme_data = struct.pack("<f", positive)
    translations = struct.pack("<ffH", 30, 40, 0) + b"\0\0"
    rotations = struct.pack("<fH", rotation, 0) + b"\0\0"
    sections = [sub, cols_rows, master_data, extreme_data, translations, rotations]
    offsets, position = [], header_size
    for s in sections:
        offsets.append(position // 4); position += len(s)
    header = struct.pack("<18H", 1, 1, 1, 2, 2, 2, 1, 1, 1, 1, 0, 0, *offsets)
    return header + b"".join(sections)


def table(parts, visible=None):
    offset = 24
    body = bytearray(b"\0" * (4 * (len(parts) + 1)))
    pointers = []
    for part in parts:
        body.extend(b"\0" * (-(offset + len(body)) % 8))
        pointers.append(len(body))
        body.extend(part)
    pointers.append(len(body))
    struct.pack_into("<" + str(len(pointers)) + "I", body, 0, *pointers)
    return struct.pack("<HHIIIII", 3, 1, 0, len(parts), offset,
                       len(parts) if visible is None else visible, 0) + body


class HVFTests(unittest.TestCase):
    def test_index_relative_base_and_shape(self):
        t = HVGL(table([shape()]))
        self.assertIsInstance(t.part(0), Shape)
        self.assertEqual(t.validate()["binary_and_structure_validation"], "PASS")
        p = ExperimentalRenderer(t).render(0, [0])[0]
        np.testing.assert_allclose(p[0], (0, 0))

    def test_negative_and_fractional_extrema(self):
        r = ExperimentalRenderer(HVGL(table([shape()])))
        np.testing.assert_allclose(r.render(0, [-0.5])[0][0], (-5, 0))
        np.testing.assert_allclose(r.render(0, [0.25])[0][0], (5, 0))

    def test_curve_parallel_factor(self):
        r = ExperimentalRenderer(HVGL(table([shape(blends=(0, 1, 1), parallel=True)])))
        np.testing.assert_allclose(r.render(0, [0])[0][0], (12.5, 37.5))

    def test_tree_axis_master_translation_and_rotation(self):
        t = HVGL(table([composite(rotation=np.pi/2), shape()], visible=1))
        self.assertEqual(t.validate()["max_tree_depth"], 2)
        p = ExperimentalRenderer(t).render(0, [0.5])[0][0]
        # Child axis=.25+.5*.5=.5; point=(10,0); rotate then translate.
        np.testing.assert_allclose(p, (30, 50), atol=1e-5)

    def test_tangent_not_silently_turned_into_corner(self):
        t = HVGL(table([shape(blends=(2,1,1))]))
        t.validate()
        with self.assertRaises(UnsupportedRendering):
            ExperimentalRenderer(t).render(0, [0])

    def test_remapping_at_leaf(self):
        hvpm = struct.pack("<HHIIII", 1, 0, 8, 1, 1, 1) + struct.pack("<I", 2)
        t = HVGL(table([composite(), shape(), shape()] , visible=1), hvpm)
        self.assertEqual(t.part(1).index, 2)
        t.validate()

    def test_incompatible_part_mapping_rejected(self):
        hvpm = struct.pack("<HHIIIII", 1, 0, 8, 1, 0, 0, 1)
        with self.assertRaises(FormatError):
            HVGL(table([shape(1), shape(0)]), hvpm).validate()

    def test_unsorted_mapping_rejected(self):
        hvpm = struct.pack("<HHI", 1, 0, 8) + struct.pack("<I6I", 2, 3, 5, 0, 4, 6, 7)
        with self.assertRaises(FormatError):
            PartMap(hvpm)

    def test_unknown_version(self):
        data = bytearray(table([shape()])); data[0] = 4
        with self.assertRaises(FormatError):
            HVGL(bytes(data))

    def test_truncated_float_payload(self):
        data = table([shape()])[:-8]
        with self.assertRaises(FormatError):
            HVGL(data).validate()

    def test_nan_float_rejected(self):
        data = bytearray(table([shape()])); struct.pack_into("<d", data, 48, float('nan'))
        with self.assertRaises(FormatError):
            HVGL(bytes(data)).validate()

    def test_tree_cycle_rejected(self):
        with self.assertRaises(FormatError):
            HVGL(table([composite(child=0)])).validate()

    def test_wrong_tree_offsets_rejected(self):
        c = bytearray(composite()); struct.pack_into("<H", c, 42, 1)
        with self.assertRaises(FormatError):
            HVGL(table([bytes(c), shape()])).validate()

    def test_unknown_shape_blend_rejected(self):
        with self.assertRaises(FormatError):
            HVGL(table([shape(blends=(255,1,1))])).validate()

    def test_root_axis_bounds(self):
        r = ExperimentalRenderer(HVGL(table([shape()])))
        for v in ([2], [float('nan')], []):
            with self.assertRaises(FormatError):
                r.render(0, v)


if __name__ == "__main__":
    unittest.main()
