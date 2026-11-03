"""Analytical plane/box contacts for adaptive field-error measurement.

The source's local branch cell supplies candidate planes, not a global coverage
certificate. Probe their box-edge contacts and interior combinations, then let
the real source evaluator measure error. No validation coordinates are inputs.
Existing chord probes still cover ancestor branches outside the centre cell.
"""
from itertools import product
import numpy as np
from cff2_geometry import require
from hvf_branch_cells import branch_cell


def plane_box_contacts(coefficients,bounds):
    a=np.asarray(coefficients,dtype=float);bounds=np.asarray(bounds,dtype=float)
    require(a.shape==(4,) and bounds.shape==(3,2) and np.isfinite(a).all()
            and np.isfinite(bounds).all() and np.all(bounds[:,0]<bounds[:,1]),'invalid_plane_box')
    contacts=set()
    for axis in range(3):
        if a[axis+1]==0:continue
        fixed=[i for i in range(3) if i!=axis]
        for ends in product((0,1),repeat=2):
            p=np.zeros(3);p[fixed]=bounds[fixed,ends]
            p[axis]=-(a[0]+sum(a[i+1]*p[i] for i in fixed))/a[axis+1]
            if bounds[axis,0]<=p[axis]<=bounds[axis,1]:contacts.add(tuple(p))
    return np.asarray(sorted(contacts)).reshape(-1,3)


def surface_probes(source,bounds):
    bounds=np.asarray(bounds);cell=branch_cell(source.table,source.gid,bounds.mean(axis=1))
    planes=set();points=set()
    for surface in cell.surfaces:
        if any(isinstance(x,str) and x.startswith('tangent') for x in surface.identity):continue
        q=surface.coefficients
        if np.any(q[1:,1:]):continue  # Rational Type-2 contacts are separate.
        a=np.r_[q[0,0],q[0,1:]+q[1:,0]]
        if not np.any(a[1:]) or tuple(a) in planes:continue
        planes.add(tuple(a));vertices=plane_box_contacts(a,bounds)
        if len(vertices)<2:continue
        centre=vertices.mean(axis=0)
        for p in np.r_[vertices,centre[None],(vertices+centre)/2]:
            points.add(tuple(p))
    require(len(points)<=16384,'branch_surface_probe_capacity')
    return np.asarray(sorted(points)).reshape(-1,3)
