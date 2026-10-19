#!/usr/bin/env python3
"""Rebuild standard quadratic variable outlines from a verified native oracle.

This is an instance reconstruction, NOT a lossless HVF-to-gvar translation.
The source's user-coordinate behavior is sampled through CoreText, so malformed
Apple avar records are never silently collapsed by a Python dictionary.  The
target keeps the original axis tags/ranges and uses an identity avar: the source
mapping is baked into the sampled geometry and metric variations.

No font is published as Swirl-VF.ttc until every original face/glyph passes the
configured independent holdout checks. Even success is bounded sampled evidence,
not a proof over the continuous design space or a Windows acceptance result.
"""
from __future__ import annotations

import argparse
import array
import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.cu2qu.cu2qu import curves_to_quadratic
from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont, TTCollection, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.models import VariationModel, normalizeLocation
from metric_variations import add_metric_variations, verify_metric_variations
from incremental_pipe import TimedLineReader


class ReconstructionError(RuntimeError):
    pass


def check(condition, message):
    if not condition:
        raise ReconstructionError(message)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized_grid(axis_tags):
    """Default plus all extrema, including all 8 three-axis mixed corners."""
    points = list(itertools.product((-1.0, 0.0, 1.0), repeat=len(axis_tags)))
    points.sort(key=lambda p: (sum(x != 0 for x in p), p))
    return [dict(zip(axis_tags, point)) for point in points]


def heldout_locations(axis_tags, seed=20261019, random_count=12):
    """Points strictly separate from the training extrema/default grid."""
    points = list(itertools.product((-0.5, 0.5), repeat=len(axis_tags)))
    for i in range(len(axis_tags)):
        for v in (-0.5, 0.5):
            p = [0.0] * len(axis_tags)
            p[i] = v
            points.append(tuple(p))
    rng = random.Random(seed)
    for _ in range(random_count):
        # Quantize SUPPORT coordinates to representable F2DOT14 values before
        # requesting the native oracle, never after creating the gvar tuples.
        points.append(tuple(rng.randint(-16000, 16000) / 16384 for _ in axis_tags))
    return [dict(zip(axis_tags, point)) for point in points]


def user_location(normalized, axes):
    out = {}
    for tag, (low, default, high) in axes.items():
        v = normalized.get(tag, 0.0)
        out[tag] = default + v * (default - low if v < 0 else high - default)
    return out


def command_signature(commands):
    return [(item[0], len(item)) for item in commands]


def compatible_coordinates(records, cubic_error=0.05):
    """Preserve contour order, direction, explicit point identity and all parts.

    Only cubic segments require cu2qu approximation. They are converted jointly
    across samples; no boolean overlap removal or pseudo-bold/stretched outline
    operation is performed. Error is separately bounded by cubic_error.
    """
    check(bool(records), "no native samples")
    commands = [r["commands"] for r in records]
    signature = command_signature(commands[0])
    check(all(command_signature(c) == signature for c in commands),
          "native outline command topology differs between instances")
    values = [[] for _ in records]
    flags, end_points = [], []
    opened = False
    cubic_count = 0
    for index, (kind, _) in enumerate(signature):
        all_commands = [c[index] for c in commands]
        check(all(all(isinstance(v, (int, float)) and math.isfinite(v) for v in c[1:])
                  for c in all_commands), "non-finite native point")
        if kind == "moveTo":
            check(not opened and all(len(c) == 3 for c in all_commands), "bad native moveTo")
            opened = True
            for points, cmd in zip(values, all_commands):
                points.append(tuple(cmd[1:]))
            flags.append(1)
        elif kind == "lineTo":
            check(opened and all(len(c) == 3 for c in all_commands), "bad native lineTo")
            for points, cmd in zip(values, all_commands):
                points.append(tuple(cmd[1:]))
            flags.append(1)
        elif kind == "qCurveTo":
            check(opened and all(len(c) == 5 for c in all_commands), "bad native quadratic")
            for points, cmd in zip(values, all_commands):
                points.extend((tuple(cmd[1:3]), tuple(cmd[3:5])))
            flags.extend((0, 1))
        elif kind == "curveTo":
            check(opened and all(len(c) == 7 for c in all_commands), "bad native cubic")
            curves = [(points[-1], tuple(cmd[1:3]), tuple(cmd[3:5]), tuple(cmd[5:7]))
                      for points, cmd in zip(values, all_commands)]
            quadratics = curves_to_quadratic(curves, [cubic_error] * len(curves))
            size = len(quadratics[0]) - 1
            check(all(len(q) == size + 1 for q in quadratics), "incompatible cubic conversion")
            for points, q in zip(values, quadratics):
                points.extend(q[1:])
            flags.extend([0] * (size - 1) + [1])
            cubic_count += 1
        elif kind == "closePath":
            check(opened and all(len(c) == 1 for c in all_commands), "bad native closePath")
            opened = False
            end_points.append(len(flags) - 1)
        else:
            raise ReconstructionError(f"unsupported native path command {kind}")
    check(not opened, "native path is open")
    return [np.asarray(p, dtype=float).reshape(-1, 2) for p in values], flags, end_points, cubic_count


def with_phantoms(points, record, source_metrics, source_vertical):
    check(record.get("error") is None, f"native oracle error: {record.get('error')}")
    aw = float(record["advance_width"])
    ah = float(record["advance_height"])
    check(math.isfinite(aw) and math.isfinite(ah) and aw >= 0 and ah >= 0,
          "invalid native advance")
    # CoreText paths are relative to the glyph's horizontal origin. glyf.xMin
    # uses control-point bounds, whereas CT's geometric LSB is the actual curve
    # extremum. Subtracting those two different bounds would move curved glyphs.
    # Preserve the explicit native origin, and derive the TT storage bearing.
    check(all(k in record for k in ("lsb", "horizontal_origin_x", "vertical_origin_x", "vertical_origin_y")),
          "native metric oracle missing explicit origins/bearing; cannot claim metric preservation")
    lsb, top = float(record["lsb"]), float(record["vertical_origin_y"])
    left, vertical_x = float(record["horizontal_origin_x"]), float(record["vertical_origin_x"])
    check(all(math.isfinite(v) for v in (lsb, top, left, vertical_x)), "invalid native bearing/origin")
    check(abs(vertical_x - (left + aw / 2)) <= 1e-5,
          "native horizontal coordinate of vertical origin is not representable by standard vmtx")
    check(-32768 <= left <= 32767 and aw <= 65535 and ah <= 65535, "unrepresentable TrueType metrics")
    return np.vstack((points, [(left, 0), (left + aw, 0), (0, top), (0, top - ah)]))


def reconstruct_glyph(training, heldout, training_locations, heldout_locations_, axes,
                      source_metrics, source_vertical, outline_limit=1.0,
                      metric_limit=1.0, cubic_error=0.05):
    check(len(training) == len(training_locations) and len(heldout) == len(heldout_locations_),
          "native sample/location count mismatch")
    check(math.isfinite(outline_limit) and outline_limit >= 0
          and math.isfinite(metric_limit) and metric_limit >= 0
          and math.isfinite(cubic_error) and cubic_error > 0,
          "invalid reconstruction error budget")
    records = training + heldout
    coords, flags, ends, cubic_count = compatible_coordinates(records, cubic_error)
    vectors = [with_phantoms(p, r, source_metrics, source_vertical) for p, r in zip(coords, records)]
    model = VariationModel(training_locations, axisOrder=list(axes))
    default = next(i for i, location in enumerate(training_locations) if not any(location.values()))
    default_points = np.asarray([[otRound(x), otRound(y)] for x, y in coords[default]], dtype=float).reshape(-1, 2)
    check(np.all(default_points >= -32768) and np.all(default_points <= 32767), "glyf coordinate overflow")
    glyph = Glyph()
    glyph.numberOfContours = len(ends)
    glyph.coordinates = GlyphCoordinates(default_points.tolist())
    glyph.endPtsOfContours = list(ends)
    glyph.flags = array.array("B", flags)
    if flags:
        glyph.flags[0] |= 0x40  # OVERLAP_SIMPLE: retain original overlapping contours.
    from fontTools.ttLib.tables.ttProgram import Program
    glyph.program = Program()
    glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    rounded = [np.asarray([[otRound(x), otRound(y)] for x, y in v], dtype=float) for v in vectors[:len(training)]]
    deltas = model.getDeltas(rounded, round=lambda a: np.floor(a + 0.5))
    tuples = []
    for support, delta in zip(model.supports[1:], deltas[1:]):
        if np.any(delta):
            check(np.all(delta >= -32768) and np.all(delta <= 32767), "gvar delta overflow")
            tuples.append(TupleVariation(support, [(int(x), int(y)) for x, y in delta]))
    error_max = metric_max = outline_bound_max = 0.0
    cubic_bound = cubic_error if cubic_count else 0.0
    failures = []
    sample_maxima = {kind: {"max_point_error_units": 0.0,
                            "max_outline_error_bound_units": 0.0,
                            "max_metric_error_units": 0.0}
                     for kind in ("training", "holdout")}
    default_error = None
    # Training points, including the default, also need acceptance checks:
    # integer base coordinates/phantoms can introduce an irreducible error.
    for n, location in enumerate(training_locations + heldout_locations_):
        kind = "training" if n < len(training) else "holdout"
        predicted = model.interpolateFromDeltas(location, deltas)
        reference = vectors[n]
        differences = np.linalg.norm(predicted[:-4] - reference[:-4], axis=1)
        point_error = float(max(differences, default=0.0))
        # The common quadratic control-point discrepancy bounds its curve
        # discrepancy by the convex-hull property. A native cubic has the
        # additional independently configured cu2qu approximation bound.
        outline_bound = point_error + cubic_bound
        aw_error = abs((predicted[-3, 0] - predicted[-4, 0]) - (reference[-3, 0] - reference[-4, 0]))
        ah_error = abs((predicted[-2, 1] - predicted[-1, 1]) - (reference[-2, 1] - reference[-1, 1]))
        origin_error = float(np.abs(predicted[-4:] - reference[-4:]).max())
        metric_error = max(float(aw_error), float(ah_error), origin_error)
        error_max, metric_max = max(error_max, point_error), max(metric_max, metric_error)
        outline_bound_max = max(outline_bound_max, outline_bound)
        measured = {"max_point_error_units": point_error,
                    "max_outline_error_bound_units": outline_bound,
                    "max_metric_error_units": metric_error}
        for key, value in measured.items():
            sample_maxima[kind][key] = max(sample_maxima[kind][key], value)
        if kind == "training" and n == default:
            default_error = measured
        if outline_bound > outline_limit or metric_error > metric_limit:
            failures.append({"location": location, "sample_kind": kind, **measured})
    # These MUST be differences of the independently rounded model phantoms.
    # Rounding the unrounded advance separately can differ by one unit and
    # silently shift the serialized model's bottom/right phantom everywhere.
    m = rounded[default]
    aw = int(m[-3, 0] - m[-4, 0])
    ah = int(m[-2, 1] - m[-1, 1])
    hmtx = (aw, glyph.xMin - int(m[-4, 0]))
    vmtx = (ah, int(m[-2, 1]) - glyph.yMax)
    check(0 <= aw <= 65535 and 0 <= ah <= 65535
          and -32768 <= hmtx[1] <= 32767 and -32768 <= vmtx[1] <= 32767,
          "rounded TrueType advance/bearing is not representable")
    return glyph, tuples, hmtx, vmtx, {
        "max_point_error_units": error_max, "max_metric_error_units": metric_max,
        "max_outline_error_bound_units": outline_bound_max,
        "cubic_approximation_bound_units": cubic_bound,
        "error_bound_policy": "quadratic point discrepancy plus cu2qu bound; includes training, default and independent holdouts",
        "point_count": len(flags), "contour_count": len(ends), "cubic_segments": cubic_count,
        "training_count": len(training), "holdout_count": len(heldout),
        "sample_maxima": sample_maxima, "default_quantization_error": default_error,
        "failures": failures,
        "continuous_space_proof": False,
    }


def verify_serialized_face(reference, serialized):
    """Prove that serialization preserved the already native-checked model.

    Every default outline/phantom coordinate, contour flag/end point, stored
    metric, tuple support and tuple delta is compared exactly after decoding.
    Equality of those complete coefficients preserves the variation function
    at ALL locations, including every native training/holdout coordinate. This
    does not expand the native sampling evidence to the continuous HVF space.
    No private native curve cache or second native extraction is needed.
    """
    expected_order, actual_order = reference.getGlyphOrder(), serialized.getGlyphOrder()
    check(len(expected_order) == len(actual_order), "serialized glyph count changed")
    for tag in ("glyf", "gvar", "hmtx", "vmtx", "fvar", "avar", "HVAR", "VVAR"):
        check((tag in reference) == (tag in serialized), f"serialized {tag} presence changed")
    for tag in ("fvar", "avar", "HVAR", "VVAR"):
        if tag in reference:
            check(reference[tag].compile(reference) == serialized[tag].compile(serialized),
                  f"serialized {tag} axis coordinates changed")
    if "HVAR" in reference:
        verify_metric_variations(reference)
        verify_metric_variations(serialized)
    expected_glyf, actual_glyf = reference["glyf"], serialized["glyf"]
    expected_h, actual_h = reference["hmtx"].metrics, serialized["hmtx"].metrics
    expected_v = reference["vmtx"].metrics if "vmtx" in reference else None
    actual_v = serialized["vmtx"].metrics if "vmtx" in serialized else None
    point_count = tuple_count = 0
    for gid, (expected_name, actual_name) in enumerate(zip(expected_order, actual_order)):
        prefix = f"serialized gid {gid}"
        expected_coords, expected_controls = expected_glyf._getCoordinatesAndControls(expected_name, expected_h, expected_v)
        actual_coords, actual_controls = actual_glyf._getCoordinatesAndControls(actual_name, actual_h, actual_v)
        check(expected_controls.numberOfContours >= 0 and actual_controls.numberOfContours >= 0,
              f"{prefix}: unexpected composite glyph in expanded reconstruction")
        check(expected_controls.numberOfContours == actual_controls.numberOfContours
              and list(expected_controls.endPts) == list(actual_controls.endPts)
              and list(expected_controls.flags) == list(actual_controls.flags),
              f"{prefix}: contour topology/flags changed")
        check(list(expected_coords) == list(actual_coords),
              f"{prefix}: default outline or metric phantom changed")
        check(expected_h[expected_name] == actual_h[actual_name]
              and (expected_v is None or expected_v[expected_name] == actual_v[actual_name]),
              f"{prefix}: stored metrics changed")
        expected_glyph, actual_glyph = expected_glyf[expected_name], actual_glyf[actual_name]
        expected_program = getattr(expected_glyph, "program", None)
        actual_program = getattr(actual_glyph, "program", None)
        check((expected_program.getBytecode() if expected_program else b"")
              == (actual_program.getBytecode() if actual_program else b""),
              f"{prefix}: hinting instructions changed")
        expected_tuples = reference["gvar"].variations.get(expected_name, [])
        actual_tuples = serialized["gvar"].variations.get(actual_name, [])
        check(len(expected_tuples) == len(actual_tuples), f"{prefix}: gvar tuple count changed")
        for number, (wanted, actual) in enumerate(zip(expected_tuples, actual_tuples)):
            check(wanted.axes == actual.axes, f"{prefix}, tuple {number}: gvar support changed")
            # The compiler can choose a packed point-set representation. Decode
            # omitted points with standard IUP before comparing full coefficients.
            if None in wanted.coordinates:
                wanted = copy.deepcopy(wanted)
                wanted.calcInferredDeltas(expected_coords, expected_controls.endPts)
            if None in actual.coordinates:
                actual = copy.deepcopy(actual)
                actual.calcInferredDeltas(actual_coords, actual_controls.endPts)
            check(wanted.coordinates == actual.coordinates,
                  f"{prefix}, tuple {number}: gvar outline/phantom delta changed")
        point_count += len(actual_coords)
        tuple_count += len(actual_tuples)
    return {"status": "PASS", "glyphs_checked": len(actual_order),
            "default_points_including_phantoms_checked": point_count,
            "gvar_tuples_checked": tuple_count,
            "method": "exact decoded outline, topology, metric phantoms and complete gvar coefficients",
            "native_holdout_error_preserved": True,
            "continuous_native_space_proof": False}


def verify_collection_tables(reference_paths, collection):
    """Check that TTC packing kept each verified face's complete table bytes."""
    check(len(reference_paths) == len(collection.fonts), "serialized TTC face count changed")
    for index, (path, actual) in enumerate(zip(reference_paths, collection.fonts)):
        with TTFont(path, lazy=True) as reference:
            check(set(reference.reader.keys()) == set(actual.reader.keys()),
                  f"TTC face {index}: table set changed")
            for tag in reference.reader.keys():
                expected_data, actual_data = reference.reader[tag], actual.reader[tag]
                if tag == "head":
                    # A collection may recalculate the global SFNT adjustment;
                    # it is not part of the outline or variation function.
                    expected_data = expected_data[:8] + b"\0" * 4 + expected_data[12:]
                    actual_data = actual_data[:8] + b"\0" * 4 + actual_data[12:]
                check(expected_data == actual_data, f"TTC face {index}: {tag} bytes changed")
    return {"status": "PASS", "faces_checked": len(reference_paths),
            "method": "all serialized face table bytes equal verified standalone face; head checksum adjustment excluded"}


class NativeOracle:
    def __init__(self, executable, source: Path, log: Path, response_timeout=30.0):
        self.stderr = open(log, "x", encoding="utf-8")
        self.proc = None
        self.reader = None
        self.response_timeout = response_timeout
        try:
            self.proc = subprocess.Popen([str(executable), str(source)], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=self.stderr, text=True,
                                         encoding="utf-8", bufsize=1)
            self.reader = TimedLineReader(self.proc.stdout.fileno())
            line = self.reader.readline(timeout=120.0)
            check(bool(line), "native oracle did not return metadata; inspect native-oracle.log")
            self.metadata = json.loads(line)
            check(self.metadata.get("type") == "metadata", "native oracle metadata missing")
            check(self.metadata.get("source_sha256") == sha256(source), "native oracle source SHA mismatch")
            check(self.metadata.get("backend") == "CoreText", "need independent CoreText user-coordinate oracle")
            check(bool(self.metadata.get("faces"))
                  and all(face.get("status") == "identity_verified" for face in self.metadata.get("faces", [])),
                  "native oracle could not verify every requested physical face")
        except Exception:
            self.close()
            raise
        self.sequence = 0

    def samples(self, face, glyph_ids, location):
        self.sequence += 1
        request_id = str(self.sequence)
        request = {"request_id": request_id, "face_index": face,
                   "location": location, "glyph_ids": glyph_ids}
        self.proc.stdin.write(json.dumps(request, allow_nan=False) + "\n")
        self.proc.stdin.flush()
        results = {}
        for _ in glyph_ids:
            line = self.reader.readline(timeout=self.response_timeout)
            check(bool(line), "native oracle ended before returning every requested glyph")
            record = json.loads(line)
            check(record.get("request_id") == request_id and record.get("face_index") == face,
                  "native oracle response identity mismatch")
            # Request failures intentionally have no glyph/location payload.
            # Report the original native error before validating success fields,
            # otherwise an axis or identity failure is disguised as a JSON echo
            # mismatch. No failed request is treated as an empty glyph.
            check(record.get("error") is None,
                  f"native request {request_id} face {face} failed: {record.get('error')}")
            check(record.get("type") != "request_error", "native request_error without error detail")
            check(record.get("location") == location,
                  "native oracle axis location mismatch: " + json.dumps({
                      "request_id": request_id, "face_index": face,
                      "requested": location, "received": record.get("location"),
                      "reported": record.get("reported_location")}, allow_nan=False))
            gid = record.get("glyph_id")
            check(gid in glyph_ids and gid not in results, "missing, duplicate or unrelated native glyph")
            check(record.get("error") is None, f"native error on glyph {gid}: {record.get('error')}")
            results[gid] = record
        return results

    def close(self):
        if self.reader is not None:
            self.reader.close()
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(timeout=10)
        if self.proc is not None:
            self.proc.stdout.close()
            if not self.proc.stdin.closed:
                self.proc.stdin.close()
        self.stderr.close()


def family_name(index, old):
    groups = [(0, 5, "UI Text"), (5, 10, "UI Display"), (10, 15, "Watch UI Text"),
              (15, 20, "Watch UI Display"), (20, 24, "Text"), (24, 28, "Extended"), (28, 32, "Watch")]
    for low, high, group in groups:
        if low <= index < high:
            return f"Swirl VF {group} {['SC','TC','HK','MO','JA'][index - low]}"
    return f"Swirl VF Face {index}"


def rename_face(font, index):
    original = font["name"].getDebugName(6)
    family = family_name(index, original)
    style = font["name"].getDebugName(2) or "Regular"
    # Replace every localized identity record, including legacy/WWS aliases.
    # Copyright, license, feature/axis and named-instance labels remain intact.
    names = {1: family, 2: style, 3: family.replace(" ", "") + ";SwirlVF-0.1",
             4: family + " " + style, 6: family.replace(" ", ""), 16: family, 17: style,
             18: family, 20: family.replace(" ", ""), 21: family, 22: style,
             25: family.replace(" ", "")}
    for record in list(font["name"].names):
        if record.nameID in names:
            font["name"].setName(names[record.nameID], record.nameID,
                                 record.platformID, record.platEncID, record.langID)
    for name_id, value in names.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)
    for number, instance in enumerate(font["fvar"].instances):
        name_id = getattr(instance, "postscriptNameID", 0xFFFF)
        if name_id != 0xFFFF:
            value = family.replace(" ", "") + f"-Instance{number}"
            for record in list(font["name"].names):
                if record.nameID == name_id:
                    font["name"].setName(value, name_id, record.platformID, record.platEncID, record.langID)
            font["name"].setName(value, name_id, 3, 1, 0x409)
    return {"original_postscript": original, "target_family": family,
            "source_face_index": index, "target_face_index": index}


def validate_io_paths(source, executable, destination, report_path):
    """Reject report/log aliases before any writable handle is opened."""
    log = report_path.parent / "native-oracle.log"
    paths = {"source": source, "oracle": executable, "destination": destination,
             "report": report_path, "log": log}
    for (a, pa), (b, pb) in itertools.combinations(paths.items(), 2):
        aliases = pa.resolve() == pb.resolve()
        if pa.exists() and pb.exists():
            aliases = aliases or pa.samefile(pb)
        check(not aliases, f"unsafe path alias: {a} and {b}; no files written")
    for name in ("destination", "report", "log"):
        path = paths[name]
        check(not path.exists() and not path.is_symlink(),
              f"{name} already exists; choose a new output/report directory")


def run(source, executable, destination, report_path, batch_size=64,
        outline_limit=1.0, metric_limit=1.0, max_extra=24):
    check(destination.name == "Swirl-VF.ttc", "the final font filename must be Swirl-VF.ttc")
    check(source.resolve() != destination.resolve(), "never overwrite the source font")
    check(not destination.exists(), "destination already exists; do not overwrite an unreviewed font")
    validate_io_paths(source, executable, destination, report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"source_sha256": sha256(source), "output_generated": False,
              "conversion_kind": "native-instance-reconstruction",
              "lossless_conversion": False, "windows_acceptance": "NOT_RUN",
              "fonttools_version": __import__('fontTools').__version__,
              "outline_limit_font_units": outline_limit, "metric_limit_font_units": metric_limit,
              "faces": [], "failures": [], "status": "RUNNING"}
    oracle = None
    try:
        oracle = NativeOracle(executable, source, report_path.parent / "native-oracle.log")
        report["oracle"] = oracle.metadata
        with TTCollection(source, lazy=True) as original:
            check(len(oracle.metadata.get("faces", [])) == len(original.fonts), "native/source face count mismatch")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="swirl-vf-", dir=destination.parent) as tmp:
                face_paths = []
                for index, src in enumerate(original.fonts):
                    check("MVAR" not in src and "VVAR" not in src,
                          "this reconstruction path has no native font-wide/VVAR metric oracle")
                    for tag in ("GSUB", "GPOS", "BASE"):
                        if tag in src:
                            layout = src[tag].table
                            check(not getattr(layout, "FeatureVariations", None)
                                  and not getattr(layout, "VarStore", None)
                                  and not getattr(layout, "ItemVarStore", None),
                                  f"{tag} variable layout requires independent remapping before replacing avar")
                    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in src["fvar"].axes}
                    training = normalized_grid(list(axes))
                    check_locations = heldout_locations(list(axes), seed=20261019 + index)
                    # Every named instance is checked if it is not already a master.
                    known = {tuple(p.items()) for p in training + check_locations}
                    for instance in src["fvar"].instances:
                        location = normalizeLocation(instance.coordinates, axes)
                        if tuple(location.items()) not in known:
                            check_locations.append(location)
                            known.add(tuple(location.items()))
                    # Sample immediately either side of all raw avar source knots.
                    # Raw records retain duplicate/out-of-order knots; only the input
                    # request positions are deduplicated, never the output semantics.
                    if "avar" in src:
                        from audit_font import raw_avar
                        raw = raw_avar(src.reader["avar"], list(axes))
                        for axis in raw["axes"]:
                            for record in axis["records"]:
                                x = record["from_f2dot14"] / 16384
                                for eps in (-1/16384, 0, 1/16384):
                                    if -1 <= x + eps <= 1:
                                        p = {a: 0.0 for a in axes}; p[axis["tag"]] = x + eps
                                        if tuple(p.items()) not in known:
                                            check_locations.append(p); known.add(tuple(p.items()))
                    with TTFont(source, fontNumber=index, lazy=False, recalcBBoxes=True,
                                recalcTimestamp=False) as out:
                        glyph_order = src.getGlyphOrder()
                        out.setGlyphOrder(glyph_order)
                        out["glyf"] = newTable("glyf"); out["glyf"].glyphs = {}; out["glyf"].glyphOrder = glyph_order
                        out["loca"] = newTable("loca")
                        out["gvar"] = newTable("gvar"); out["gvar"].version = 1; out["gvar"].reserved = 0; out["gvar"].variations = {}
                        face_report = {"face_index": index, "glyph_count": len(glyph_order),
                                       "axes": axes, "training_points": len(training),
                                       "initial_holdout_points": len(check_locations),
                                       "max_outline_error": 0.0, "max_metric_error": 0.0,
                                       "glyphs_with_adaptive_training": 0, "retained_aat_behavior_windows": "NOT_VERIFIED"}
                        report["faces"].append(face_report)
                        for start in range(0, len(glyph_order), batch_size):
                            gids = list(range(start, min(start + batch_size, len(glyph_order))))
                            initial = [oracle.samples(index, gids, user_location(p, axes)) for p in training + check_locations]
                            for gid in gids:
                                name = glyph_order[gid]
                                train = [point[gid] for point in initial[:len(training)]]
                                held = [point[gid] for point in initial[len(training):]]
                                tl, hl = list(training), list(check_locations)
                                attempts = 0
                                while True:
                                    glyph, tuples, hm, vm, evidence = reconstruct_glyph(
                                        train, held, tl, hl, axes, src["hmtx"].metrics[name],
                                        src["vmtx"].metrics.get(name) if "vmtx" in src else None,
                                        outline_limit, metric_limit)
                                    if not evidence["failures"]:
                                        break
                                    check(not any(f["sample_kind"] == "training" for f in evidence["failures"]),
                                          f"face {index} gid {gid}: training/default quantization exceeds error budget")
                                    check(attempts < max_extra,
                                          f"face {index} gid {gid}: holdout error persists after {attempts} adaptive points")
                                    worst = max(evidence["failures"], key=lambda f: max(f["max_outline_error_bound_units"], f["max_metric_error_units"]))
                                    k = hl.index(worst["location"])
                                    peak = {tag: otRound(value * 16384) / 16384 for tag, value in hl[k].items()}
                                    check(peak not in tl, "gvar F2DOT14 support precision cannot resolve the remaining native error")
                                    tl.append(peak)
                                    if peak == hl[k]:
                                        hl.pop(k); train.append(held.pop(k))
                                    else:
                                        train.append(oracle.samples(index, [gid], user_location(peak, axes))[gid])
                                    attempts += 1
                                    # New independent points after every refinement, never
                                    # report the promoted training point as a passing test.
                                    additions = heldout_locations(list(axes), seed=index*100000+gid*31+attempts,
                                                                  random_count=4)[-4:]
                                    for p in additions:
                                        if p not in tl and p not in hl:
                                            hl.append(p); held.append(oracle.samples(index, [gid], user_location(p, axes))[gid])
                                out["glyf"].glyphs[name] = glyph
                                out["gvar"].variations[name] = tuples
                                out["hmtx"].metrics[name] = hm
                                if "vmtx" in out:
                                    out["vmtx"].metrics[name] = vm
                                face_report["max_outline_error"] = max(face_report["max_outline_error"], evidence["max_outline_error_bound_units"])
                                face_report["max_metric_error"] = max(face_report["max_metric_error"], evidence["max_metric_error_units"])
                                face_report["glyphs_with_adaptive_training"] += bool(attempts)
                            print(f"face={index} glyphs={start+len(gids)}/{len(glyph_order)}", file=sys.stderr, flush=True)
                        replaced = [tag for tag in ("hvgl", "hvpm", "HVAR", "VVAR", "VORG") if tag in out]
                        for tag in replaced:
                            del out[tag]
                        out["avar"] = newTable("avar"); out["avar"].majorVersion = 1; out["avar"].minorVersion = 0
                        out["avar"].segments = {tag: {-1.0:-1.0, 0.0:0.0, 1.0:1.0} for tag in axes}
                        face_report["identity"] = rename_face(out, index)
                        face_report["replaced_tables"] = replaced
                        face_report["metric_variation_verification"] = add_metric_variations(out)
                        face_report["metrics_strategy"] = "gvar phantom points plus exactly equivalent HVAR/VVAR advances; no native-value correction"
                        face_report["bearing_storage_note"] = "hmtx LSB uses glyf control bounds and preserves the CoreText origin; native geometric LSB is separately observed"
                        face_report["outline_error_policy"] = "training and holdout quadratic point discrepancy plus cubic approximation bound"
                        face_report["retained_tables"] = sorted(set(src.keys()) & set(out.keys()))
                        path = Path(tmp) / f"face-{index}.ttf"
                        out.save(path)
                        with TTFont(path) as verified:
                            face_report["serialized_model_verification"] = verify_serialized_face(out, verified)
                            check(verified["cmap"].compile(verified) == src["cmap"].compile(src), "serialized cmap changed")
                    face_paths.append(path)
                candidate = Path(tmp) / "candidate.ttc"
                with TTCollection() as collection:
                    # Packaging must not rewrite timestamps after each face's
                    # complete serialized model has already been verified.
                    for path in face_paths:
                        collection.fonts.append(TTFont(path, lazy=True, recalcTimestamp=False))
                    collection.save(candidate, shareTables=True)
                    with TTCollection(candidate, lazy=True) as reopened:
                        report["collection_verification"] = verify_collection_tables(face_paths, reopened)
                check(sha256(source) == report["source_sha256"], "source changed during conversion")
                report["output_sha256"] = sha256(candidate)
                report["output_size_bytes"] = candidate.stat().st_size
                report["status"] = "RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED"
                # Same-filesystem hard linking is an atomic no-replace publication.
                # A destination appearing after preflight cannot be overwritten.
                os.link(candidate, destination)
                candidate.unlink()
                report["output_generated"] = True
    except Exception as error:
        report["status"] = "BLOCKED"
        report["failures"].append({"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if oracle is not None:
            oracle.close()
        with report_path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--oracle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    check(1 <= args.batch_size <= 1024, "batch size outside 1..1024")
    try:
        run(args.source, args.oracle, args.output, args.report, args.batch_size)
    except (ReconstructionError, OSError, ValueError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
