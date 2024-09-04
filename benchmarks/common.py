from multimethod import multimethod as multimethod_dispatch
from multipledispatch import dispatch as _md_dispatch
from plum import dispatch as plum_dispatch
from runtype import multidispatch as runtype_dispatch

from ovld import ovld as ovld_dispatch


def multipledispatch_dispatch(fn):
    anns = fn.__annotations__.values()
    anns = [
        tuple(ann.__args__) if hasattr(ann, "__args__") else ann for ann in anns
    ]
    return _md_dispatch(*anns)(fn)


__all__ = [
    "multimethod_dispatch",
    "plum_dispatch",
    "runtype_dispatch",
    "ovld_dispatch",
    "multipledispatch_dispatch",
]
