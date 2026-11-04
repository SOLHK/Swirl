"""Propagate HVF axes as piecewise-affine functions along a design-space line.

Every composite axis is an affine combination of positive/negative child-axis
parts. Consequently its zero crossings can be found before sampling outlines.
Within that partition raw shape coordinates are affine. A Type-2 projection
changes regime at roots of (P-A).(B-A)=0 or (P-B).(B-A)=0: quadratic equations,
not necessarily axis-aligned master locations. Rotations are smooth within the
same axis partition and are left to geometric error-driven refinement.

This symbolic line partition is float64, not a universal continuous-space proof.
It does not change source coordinates or claim that a slice covers three axes.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from hvf import Composite,require


@dataclass(frozen=True)
class LinearPieces:
    knots: np.ndarray
    values: np.ndarray

    @classmethod
    def constant(cls,value):
        return cls(np.asarray([-1.,1.]),np.asarray([value,value],dtype=float))

    def at(self,x):return np.interp(x,self.knots,self.values)

    def add_scaled(self,other,scale=1.):
        if scale==0:return self
        knots=np.union1d(self.knots,other.knots)
        require(len(knots)<=65536,'piecewise_axis_capacity')
        return LinearPieces(knots,self.at(knots)+scale*other.at(knots))

    def crossings(self,value=0.):
        y=self.values-value
        roots=list(self.knots[y==0])
        for i in np.flatnonzero((y[:-1]<0)&(y[1:]>0)|(y[:-1]>0)&(y[1:]<0)):
            roots.append(float(self.knots[i]-y[i]*(self.knots[i+1]-self.knots[i])/(y[i+1]-y[i])))
        return sorted(set(x for x in roots if -1<x<1))

    def positive(self,sign=1.):
        require(sign in (-1,1),'piecewise_axis_sign')
        knots=np.union1d(self.knots,self.crossings())
        return LinearPieces(knots,np.maximum(sign*self.at(knots),0.))


def projection_roots(points):
    """Local t in (0,1), with A,B,P each given at the interval's endpoints.

    Solve in local coordinates to avoid subtracting large global polynomial
    coefficients. Constant zero equations introduce no new partition boundary.
    """
    a,b,p=[np.asarray(v,dtype=float) for v in points]
    require(all(v.shape==(2,2) and np.isfinite(v).all() for v in (a,b,p)),
            'invalid_projection_root_input')
    d0=b[0]-a[0];d1=(b[1]-a[1])-d0
    roots=[]
    for label,origin in (('lower',a),('upper',b)):
        u0=p[0]-origin[0];u1=(p[1]-origin[1])-u0
        c=np.asarray([np.dot(u0,d0),np.dot(u0,d1)+np.dot(u1,d0),np.dot(u1,d1)])
        # Scale the complete polynomial, never discard a small valid leading
        # coefficient by an arbitrary geometry epsilon.
        if not np.any(c):continue
        c=c/np.max(np.abs(c))
        for root in np.polynomial.polynomial.polyroots(c):
            if np.isreal(root) and 0<float(np.real(root))<1:
                roots.append((label,float(np.real(root))))
    return roots


def line_partition(table,gid,varying_axis,fixed_coordinates):
    """Return exact structural branch candidates for one root-axis sweep."""
    root=table.part(gid);fixed=np.asarray(fixed_coordinates,dtype=float)
    require(fixed.shape==(root.axis_count,) and 0<=varying_axis<root.axis_count
            and np.isfinite(fixed).all() and (np.abs(fixed)<=1).all(),'invalid_piecewise_root_line')
    values=[LinearPieces.constant(0.) for _ in range(root.tree_axes)]
    for i,v in enumerate(fixed):values[i]=LinearPieces.constant(v)
    values[varying_axis]=LinearPieces(np.asarray([-1.,1.]),np.asarray([-1.,1.]))
    records=[];active=set();node_count=0
    def emit(kind,part,base,field,x):
        if -1<x<1:records.append(dict(kind=kind,part=part,tree_part_offset=base,field=field,coordinate=float(x)))
    def visit(index,part_base,axis_base,depth):
        nonlocal node_count
        require(index not in active and depth<=256,'cyclic_piecewise_hierarchy')
        active.add(index);node_count+=1
        part=table.part(index);axes=values[axis_base:axis_base+part.axis_count]
        weights=[]
        for axis,value in enumerate(axes):
            for x in value.crossings():emit('axis_zero',index,part_base,axis,x)
            weights.extend((value.positive(-1),value.positive(1)))
        if isinstance(part,Composite):
            base=axis_base+part.axis_count
            for row,v in zip(part.master_rows,part.master_values):
                j=base+int(row);values[j]=values[j].add_scaled(LinearPieces.constant(v))
            for col,w in enumerate(weights):
                first,last=map(int,part.column_starts[col:col+2])
                for row,v in zip(part.extreme_rows[first:last],part.extreme_values[first:last]):
                    j=base+int(row);values[j]=values[j].add_scaled(w,float(v))
            for child,part_row,axis_row in part.subparts:
                visit(child,part_base+1+part_row,base+axis_row,depth+1)
        else:
            knots=np.asarray(sorted(set([-1.,1.,*[x for w in weights for x in w.knots]])))
            require(len(knots)*part.master.size<=8_000_000,'piecewise_shape_capacity')
            raw=np.broadcast_to(part.master,(len(knots),*part.master.shape)).copy()
            if weights:raw+=np.einsum('na,asp->nsp',np.stack([w.at(knots) for w in weights],axis=1),part.delta)
            start=0
            for path,size in enumerate(part.path_sizes):
                if size>=3:
                    for i,kind in enumerate(part.blends[start:start+size]):
                        field=[path,i]
                        if kind==0:
                            factor=LinearPieces(knots,raw[:,start+i,0])
                            for value in (0.,1.):
                                for x in factor.crossings(value):emit(f'curve_{int(value)}',index,part_base,field,x)
                        elif kind==2:
                            a=raw[:,start+(i-1)%size,2:4];b=raw[:,start+i,2:4];p=raw[:,start+i,:2]
                            for j,(lo,hi) in enumerate(zip(knots[:-1],knots[1:])):
                                for side,t in projection_roots((a[j:j+2],b[j:j+2],p[j:j+2])):
                                    emit('tangent_'+side,index,part_base,field,lo+t*(hi-lo))
                        else:require(kind==1,'unsupported_piecewise_tangent_type')
                start+=size
        active.remove(index)
    visit(gid,0,0,0)
    records.sort(key=lambda r:r['coordinate'])
    return {'glyph_id':gid,'varying_axis_index':varying_axis,'fixed_coordinates':fixed.tolist(),
            'node_count':node_count,'events':records,
            'knots':sorted(set([0.,*[r['coordinate'] for r in records]])),
            'three_dimensional_acceptance':False}
