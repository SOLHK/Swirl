"""Lossless CFF2 instruction/literal sharing through a small local dictionary.

Unlike coefficient approximation or glyph removal, this transformation retains
the exact expanded bytes and arithmetic order. Each helper is call-free and
inherits the caller's variation state. A 215-entry bank has two-byte calls.
The per-glyph expanded execution budget is checked before mutation. This pass
accepts the generated unhinted, single-result-blend dialect, not arbitrary CFF.
"""
from __future__ import annotations
from collections import Counter
from functools import lru_cache
from fontTools.cffLib import SubrsIndex
from fontTools.misc.psCharStrings import T2CharString, calcSubrBias
from cff2_geometry import require
from cff2_structure import tokens, programs, bytecode


def candidates(data, minimum=6, maximum=128):
    begin = None
    for start, end, op, value in tokens(data):
        if end-start == 1 and data[start] in (139, 140, 16):
            if begin is None: begin = start
            if end-begin == maximum:
                yield begin, end; begin = None
        else:
            if begin is not None and start-begin >= minimum: yield begin, start
            begin = None
            # Exact 16.16 literals on the central half-unit grid. The bounded
            # candidate alphabet avoids a dictionary of every source coefficient.
            if data[start] == 255 and abs(value) <= .25: yield start, end
    if begin is not None and len(data)-begin >= minimum: yield begin, len(data)


def rewrite(data, selected):
    pieces, cursor, calls = [], 0, 0
    for a, b in candidates(data):
        key = data[a:b]
        if key in selected:
            pieces.extend((data[cursor:a], bytes((selected[key]+32, 10))))
            cursor = b; calls += 1
    pieces.append(data[cursor:])
    return b''.join(pieces), calls


def expand_local(data, helpers):
    """Expand only the new local calls, leaving existing global calls intact."""
    pieces, cursor, previous = [], 0, None
    for a, b, op, value in tokens(data):
        if op == 10:
            require(previous is not None and previous[2] is None
                    and type(previous[3]) is int, 'dynamic_local_call_not_supported')
            start, _, _, operand = previous
            index = operand+107
            require(0 <= index < len(helpers), 'structural_local_call_out_of_range')
            pieces.extend((data[cursor:start], helpers[index])); cursor = b
        previous = (a,b,op,value)
    pieces.append(data[cursor:]); return b''.join(pieces)


def analyze(data):
    """Compact symbolic stack trace, retaining only operators and call targets."""
    events, pending, previous, count = [], 0, None, 0
    for a,b,op,value in tokens(data):
        count += 1
        if op is None:
            pending += 1
        else:
            if pending: events.append(('push',pending)); pending=0
            if op in (15,29):
                require(previous is not None and type(previous) is int, 'dynamic_CFF2_index_not_supported')
                events.append((op,previous))
            elif op == 16:
                require(previous == 1, 'single_result_generated_blend_required')
                events.append((op,1))
            elif op in (21,5,8): events.append((op,2 if op in (21,5) else 6))
            else: raise ValueError('unsupported_structural_pool_operator:'+str(op))
        previous = value if op is None else None
    if pending: events.append(('push',pending))
    return events, count+1


def compress(font, *, maximum_helpers=215, operation_limit=200000):
    require(type(maximum_helpers) is int and 1 <= maximum_helpers <= 215,
            'structural_helper_bank_must_have_two_byte_calls')
    require(type(operation_limit) is int and 1 <= operation_limit <= 200000,
            'invalid_structural_execution_budget')
    cff=font['CFF2'].cff; top=cff.topDictIndex[0]
    require(len(top.FDArray)==1 and not getattr(top.FDArray[0].Private,'Subrs',()),
            'single_font_dict_without_existing_local_subroutines_required')
    counts=Counter()
    for _,_,cs in programs(font):
        data=bytecode(cs); counts.update(data[a:b] for a,b in candidates(data))
    scored=sorted(((len(p)-2)*n-len(p)-4,p,n) for p,n in counts.items()
                  if (len(p)-2)*n>len(p)+4)
    chosen=sorted(scored[-maximum_helpers:],reverse=True)
    helpers=[p for _,p,_ in chosen]; selected={p:i for i,p in enumerate(helpers)}
    pending=[]; global_events=[]; global_counts=[]; global_insertions=[]
    for cs in cff.GlobalSubrs:
        old=bytecode(cs); new, calls=rewrite(old,selected)
        require(expand_local(new,helpers)==old, 'structural_expanded_bytes_changed')
        require(len(new)<=65535,'structural_charstring_byte_limit_exceeded')
        events,total=analyze(old)
        require(all(op!=15 for op,_ in events),'global_vsindex_state_change_not_supported')
        global_events.append(events);global_counts.append(total);global_insertions.append(calls)
        pending.append((cs,new))
    bias=calcSubrBias(cff.GlobalSubrs)
    active=set()
    @lru_cache(None)
    def summary(index, regions):
        require(0 <= index < len(global_events), 'global_subroutine_out_of_range')
        require(index not in active, 'recursive_global_subroutine')
        active.add(index)
        try: return walk(global_events[index],global_counts[index],global_insertions[index],regions)
        finally: active.remove(index)

    def walk(events,operations,insertions,regions):
        current=peak=0; depth=0
        for op,value in events:
            if op=='push': current+=value;peak=max(peak,current)
            elif op==15:
                require(0 <= value < len(top.VarStore.otVarStore.VarData), 'invalid_generated_vsindex')
                regions=len(top.VarStore.otVarStore.VarData[value].VarRegionIndex);current-=1
            elif op==29:
                current-=1
                change,child_peak,child_ops,child_insertions,child_depth=summary(value+bias,regions)
                peak=max(peak,current+child_peak);current+=change
                operations+=child_ops;insertions+=child_insertions;depth=max(depth,child_depth+1)
            elif op==16: current-=regions+1
            else: current-=value
        return current,peak,operations,insertions,depth

    old_ops=[];new_ops=[];stacks=[];depths=[]
    initial=len(top.VarStore.otVarStore.VarData[getattr(top.FDArray[0].Private,'vsindex',0)].VarRegionIndex)
    for name in font.getGlyphOrder():
        cs=top.CharStrings[name];old=bytecode(cs);new,insertions=rewrite(old,selected)
        require(expand_local(new,helpers)==old,'structural_expanded_bytes_changed')
        require(len(new)<=65535,'structural_charstring_byte_limit_exceeded')
        events,total=analyze(old)
        change,peak,n,calls,depth=walk(events,total,insertions,initial)
        require(change==0,'generated_glyph_final_stack_not_empty')
        bound=peak+int(bool(calls))
        require(bound<=513 and depth+int(bool(calls))<=10,'structural_stack_or_depth_limit')
        require(n+3*calls<operation_limit,'structural_expanded_operation_limit')
        old_ops.append(n);new_ops.append(n+3*calls);stacks.append(bound);depths.append(depth+int(bool(calls)))
        pending.append((cs,new))
    # All guards and exact byte comparisons complete before the first mutation.
    bank=SubrsIndex()
    for data in helpers: bank.append(T2CharString(bytecode=data,private=top.FDArray[0].Private,globalSubrs=cff.GlobalSubrs))
    for cs,new in pending: cs.setBytecode(new)
    top.FDArray[0].Private.Subrs=bank
    font.recalcBBoxes=False; font.recalcTimestamp=False
    return dict(local_helpers=len(helpers),structural_helpers=sum(p[0]!=255 for p in helpers),
        literal_helpers=sum(p[0]==255 for p in helpers),
        expected_payload_savings=sum((len(p)-2)*n-len(p) for _,p,n in chosen),
        maximum_original_operations=max(old_ops),maximum_compressed_operations=max(new_ops),
        maximum_operand_stack_bound=max(stacks),maximum_subroutine_depth=max(depths),
        exact_expanded_bytes_verified=True,coefficients_changed=0,operation_limit=operation_limit,
        local_call_bytes=2,global_subroutine_indices_unchanged=True)
