from functools import singledispatchmethod

import pytest
from multipledispatch import dispatch as multipledispatch_dispatch

from ovld import recurse
from ovld.core import OvldBase

from .common import (
    fastcore_dispatch,
    multimethod_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
)


class BaseMulter:
    def __init__(self, factor):
        self.factor = factor


def make_multer(dispatch):
    class Multer(BaseMulter):
        @dispatch
        def __call__(self, x: list):
            return [self(a) for a in x]

        @dispatch
        def __call__(self, x: tuple):
            return tuple(self(a) for a in x)

        @dispatch
        def __call__(self, x: dict):
            return {k: self(v) for k, v in x.items()}

        @dispatch
        def __call__(self, x: object):
            return x * self.factor

    return Multer


#####################
# ovld with recurse #
#####################


class OvldRecurseMulter(BaseMulter, OvldBase):
    def __call__(self, x: list):
        return [recurse(a) for a in x]

    def __call__(self, x: tuple):
        return tuple(recurse(a) for a in x)

    def __call__(self, x: dict):
        return {k: recurse(v) for k, v in x.items()}

    def __call__(self, x: object):
        return x * self.factor


####################
# multipledispatch #
####################


# shim doesn't work


class MultipleDispatchMulter(BaseMulter):
    @multipledispatch_dispatch(list)
    def __call__(self, x: list):
        return [self(a) for a in x]

    @multipledispatch_dispatch(tuple)
    def __call__(self, x: tuple):
        return tuple(self(a) for a in x)

    @multipledispatch_dispatch(dict)
    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    @multipledispatch_dispatch(object)
    def __call__(self, x: object):
        return x * self.factor


##################
# singledispatch #
##################


class SingleDispatchMulter(BaseMulter):
    @singledispatchmethod
    def __call__(self, x):
        return x * self.factor

    @__call__.register
    def _(self, x: tuple):
        return tuple(self(a) for a in x)

    @__call__.register
    def _(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    @__call__.register
    def _(self, x: list):
        return [self(a) for a in x]


##############
# isinstance #
##############


class IsinstanceMulter:
    def __init__(self, factor):
        self.factor = factor

    def __call__(self, x):
        if isinstance(x, dict):
            return {k: self(v) for k, v in x.items()}
        elif isinstance(x, tuple):
            return tuple(self(a) for a in x)
        elif isinstance(x, list):
            return [self(a) for a in x]
        else:
            return x * self.factor


####################
# Test definitions #
####################


A = {"xs": list(range(0, 50)), "ys": ("o", (6, 7))}
C = {"xs": list(range(0, 150, 3)), "ys": ("ooo", (18, 21))}


def make_test(cls):
    @pytest.mark.benchmark(group="multer")
    def test(benchmark):
        result = benchmark(cls(3), A)
        assert result == C

    return test


test_multer_ovld = make_test(make_multer(ovld_dispatch))
test_multer_recurse = make_test(OvldRecurseMulter)
test_multer_plum = make_test(make_multer(plum_dispatch))
test_multer_multimethod = make_test(make_multer(multimethod_dispatch))
test_multer_singledispatch = make_test(SingleDispatchMulter)
test_multer_multipledispatch = make_test(MultipleDispatchMulter)
test_multer_runtype = make_test(make_multer(runtype_dispatch))
test_multer_fastcore = make_test(make_multer(fastcore_dispatch))

test_multer_custom_isinstance = make_test(IsinstanceMulter)
