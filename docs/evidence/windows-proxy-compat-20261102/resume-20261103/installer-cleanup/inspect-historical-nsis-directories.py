#!/usr/bin/env python3
"""Read the reviewed historical NSIS bytecode; never execute its payload."""
import hashlib
import json
import lzma
import pathlib
import struct
import sys

root = pathlib.Path(__file__).parent
setup = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root / '24af-installer/Swirl-Setup.exe'
manifest_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else root / '24af-package-evidence/installer-bin/package-manifest.json'
data = setup.read_bytes()
manifest_bytes = manifest_path.read_bytes()
setup_sha = hashlib.sha256(data).hexdigest()
manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
assert setup_sha == '082c6e60ffa968d0e6d3d8766a055e7dc49b5a6263de1f66c74352218b6ea84b'
assert manifest_sha == '95e57c627ba3948422075ea22b731dc3bb77e386719e91cbf2450fb6a0758003'
first = data.index(b'\xef\xbe\xad\xdeNullsoftInst') - 4
header_size = struct.unpack_from('<I', data, first + 20)[0]
assert 0 < header_size < 8 * 1024 * 1024
assert data[first + 28:first + 33] == bytes.fromhex('5d00008000')
decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{
    'id': lzma.FILTER_LZMA1, 'dict_size': 8388608, 'lc': 3, 'lp': 0, 'pb': 2,
}])
unpacked = decoder.decompress(data[first + 33:], max_length=header_size + 4)
assert len(unpacked) == header_size + 4
assert struct.unpack_from('<I', unpacked)[0] == header_size
header = unpacked[4:]
blocks = [struct.unpack_from('<II', header, 4 + i * 8) for i in range(8)]
entry_offset, entry_count = blocks[2]
strings_offset, _ = blocks[3]
languages_offset, _ = blocks[4]
assert entry_offset + entry_count * 28 == strings_offset
assert 0 < strings_offset < languages_offset <= len(header)
strings = header[strings_offset:languages_offset].decode('utf-16le')
entries = [struct.unpack_from('<7i', header, entry_offset + i * 28) for i in range(entry_count)]
manifest = json.loads(manifest_bytes)
owned_directories = {str(parent) for file in manifest['files']
    for parent in pathlib.PurePosixPath(file['path']).parents if str(parent) != '.'}
directory_commands = []
for index, entry in enumerate(entries):
    if entry[0] != 11 or entry[2] != 1:
        continue
    text = strings[entry[1]:].split('\0', 1)[0]
    # NSIS File /r saved the deployment root in its internal variable 31.
    # This exact string encoding is checked against the pinned fixture only.
    prefix = '\x03\u809f\\'
    if not text.startswith(prefix):
        continue
    relative = text[len(prefix):].replace('\\', '/')
    directory_commands.append({'entry_index': index, 'opcode': 11, 'set_output_path': True,
        'string_offset': entry[1], 'relative_path': relative,
        'has_manifest_descendant': relative in owned_directories})
unused = [entry for entry in directory_commands if not entry['has_manifest_descendant']]
report = {
    'schema': 1, 'scope': 'Historical artifact bytecode inspection, not a Windows execution result.',
    'source_head_sha': '24af5838e39b4612321a7ee2b1be11d78fb9b6dd',
    'checkout_sha': manifest['source_sha'], 'installer_sha256': setup_sha,
    'manifest_sha256': manifest_sha, 'header_sha256': hashlib.sha256(header).hexdigest(),
    'header_offset': first, 'header_size': header_size, 'entry_count': entry_count,
    'payload_directory_commands': len(directory_commands),
    'directories_without_manifest_descendants': unused,
    'conclusion': 'The reviewed installer contains directory-creation commands for 11 paths with no owned file descendants. Their actual post-uninstall remainder requires the Windows diagnostic workflow.',
    'format_sources': [
        'https://github.com/NSIS-Dev/nsis/blob/master/Source/exehead/exec.c',
        'https://nsis.sourceforge.io/Docs/Chapter4.html#4.9.1.10',
    ],
}
assert len(unused) == 11
out = root / 'historical-nsis-directory-evidence.json'
out.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
