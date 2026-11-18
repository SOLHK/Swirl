"""Read generated CFF2 bytecode without allocating a decoded operand program.

The scanner retains exact bytes, including distinct fixed-point encodings.
It is intentionally limited to the unhinted operators emitted by this compiler.
No arbitrary external font is silently rewritten through this contract.
"""
from __future__ import annotations
from collections import Counter
import struct

OPERATORS = {4, 5, 6, 7, 8, 10, 15, 16, 21, 22, 24, 25, 26, 27, 29, 30, 31}


def tokens(data):
    offset = 0
    while offset < len(data):
        start = offset; b = data[offset]; offset += 1
        if 32 <= b <= 246:
            value, op = b-139, None
        elif 247 <= b <= 254:
            if offset >= len(data): raise ValueError('truncated_CFF2_number')
            value = (b-247)*256+data[offset]+108 if b <= 250 else -(b-251)*256-data[offset]-108
            offset += 1; op = None
        elif b in (28, 255):
            size = 2 if b == 28 else 4
            if offset+size > len(data): raise ValueError('truncated_CFF2_number')
            value = struct.unpack_from('>h' if b == 28 else '>i', data, offset)[0]
            if b == 255: value /= 65536
            offset += size; op = None
        elif b in OPERATORS:
            value, op = None, b
        else:
            raise ValueError('unsupported_generated_CFF2_operator:'+str(b))
        yield start, offset, op, value


def structural_runs(data, *, minimum=6, maximum=128):
    """Runs of literal 0/1 and blend, split only on actual token boundaries."""
    begin = None
    for start, end, op, value in tokens(data):
        structural = end-start == 1 and data[start] in (139, 140, 16)
        if structural:
            if begin is None: begin = start
            if end-begin == maximum:
                yield begin, end
                begin = None
        else:
            if begin is not None and start-begin >= minimum: yield begin, start
            begin = None
    if begin is not None and len(data)-begin >= minimum: yield begin, len(data)


def program_stats(data):
    counts = Counter(); numeric_bytes = 0
    for start, end, op, value in tokens(data):
        counts['tokens'] += 1
        if op is None:
            counts['numbers'] += 1; numeric_bytes += end-start
            counts['zero_numbers'] += value == 0
        else:
            counts['operator_'+str(op)] += 1
    return dict(counts, numeric_bytes=numeric_bytes, bytes=len(data))


def bytecode(charstring):
    if charstring.bytecode is None: charstring.compile(isCFF2=True)
    return charstring.bytecode


def programs(font):
    cff = font['CFF2'].cff; top = cff.topDictIndex[0]
    for name in font.getGlyphOrder(): yield 'main', name, top.CharStrings[name]
    for i, sub in enumerate(cff.GlobalSubrs): yield 'global', i, sub
    for fd_index, fd in enumerate(top.FDArray):
        for i, sub in enumerate(getattr(fd.Private, 'Subrs', ())): yield 'local', (fd_index, i), sub
