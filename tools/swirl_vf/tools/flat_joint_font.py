"""Certified collapse of eligible octant fields to ordinary CFF2 deltas.

No hidden axes or GSUB patch glyphs are needed when a 27-node multilinear
field stays within a declared distance of the retained tricubic atlas. The
certificate bounds every control point throughout each cell using outward
interval Bernstein coefficients, including the new 16.16 serialization.
It bounds representation change, not the source interpolation error.
"""
from itertools import product
from math import comb
import numpy as np
from fontTools.varLib.models import VariationModel,supportScalar
import cff2_geometry as geometry
from joint_polynomial import TAGS
from localized_projection_font import build as localized_build,copy_metric_variations

down=lambda x:np.nextafter(x,-np.inf)
up=lambda x:np.nextafter(x,np.inf)


def bernstein_control_bound(power_difference):
    """Outward-rounded interval bound in L1, hence also in Euclidean norm."""
    lo=down(power_difference).reshape(4,4,4,-1,2)
    hi=up(power_difference).reshape(4,4,4,-1,2)
    # Relative operands become absolute control points. Each addition rounds
    # outward separately; a single padding on np.cumsum would be insufficient.
    for j in range(1,lo.shape[-2]):
        lo[...,j,:]=down(lo[...,j,:]+lo[...,j-1,:])
        hi[...,j,:]=up(hi[...,j,:]+hi[...,j-1,:])
    for axis in range(3):
        a,b=np.moveaxis(lo,axis,0),np.moveaxis(hi,axis,0)
        lower=np.zeros_like(a);upper=np.zeros_like(b)
        for i in range(4):
            for k in range(i+1):
                ratio=comb(i,k)/comb(3,k);rlo,rhi=down(ratio),up(ratio)
                products=np.stack((a[k]*rlo,a[k]*rhi,b[k]*rlo,b[k]*rhi))
                lower[i]=down(lower[i]+down(products.min(axis=0)))
                upper[i]=up(upper[i]+up(products.max(axis=0)))
        lo,hi=np.moveaxis(lower,0,axis),np.moveaxis(upper,0,axis)
    magnitude=np.maximum(np.abs(lo),np.abs(hi))
    return float(up(magnitude[...,0]+magnitude[...,1]).max())


def collapse(atlas,*,budget=1/1024):
    geometry.require(0<budget<=geometry.LIMIT/8,'invalid_flat_representation_budget')
    expected={tuple(np.c_[lo,np.asarray(lo)+1].ravel()) for lo in product((-1.,0.),repeat=3)}
    geometry.require(len(atlas.boxes)==8 and {tuple(b.bounds.ravel()) for b in atlas.boxes}==expected,
                     'flat_requires_complete_eight_octants')
    points=np.asarray(list(product((-1.,0.,1.),repeat=3)))
    locations=[{tag:float(x) for tag,x in zip(TAGS,p) if x} for p in points]
    variation=VariationModel(locations,axisOrder=list(TAGS))
    deltas=np.asarray(variation.getDeltas(atlas.values(points)))
    deltas=np.floor(deltas*65536+.5)/65536
    geometry.require(np.isfinite(deltas).all() and np.all((deltas>=-32768)&(deltas<32768)),
                     'flat_fixed_coefficient_overflow')
    # At these integer support corners all scalars are 0 or 1, and sums of
    # <=27 signed 16.16 operands are exactly representable in binary64.
    corners=np.asarray(list(product((0.,1.),repeat=3)))
    maximum=0.
    for box in atlas.boxes:
        q=box.from_local(corners)
        weights=np.asarray([[supportScalar(dict(zip(TAGS,p)),s) for s in variation.supports] for p in q])
        geometry.require(np.all((weights==0)|(weights==1)),'nonbinary_flat_corner_weight')
        values=(weights@deltas).reshape(2,2,2,-1)
        linear=np.zeros_like(box.coefficients)
        for index in product((0,1),repeat=3):
            for corner in product(*[range(i+1) for i in index]):
                linear[index]+=(-1)**sum(i-j for i,j in zip(index,corner))*values[corner]
        maximum=max(maximum,bernstein_control_bound(box.coefficients-linear))
    geometry.require(maximum<=budget,'flat_representation_bound_exceeded:'+str(maximum))
    proof=dict(sampled_geometry_passed=True,representation_change_control_bound=maximum,
        representation_budget=budget,bound_kind='outward_interval_Bernstein_L1',
        whole_source_error_certified=False,serialized_native_verification='NOT_RUN')
    return geometry.compact(geometry.OutlineModel(TAGS,atlas.boxes[0].operators,variation.supports,deltas,proof))


def build(source,gid,atlas,parameters,*,budget=1/1024):
    geometry.require(parameters.coefficients.shape[1]==0,'flat_requires_no_projection_factors')
    model=collapse(atlas,budget=budget)
    # Reuse the existing source metrics/profile builder. Only eight small
    # provisional cells can reach here; none is retained in the final font.
    font=localized_build(source,gid,atlas,parameters)
    order=font.getGlyphOrder()[:3];font.setGlyphOrder(order)
    for tag in ('hmtx','vmtx'):
        if tag in font:font[tag].metrics={n:font[tag].metrics[n] for n in order}
    for tag in ('HVAR','VVAR'):
        if tag in font:del font[tag]
        copy_metric_variations(source,font,tag,source.getGlyphOrder()[gid],gid,())
    if 'GSUB' in font:del font['GSUB']
    empty=geometry.OutlineModel(TAGS,(),[{}],np.zeros((1,0)),{'sampled_geometry_passed':True})
    result=geometry.install(font,{order[0]:empty,order[1]:empty,order[2]:model},release_programs=True)
    result._swirl_projection_receipt=dict(scope='selected_source_glyph_flat_research_probe',
        **model.evidence,production_accepted=False,source_gid=gid,physical_axes=list(TAGS),
        computational_axes=0,patch_glyphs=0,glyphs=3,cff2_regions=len(model.supports)-1,
        maximum_operand_stack=len(model.supports)+max(n for _,n in model.operators))
    return result
