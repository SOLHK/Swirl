"""C1 TTC integrity/streaming tests using only original geometric font data."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import tracemalloc
from types import SimpleNamespace
import unittest
from unittest import mock

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import normalizeLocation

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "tools"),
               str(Path(__file__).resolve().parents[1] / "platform")]
from rebuild_c1_fixture import AXES, BASE_ORDER, write_faces
from ttc_staging_contract import StagingError
import ttc_staging_pack as pack


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stat_copy(value, **overrides):
    fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
    fields.update(overrides)
    return SimpleNamespace(**fields)


class PackingTests(unittest.TestCase):
    def fixture(self, count=2):
        temporary = tempfile.TemporaryDirectory(prefix="c1-original-pack-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paths = write_faces(root / "faces", count)
        return root, paths, root / "original-geometry.ttc"

    def assert_no_candidate(self, root, output):
        self.assertFalse(output.exists())
        self.assertFalse(list(root.glob(".ttc-staging-*")))

    def test_all_32_faces_reopen_exact_gid_axes_names_regions_layout_and_table_bytes(self):
        root, paths, output = self.fixture(32)
        hashes = [sha(path) for path in paths]
        result = pack.pack_collection(paths, output, expected_sha256=hashes, chunk_size=37)
        self.assertEqual(result["status"], "STAGED_COLLECTION")
        self.assertEqual(result["faces"], 32)
        self.assertFalse(result["production_accepted"])
        self.assertFalse(result["native_source_equivalence"])
        self.assertEqual(result["sha256"], sha(output))
        self.assertGreater(result["table_references_shared"], 0)
        with TTCollection(output, lazy=True) as collection:
            self.assertEqual(len(collection.fonts), 32)
            names = set()
            for index, (path, actual) in enumerate(zip(paths, collection.fonts)):
                with TTFont(path, lazy=True) as expected:
                    self.assertEqual(actual.getGlyphOrder(), list(BASE_ORDER))
                    self.assertEqual(actual["maxp"].numGlyphs, 7)
                    self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                                      for a in actual["fvar"].axes],
                                     [(tag, *values) for tag, values in AXES.items()])
                    self.assertEqual(len(actual["fvar"].instances), 2)
                    self.assertEqual(actual.getBestCmap()[0xE000 + index], "regional")
                    self.assertEqual(actual.getBestCmap()[0x20000 + index], "curve")
                    self.assertNotIn("unencoded", actual.getBestCmap().values())
                    uvs = next(t for t in actual["cmap"].tables if t.format == 14)
                    self.assertEqual(uvs.uvsDict[0xFE00], [(65, None), (0xE000 + index, "regional.alt")])
                    self.assertEqual(actual["OS/2"].usWeightClass, 500)
                    self.assertEqual(actual["OS/2"].usWidthClass, 1 + index % 9)
                    self.assertEqual(actual["name"].getDebugName(6), expected["name"].getDebugName(6))
                    names.add(actual["name"].getDebugName(6))
                    for tag in ("GSUB", "GPOS", "GDEF", "gvar", "HVAR", "VVAR", "vmtx", "hmtx"):
                        self.assertIn(tag, actual)
                    self.assertEqual(set(expected.reader.tables), set(actual.reader.tables))
                    for tag in expected.reader.tables:
                        a, b = expected.reader[tag], actual.reader[tag]
                        if tag == "head":
                            a = a[:8] + b"\0" * 4 + a[12:]
                        self.assertEqual(a, b, (index, tag))
            self.assertEqual(len(names), 32)
        self.assertEqual([sha(path) for path in paths], hashes)
        self.assertFalse(list(root.glob(".ttc-staging-*")))

    def test_32_faces_all_gids_unseen_mixed_axis_interpolation_and_metric_phantoms(self):
        _, paths, output = self.fixture(32)
        pack.pack_collection(paths, output)
        locations = [dict(zip(AXES, xyz)) for xyz in
                     [(0, 0, 0), (1, -1, 1), (.25, -.5, .75), (-.75, .5, -.25)]]
        observations = 0
        with TTCollection(output, lazy=True) as collection:
            for index, actual in enumerate(collection.fonts):
                for location in locations:
                    glyph_set = actual.getGlyphSet(location=location, normalized=True)
                    x, w, y = (location[t] for t in AXES)
                    for gid, name in enumerate(actual.getGlyphOrder()):
                        record = RecordingPen()
                        glyph_set[name].draw(record)
                        expected_width = 250 + gid % 21 * 21 + index + 80*x + 20*w + 12*x*y
                        self.assertAlmostEqual(glyph_set[name].width, expected_width, places=10)
                        if gid < 2:
                            self.assertEqual(record.value, [])
                        else:
                            base = RecordingPen()
                            actual.getGlyphSet()[name].draw(base)
                            left, bottom = 10 + gid % 11, -20
                            expected = [(op, tuple((px + (80*x+20*w+12*x*y if px > left else 0),
                                                  py + (60*y if py > bottom else 0))
                                                 for px, py in points))
                                        for op, points in base.value]
                            self.assertEqual(record.value, expected)
                        observations += 1
                # Use full varLib instancing as a second consumer of stored
                # gvar and VVAR. The non-default phantom height is independent
                # of glyph bounds and includes empty .notdef/space glyphs.
                user = {tag: low + (high - low) * .75 for tag, (low, _, high) in AXES.items()}
                normalized = normalizeLocation(user, AXES)
                instance = instantiateVariableFont(actual, user, inplace=False)
                for gid, name in enumerate(actual.getGlyphOrder()):
                    expected_height = int(1000 + index + 60 * normalized["HGHT"] + .5)
                    self.assertEqual(instance["vmtx"].metrics[name][0], expected_height)
                instance.close()
        self.assertEqual(observations, 32 * 7 * 4)

    def test_table_sharing_is_optional_and_never_changes_face_bytes(self):
        root, paths, shared = self.fixture(3)
        unshared = root / "without-sharing.ttc"
        yes = pack.pack_collection(paths, shared)
        no = pack.pack_collection(paths, unshared, share_tables=False)
        self.assertGreater(yes["table_references_shared"], 0)
        self.assertEqual(no["table_references_shared"], 0)
        self.assertLess(shared.stat().st_size, unshared.stat().st_size)
        with TTCollection(shared, lazy=True) as a, TTCollection(unshared, lazy=True) as b:
            for af, bf in zip(a.fonts, b.fonts):
                self.assertEqual({t: af.reader[t] for t in af.reader.keys()},
                                 {t: bf.reader[t] for t in bf.reader.keys()})

    def test_hash_collision_never_coalesces_different_table_bytes(self):
        _, paths, output = self.fixture(2)
        for path, values in zip(paths, ((1, 2), (2, 1))):
            with TTFont(path) as font:
                font["TEST"] = newTable("TEST")
                font["TEST"].data = struct.pack(">II", *values)
                font.save(path)
        real = pack._fingerprint
        def collision(*args, **kwargs):
            _, checksum = real(*args, **kwargs)
            return "0" * 64, checksum
        with mock.patch.object(pack, "_fingerprint", side_effect=collision):
            pack.pack_collection(paths, output)
        with TTCollection(output, lazy=True) as collection:
            self.assertNotEqual(collection.fonts[0].reader.tables["TEST"].offset,
                                collection.fonts[1].reader.tables["TEST"].offset)
            for font, values in zip(collection.fonts, ((1, 2), (2, 1))):
                self.assertEqual(font.reader["TEST"], struct.pack(">II", *values))

    def test_large_shared_table_does_not_create_full_table_memory_cache(self):
        _, paths, output = self.fixture(1)
        with TTFont(paths[0]) as font:
            font["TEST"] = newTable("TEST")
            font["TEST"].data = b"C1 original geometric metadata\0\0" * 65536
            table_size = len(font["TEST"].data)
            font.save(paths[0])
        del font
        tracemalloc.start()
        try:
            report = pack.pack_collection([paths[0], paths[0]], output, chunk_size=4096)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, table_size // 2, "writer buffered a complete large table")
        self.assertEqual(report["copy_chunk_bytes"], 4096)
        self.assertGreater(report["table_references_shared"], 0)

    def test_head_checksum_zeroing_works_across_all_small_chunk_boundaries(self):
        root, paths, _ = self.fixture(1)
        for chunk in (1, 3, 7, 13, 64):
            target = root / f"chunk-{chunk}.ttc"
            pack.pack_collection(paths, target, chunk_size=chunk)
            with TTCollection(target, lazy=True) as collection:
                self.assertEqual(collection.fonts[0].reader["head"][8:12], b"\0" * 4)

    def test_expected_hash_mismatch_rejects_before_output(self):
        root, paths, output = self.fixture(1)
        with self.assertRaisesRegex(StagingError, "source_sha256_mismatch"):
            pack.pack_collection(paths, output, expected_sha256=["0" * 64])
        self.assert_no_candidate(root, output)

    def test_bad_checksum_rejects_before_output(self):
        root, paths, output = self.fixture(1)
        with TTFont(paths[0], lazy=True) as font:
            offset = font.reader.tables["name"].offset
        data = bytearray(paths[0].read_bytes())
        data[offset + 1] ^= 1
        paths[0].write_bytes(data)
        with self.assertRaisesRegex(StagingError, "source_table_checksum_mismatch"):
            pack.pack_collection(paths, output)
        self.assert_no_candidate(root, output)

    def test_invalid_sfnt_headers_and_ranges_are_not_repaired(self):
        root, paths, output = self.fixture(1)
        original = paths[0].read_bytes()
        cases = [
            (lambda b: b.__setitem__(slice(0, 4), b"ttcf"), "unsupported_standalone_sfnt"),
            (lambda b: b.__setitem__(slice(4, 6), b"\0\0"), "invalid_sfnt_table_count"),
            (lambda b: b.__setitem__(slice(6, 8), b"\0\0"), "invalid_sfnt_search_fields"),
            (lambda b: b.__setitem__(slice(28, 32), b[12:16]), "duplicate_or_unsorted_table_tag"),
            (lambda b: b.__setitem__(slice(20, 24), struct.pack(">I", 3)), "invalid_table_range"),
            (lambda b: b.__setitem__(slice(20, 28), struct.pack(">II", 0xFFFFFFFC, 8)), "ttc_offset_overflow"),
            (lambda b: b.__setitem__(slice(36, 44), b[20:28]), "overlapping_standalone_tables"),
        ]
        for mutate, code in cases:
            with self.subTest(code=code):
                data = bytearray(original)
                mutate(data)
                paths[0].write_bytes(data)
                with self.assertRaisesRegex(StagingError, code):
                    pack.pack_collection(paths, output)
                self.assert_no_candidate(root, output)
        paths[0].write_bytes(b"\0\1\0\0")
        with self.assertRaisesRegex(StagingError, "truncated_sfnt_header"):
            pack.pack_collection(paths, output)

    def test_existing_destination_never_changes(self):
        root, paths, output = self.fixture(1)
        output.write_bytes(b"confirmed existing output")
        with self.assertRaisesRegex(StagingError, "destination_exists"):
            pack.pack_collection(paths, output)
        self.assertEqual(output.read_bytes(), b"confirmed existing output")
        self.assertFalse(list(root.glob(".ttc-staging-*")))

    def test_production_filename_is_reserved_even_for_valid_synthetic_input(self):
        root, paths, _ = self.fixture(1)
        for name in ("Swirl-VF.ttc", "swirl-vf.TTC", "SWIRL-VF.TTC"):
            output = root / name
            with self.subTest(name=name), self.assertRaisesRegex(StagingError, "production_filename_reserved"):
                pack.pack_collection(paths, output)
            self.assert_no_candidate(root, output)

    def test_standalone_contracts_survive_streaming_pack_and_validation_callback(self):
        from ttc_staging_validate import face_contract, validate_collection
        root, paths, output = self.fixture(2)
        expected = []
        for path in paths:
            with TTFont(path) as font:
                expected.append(face_contract(font))
        validations = []
        def validate(candidate):
            self.assertFalse(output.exists())
            validations.append(validate_collection(candidate, expected))
        pack.pack_collection(paths, output, validate=validate)
        self.assertEqual(validations[0]["glyphs_checked"], 14)
        self.assertFalse(validations[0]["production_accepted"])

    def test_source_symlink_and_output_symlink_are_rejected(self):
        root, paths, output = self.fixture(1)
        alias = root / "alias.ttf"
        try:
            alias.symlink_to(paths[0])
        except OSError:
            self.skipTest("this host does not allow unprivileged symbolic links")
        with self.assertRaisesRegex(StagingError, "source_not_regular"):
            pack.pack_collection([alias], output)
        output.symlink_to(paths[0])
        before = paths[0].read_bytes()
        with self.assertRaisesRegex(StagingError, "destination_exists"):
            pack.pack_collection(paths, output)
        self.assertEqual(paths[0].read_bytes(), before)

    def test_callback_failure_cleans_candidate_and_preserves_input(self):
        root, paths, output = self.fixture(1)
        before = sha(paths[0])
        def fail(candidate):
            self.assertTrue(candidate.exists())
            self.assertFalse(output.exists())
            raise StagingError("font_tables", "test_contract_rejection")
        with self.assertRaisesRegex(StagingError, "test_contract_rejection"):
            pack.pack_collection(paths, output, validate=fail)
        self.assert_no_candidate(root, output)
        self.assertEqual(sha(paths[0]), before)

    def test_callback_cannot_modify_candidate_after_integrity_check(self):
        root, paths, output = self.fixture(1)
        def mutate(candidate):
            with candidate.open("r+b") as stream:
                stream.write(b"bad!")
        with self.assertRaisesRegex(StagingError, "ttc_header_changed"):
            pack.pack_collection(paths, output, validate=mutate)
        self.assert_no_candidate(root, output)

    def test_callback_cannot_append_unverified_bytes(self):
        root, paths, output = self.fixture(1)
        def mutate(candidate):
            with candidate.open("ab") as stream:
                stream.write(b"unverified")
        with self.assertRaisesRegex(StagingError, "ttc_size_changed"):
            pack.pack_collection(paths, output, validate=mutate)
        self.assert_no_candidate(root, output)

    def test_source_change_after_copy_blocks_collection(self):
        root, paths, output = self.fixture(1)
        def mutate(_candidate):
            with paths[0].open("ab") as stream:
                stream.write(b"source changed")
        with self.assertRaisesRegex(StagingError, "source_changed_during_pack"):
            pack.pack_collection(paths, output, validate=mutate)
        self.assert_no_candidate(root, output)

    def test_windows_path_and_fd_change_times_can_differ_without_changing_identity(self):
        # Reproduce CPython's Windows lstat creation-time / fstat change-time
        # split on every CI platform; do not require a Windows runner to guard
        # against reintroducing a cross-API ctime comparison.
        root, paths, output = self.fixture(2)
        real_fstat = pack.os.fstat
        def descriptor_stat(fd):
            value = real_fstat(fd)
            return stat_copy(value, st_ctime_ns=value.st_ctime_ns + 123456789)
        hashes = [sha(path) for path in paths]
        with mock.patch.object(pack.os, "fstat", side_effect=descriptor_stat):
            result = pack.pack_collection(paths, output, expected_sha256=hashes)
        self.assertEqual(result["source_sha256"], hashes)
        with TTCollection(output, lazy=True) as collection:
            self.assertEqual(len(collection.fonts), 2)
            self.assertEqual(collection.fonts[0].getGlyphOrder(), list(BASE_ORDER))
        self.assertFalse(list(root.glob(".ttc-staging-*")))

    def test_path_and_descriptor_still_bind_device_inode_size_and_mtime(self):
        root, paths, output = self.fixture(1)
        real_fstat = pack.os.fstat
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns"):
            def descriptor_stat(fd):
                value = real_fstat(fd)
                return stat_copy(value, **{field: getattr(value, field) + 1})
            with self.subTest(field=field), mock.patch.object(pack.os, "fstat", side_effect=descriptor_stat):
                with self.assertRaisesRegex(StagingError, "source_changed_before_open"):
                    pack.pack_collection(paths, output)
            self.assert_no_candidate(root, output)

    def test_same_bytes_path_replacement_between_stat_and_open_is_rejected(self):
        root, paths, output = self.fixture(1)
        real_regular = pack._regular
        replaced = False
        original = sha(paths[0])
        def replace_before_open(path):
            nonlocal replaced
            value = real_regular(path)
            if path == paths[0] and not replaced:
                replacement = root / "replacement.ttf"
                replacement.write_bytes(path.read_bytes())
                pack.os.utime(replacement, ns=(value.st_atime_ns, value.st_mtime_ns))
                replacement.replace(path)
                replaced = True
            return value
        with mock.patch.object(pack, "_regular", side_effect=replace_before_open):
            with self.assertRaisesRegex(StagingError, "source_changed_before_open"):
                pack.pack_collection(paths, output)
        self.assertEqual(sha(paths[0]), original)
        self.assert_no_candidate(root, output)

    def test_change_time_is_still_checked_separately_for_each_api_and_phase(self):
        root, paths, output = self.fixture(1)
        real_regular, real_fstat = pack._regular, pack.os.fstat
        for api in ("path", "fd"):
            for phase in ("scan", "pack"):
                calls = {"path": 0, "fd": 0}
                after_callback = False
                def change(value, current):
                    calls[current] += 1
                    during_scan = phase == "scan" and calls[current] >= {"path": 3, "fd": 2}[current]
                    if api == current and (during_scan or after_callback):
                        return stat_copy(value, st_ctime_ns=value.st_ctime_ns + 1)
                    return value
                def path_stat(path):
                    return change(real_regular(path), "path")
                def descriptor_stat(fd):
                    return change(real_fstat(fd), "fd")
                def mutate_metadata(_candidate):
                    nonlocal after_callback
                    after_callback = True
                code = "source_changed_during_scan" if phase == "scan" else "source_changed_during_pack"
                with self.subTest(api=api, phase=phase), \
                        mock.patch.object(pack, "_regular", side_effect=path_stat), \
                        mock.patch.object(pack.os, "fstat", side_effect=descriptor_stat):
                    with self.assertRaisesRegex(StagingError, code):
                        pack.pack_collection(paths, output, validate=mutate_metadata)
                self.assert_no_candidate(root, output)

    def test_full_file_hash_detects_changes_even_when_all_metadata_is_unchanged(self):
        root, paths, output = self.fixture(1)
        # Bytes outside table ranges must also remain immutable. Freeze both
        # metadata APIs so only the whole-source content guard can detect this.
        with paths[0].open("ab") as stream:
            stream.write(b"original synthetic trailing metadata")
        real_regular, real_fstat = pack._regular, pack.os.fstat
        path_snapshot = real_regular(paths[0])
        with paths[0].open("rb") as stream:
            fd_snapshot = real_fstat(stream.fileno())
        def path_stat(path):
            return path_snapshot if path == paths[0] else real_regular(path)
        def descriptor_stat(fd):
            value = real_fstat(fd)
            return fd_snapshot if (value.st_dev, value.st_ino) == (fd_snapshot.st_dev, fd_snapshot.st_ino) else value
        def mutate(_candidate):
            with paths[0].open("r+b") as stream:
                stream.seek(-1, 2)
                stream.write(b"!")
        with mock.patch.object(pack, "_regular", side_effect=path_stat), \
                mock.patch.object(pack.os, "fstat", side_effect=descriptor_stat):
            with self.assertRaisesRegex(StagingError, "source_changed_during_pack"):
                pack.pack_collection(paths, output, validate=mutate)
        self.assert_no_candidate(root, output)

    def test_source_identity_is_rechecked_after_hash_read_completes(self):
        root, paths, output = self.fixture(1)
        face = pack._describe_face(paths[0], 4096, None)
        real_hash = pack._file_hash
        def change_after_read(stream, size, chunk_size):
            digest = real_hash(stream, size, chunk_size)
            with paths[0].open("ab") as writer:
                writer.write(b"changed after final read")
            return digest
        with paths[0].open("rb") as stream, mock.patch.object(pack, "_file_hash", side_effect=change_after_read):
            with self.assertRaisesRegex(StagingError, "source_changed_during_pack"):
                pack._source_unchanged(face, stream, 4096)
        self.assert_no_candidate(root, output)

    def test_concurrent_publisher_is_never_overwritten(self):
        root, paths, output = self.fixture(1)
        def race(_candidate):
            output.write_bytes(b"another confirmed result")
        with self.assertRaisesRegex(StagingError, "destination_exists"):
            pack.pack_collection(paths, output, validate=race)
        self.assertEqual(output.read_bytes(), b"another confirmed result")
        self.assertFalse(list(root.glob(".ttc-staging-*")))

    def test_interrupted_serialization_leaves_no_output_or_temp_candidate(self):
        root, paths, output = self.fixture(1)
        with mock.patch.object(pack, "_verify_packed", side_effect=OSError("simulated disk failure")):
            with self.assertRaisesRegex(StagingError, "ttc_pack_io_failure"):
                pack.pack_collection(paths, output)
        self.assert_no_candidate(root, output)

    def test_post_publish_durability_failure_removes_only_own_output(self):
        root, paths, output = self.fixture(1)
        with mock.patch.object(pack, "_fsync_directory", side_effect=OSError("directory failure")):
            with self.assertRaisesRegex(StagingError, "ttc_pack_io_failure"):
                pack.pack_collection(paths, output)
        self.assert_no_candidate(root, output)

    def test_missing_file_is_classified_as_platform_read(self):
        root, paths, output = self.fixture(1)
        paths[0].unlink()
        with self.assertRaises(StagingError) as error:
            pack.pack_collection(paths, output)
        self.assertEqual(error.exception.category, "platform_read")
        self.assert_no_candidate(root, output)

    def test_invalid_parameters_and_partial_hash_lists_reject(self):
        root, paths, output = self.fixture(1)
        for kwargs in ({"chunk_size": 0}, {"chunk_size": True}, {"chunk_size": 2**30},
                       {"expected_sha256": []}, {"expected_sha256": ["bad"]},
                       {"share_tables": 1}, {"validate": "pretend validator"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(StagingError):
                pack.pack_collection(paths, output, **kwargs)
        with self.assertRaisesRegex(StagingError, "invalid_collection_face_count"):
            pack.pack_collection([], output)
        self.assert_no_candidate(root, output)


if __name__ == "__main__":
    unittest.main()
