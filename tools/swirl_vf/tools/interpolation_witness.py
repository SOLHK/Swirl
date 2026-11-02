"""Necessary error bounds for ordinary CFF2 blends inside one support cell.

With d varying axes and no support knot crossed, each region scalar restricted
to a chord is a polynomial of degree at most d. Summation, coefficient
quantization and relative-to-absolute control-point accumulation preserve that
degree. A (d+1)st divided difference annihilates EVERY such model, independently
of its fitted coefficients. Its norm / weight L1 norm is a necessary lower
bound on the largest error at the supplied observations (triangle inequality).

The arithmetic certificate treats supplied binary64 observations as exact
rationals. It does not certify a source evaluator, native rounding, nested
blends, avar remapping, or absence of error between observations.
"""
from fractions import Fraction
import math

import numpy as np
from cff2_geometry import LIMIT, require


def polynomial_witness(parameters, control_points, degree):
    t=np.asarray(parameters,dtype=float)
    p=np.asarray(control_points,dtype=float)
    require(type(degree) is int and 0<=degree<=3 and t.shape==(degree+2,)
            and np.isfinite(t).all() and (np.diff(t)>0).all()
            and 0<=t[0]<t[-1]<=1,'invalid_polynomial_witness_parameters')
    require(p.ndim==3 and p.shape[0]==len(t) and p.shape[1]>0
            and p.shape[2]==2 and np.isfinite(p).all(),
            'invalid_polynomial_witness_points')
    exact=[Fraction(float(x)) for x in t]
    weights=[1/math.prod(x-y for j,y in enumerate(exact) if i!=j)
             for i,x in enumerate(exact)]
    scale=sum(abs(w) for w in weights)
    weights=[w/scale for w in weights]
    squared=[]
    for point in range(p.shape[1]):
        residual=[sum(w*Fraction(float(p[i,point,axis]))
                      for i,w in enumerate(weights)) for axis in range(2)]
        squared.append(sum(v*v for v in residual))
    index=max(range(len(squared)),key=squared.__getitem__)
    lower=squared[index]
    return dict(degree=degree,observation_count=len(t),control_index=index,
                lower_bound=math.sqrt(float(lower)),
                squared_lower_bound_numerator=str(lower.numerator),
                squared_lower_bound_denominator=str(lower.denominator),
                exceeds_limit=lower>Fraction(LIMIT)**2,
                limit_source_font_units=LIMIT,
                scope='necessary_bound_for_supplied_observations',
                source_and_native_arithmetic_certified=False)


def flat_cell_degree(axis_tags,supports,start,end):
    """Validate a chord lies inside one ordinary-blend polynomial cell."""
    tags=tuple(axis_tags);a=np.asarray(start,dtype=float);b=np.asarray(end,dtype=float)
    require(1<=len(tags)<=3 and len(set(tags))==len(tags)
            and all(isinstance(t,str) and len(t)==4 for t in tags)
            and a.shape==b.shape==(len(tags),) and np.isfinite(a).all()
            and np.isfinite(b).all() and (np.abs(a)<=1).all()
            and (np.abs(b)<=1).all() and np.any(a!=b),'invalid_flat_cell_chord')
    require(isinstance(supports,(list,tuple)) and len(supports)>0,
            'flat_cell_supports_required')
    for support in supports:
        require(isinstance(support,dict) and set(support)<=set(tags),
                'invalid_flat_cell_support_axes')
        for tag,triple in support.items():
            values=np.asarray(triple,dtype=float)
            require(values.shape==(3,) and np.isfinite(values).all()
                    and (np.abs(values)<=1).all() and (np.diff(values)>=0).all()
                    and (values[1]==0 or values[0]*values[2]>=0),
                    'invalid_flat_cell_support')
            if values[1]==0:continue  # OpenType: axis does not participate.
            axis=tags.index(tag);lo,hi=sorted((a[axis],b[axis]))
            require(not np.any((lo<values)&(values<hi)),
                    'flat_cell_chord_crosses_support_knot')
    return int(np.count_nonzero(a!=b))
