"""Bound observed native path differences without overriding a topology gate.

Each transition consumes a cubic from both oriented paths, or a cubic from one
path while the other stays at its current endpoint. Convexity bounds every
point by the maximum distance between the paired Bernstein controls. A complete
monotone transition chain covers every segment on both paths, including short
closing edges and small curves; nothing is deleted or snapped. It proves a
Frechet upper bound for these observed paths, not control/topology identity,
native axis transport, continuous design-space accuracy or font acceptance.

All coefficients and squared bounds use exact rational arithmetic on supplied
binary64 coordinates. Lines are elevated exactly. No flattening or curve sample
grid is used. The search is deliberately incomplete for general reparameterized
curves: failure to find a chain does not prove a lower bound.
"""
from __future__ import annotations
from fractions import Fraction
import heapq
import math


def _point(row):
    if not isinstance(row,(tuple,list)) or len(row) != 3 or type(row[0]) is not int or \
            any(type(v) not in (int,float) or not math.isfinite(v) for v in row):
        raise ValueError('invalid_native_path_element')
    return tuple(Fraction(v) for v in row[1:])


def qt_contours(elements):
    """Read actual Qt element types; preserve all contours and all segments."""
    contours, current, start, previous = [], None, None, None
    i = 0
    def finish():
        if current is not None:
            if previous != start:
                raise ValueError('native_contour_not_exactly_closed')
            contours.append((start,tuple(current)))
    while i < len(elements):
        row = elements[i];point = _point(row);kind = row[0]
        if type(kind) is not int:
            raise ValueError('invalid_native_path_type')
        if kind == 0:
            finish();current=[];start=previous=point
        elif current is None:
            raise ValueError('native_segment_without_move')
        elif kind == 1:
            a=tuple((2*p+q)/3 for p,q in zip(previous,point))
            b=tuple((p+2*q)/3 for p,q in zip(previous,point))
            current.append((previous,a,b,point));previous=point
        elif kind == 2:
            if i+2 >= len(elements) or elements[i+1][0]!=3 or elements[i+2][0]!=3:
                raise ValueError('incomplete_native_cubic')
            second,end = _point(elements[i+1]),_point(elements[i+2])
            current.append((previous,point,second,end));previous=end;i+=2
        else:
            raise ValueError('unexpected_native_curve_data')
        i+=1
    finish()
    return contours


def _squared(p,q):
    return sum((a-b)**2 for a,b in zip(p,q))


def _bound(left,right):
    return max(_squared(p,q) for p,q in zip(left,right))


def _sqrt_upper(value):
    result=math.sqrt(float(value))
    if not math.isfinite(result):
        raise ValueError('curve_bound_overflow')
    while Fraction(result)**2 < value:
        result=math.nextafter(result,math.inf)
    return result


def _chain(lhs,rhs,limit_squared,max_states):
    a,left=lhs;b,right=rhs;n,m=len(left),len(right)
    initial=_squared(a,b)
    if initial>limit_squared:return None
    best={(0,0):initial};parent={};queue=[(initial,0,0)];visited=0
    while queue:
        cost,i,j=heapq.heappop(queue)
        if best[(i,j)]!=cost:continue
        visited+=1
        if visited>max_states:raise ValueError('curve_certificate_state_budget')
        if i==n and j==m:
            paired=left_only=right_only=0;key=(i,j)
            while key!=(0,0):
                before=parent[key];di=key[0]-before[0];dj=key[1]-before[1]
                paired+=di==1 and dj==1;left_only+=di==1 and dj==0;right_only+=di==0 and dj==1
                key=before
            return dict(squared=cost,paired=paired,left_only=left_only,right_only=right_only,
                        states=visited,left_segments=n,right_segments=m)
        p=left[i][0] if i<n else (left[-1][-1] if n else a)
        q=right[j][0] if j<m else (right[-1][-1] if m else b)
        candidates=[]
        if i<n and j<m:candidates.append((i+1,j+1,_bound(left[i],right[j])))
        if i<n:candidates.append((i+1,j,_bound(left[i],(q,)*4)))
        if j<m:candidates.append((i,j+1,_bound((p,)*4,right[j])))
        for ni,nj,step in candidates:
            proposed=max(cost,step)
            if proposed<=limit_squared and ((ni,nj) not in best or proposed<best[(ni,nj)]):
                best[(ni,nj)]=proposed;parent[(ni,nj)]=(i,j)
                heapq.heappush(queue,(proposed,ni,nj))
    return None


def certify_qt_paths(left,right,*,limit=1/32,max_states=100000):
    """Separate diagnostic; never convert a raw topology failure into a pass."""
    if type(limit) not in (int,float) or not math.isfinite(limit) or limit<0:
        raise ValueError('invalid_curve_certificate_limit')
    if type(max_states) is not int or not 1<=max_states<=1000000:
        raise ValueError('invalid_curve_certificate_budget')
    lhs,rhs=qt_contours(left),qt_contours(right)
    result=dict(status='NO_CERTIFICATE',scope='supplied_observed_paths_only',
                strict_path_gate_overridden=False,production_accepted=False,
                limit=limit,left_contours=len(lhs),right_contours=len(rhs),contours=[])
    if len(lhs)!=len(rhs):
        result['reason']='contour_count_differs';return result
    maximum=Fraction(0)
    for i,(a,b) in enumerate(zip(lhs,rhs)):
        chain=_chain(a,b,Fraction(limit)**2,max_states)
        if chain is None:
            result.update(reason='no_bounded_monotone_segment_chain',failed_contour=i)
            return result
        value=chain.pop('squared');maximum=max(maximum,value)
        result['contours'].append(dict(chain,max_curve_distance_bound=_sqrt_upper(value)))
    result.update(status='BOUND_WITHIN_LIMIT',max_curve_distance_bound=_sqrt_upper(maximum),
                  squared_bound_numerator=str(maximum.numerator),
                  squared_bound_denominator=str(maximum.denominator))
    return result


def point_separation(point,cubics,*,limit=1/32,max_states=100000):
    """Prove a point is farther than limit from the ENTIRE supplied curve set.

    Exact de Casteljau subdivision shrinks convex-hull bounding boxes. A box
    distance is a lower bound; subdivision cannot fabricate a curve sample.
    The caller must independently establish that the query belongs to its
    reference outline. This does not accept a font or prove an optimal fit.
    """
    if type(limit) not in (int,float) or not math.isfinite(limit) or limit<0 or \
            type(max_states) is not int or not 1<=max_states<=1000000:
        raise ValueError('invalid_separation_contract')
    def rational(p):
        if len(p)!=2 or any(type(v) not in (int,float,Fraction) or
                           (type(v) is float and not math.isfinite(v)) for v in p):
            raise ValueError('invalid_separation_point')
        return tuple(Fraction(v) for v in p)
    q=rational(point);limit_squared=Fraction(limit)**2
    def lower(c):
        return sum(max(min(p[a] for p in c)-q[a],q[a]-max(p[a] for p in c),Fraction(0))**2
                   for a in range(2))
    def split(c):
        rows=[c]
        for _ in range(3):
            rows.append([tuple((x+y)/2 for x,y in zip(a,b))
                         for a,b in zip(rows[-1],rows[-1][1:])])
        return [row[0] for row in rows],[row[-1] for row in reversed(rows)]
    if not 1<=len(cubics)<=10000:raise ValueError('invalid_separation_curve_count')
    queue=[];serial=0;steps=0
    for c in cubics:
        if len(c)!=4:raise ValueError('separation_requires_cubics')
        curve=tuple(map(rational,c));heapq.heappush(queue,(lower(curve),serial,curve,0));serial+=1
    while queue:
        value,_,c,depth=heapq.heappop(queue)
        if value>limit_squared:
            report=math.sqrt(float(value))
            while Fraction(report)**2>value:report=math.nextafter(report,-math.inf)
            return dict(status='SEPARATED_BEYOND_LIMIT',distance_lower_bound=report,
                        squared_lower_numerator=str(value.numerator),
                        squared_lower_denominator=str(value.denominator),subdivisions=steps)
        if min(_squared(q,p) for p in (c[0],c[-1]))<=limit_squared:
            return dict(status='NOT_SEPARATED',subdivisions=steps)
        if depth>=40 or steps>=max_states:
            return dict(status='NO_SEPARATION_CERTIFICATE',reason='resource_budget',subdivisions=steps)
        for child in split(c):
            heapq.heappush(queue,(lower(child),serial,child,depth+1));serial+=1
        steps+=1
    raise AssertionError('nonempty_separation_queue_exhausted')
