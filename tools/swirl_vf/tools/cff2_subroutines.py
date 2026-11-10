"""Keep generated CFF2 CharStrings within the 65,535-byte format limit.

Split only at completed drawing operators, where our generator's operand
stack is empty. One glyph-level vsindex is retained before all calls. Global
subroutines have no calls or variation-state changes, so nesting depth is one.
This preserves the encoded operands, geometry and variation function exactly;
it cannot repair an inaccurate model or an overflowing blend operand stack.

https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#charstring
https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#subroutines
"""
from __future__ import annotations

from fontTools.misc.psCharStrings import T2CharString, calcSubrBias

MAX_BYTES = 65535
DRAWING = frozenset(('rmoveto', 'rlineto', 'rrcurveto'))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def encode(program, private, subroutines):
    result = T2CharString(program=list(program), private=private, globalSubrs=subroutines)
    result.compile(isCFF2=True)
    return result


def pack(font, *, byte_limit=MAX_BYTES, release_programs=False):
    """Pack a detached, generated unhinted CFF2 font without changing its GIDs.

    A smaller byte_limit is permitted for authored boundary tests, never a
    larger one. Existing subroutines are accepted only when all main strings
    already fit; extending an arbitrary external program is out of scope.
    The caller should discard its detached candidate if a format guard fails.
    """
    require(type(byte_limit) is int and 32 <= byte_limit <= MAX_BYTES, 'invalid_cff2_byte_limit')
    require(type(release_programs) is bool, 'invalid_cff2_program_memory_policy')
    cff = font['CFF2'].cff
    top = cff.topDictIndex[0]
    globals_ = cff.GlobalSubrs
    pending = []
    report = {'glyphs_repacked': 0, 'global_subroutines_added': 0,
              'maximum_input_bytes': 0, 'maximum_output_bytes': 0, 'maximum_subroutine_bytes': 0}
    for name in font.getGlyphOrder():
        cs = top.CharStrings[name]
        # An already encoded, bounded main needs no transformation. In
        # particular, do not recursively decompile all shared operand helpers
        # just to measure the caller's byte length. This is the same length
        # contract as the decoded branch below, with byte-for-byte preservation.
        if cs.bytecode is not None and len(cs.bytecode) <= byte_limit:
            size = len(cs.bytecode)
            report['maximum_input_bytes'] = max(report['maximum_input_bytes'], size)
            report['maximum_output_bytes'] = max(report['maximum_output_bytes'], size)
            continue
        cs.decompile()
        program = list(cs.program)
        original = encode(program, cs.private, globals_)
        size = len(original.bytecode)
        report['maximum_input_bytes'] = max(report['maximum_input_bytes'], size)
        if size <= byte_limit:
            report['maximum_output_bytes'] = max(report['maximum_output_bytes'], size)
            if release_programs:
                cs.setBytecode(original.bytecode)
            continue
        require(not len(globals_) and not getattr(cs.private, 'Subrs', ()),
                'oversized_external_subroutine_program_unsupported')
        prefix = program[:2] if len(program) >= 2 and program[1] == 'vsindex' else []
        tokens = program[len(prefix):]
        blocks, block = [], []
        for token in tokens:
            require(not isinstance(token, str) or token in DRAWING or token == 'blend',
                    'unsupported_generated_cff2_operator')
            block.append(token)
            if isinstance(token, str) and token in DRAWING:
                compiled = encode(block, cs.private, globals_)
                require(len(compiled.bytecode) <= byte_limit, 'single_cff2_drawing_operation_too_large')
                blocks.append((block, len(compiled.bytecode)))
                block = []
        require(not block and blocks, 'unfinished_generated_cff2_program')
        chunks, chunk, chunk_size = [], [], 0
        for block, size in blocks:
            if chunk and chunk_size + size > byte_limit:
                chunks.append(chunk); chunk, chunk_size = [], 0
            chunk.extend(block); chunk_size += size
        if chunk:
            chunks.append(chunk)
        if release_programs:
            chunks = [encode(chunk, cs.private, globals_) for chunk in chunks]
            cs.setBytecode(original.bytecode)
        pending.append((cs, prefix, chunks))
    if not pending:
        return report
    indices, programs, callers = {}, [], []
    for cs, prefix, chunks in pending:
        selected = []
        for chunk in chunks:
            sub = chunk if isinstance(chunk, T2CharString) else encode(chunk, cs.private, globals_)
            key = sub.bytecode
            if key not in indices:
                require(len(programs) < 65536, 'cff2_subroutine_call_index_overflow')
                indices[key] = len(programs); programs.append(sub)
                report['maximum_subroutine_bytes'] = max(report['maximum_subroutine_bytes'], len(key))
            selected.append(indices[key])
        callers.append((cs, prefix, selected))
    bias = calcSubrBias(programs)
    # Check every caller before mutating the font's shared subroutine index.
    replacements = []
    for cs, prefix, selected in callers:
        program = list(prefix)
        for index in selected:
            operand = index - bias
            require(-32768 <= operand <= 32767, 'cff2_subroutine_operand_overflow')
            program.extend((operand, 'callgsubr'))
        compiled = encode(program, cs.private, globals_)
        require(len(compiled.bytecode) <= byte_limit, 'cff2_subroutine_caller_too_large')
        report['maximum_output_bytes'] = max(report['maximum_output_bytes'], len(compiled.bytecode))
        replacements.append((cs, compiled.bytecode if release_programs else program))
    for program in programs:
        globals_.append(program)
    for cs, program in replacements:
        if release_programs:
            cs.setBytecode(program)
        else:
            cs.setProgram(program)
    report['glyphs_repacked'] = len(replacements)
    report['global_subroutines_added'] = len(programs)
    return report
