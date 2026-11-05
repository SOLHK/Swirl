"""Exact-zero column storage and streaming private NumPy archives.

Projection directions affect few controls. Dense factor-by-control tensors
repeat their zero columns in every cell; retaining only exact nonzero columns
changes neither coefficients nor polynomial arithmetic. No tolerance is used.
"""
from dataclasses import dataclass
import zipfile
import numpy as np
from cff2_geometry import require
from joint_polynomial import PolynomialBox


@dataclass
class SparseFieldBox:
    bounds: np.ndarray
    operators: tuple
    columns: np.ndarray
    data: np.ndarray
    evidence: dict

    def __post_init__(self):
        width=sum(n for _,n in self.operators)
        require(self.data.shape==(4,4,4,len(self.columns)) and np.isfinite(self.data).all()
            and self.columns.ndim==1 and np.issubdtype(self.columns.dtype,np.integer)
            and np.all((self.columns>=0)&(self.columns<width)) and np.all(np.diff(self.columns)>0),
            'invalid_sparse_polynomial_columns')
        # Reuse the existing box-domain validation on an empty authored field.
        PolynomialBox(self.bounds,(),np.empty((4,4,4,0)),{})

    @classmethod
    def from_model(cls,model):
        if isinstance(model,cls):return model
        columns=np.flatnonzero(np.any(model.coefficients!=0,axis=(0,1,2)))
        return cls(model.bounds.copy(),model.operators,columns,
                   model.coefficients[...,columns].copy(),dict(model.evidence))

    @property
    def coefficients(self):
        result=np.zeros((4,4,4,sum(n for _,n in self.operators)))
        result[...,self.columns]=self.data
        return result

    from_local=PolynomialBox.from_local
    to_local=PolynomialBox.to_local

    def values(self,positions):
        # Keep the original einsum contraction plan and operand shape. A narrower
        # tensor can select a different floating-point operation order. Dense
        # coefficients exist for this one evaluation only, never the whole atlas.
        return PolynomialBox(self.bounds,self.operators,self.coefficients,self.evidence).values(positions)


def save_arrays(path,arrays,streams):
    """Write valid .npy members into .npz without concatenating coefficient data."""
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name,array in arrays.items():
            with z.open(name+'.npy','w',force_zip64=True) as member:
                np.lib.format.write_array(member,np.asarray(array),allow_pickle=False)
        for name,(shape,dtype,chunks) in streams.items():
            with z.open(name+'.npy','w',force_zip64=True) as member:
                np.lib.format.write_array_header_2_0(member,dict(descr=np.lib.format.dtype_to_descr(np.dtype(dtype)),fortran_order=False,shape=shape))
                written=0
                for chunk in chunks:
                    data=np.asarray(chunk,dtype=dtype,order='C').tobytes();member.write(data);written+=len(data)
                require(written==int(np.prod(shape))*np.dtype(dtype).itemsize,'streamed_array_size_mismatch')


def legacy_coefficient_slices(path,expected_shape):
    """Read one legacy dense box at a time, with shape/dtype checks before data."""
    with zipfile.ZipFile(path) as archive,archive.open('coefficients.npy') as stream:
        version=np.lib.format.read_magic(stream)
        require(version in ((1,0),(2,0)),'unsupported_private_array_version')
        read_header=(np.lib.format.read_array_header_1_0 if version==(1,0)
                     else np.lib.format.read_array_header_2_0)
        shape,fortran,dtype=read_header(stream)
        require(shape==expected_shape and not fortran and dtype==np.dtype('<f8'),
                'invalid_projection_atlas_storage')
        size=int(np.prod(shape[1:]))*dtype.itemsize
        for _ in range(shape[0]):
            payload=stream.read(size)
            require(len(payload)==size,'truncated_projection_atlas_storage')
            yield np.frombuffer(payload,dtype=dtype).reshape(shape[1:])
        require(not stream.read(1),'trailing_projection_atlas_storage')
