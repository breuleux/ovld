import pytest

from .common import (
    function_builder,
    multimethod_dispatch,
    multipledispatch_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
    with_functions,
)

###############################
# multiple dispatch libraries #
###############################


@function_builder
def make_add(dispatch):
    @dispatch
    def add(x: list, y: list):
        return [add(a, b) for a, b in zip(x, y)]

    @dispatch
    def add(x: tuple, y: tuple):
        return tuple(add(a, b) for a, b in zip(x, y))

    @dispatch
    def add(x: dict, y: dict):
        return {k: add(v, y[k]) for k, v in x.items()}

    @dispatch
    def add(x: object, y: object):
        return x + y

    return add


##############
# isinstance #
##############


def add_isinstance(x, y):
    if isinstance(x, dict) and isinstance(y, dict):
        return {k: add_isinstance(v, y[k]) for k, v in x.items()}
    elif isinstance(x, tuple) and isinstance(y, tuple):
        return tuple(add_isinstance(a, b) for a, b in zip(x, y))
    elif isinstance(x, list) and isinstance(y, list):
        return [add_isinstance(a, b) for a, b in zip(x, y)]
    else:
        return x + y


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


####################
# Test definitions #
####################

A = {"xs": list(range(50)), "ys": ("o", (6, 7))}
B = {"xs": list(range(10, 60)), "ys": ("x", (7, 6))}
C = {"xs": list(range(10, 110, 2)), "ys": ("ox", (13, 13))}


@pytest.mark.benchmark(group="add")
@with_functions(
    ovld=make_add(ovld_dispatch),
    plum=make_add(plum_dispatch),
    multimethod=make_add(multimethod_dispatch),
    multipledispatch=make_add(multipledispatch_dispatch),
    runtype=make_add(runtype_dispatch),
    custom__isinstance=add_isinstance,
    custom__match=add_match,
)
def test_add(fn, benchmark):
    result = benchmark(fn, A, B)
    assert result == C
