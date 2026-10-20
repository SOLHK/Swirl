"""Resumable C1 synthetic reconstruction using the existing glyph algorithm.

Only original, standard-format test fixtures are admitted. The future native
A3/B1 adapter is intentionally unavailable. This module cannot publish a file
named Swirl-VF.ttc or change production acceptance. No HVF geometry is rewritten.

Memory policy: retain one sample batch and process one face at a time, with
two representations of that face during exact serialization verification.
FontTools serialization still needs a complete face; the encoded sample/model
limits are data budgets, not a claimed OS/RSS ceiling. TTC packing
has its own fixed-size byte buffers and never caches every face's table bytes.
"""
from __future__ import annotations

import array
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile

import fontTools
import numpy as np
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.models import normalizeLocation

import rebuild
from metric_variations import add_metric_variations
from ttc_staging_contract import StagingError, require
from ttc_staging_store import BatchStore, canonical_bytes, file_digest, digest_bytes, _safe_path
from ttc_staging_validate import validate_face, face_contract, validate_collection
from ttc_staging_pack import pack_collection


AXIS_TAGS = ("WDTH", "wght", "HGHT")
APPLE_SOURCE_SHA256 = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def encode_model(gid, result):
    glyph, variations, hm, vm, proof = result
    require(not proof["failures"], "outline", "glyph_model_failed", glyph_id=gid)
    return {"gid": gid, "points": [list(pair) for pair in glyph.coordinates],
            "end_points": list(glyph.endPtsOfContours), "flags": list(glyph.flags),
            "hmtx": list(hm), "vmtx": list(vm),
            "variations": [{"axes": {tag: list(support) for tag, support in variation.axes.items()},
                            "deltas": [list(pair) for pair in variation.coordinates]}
                           for variation in variations],
            "verification": {key: proof[key] for key in
                ("max_outline_error_bound_units", "max_metric_error_units", "training_count", "holdout_count")}}


def decode_model(record):
    """No pickle, code execution, omitted GIDs, or implicit sparse model repair."""
    required = {"gid", "points", "end_points", "flags", "hmtx", "vmtx", "variations", "verification"}
    require(type(record) is dict and set(record) == required and _int(record["gid"], 0, 65534),
            "serialization", "invalid_glyph_model")
    points, ends, flags = record["points"], record["end_points"], record["flags"]
    require(type(points) is list and len(points) <= 65535 and type(flags) is list
            and len(flags) == len(points) and type(ends) is list and len(ends) <= 32767,
            "outline", "invalid_glyph_topology")
    require(all(type(pair) is list and len(pair) == 2 and all(_int(n, -32768, 32767) for n in pair)
                for pair in points), "outline", "invalid_glyph_coordinate")
    require(all(_int(flag, 0, 255) and flag & ~0x41 == 0 for flag in flags),
            "outline", "invalid_glyph_flags")
    require((not points and not ends) or (bool(ends) and all(_int(n, 0, len(points) - 1) for n in ends)
            and all(a < b for a, b in zip([-1] + ends[:-1], ends)) and ends[-1] == len(points) - 1),
            "outline", "invalid_contour_end_points")
    for key in ("hmtx", "vmtx"):
        value = record[key]
        require(type(value) is list and len(value) == 2 and _int(value[0], 0, 65535)
                and _int(value[1], -32768, 32767), "metrics", "invalid_model_metrics")
    variations = []
    require(type(record["variations"]) is list and len(record["variations"]) <= 4095,
            "outline", "invalid_model_variations")
    for value in record["variations"]:
        require(type(value) is dict and set(value) == {"axes", "deltas"}
                and type(value["axes"]) is dict and bool(value["axes"])
                and set(value["axes"]) <= set(AXIS_TAGS), "input_axis", "invalid_model_support")
        for support in value["axes"].values():
            require(type(support) is list and len(support) == 3
                    and all(type(v) in (int, float) and math.isfinite(v) and -1 <= v <= 1
                            and v * 16384 == int(v * 16384) for v in support)
                    and support[0] <= support[1] <= support[2]
                    and support[1] != 0 and not support[0] < 0 < support[2],
                    "input_axis", "invalid_model_support")
        deltas = value["deltas"]
        require(type(deltas) is list and len(deltas) == len(points) + 4
                and all(type(p) is list and len(p) == 2 and all(_int(n, -32768, 32767) for n in p)
                        for p in deltas), "outline", "invalid_model_delta_count")
        variations.append(TupleVariation({tag: tuple(v) for tag, v in value["axes"].items()},
                                         [tuple(v) for v in deltas]))
    proof = record["verification"]
    require(type(proof) is dict and set(proof) == {"max_outline_error_bound_units", "max_metric_error_units",
                                                  "training_count", "holdout_count"}
            and all(type(proof[k]) in (int, float) and math.isfinite(proof[k]) and 0 <= proof[k] <= 1
                    for k in ("max_outline_error_bound_units", "max_metric_error_units"))
            and _int(proof["training_count"], 27, 10000) and _int(proof["holdout_count"], 1, 10000),
            "serialization", "invalid_model_verification")
    glyph = Glyph()
    glyph.numberOfContours = len(ends)
    glyph.coordinates = GlyphCoordinates([tuple(p) for p in points])
    glyph.endPtsOfContours = list(ends)
    glyph.flags = array.array("B", flags)
    glyph.program = Program()
    glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    return glyph, variations, tuple(record["hmtx"]), tuple(record["vmtx"])


def builder_identity():
    root = Path(__file__).parent
    names = ("rebuild.py", "metric_variations.py", "ttc_staging_engine.py", "ttc_staging_store.py",
             "ttc_staging_validate.py", "ttc_staging_pack.py", "ttc_staging_contract.py")
    return digest_bytes(canonical_bytes({name: file_digest(root / name) for name in names}))


def _source_faces(source):
    """Admit only the named original test generators; no original Apple input."""
    with source.open("rb") as stream:
        header = stream.read(12)
    require(len(header) == 12 and header[:4] == b"ttcf"
            and struct.unpack(">I", header[4:8])[0] in (0x10000, 0x20000)
            and 1 <= struct.unpack(">I", header[8:12])[0] <= 32,
            "font_tables", "synthetic_ttc_header")
    counts, identities = [], []
    for index in range(struct.unpack(">I", header[8:12])[0]):
        with TTFont(source, fontNumber=index, lazy=True) as font:
            require(not any(tag in font for tag in ("hvgl", "hvpm", "CFF ", "CFF2")),
                    "input_axis", "production_adapter_unavailable")
            require(all(tag in font for tag in ("glyf", "gvar", "fvar", "hmtx", "vmtx", "name", "STAT")),
                    "font_tables", "synthetic_required_table_missing")
            family = font["name"].getDebugName(1) or ""
            require(family.startswith(("C1 Original Geometry ", "Swirl Synthetic Three Axis ")),
                    "input_axis", "original_fixture_identity_required")
            require(tuple(a.axisTag for a in font["fvar"].axes) == AXIS_TAGS,
                    "input_axis", "original_axis_tags_or_order_changed")
            require("MVAR" not in font and "VORG" not in font, "metrics", "unmapped_metric_table")
            for tag in ("GSUB", "GPOS", "BASE", "GDEF"):
                if tag in font:
                    table = font[tag].table
                    require(not any(getattr(table, attr, None) for attr in
                                    ("FeatureVariations", "VarStore", "ItemVarStore")),
                            "font_tables", "unmapped_layout_variations", table=tag)
            count = font["maxp"].numGlyphs
            require(1 <= count <= 65535 and len(font.getGlyphOrder()) == count,
                    "font_tables", "synthetic_gid_count")
            names = set(font.getGlyphOrder())
            for subtable in font["cmap"].tables:
                if subtable.format == 14:
                    mapped = [name for entries in subtable.uvsDict.values() for _, name in entries if name is not None]
                else:
                    mapped = list(subtable.cmap.values())
                require(all(name in names and 0 <= font.getGlyphID(name) < count for name in mapped),
                        "font_tables", "source_cmap_gid_reference", face_index=index)
            # No dict interpretation of raw source avar; this synthetic path
            # accepts identity mappings only. Real A3 semantics stay gated.
            if "avar" in font:
                require(font["avar"].majorVersion == 1 and all(
                    mappings == {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}
                    for mappings in font["avar"].segments.values())
                    and set(font["avar"].segments) == set(AXIS_TAGS),
                    "input_axis", "nonidentity_synthetic_avar")
            counts.append(count)
            identities.append({"face_index": index, "glyph_count": count,
                               "tables": {tag: hashlib.sha256(font.reader[tag]).hexdigest()
                                          for tag in font.reader.keys()}})
    return counts, digest_bytes(canonical_bytes(identities))


def _batch_models(source_font, face, start, stop, factory, source_hash, store, sample_limit):
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in source_font["fvar"].axes}
    training = rebuild.normalized_grid(list(axes))
    holdouts = rebuild.heldout_locations(list(axes), seed=20261019 + face)
    for instance in source_font["fvar"].instances:
        normalized = normalizeLocation(instance.coordinates, axes)
        if normalized not in training and normalized not in holdouts:
            holdouts.append(normalized)
    gids, samples = list(range(start, stop)), []
    try:
        session = factory()
    except StagingError:
        raise
    except Exception as error:
        raise StagingError("platform_read", "oracle_session_creation_failed", face_index=face) from error
    total_bytes = 0
    try:
        require(getattr(session, "synthetic_only", False) is True,
                "platform_read", "synthetic_oracle_marker_required")
        require(getattr(session, "source_sha256", None) == source_hash,
                "platform_read", "synthetic_oracle_source_mismatch")
        for location in training + holdouts:
            try:
                rows = session.samples(face, gids, rebuild.user_location(location, axes))
            except StagingError:
                raise
            except Exception as error:
                raise StagingError("platform_read", "oracle_sample_failed", face_index=face,
                                   gid_first=start, gid_last=stop - 1) from error
            require(type(rows) is dict and all(type(gid) is int for gid in rows)
                    and set(rows) == set(gids), "platform_read", "batch_gids_mismatch", face_index=face)
            total_bytes += len(canonical_bytes(rows))
            require(total_bytes <= sample_limit, "serialization", "sample_memory_budget",
                    limit_bytes=sample_limit, observed_bytes=total_bytes)
            samples.append(rows)
        models = []
        order = source_font.getGlyphOrder()
        for gid in gids:
            try:
                result = rebuild.reconstruct_glyph(
                    [rows[gid] for rows in samples[:len(training)]],
                    [rows[gid] for rows in samples[len(training):]], training, holdouts, axes,
                    source_font["hmtx"].metrics[order[gid]], source_font["vmtx"].metrics[order[gid]],
                    outline_limit=1.0, metric_limit=1.0)
            except rebuild.ReconstructionError as error:
                metric_errors = {"invalid native advance", "invalid native bearing/origin",
                    "native metric oracle missing explicit origins/bearing; cannot claim metric preservation",
                    "unrepresentable TrueType metrics", "rounded TrueType advance/bearing is not representable"}
                category = "metrics" if "metric_representation" in error.context or str(error) in metric_errors else "outline"
                raise StagingError(category, "existing_reconstructor_rejected", face_index=face, glyph_id=gid) from error
            except (KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
                raise StagingError("platform_read", "invalid_sample_record", face_index=face, glyph_id=gid) from error
            proof = result[-1]
            if proof["failures"]:
                category = "metrics" if proof["max_metric_error_units"] > 1.0 else "outline"
                raise StagingError(category, "sampled_model_budget_exceeded", face_index=face, glyph_id=gid,
                                   max_outline_error=proof["max_outline_error_bound_units"],
                                   max_metric_error=proof["max_metric_error_units"])
            model = encode_model(gid, result)
            decode_model(model)
            models.append(model)
        try:
            summary = session.finish()
        except StagingError:
            raise
        except Exception as error:
            raise StagingError("platform_read", "oracle_finalization_failed", face_index=face) from error
        try:
            rebuild.verify_session_summary(summary, source_hash, len(samples), len(samples) * len(gids))
        except rebuild.ReconstructionError as error:
            raise StagingError("platform_read", "batch_summary_mismatch", face_index=face) from error
        require(summary.get("synthetic_test_double_only") is True,
                "platform_read", "synthetic_summary_required")
        require(file_digest(Path(session.source)) == source_hash,
                "platform_read", "source_changed_during_batch")
        evidence = {"schema": 1, "source_sha256": source_hash, "recipe_sha256": store.recipe_sha256,
                    "face_index": face, "gid_start": start, "gid_stop": stop,
                    "session_finished": True, "source_unchanged": True,
                    "request_count": len(samples), "observation_count": len(samples) * len(gids),
                    "kind": "synthetic_analytic"}
        return models, evidence, total_bytes
    finally:
        try:
            session.close()
        except StagingError:
            raise
        except Exception as error:
            raise StagingError("platform_read", "oracle_close_failed", face_index=face) from error


def run_synthetic_staging(source, checkpoint_dir, destination, oracle_factory, *, oracle_sha256,
                          batch_size=64, max_sample_bytes=64 * 1024**2,
                          max_batch_bytes=64 * 1024**2, max_face_model_bytes=256 * 1024**2):
    """Run all GIDs, retaining batch progress across failures. Synthetic only.

    Each factory call must produce a new complete analytic session. It exposes
    synthetic_only=True, source/source_sha256, samples, finish and close. The
    caller binds the exact generator bytes in oracle_sha256. A future production
    entry point needs reviewed native admission, never a change to this flag.
    """
    source, checkpoint_dir, destination = map(_safe_path, (source, checkpoint_dir, destination))
    require(destination.name.casefold() != "swirl-vf.ttc", "input_axis", "production_filename_reserved")
    require(not destination.exists() and not destination.is_symlink(), "serialization", "output_exists")
    require(source != destination and not source.is_relative_to(checkpoint_dir)
            and not destination.is_relative_to(checkpoint_dir), "serialization", "protected_path_alias")
    require(all(_int(n, 1024, 512 * 1024**2) for n in (max_sample_bytes, max_batch_bytes, max_face_model_bytes)),
            "serialization", "invalid_memory_budget")
    require(type(oracle_sha256) is str and len(oracle_sha256) == 64
            and all(c in "0123456789abcdef" for c in oracle_sha256),
            "platform_read", "invalid_oracle_identity")
    try:
        source_hash = file_digest(source)
    except OSError as error:
        raise StagingError("platform_read", "source_read_failed") from error
    require(source_hash != APPLE_SOURCE_SHA256, "input_axis", "production_adapter_unavailable")
    try:
        counts, identity = _source_faces(source)
    except StagingError:
        raise
    except Exception as error:
        raise StagingError("font_tables", "source_structure_read_failed") from error
    binding = {"mode": "synthetic", "source_sha256": source_hash, "builder_sha256": builder_identity(),
               "source_identity_sha256": identity, "oracle_sha256": oracle_sha256,
               "dependencies": {"python": list(sys.version_info[:3]), "fonttools": fontTools.__version__,
                                "numpy": np.__version__},
               "settings": {"outline_limit": 1.0, "metric_limit": 1.0, "cubic_error": 0.05,
                            "max_sample_bytes": max_sample_bytes, "max_face_model_bytes": max_face_model_bytes,
                            "adaptive_training": "not_enabled_in_synthetic_staging"}}
    store = BatchStore(checkpoint_dir, binding, counts, batch_size=batch_size, max_payload_bytes=max_batch_bytes)
    reused = built = peak_samples = peak_face_bytes = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with store.writer(), tempfile.TemporaryDirectory(prefix="c1-face-assembly-", dir=destination.parent) as temporary:
        paths, contracts, face_reports = [], [], []
        for face, count in enumerate(counts):
            require(file_digest(source) == source_hash, "platform_read", "source_changed_before_face")
            # TTCollection would retain every opened face. Open and release one
            # physical face independently so there is no 32-face decoded cache.
            with TTFont(source, fontNumber=face, lazy=True, recalcTimestamp=False) as source_font:
                for _, start, stop in store.ranges(face):
                    restored = store.restore(face, start, stop)
                    if restored is not None:
                        # Content integrity alone is insufficient; revalidate
                        # the complete model schema and every GID on restore.
                        for model in restored[0]:
                            decode_model(model)
                        reused += 1
                        continue
                    models, proof, sample_bytes = _batch_models(source_font, face, start, stop,
                        oracle_factory, source_hash, store, max_sample_bytes)
                    require(file_digest(source) == source_hash, "platform_read", "source_changed_before_checkpoint")
                    store.commit(face, start, stop, models, proof)
                    built += 1
                    peak_samples = max(peak_samples, sample_bytes)
            # Bound encoded face size before materializing any model for this
            # face. FontTools object overhead is separate and documented.
            face_bytes = 0
            for _, start, stop in store.ranges(face):
                restored = store.restore(face, start, stop)
                require(restored is not None, "serialization", "incomplete_face_checkpoint")
                face_bytes += len(canonical_bytes(restored[0]))
                require(face_bytes <= max_face_model_bytes, "serialization", "face_model_memory_budget",
                        limit_bytes=max_face_model_bytes, observed_bytes=face_bytes, face_index=face)
            peak_face_bytes = max(peak_face_bytes, face_bytes)
            with TTFont(source, fontNumber=face, lazy=True, recalcTimestamp=False) as out:
                order = list(out.getGlyphOrder())
                regenerated = {"head", "maxp", "hhea", "hmtx", "vhea", "vmtx",
                               "glyf", "loca", "gvar", "HVAR", "VVAR"}
                retained = {tag: out.getTableData(tag) for tag in out.reader.keys() if tag not in regenerated}
                expected_tables = set(out.reader.keys()) | {"HVAR", "VVAR"}
                out["glyf"] = newTable("glyf")
                out["glyf"].glyphs, out["glyf"].glyphOrder = {}, order
                out["loca"] = newTable("loca")
                out["gvar"] = newTable("gvar")
                out["gvar"].version, out["gvar"].reserved, out["gvar"].variations = 1, 0, {}
                for _, start, stop in store.ranges(face):
                    models, _ = store.restore(face, start, stop)
                    for model in models:
                        glyph, variations, hm, vm = decode_model(model)
                        name = order[model["gid"]]
                        out["glyf"].glyphs[name], out["gvar"].variations[name] = glyph, variations
                        out["hmtx"].metrics[name], out["vmtx"].metrics[name] = hm, vm
                # Reuse exactly the shared validated metric encoder.
                for tag in ("HVAR", "VVAR"):
                    if tag in out:
                        del out[tag]
                add_metric_variations(out)
                path = Path(temporary) / f"face-{face:05d}.ttf"
                out.save(path)
                with TTFont(path, lazy=True, recalcTimestamp=False) as reopened:
                    coefficients = rebuild.verify_serialized_face(out, reopened)
                    require(reopened.getGlyphOrder() == order, "font_tables",
                            "reconstruction_gid_order_changed", face_index=face)
                    require(set(reopened.reader.keys()) == expected_tables, "font_tables",
                            "reconstruction_table_set_changed", face_index=face)
                    for tag, data in retained.items():
                        require(reopened.getTableData(tag) == data,
                                "input_axis" if tag in ("fvar", "avar") else "font_tables",
                                "reconstruction_retained_table_changed", table=str(tag), face_index=face)
                    structure = validate_face(reopened)
                    contracts.append(face_contract(reopened))
                face_reports.append({"face_index": face, "glyphs_checked": count,
                                     "coefficients": coefficients, "structure": structure})
                paths.append(path)
            # Closing TTFont releases its file handle, but these local bindings
            # still own decoded tables and the final restored batch. Lazy table
            # readers may also form cycles; collect them before sampling the
            # next face so the face-at-a-time policy covers object lifetimes.
            del source_font, out, reopened, retained, order, models, model
            del restored, glyph, variations, hm, vm, data
            gc.collect()
        require(file_digest(source) == source_hash, "platform_read", "source_changed_before_packing")
        collection_report = {}
        def verify(candidate):
            collection_report.update(validate_collection(candidate, contracts))
            require(file_digest(source) == source_hash, "platform_read", "source_changed_before_publication")
        packed = pack_collection(paths, destination, expected_sha256=[file_digest(p) for p in paths], validate=verify)
        return {"status": "SYNTHETIC_STAGING_PASS", "source_sha256": source_hash,
                "recipe_sha256": store.recipe_sha256, "synthetic_only": True,
                "production_accepted": False, "apple_or_coretext_executed": False,
                "original_faces_completed": 0, "batches_built": built, "batches_reused": reused,
                "peak_sample_encoded_bytes": peak_samples, "peak_face_model_encoded_bytes": peak_face_bytes,
                "memory_scope": "encoded budgets; one face at a time, two representations during verification; not an RSS ceiling",
                "faces": face_reports, "collection": collection_report, "packing": packed}
