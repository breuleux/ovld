import sys
from functools import singledispatch

import pytest
from multimethod import multimethod as multimethod_dispatch
from multipledispatch import dispatch as _md_dispatch
from plum import dispatch as plum_dispatch
from runtype import multidispatch as runtype_dispatch

from ovld import ovld as ovld_dispatch


def _locate(fn):
    fr = sys._getframe(1)
    while fr and fn.__code__ not in fr.f_code.co_consts:
        fr = fr.f_back
    return fr.f_locals.get(fn.__name__, None)


def _getanns(fn):
    anns = fn.__annotations__.values()
    anns = [tuple(ann.__args__) if hasattr(ann, "__args__") else ann for ann in anns]
    return anns


def multipledispatch_dispatch(fn):
    anns = _getanns(fn)
    existing = _locate(fn)
    if existing:
        existing.register(*anns)(fn)
        return existing
    else:
        return _md_dispatch(*anns)(fn)


def singledispatch_dispatch(fn):
    existing = _locate(fn)
    if existing:
        existing.register(fn)
        return existing
    else:
        return singledispatch(fn)


def with_functions(**tests):
    return pytest.mark.parametrize(
        "fn",
        argvalues=list(tests.values()),
        ids=list(tests.keys()),
    )


def function_builder(defn):
    def wrapper(dispatch):
        try:
            rval = defn(dispatch)
        except Exception as exc:
            e = exc

            def reraise(*args, **kwargs):
                raise e

            rval = reraise
        try:
            rval._dispatch = dispatch
        except AttributeError:
            pass
        return rval

    return wrapper


__all__ = [
    "multimethod_dispatch",
    "plum_dispatch",
    "runtype_dispatch",
    "ovld_dispatch",
    "multipledispatch_dispatch",
    "singledispatch_dispatch",
    "function_builder",
    "with_functions",
]
