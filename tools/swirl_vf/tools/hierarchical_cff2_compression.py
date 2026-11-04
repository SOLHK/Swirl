"""Bounded approximation of a hierarchical CFF2 interpolant, not its source.

The difference between two models on the same knots is multi-affine on every
grid cell. Its Euclidean control error is bounded by the largest vertex error,
by convexity. Outward-rounded interval synthesis bounds every grid vertex.
Thus a nonzero coefficient may be omitted only with an explicit uniform model
error certificate. Source fitting, serialization and native arithmetic still
require independent validation; this operation clears their acceptance flags.
"""
from __future__ import annotations
import copy
import numpy as np
from fontTools.varLib.models import supportScalar
from cff2_geometry import OutlineModel, LIMIT, require
from local_cff2_geometry import validate_knots


def layout(knots):
    anchor = int(np.argmin(np.abs(knots)))
    supports, instructions = {None: anchor}, []
    def interval(lo, hi):
        if hi-lo <= 1:
            return
        mid = (lo+hi)//2
        supports[tuple(map(float,(knots[lo],knots[mid],knots[hi])))] = mid
        instructions.append((mid,lo,hi))
        interval(lo,mid); interval(mid,hi)
    if anchor:
        supports[tuple(map(float,(knots[0],knots[0],knots[anchor])))] = 0
        instructions.append((0,anchor,anchor)); interval(0,anchor)
    if anchor < len(knots)-1:
        supports[tuple(map(float,(knots[anchor],knots[-1],knots[-1])))] = len(knots)-1
        instructions.append((len(knots)-1,anchor,anchor)); interval(anchor,len(knots)-1)
    return anchor, supports, instructions


def synthesize(coefficients, knots, *, outward=False):
    """Reconstruct tensor nodes. Interval endpoints enclose ideal arithmetic."""
    low = coefficients.copy(); high = coefficients.copy() if outward else None
    def weighted(lo, hi, value):
        a=max(0.,np.nextafter(value,-np.inf)); b=min(1.,np.nextafter(value,np.inf))
        return (np.nextafter(np.where(lo>=0,lo*a,lo*b),-np.inf),
                np.nextafter(np.where(hi>=0,hi*b,hi*a),np.inf))
    for axis,k in enumerate(knots):
        anchor,_,steps = layout(k)
        lo = np.moveaxis(low,axis,0); result_lo = np.empty_like(lo)
        result_lo[anchor] = lo[anchor]
        if outward:
            hi=np.moveaxis(high,axis,0); result_hi=np.empty_like(hi); result_hi[anchor]=hi[anchor]
        for i,a,b in steps:
            if a==b:
                result_lo[i] = lo[i]+result_lo[a]
                if outward:
                    result_lo[i] = np.nextafter(result_lo[i],-np.inf)
                    result_hi[i] = np.nextafter(hi[i]+result_hi[a],np.inf)
            else:
                # F2DOT14 differences are exact in binary64; a single outward
                # step encloses each quotient's mathematical real value.
                left=(k[b]-k[i])/(k[b]-k[a]); right=(k[i]-k[a])/(k[b]-k[a])
                if not outward:
                    result_lo[i] = lo[i]+left*result_lo[a]+right*result_lo[b]
                else:
                    al,ah=weighted(result_lo[a],result_hi[a],left)
                    bl,bh=weighted(result_lo[b],result_hi[b],right)
                    result_lo[i]=np.nextafter(lo[i]+np.nextafter(al+bl,-np.inf),-np.inf)
                    result_hi[i]=np.nextafter(hi[i]+np.nextafter(ah+bh,np.inf),np.inf)
        low=np.moveaxis(result_lo,0,axis)
        if outward: high=np.moveaxis(result_hi,0,axis)
    return (low,high) if outward else low


def uniform_bound(coefficients, knots):
    if not np.any(coefficients):
        return 0.
    low,high=synthesize(coefficients,knots,outward=True)
    bound=np.maximum(np.abs(low),np.abs(high)).reshape(*coefficients.shape[:-1],-1,2)
    squares=np.nextafter(bound*bound,np.inf)
    squared=np.nextafter(squares[...,0]+squares[...,1],np.inf)
    return float(np.nextafter(np.sqrt(squared),np.inf).max(initial=0))


def compress(model, *, max_regions=506, error_budget=LIMIT/4):
    require(isinstance(model,OutlineModel) and model.evidence.get('basis')=='hierarchical',
            'hierarchical_local_model_required')
    require(type(max_regions) is int and 1 <= max_regions <= 506
            and 0 <= error_budget <= LIMIT/4, 'invalid_hierarchical_compression_budget')
    knots=validate_knots(model.evidence['knots']); shape=tuple(map(len,knots))
    require(len(model.axis_tags)==3 and len(set(model.axis_tags))==3 and model.supports[0]=={},
            'invalid_hierarchical_model_axes')
    require(model.deltas.ndim==2 and len(model.deltas)==len(model.supports)
            and model.deltas.shape[1]==sum(n for _,n in model.operators)
            and model.deltas.shape[1]%2==0 and np.isfinite(model.deltas).all(),
            'invalid_hierarchical_model_coefficients')
    require(np.prod(shape)*model.deltas.shape[1]<=16_000_000,
            'hierarchical_certificate_resource_limit')
    ticks=model.deltas*65536
    require(np.equal(ticks,np.round(ticks)).all() and ((ticks>=-2**31)&(ticks<2**31)).all(),
            'encoded_16_16_coefficients_required')
    # Integral accumulation avoids treating relative-operand accuracy as
    # absolute-control accuracy. Conversion to binary64 remains exact here.
    absolute=np.cumsum(ticks.astype(np.int64).reshape(len(ticks),-1,2),axis=1)
    require((np.abs(absolute)<2**53).all(), 'exact_control_accumulation_overflow')
    absolute=absolute.reshape(len(ticks),-1).astype(float)/65536
    maps=[layout(k)[1] for k in knots]
    indices=[]
    for support in model.supports:
        require(set(support)<=set(model.axis_tags), 'unknown_hierarchical_support_axis')
        key=[tuple(support[t]) if t in support else None for t in model.axis_tags]
        require(all(v in m for v,m in zip(key,maps)), 'support_not_in_hierarchical_grid')
        indices.append(tuple(m[v] for v,m in zip(key,maps)))
    require(len(set(indices))==len(indices), 'duplicate_hierarchical_support')
    score=(np.linalg.norm(absolute[1:].reshape(len(absolute)-1,-1,2),axis=2).max(axis=1,initial=0)
           if len(absolute)>1 else np.empty(0))
    order=np.argsort(-score,kind='stable')+1
    initial=min(len(order),max_regions//2)
    kept=set(map(int,order[:initial]))|{0}; remaining=set(range(len(absolute)))-kept
    def grid():
        c=np.zeros((*shape,absolute.shape[1]))
        for i in remaining:c[indices[i]]=absolute[i]
        return c
    if remaining:
        error=synthesize(grid(),knots).reshape(*shape,-1,2)
        weights=[np.asarray([[supportScalar({tag:float(x)},{tag:tuple(s[tag])} if tag in s else {})
            for x in k] for s in model.supports]) for tag,k in zip(model.axis_tags,knots)]
        while len(kept)-1 < max_regions:
            if not error.size:break
            norms=np.sum(error*error,axis=-1)
            worst=np.unravel_index(norms.argmax(),norms.shape)
            if float(norms[worst]) <= error_budget*error_budget:
                break
            x,y,z,control=worst; value=error[worst]; choices=np.asarray(sorted(remaining),dtype=int)
            scalar=weights[0][choices,x]*weights[1][choices,y]*weights[2][choices,z]
            contribution=scalar[:,None]*absolute[choices].reshape(len(choices),-1,2)[:,control]
            gain=np.sum(value*value)-np.sum((value-contribution)**2,axis=1)
            chosen=int(choices[gain.argmax()]); kept.add(chosen); remaining.remove(chosen)
            active=[np.flatnonzero(w[chosen]) for w in weights]
            w=(weights[0][chosen,active[0]][:,None,None]*weights[1][chosen,active[1]][None,:,None]
               *weights[2][chosen,active[2]][None,None,:])
            error[np.ix_(*active)] -= w[...,None,None]*absolute[chosen].reshape(-1,2)
            if not remaining:break
    bound=uniform_bound(grid(),knots)
    selected=sorted(kept); evidence=copy.deepcopy(model.evidence)
    evidence.update(sampled_geometry_passed=False,serialized_verification='NOT_RUN',
                    native_verification='NOT_RUN',production_accepted=False)
    evidence['uniform_model_compression']=dict(input_regions=len(model.supports)-1,
        output_regions=len(selected)-1,error_budget=error_budget,max_control_error_bound=bound,
        within_budget=bound<=error_budget,scope='reference_encoded_model_on_declared_box_only',
        proof='multiaffine_vertex_convexity_with_outward_interval_synthesis',
        source_error_certified=False)
    return OutlineModel(model.axis_tags,model.operators,[model.supports[i] for i in selected],
                        model.deltas[selected].copy(),evidence)
