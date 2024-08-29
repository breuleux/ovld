import pytest
from multimethod import multimethod as multimethod_dispatch
from multipledispatch import dispatch as multipledispatch_dispatch
from plum import dispatch as plum_dispatch

from ovld import ovld as ovld_dispatch
from ovld import recurse

A = {"xs": list(range(50)), "ys": ("o", (6, 7))}
B = {"xs": list(range(10, 60)), "ys": ("x", (7, 6))}
C = {"xs": list(range(10, 110, 2)), "ys": ("ox", (13, 13))}

########
# ovld #
########


@ovld_dispatch
def add_ovld(x: list, y: list):
    """One."""
    return [add_ovld(a, b) for a, b in zip(x, y)]


@ovld_dispatch
def add_ovld(x: tuple, y: tuple):
    return tuple(add_ovld(a, b) for a, b in zip(x, y))


@ovld_dispatch
def add_ovld(x: dict, y: dict):
    return {k: add_ovld(v, y[k]) for k, v in x.items()}


@ovld_dispatch
def add_ovld(x: object, y: object):
    return x + y


@pytest.mark.benchmark(group="add")
def test_add_ovld(benchmark):
    result = benchmark(add_ovld, A, B)
    assert result == C


################
# ovld_recurse #
################


@ovld_dispatch
def add_ovld_recurse(x: list, y: list):
    """One."""
    return [recurse(a, b) for a, b in zip(x, y)]


@ovld_dispatch
def add_ovld_recurse(x: tuple, y: tuple):
    return tuple(recurse(a, b) for a, b in zip(x, y))


@ovld_dispatch
def add_ovld_recurse(x: dict, y: dict):
    return {k: recurse(v, y[k]) for k, v in x.items()}


@ovld_dispatch
def add_ovld_recurse(x: object, y: object):
    return x + y


@pytest.mark.benchmark(group="add")
def test_add_ovld_recurse(benchmark):
    result = benchmark(add_ovld_recurse, A, B)
    assert result == C


########
# plum #
########


@plum_dispatch
def add_plum(x: list, y: list):
    """Three."""
    return [add_plum(a, b) for a, b in zip(x, y)]


@plum_dispatch
def add_plum(x: tuple, y: tuple):
    return tuple(add_plum(a, b) for a, b in zip(x, y))


@plum_dispatch
def add_plum(x: dict, y: dict):
    return {k: add_plum(v, y[k]) for k, v in x.items()}


@plum_dispatch
def add_plum(x: object, y: object):
    return x + y


@pytest.mark.benchmark(group="add")
def test_add_plum(benchmark):
    result = benchmark(add_plum, A, B)
    assert result == C


###############
# multimethod #
###############


@multimethod_dispatch
def add_multimethod(x: list, y: list):
    """Three."""
    return [add_multimethod(a, b) for a, b in zip(x, y)]


@multimethod_dispatch
def add_multimethod(x: tuple, y: tuple):
    return tuple(add_multimethod(a, b) for a, b in zip(x, y))


@multimethod_dispatch
def add_multimethod(x: dict, y: dict):
    return {k: add_multimethod(v, y[k]) for k, v in x.items()}


@multimethod_dispatch
def add_multimethod(x: object, y: object):
    return x + y


@pytest.mark.benchmark(group="add")
def test_add_multimethod(benchmark):
    result = benchmark(add_multimethod, A, B)
    assert result == C


####################
# multipledispatch #
####################


@multipledispatch_dispatch(list, list)
def add_multipledispatch(x, y):
    """Four."""
    return [add_multipledispatch(a, b) for a, b in zip(x, y)]


@multipledispatch_dispatch(tuple, tuple)
def add_multipledispatch(x, y):
    return tuple(add_multipledispatch(a, b) for a, b in zip(x, y))


@multipledispatch_dispatch(dict, dict)
def add_multipledispatch(x, y):
    return {k: add_multipledispatch(v, y[k]) for k, v in x.items()}


@multipledispatch_dispatch(object, object)
def add_multipledispatch(x, y):
    return x + y


@pytest.mark.benchmark(group="add")
def test_add_multipledispatch(benchmark):
    result = benchmark(add_multipledispatch, A, B)
    assert result == C


##############
# isinstance #
##############


def add_isinstance(x, y):
    """Five."""
    if isinstance(x, dict) and isinstance(y, dict):
        return {k: add_isinstance(v, y[k]) for k, v in x.items()}
    elif isinstance(x, tuple) and isinstance(y, tuple):
        return tuple(add_isinstance(a, b) for a, b in zip(x, y))
    elif isinstance(x, list) and isinstance(y, list):
        return [add_isinstance(a, b) for a, b in zip(x, y)]
    else:
        return x + y


@pytest.mark.benchmark(group="add")
def test_add_isinstance(benchmark):
    result = benchmark(add_isinstance, A, B)
    assert result == C


###################
# match statement #
###################


def add_match(x, y):
    match (x, y):
        case ({}, {}):
            return {k: add_match(v, y[k]) for k, v in x.items()}
        case (tuple(), tuple()):
            return tuple(add_match(a, b) for a, b in zip(x, y))
        case ([*x], [*y]):
            return [add_match(a, b) for a, b in zip(x, y)]
        case _:
            return x + y


@pytest.mark.benchmark(group="add")
def test_add_match(benchmark):
    result = benchmark(add_match, A, B)
    assert result == C
