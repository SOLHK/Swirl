"""Independent raw TTC corruption tests built exclusively from original geometry."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.ttLib import TTFont, newTable

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'tools'),
               str(Path(__file__).resolve().parents[1] / 'platform')]
from rebuild_c1_fixture import write_faces
from ttc_staging_contract import StagingError
import ttc_staging_binary as binary
import ttc_staging_pack as pack


def directories(data):
    count = struct.unpack_from('>I', data, 8)[0]
    return list(struct.unpack_from('>' + str(count) + 'I', data, 12))


def entries(data, face=0):
    directory = directories(data)[face]
    count = struct.unpack_from('>H', data, directory + 4)[0]
    result = {}
    for index in range(count):
        position = directory + 12 + 16 * index
        tag, checksum, offset, length = struct.unpack_from('>4sIII', data, position)
        result[tag] = (position, checksum, offset, length)
    return result


class BinaryCollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='c1-original-binary-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.paths = write_faces(self.root / 'faces', 2)
        # Force every possible padding width, independent of FontTools versions.
        for path in self.paths:
            with TTFont(path) as font:
                for tag, payload in [('PAD1', b'x'), ('PAD2', b'xy'),
                                     ('PAD3', b'xyz'), ('ZERO', b'')]:
                    font[tag] = newTable(tag)
                    font[tag].data = payload
                font.save(path)
        self.good = self.root / 'original.ttc'
        pack.pack_collection(self.paths, self.good)
        self.data = self.good.read_bytes()
        self.bad = self.root / 'changed.ttc'

    def reject(self, mutate, code):
        changed = bytearray(self.data)
        mutate(changed)
        self.bad.write_bytes(changed)
        with self.assertRaisesRegex(StagingError, code) as raised:
            binary.validate_ttc_binary(self.bad, chunk_size=7)
        self.assertNotIn(str(self.root), str(raised.exception.to_dict()))

    def test_independent_good_report_matches_actual_bytes(self):
        result = binary.validate_ttc_binary(self.good, chunk_size=37)
        self.assertEqual(result['faces'], 2)
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(result['byte_size'], len(self.data))
        self.assertEqual(result['table_references'], sum(len(entries(self.data, i)) for i in range(2)))
        self.assertFalse(result['production_accepted'])
        self.assertFalse(result['native_source_equivalence'])

    def test_32_faces_are_verified_with_and_without_sharing(self):
        paths = write_faces(self.root / 'full-collection', 32)
        for sharing in (True, False):
            target = self.root / ('shared.ttc' if sharing else 'unshared.ttc')
            report = pack.pack_collection(paths, target, share_tables=sharing, chunk_size=37)
            checked = binary.validate_ttc_binary(target, chunk_size=37)
            self.assertEqual(checked['faces'], 32)
            self.assertEqual(checked['sha256'], report['sha256'])

    def test_padding_corruption_blocks_packer_publication(self):
        source_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths]
        for tag in (b'PAD1', b'PAD2', b'PAD3'):
            _, _, offset, length = entries(self.data)[tag]
            for pad_index in range((-length) % 4):
                target = self.root / f'must-not-publish-{tag.decode()}-{pad_index}.ttc'
                def corrupt(candidate):
                    actual = entries(candidate.read_bytes())[tag]
                    with candidate.open('r+b') as stream:
                        stream.seek(actual[2] + actual[3] + pad_index)
                        stream.write(b'!')
                with self.subTest(tag=tag, pad_index=pad_index):
                    with self.assertRaisesRegex(StagingError, 'ttc_nonzero_padding'):
                        pack.pack_collection(self.paths, target, validate=corrupt)
                    self.assertFalse(target.exists())
                    self.assertFalse(list(self.root.glob('.ttc-staging-*')))
        self.assertEqual([hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths], source_hashes)

    def test_packer_attaches_independent_binary_evidence(self):
        target = self.root / 'reported.ttc'
        result = pack.pack_collection(self.paths, target)
        self.assertEqual(result['binary_validation'], binary.validate_ttc_binary(target))
        self.assertEqual(result['binary_validation']['sha256'], result['sha256'])

    def test_large_table_verification_has_bounded_byte_buffers(self):
        import tracemalloc
        with TTFont(self.paths[0]) as font:
            font['TEST'] = newTable('TEST')
            font['TEST'].data = b'C1 original metadata' * 100000
            table_bytes = len(font['TEST'].data)
            font.save(self.paths[0])
        del font
        target = self.root / 'large-original.ttc'
        pack.pack_collection([self.paths[0]], target)
        tracemalloc.start()
        try:
            binary.validate_ttc_binary(target, chunk_size=4096)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, table_bytes // 4)

    def test_all_small_chunk_boundaries_accept_valid_checksum_and_padding(self):
        for chunk in (1, 2, 3, 5, 7, 13, 64, 65536):
            with self.subTest(chunk=chunk):
                self.assertEqual(binary.validate_ttc_binary(self.good, chunk_size=chunk)['faces'], 2)

    def test_every_forced_padding_byte_is_checked(self):
        for tag in (b'PAD1', b'PAD2', b'PAD3'):
            _, _, offset, length = entries(self.data)[tag]
            for index in range((-length) % 4):
                with self.subTest(tag=tag, index=index):
                    self.reject(lambda b: b.__setitem__(offset + length + index, 1), 'ttc_nonzero_padding')

    def test_header_and_version_are_checked(self):
        self.reject(lambda b: b.__setitem__(slice(0, 4), b'bad!'), 'ttc_binary_unsupported_header')
        self.reject(lambda b: struct.pack_into('>I', b, 4, 0x00020000), 'ttc_binary_unsupported_header')

    def test_face_count_is_bounded(self):
        for count in (0, 65536):
            with self.subTest(count=count):
                self.reject(lambda b: struct.pack_into('>I', b, 8, count), 'ttc_binary_invalid_face_count')
        self.reject(lambda b: struct.pack_into('>I', b, 8, 65535), 'ttc_binary_truncated')

    def test_directory_alias_cannot_fake_a_second_face(self):
        self.reject(lambda b: struct.pack_into('>I', b, 16, directories(b)[0]), 'ttc_binary_directory_alias')

    def test_directory_alignment_and_range(self):
        for offset in (1, 12, len(self.data) + 4):
            with self.subTest(offset=offset):
                self.reject(lambda b: struct.pack_into('>I', b, 12, offset), 'ttc_binary_directory_range')

    def test_sfnt_signature_and_table_count(self):
        d = directories(self.data)[0]
        self.reject(lambda b: b.__setitem__(slice(d, d+4), b'OTTO'), 'ttc_binary_invalid_sfnt')
        for count in (0, 4096):
            self.reject(lambda b: struct.pack_into('>H', b, d+4, count), 'ttc_binary_invalid_sfnt')

    def test_search_fields_are_independently_checked(self):
        d = directories(self.data)[0]
        self.reject(lambda b: struct.pack_into('>H', b, d+6, 0), 'ttc_binary_search_fields')

    def test_metadata_budget_is_not_bypassed_by_valid_bytes(self):
        with self.assertRaisesRegex(StagingError, 'ttc_binary_record_budget'):
            binary.validate_ttc_binary(self.good, max_table_records=1)

    def test_invalid_table_tag(self):
        p = next(iter(entries(self.data).values()))[0]
        for tag in (b'a b ', b'\x00abc', b'    '):
            self.reject(lambda b: b.__setitem__(slice(p, p+4), tag), 'ttc_binary_table_tag')

    def test_duplicate_and_unsorted_table_tags(self):
        items = list(entries(self.data).items())
        first, second = items[0], items[1]
        p = second[1][0]
        self.reject(lambda b: b.__setitem__(slice(p, p+4), first[0]), 'ttc_binary_table_order')

    def test_signed_collection_is_outside_unsigned_profile(self):
        p = next(iter(entries(self.data).values()))[0]
        self.reject(lambda b: b.__setitem__(slice(p, p+4), b'DSIG'), 'ttc_binary_signed_input')

    def test_out_of_bounds_and_unaligned_table_offsets(self):
        p = entries(self.data)[b'PAD1'][0]
        for offset in (1, 12, len(self.data) + 4, 0xFFFFFFFC):
            self.reject(lambda b: struct.pack_into('>I', b, p+8, offset), 'ttc_binary_table_range')

    def test_declared_table_length_cannot_overflow_range(self):
        p = entries(self.data)[b'PAD1'][0]
        self.reject(lambda b: struct.pack_into('>I', b, p+12, 0xFFFFFFFF), 'ttc_binary_table_range')

    def test_partial_table_overlap(self):
        first = entries(self.data)[b'GDEF']
        p = entries(self.data)[b'GPOS'][0]
        self.reject(lambda b: struct.pack_into('>I', b, p+8, first[2]+4), 'ttc_binary_overlap')

    def test_table_cannot_overlap_a_directory(self):
        p = entries(self.data)[b'PAD1'][0]
        self.reject(lambda b: struct.pack_into('>I', b, p+8, directories(b)[0]), 'ttc_binary_overlap')

    def test_shared_interval_cannot_disagree_about_checksum(self):
        first = entries(self.data, 0)[b'PAD1']
        second = entries(self.data, 1)[b'PAD1']
        self.assertEqual(first[2], second[2])
        self.reject(lambda b: struct.pack_into('>I', b, second[0]+4, second[1]^1),
                    'ttc_binary_shared_table_conflict')

    def test_missing_or_short_head(self):
        p = entries(self.data)[b'head'][0]
        self.reject(lambda b: b.__setitem__(slice(p, p+4), b'heae'), 'ttc_binary_head_missing_or_short')
        self.reject(lambda b: struct.pack_into('>I', b, p+12, 4), 'ttc_binary_head_missing_or_short')

    def test_c1_head_adjustment_must_remain_zero(self):
        offset = entries(self.data)[b'head'][2]
        self.reject(lambda b: struct.pack_into('>I', b, offset+8, 1), 'ttc_binary_head_adjustment')

    def test_payload_bitflip_fails_checksum(self):
        offset = entries(self.data)[b'PAD2'][2]
        self.reject(lambda b: b.__setitem__(offset, b[offset]^1), 'ttc_binary_checksum')

    def test_zero_length_tables_still_require_zero_checksum(self):
        p = entries(self.data)[b'ZERO'][0]
        self.reject(lambda b: struct.pack_into('>I', b, p+4, 1), 'ttc_binary_checksum')

    def test_unclaimed_trailing_bytes_are_rejected_even_when_zero(self):
        for tail in (b'\0\0\0\0', b'junk'):
            self.reject(lambda b: b.extend(tail), 'ttc_binary_trailing_bytes')

    def test_zero_gap_is_allowed_but_nonzero_gap_is_rejected(self):
        changed = bytearray(self.data)
        cut = min(item[2] for item in entries(changed).values())
        all_entries = [v for i in range(2) for v in entries(changed, i).values()]
        changed[cut:cut] = b'\0'*4
        for position, _, offset, _ in all_entries:
            struct.pack_into('>I', changed, position+8, offset+4)
        self.bad.write_bytes(changed)
        self.assertEqual(binary.validate_ttc_binary(self.bad)['faces'], 2)
        changed[cut+2] = 1
        self.bad.write_bytes(changed)
        with self.assertRaisesRegex(StagingError, 'ttc_nonzero_padding'):
            binary.validate_ttc_binary(self.bad)

    def test_truncations_never_return_pass(self):
        for length in (0, 1, 3, 11, 12, 15, 19, 20, 31, 100, len(self.data)-1):
            self.bad.write_bytes(self.data[:length])
            with self.subTest(length=length), self.assertRaises(StagingError):
                binary.validate_ttc_binary(self.bad)

    def test_invalid_parameters(self):
        for value in (0, -1, True, .5, 16*1024*1024+1):
            with self.subTest(chunk=value), self.assertRaisesRegex(StagingError, 'ttc_binary_invalid_chunk_size'):
                binary.validate_ttc_binary(self.good, chunk_size=value)
        for value in (0, -1, True, .5, 1048577):
            with self.subTest(records=value), self.assertRaisesRegex(StagingError, 'ttc_binary_invalid_record_budget'):
                binary.validate_ttc_binary(self.good, max_table_records=value)

    def test_missing_file_is_a_safe_platform_read_error(self):
        with self.assertRaisesRegex(StagingError, 'platform_read:ttc_binary_read_failed') as raised:
            binary.validate_ttc_binary(self.root / 'private-nonexistent.ttc')
        self.assertNotIn('private', str(raised.exception.to_dict()))

    def test_modification_after_hash_read_is_not_accepted(self):
        original = binary._blocks
        changed = False
        def mutate_after_hash(stream, offset, count, chunk):
            nonlocal changed
            yield from original(stream, offset, count, chunk)
            if offset == 0 and count == len(self.data) and not changed:
                with self.good.open('ab') as writer:
                    writer.write(b'!')
                changed = True
        with mock.patch.object(binary, '_blocks', side_effect=mutate_after_hash):
            with self.assertRaisesRegex(StagingError, 'ttc_binary_changed'):
                binary.validate_ttc_binary(self.good)
        self.assertTrue(changed)


if __name__ == '__main__':
    unittest.main()
