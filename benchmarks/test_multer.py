import pytest
from multimethod import multimethod as multimethod_dispatch
from multipledispatch import dispatch as multipledispatch_dispatch
from plum import dispatch as plum_dispatch
from runtype import multidispatch as runtype_dispatch

from ovld import recurse
from ovld.core import OvldBase

A = {"xs": list(range(0, 50)), "ys": ("o", (6, 7))}
C = {"xs": list(range(0, 150, 3)), "ys": ("ooo", (18, 21))}


########
# ovld #
########


class OvldMulter(OvldBase):
    def __init__(self, factor):
        self.factor = factor

    def __call__(self, x: list):
        return [self(a) for a in x]

    def __call__(self, x: tuple):
        return tuple(self(a) for a in x)

    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    def __call__(self, x: object):
        return x * self.factor


@pytest.mark.benchmark(group="multer")
def test_multer_ovld(benchmark):
    result = benchmark(OvldMulter(3), A)
    assert result == C


################
# ovld_recurse #
################


class OvldRecurseMulter(OvldBase):
    def __init__(self, factor):
        self.factor = factor

    def __call__(self, x: list):
        return [recurse(a) for a in x]

    def __call__(self, x: tuple):
        return tuple(recurse(a) for a in x)

    def __call__(self, x: dict):
        return {k: recurse(v) for k, v in x.items()}

    def __call__(self, x: object):
        return x * self.factor


@pytest.mark.benchmark(group="multer")
def test_multer_ovld_recurse(benchmark):
    result = benchmark(OvldRecurseMulter(3), A)
    assert result == C


########
# plum #
########


class PlumMulter:
    def __init__(self, factor):
        self.factor = factor

    @plum_dispatch
    def __call__(self, x: list):
        return [self(a) for a in x]

    @plum_dispatch
    def __call__(self, x: tuple):
        return tuple(self(a) for a in x)

    @plum_dispatch
    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    @plum_dispatch
    def __call__(self, x: object):
        return x * self.factor


@pytest.mark.benchmark(group="multer")
def test_multer_plum(benchmark):
    result = benchmark(PlumMulter(3), A)
    assert result == C


####################
# multipledispatch #
####################


class MultipleDispatchMulter:
    def __init__(self, factor):
        self.factor = factor

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


@pytest.mark.benchmark(group="multer")
def test_multer_multipledispatch(benchmark):
    result = benchmark(MultipleDispatchMulter(3), A)
    assert result == C


###############
# multimethod #
###############


class MultimethodMulter:
    def __init__(self, factor):
        self.factor = factor

    @multimethod_dispatch
    def __call__(self, x: list):
        return [self(a) for a in x]

    @multimethod_dispatch
    def __call__(self, x: tuple):
        return tuple(self(a) for a in x)

    @multimethod_dispatch
    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    @multimethod_dispatch
    def __call__(self, x: object):
        return x * self.factor


@pytest.mark.benchmark(group="multer")
def test_multer_multimethod(benchmark):
    result = benchmark(MultimethodMulter(3), A)
    assert result == C


###########
# runtype #
###########


class RuntypeMulter:
    def __init__(self, factor):
        self.factor = factor

    @runtype_dispatch
    def __call__(self, x: list):
        return [self(a) for a in x]

    @runtype_dispatch
    def __call__(self, x: tuple):
        return tuple(self(a) for a in x)

    @runtype_dispatch
    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    @runtype_dispatch
    def __call__(self, x: object):
        return x * self.factor


@pytest.mark.benchmark(group="multer")
def test_multer_runtype(benchmark):
    result = benchmark(RuntypeMulter(3), A)
    assert result == C


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


@pytest.mark.benchmark(group="multer")
def test_multer_custom_isinstance(benchmark):
    result = benchmark(IsinstanceMulter(3), A)
    assert result == C
