"""Align Windows VF line metrics with hhea, preserving the clipping rectangle.

Reviewed: Microsoft OS/2 variation recommendations and Apache-2.0 gftools
fix_vertical_metrics. Our source of line spacing is the original Mac hhea,
not legacy Windows clipping bounds. No upstream implementation is copied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time

from fontTools.ttLib import TTCollection
from fontTools.ttLib.sfnt import calcChecksum
from windows_font_inventory import sha256
from windows_gvar import require
from ttc_staging_binary import validate_ttc_binary


def align_line_metrics(font):
    os2, hhea = font['OS/2'], font['hhea']
    require(os2.version >= 4 and 'MVAR' not in font, 'review_variable_line_metrics_before_alignment')
    before = [os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap, os2.fsSelection]
    for target, source in [('sTypoAscender', 'ascent'), ('sTypoDescender', 'descent'), ('sTypoLineGap', 'lineGap')]:
        setattr(os2, target, getattr(hhea, source))
    os2.fsSelection |= 128
    return dict(before=before, after=[os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap, os2.fsSelection],
                clipping_unchanged=[os2.usWinAscent, os2.usWinDescent])


def patch_collection(source, destination):
    """Same-length metadata edits in a fresh copy; verify all other bytes."""
    require(not destination.exists(), 'fresh_metadata_candidate_required')
    before = sha256(source)
    patches, faces = {}, []
    with source.open('rb') as stream:
        magic, version, count = struct.unpack('>4sII', stream.read(12))
        require((magic, version, count) == (b'ttcf', 0x10000, 4), 'four_face_TTC_v1_required')
        offsets = struct.unpack('>4I', stream.read(16))
    with TTCollection(source, lazy=True) as collection, source.open('rb') as stream:
        for index, font in enumerate(collection.fonts):
            faces.append(align_line_metrics(font))
            font['head'].fontRevision = .101
            font['head'].checkSumAdjustment = 0
            for record in font['name'].names:
                if record.nameID in (3, 5):
                    record.string = record.toUnicode().replace('0.1.0', '0.1.1')
            changed = {tag: font[tag].compile(font) for tag in ('OS/2', 'head', 'name')}
            stream.seek(offsets[index]+4)
            number = struct.unpack('>H', stream.read(2))[0]
            for n in range(number):
                entry = offsets[index]+12+n*16
                stream.seek(entry)
                tag, checksum, offset, length = struct.unpack('>4sIII', stream.read(16))
                name = tag.decode('ascii')
                if name not in changed:
                    continue
                data = changed[name]
                require(len(data) == length, 'metadata_size_changed_repack_required')
                require(offset not in patches or patches[offset] == data, 'shared_metadata_conflict')
                patches[offset] = data
                patches[entry+4] = struct.pack('>I', calcChecksum(data))
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024*1024)
    with destination.open('r+b') as stream:
        for offset, data in sorted(patches.items()):
            stream.seek(offset); stream.write(data)
    ranges = [(offset, offset+len(data)) for offset, data in sorted(patches.items())]
    with source.open('rb') as old, destination.open('rb') as new:
        offset = 0
        while a := old.read(1024*1024):
            b = new.read(len(a))
            aa, bb = bytearray(a), bytearray(b)
            for low, high in ranges:
                start, stop = max(0, low-offset), min(len(a), high-offset)
                if start < stop:
                    aa[start:stop] = bb[start:stop] = b'\0'*(stop-start)
            require(aa == bb, 'nonmetadata_bytes_changed')
            offset += len(a)
        require(not new.read(1), 'candidate_length_changed')
    require(sha256(source) == before, 'metadata_source_changed')
    result = dict(status='PASS_METADATA_ONLY_UPDATE', parent_sha256=before, faces=faces,
                  changed_tables=['OS/2', 'head', 'name'], all_other_bytes_identical=True,
                  binary_validation=validate_ttc_binary(destination))
    return result


def deliver(source, output):
    started = time.monotonic()
    source, output = source.resolve(), output.resolve()
    require(not output.exists() and not any((p/'.git').exists() for p in (output, *output.parents)), 'fresh_private_output_required')
    report = json.loads((source.parent/'report.json').read_text())
    require(sha256(source) == report['sha256'], 'source_candidate_identity_mismatch')
    output.mkdir(parents=True, mode=0o700)
    candidate = output/'SwirlVF.ttc'
    proof = patch_collection(source, candidate)
    for style in ('Text', 'Display'):
        shutil.copyfile(source.parent/(style+'-glyph-report.json'), output/(style+'-glyph-report.json'))
    for row in report['faces']:
        row['previous_standalone_sha256'] = row.pop('sha256')
        row.pop('bytes')
    report.update(version='0.1.1 Beta', sha256=sha256(candidate), bytes=candidate.stat().st_size,
                  metadata_parent_candidate_sha256=proof['parent_sha256'], line_metrics='SOURCE_HHEA_ALIGNED_USE_TYPO_METRICS',
                  metadata_update_seconds=time.monotonic()-started, packaging=proof,
                  Windows_DirectWrite='NOT_RUN', production_accepted=False)
    (output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('version', 'bytes', 'sha256', 'metadata_update_seconds')}), flush=True)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    deliver(a.candidate, a.output)
