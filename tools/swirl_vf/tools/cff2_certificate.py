"""Exact coefficient identity for serialized ordinary-blend CFF2 models.

Decode the reopened CharStrings, including subroutine calls, into integer
16.16 coefficients indexed by serialized F2DOT14 region supports. Matching
every coefficient proves the same ideal function at ALL simultaneous axis
coordinates, without selecting sample points. This is a serialization proof,
not source-fit, native arithmetic, metrics, shaping or delivery acceptance.

Nested blends are outside this ordinary-blend certificate. They are allowed
by OpenType 1.9.1 but fail the measured DirectWrite compatibility controls.
https://learn.microsoft.com/en-us/typography/opentype/spec/cff2
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fontTools.misc.psCharStrings import calcSubrBias
from fontTools.ttLib import TTFont


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def integer_fixed(value, scale=65536):
    require(math.isfinite(value) and value * scale == int(value * scale),
            'certificate_coefficient_not_exactly_encoded')
    return int(value * scale)


def support_key(support, tags):
    require(set(support) <= set(tags), 'certificate_unknown_support_axis')
    key = []
    for axis, tag in enumerate(tags):
        if tag not in support:
            continue
        triple = tuple(integer_fixed(v, 16384) for v in support[tag])
        require(len(triple) == 3, 'certificate_support_dimensions')
        low, peak, high = triple
        require(-16384 <= low <= peak <= high <= 16384 and
                not (low < 0 < high and peak != 0), 'certificate_invalid_region')
        if peak:
            key.append((axis, *triple))
    return tuple(key)


@dataclass
class Operand:
    coefficients: dict
    blended: bool = False

    def constant(self):
        require(not self.blended and set(self.coefficients) <= {()},
                'certificate_nested_or_variable_control_operand')
        return self.coefficients.get((), 0)


def decode(font, name, *, max_tokens=2_000_000):
    """Read encoded tokens, without FontTools' numeric outline interpreter."""
    require(type(max_tokens) is int and max_tokens > 0, 'certificate_token_budget')
    top = font['CFF2'].cff.topDictIndex[0]
    charstring = top.CharStrings[name]
    private = charstring.private
    globals_ = font['CFF2'].cff.GlobalSubrs
    tags = tuple(a.axisTag for a in font['fvar'].axes)
    store = getattr(top, 'VarStore', None)
    store = store.otVarStore if store is not None else None
    if store is not None:
        require(store.VarRegionList.RegionAxisCount == len(tags), 'certificate_region_axis_count')
    index = getattr(private, 'vsindex', 0)
    stack, operators, operands, active = [], [], [], set()
    tokens = 0
    used_vsindex = used_blend = False

    def regions():
        require(store is not None and type(index) is int and 0 <= index < len(store.VarData),
                'certificate_invalid_vsindex')
        keys = []
        for region_id in store.VarData[index].VarRegionIndex:
            require(0 <= region_id < len(store.VarRegionList.Region), 'certificate_invalid_region_index')
            axes = store.VarRegionList.Region[region_id].VarRegionAxis
            require(len(axes) == len(tags), 'certificate_region_axis_count')
            keys.append(support_key({tag: (a.StartCoord, a.PeakCoord, a.EndCoord)
                                     for tag, a in zip(tags, axes)}, tags))
        return keys

    def pop_integer():
        require(stack, 'certificate_stack_underflow')
        value = stack.pop().constant()
        require(value % 65536 == 0, 'certificate_integer_control_operand')
        return value // 65536

    def visit(cs, depth):
        nonlocal tokens, index, used_vsindex, used_blend
        require(depth <= 10 and id(cs) not in active, 'certificate_recursive_or_deep_subroutine')
        require(cs.bytecode is not None and len(cs.bytecode) <= 65535,
                'certificate_serialized_charstring_required')
        active.add(id(cs))
        offset = 0
        while True:
            token, is_operator, offset = cs.getToken(offset)
            if token is None:
                break
            tokens += 1
            require(tokens <= max_tokens, 'certificate_token_budget_exceeded')
            if not is_operator:
                value = integer_fixed(token)
                stack.append(Operand({(): value} if value else {}))
                require(len(stack) <= 513, 'certificate_operand_stack_overflow')
            elif token == 'vsindex':
                require(not used_vsindex and not used_blend and len(stack) == 1,
                        'certificate_vsindex_order_or_count')
                index = pop_integer(); used_vsindex = True
                regions()
            elif token == 'blend':
                keys = regions(); count = pop_integer(); size = count * (len(keys) + 1)
                require(count > 0 and len(stack) >= size, 'certificate_blend_stack_underflow')
                values = stack[-size:]; del stack[-size:]
                # Earlier results below these operands may be ordinary arguments
                # of the next drawing operator; they are not nested blends.
                constants = [value.constant() for value in values]
                for i in range(count):
                    coefficients = {(): constants[i]}
                    for key, delta in zip(keys, constants[count+i*len(keys):count+(i+1)*len(keys)]):
                        coefficients[key] = coefficients.get(key, 0) + delta
                    stack.append(Operand({k: v for k, v in coefficients.items() if v}, True))
                used_blend = True
            elif token in ('callgsubr', 'callsubr'):
                subrs = globals_ if token == 'callgsubr' else getattr(private, 'Subrs', ())
                subindex = pop_integer() + calcSubrBias(subrs)
                require(0 <= subindex < len(subrs), 'certificate_subroutine_index')
                visit(subrs[subindex], depth + 1)
            elif token in ('rmoveto', 'rlineto', 'rrcurveto'):
                width = 6 if token == 'rrcurveto' else 2
                require(stack and len(stack) % width == 0 and (token != 'rmoveto' or len(stack) == 2),
                        'certificate_drawing_operand_count')
                require(operators or token == 'rmoveto', 'certificate_path_without_moveto')
                operators.extend([(token, width)] * (len(stack) // width))
                operands.extend(value.coefficients for value in stack); stack.clear()
            else:
                raise ValueError('certificate_unsupported_operator:' + str(token))
        active.remove(id(cs))

    visit(charstring, 0)
    require(not stack, 'certificate_unconsumed_operands')
    return tuple(operators), operands, tokens


def certify(font, models):
    """Sufficient exact identity proof, refusing unsupported representations."""
    require(font.reader is not None and 'CFF2' in font.reader and font.reader.sfntVersion == 'OTTO',
            'certificate_reopened_CFF2_font_required')
    # A reopened TTFont may already have edited/decompiled tables or a cached
    # glyph order. Those objects are not the saved artifact. Borrow its actual
    # SFNT reader into a fresh table cache, without closing the caller's stream.
    raw = TTFont(lazy=True, recalcBBoxes=False, recalcTimestamp=False)
    raw.reader = font.reader
    raw.sfntVersion = font.reader.sfntVersion
    raw._tableCache = None  # Do not share a previously decompiled TTC table.
    font = raw
    order = font.getGlyphOrder()
    require(set(models) == set(order) and len(order) == font['maxp'].numGlyphs and
            len(order) == len(font['CFF2'].cff.topDictIndex[0].CharStrings.charStrings),
            'certificate_complete_GID_coverage_required')
    tags = tuple(a.axisTag for a in font['fvar'].axes)
    operands = tokens = 0
    for name in order:
        model = models[name]
        require(model.axis_tags == tags and hasattr(model, 'deltas'),
                'certificate_ordinary_model_axes_required')
        ops, actual, count = decode(font, name)
        require(ops == model.operators and model.deltas.shape == (len(model.supports), len(actual)),
                'certificate_topology_or_coefficient_dimensions')
        keys = [support_key(s, tags) for s in model.supports]
        for column, observed in enumerate(actual):
            expected = {}
            for key, row in zip(keys, model.deltas):
                expected[key] = expected.get(key, 0) + integer_fixed(row[column])
            require(observed == {k: v for k, v in expected.items() if v},
                    'certificate_serialized_coefficient_mismatch:' + name + ':' + str(column))
        operands += len(actual); tokens += count
    return {'status': 'PASS_EXACT_SERIALIZED_CFF2_COEFFICIENTS', 'glyphs': len(order),
            'operands': operands, 'decoded_tokens': tokens, 'axes': list(tags),
            'all_simultaneous_design_coordinates': True, 'read_saved_SFNT_tables': True,
            'source_fit_accepted': False,
            'native_execution': False, 'metrics_verified': False, 'production_accepted': False}
