"""Share polynomial operand programs without changing CFF2 arithmetic.

Helpers return one stack value and contain no calls or vsindex. Drawing chunks
may call helpers, so the maximum added subroutine depth is two. Region counts
are part of every helper identity. No delta is dropped or refitted.
OpenType permits subroutines to produce operands, not only complete contours:
https://learn.microsoft.com/en-us/typography/opentype/spec/cff2#subroutines
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from fontTools.misc.psCharStrings import T2CharString, calcSubrBias
from cff2_geometry import require

LIMIT = 65535
DRAWING = {'rmoveto', 'rlineto', 'rrcurveto'}


def encoded(program):
    result = T2CharString(program=list(program))
    result.compile(isCFF2=True)
    return result.bytecode


@dataclass(eq=False)
class Expression:
    data: bytes
    regions: int
    token_count: int
    count: int = 0


class ExpressionPool:
    def __init__(self, *, maximum_helpers=32768, minimum_bytes=16):
        require(type(maximum_helpers) is int and 0 <= maximum_helpers <= 65536
                and type(minimum_bytes) is int and minimum_bytes >= 4,
                'invalid_expression_pool_budget')
        self.maximum_helpers, self.minimum_bytes = maximum_helpers, minimum_bytes
        self.expressions = {}

    def intern(self, program, regions):
        require(type(regions) is int and 0 <= regions <= 511
                and all(not isinstance(t, str) or t == 'blend' for t in program),
                'expression_must_preserve_variation_and_drawing_state')
        data = encoded(program)
        key = (regions, data)
        node = self.expressions.setdefault(key, Expression(data, regions, len(program)))
        node.count += 1
        return node

    def compile(self, programs):
        """Return bounded main strings, helpers/chunks, and an encoding receipt."""
        references = Counter(token for program in programs.values() for token in program
                             if isinstance(token, Expression))
        for expression in self.expressions.values():
            expression.count = references[expression]
        useful = [e for e in self.expressions.values()
                  if self.minimum_bytes <= len(e.data) <= LIMIT
                  and (e.count-1)*len(e.data) > 4*e.count]
        useful.sort(key=lambda e: (-((e.count-1)*len(e.data)-4*e.count), e.regions, e.data))
        helpers = useful[:self.maximum_helpers]
        selected = {node: index for index, node in enumerate(helpers)}
        mains, chunks, operation_counts = {}, [], {}

        def pieces(tokens):
            output, plain = [], []
            for token in tokens:
                if isinstance(token, Expression):
                    if plain:
                        output.append(encoded(plain)); plain = []
                    output.append(selected[token] if token in selected else token.data)
                else:
                    plain.append(token)
            if plain:
                output.append(encoded(plain))
            return output

        def maximum_size(items):
            return sum(4 if isinstance(item, int) else len(item) for item in items)

        for name, tokens in programs.items():
            # HarfBuzz counts numeric tokens too. Every helper call contributes
            # an index, call operator, and implicit return; the main has an
            # implicit end. Sharing bytes does not reduce executed operations.
            operation_counts[name] = 1+sum(
                token.token_count+(3 if token in selected else 0)
                if isinstance(token, Expression) else 1 for token in tokens)
            prefix = encoded(tokens[:2]) if len(tokens) >= 2 and tokens[1] == 'vsindex' else b''
            body = tokens[2:] if prefix else tokens
            blocks, block = [], []
            for token in body:
                block.append(token)
                if isinstance(token, str) and token in DRAWING:
                    current = pieces(block)
                    require(maximum_size(current) <= LIMIT, 'single_pooled_drawing_operation_too_large')
                    blocks.append(current); block = []
            require(not block, 'unfinished_pooled_charstring')
            flattened = [item for block in blocks for item in block]
            if len(prefix)+maximum_size(flattened) <= LIMIT:
                mains[name] = [prefix, *flattened]
                continue
            calls, chunk = [], []
            for block in blocks:
                if chunk and maximum_size(chunk)+maximum_size(block) > LIMIT:
                    calls.append(len(helpers)+len(chunks)); chunks.append(chunk); chunk = []
                chunk.extend(block)
            if chunk:
                calls.append(len(helpers)+len(chunks)); chunks.append(chunk)
            require(len(prefix)+4*len(calls) <= LIMIT, 'pooled_charstring_caller_too_large')
            mains[name] = [prefix, *calls]
            operation_counts[name] += 3*len(calls)
        count = len(helpers)+len(chunks)
        require(count <= 65536, 'pooled_subroutine_index_overflow')
        bias = calcSubrBias([None]*count)
        calls = []
        for index in range(count):
            operand = index-bias
            require(-32768 <= operand <= 32767, 'pooled_subroutine_operand_overflow')
            calls.append(encoded([operand, 'callgsubr']))

        def resolve(items):
            return b''.join(calls[item] if isinstance(item, int) else item for item in items)

        main_bytes = {name: resolve(items) for name, items in mains.items()}
        sub_bytes = [node.data for node in helpers]+[resolve(chunk) for chunk in chunks]
        require(all(len(data) <= LIMIT for data in [*main_bytes.values(), *sub_bytes]),
                'pooled_charstring_byte_limit_exceeded')
        report = dict(shared_expressions=len(helpers), drawing_chunks=len(chunks),
                      maximum_added_subroutine_depth=2 if chunks else int(bool(helpers)),
                      encoded_program_bytes=sum(map(len, main_bytes.values()))+sum(map(len, sub_bytes)),
                      maximum_main_bytes=max(map(len, main_bytes.values()), default=0),
                      maximum_subroutine_bytes=max(map(len, sub_bytes), default=0),
                      maximum_interpreter_operations=max(operation_counts.values(), default=0),
                      harfbuzz_14_6_operation_limit=200000,
                      glyphs_reaching_operation_limit=sum(n >= 200000 for n in operation_counts.values()))
        return ({name: T2CharString(bytecode=data) for name, data in main_bytes.items()},
                [T2CharString(bytecode=data) for data in sub_bytes], report)
