import pytest

from .common import (
    fastcore_dispatch,
    multimethod_dispatch,
    multipledispatch_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
)

###############################
# multiple dispatch libraries #
###############################


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


def make_test(fn):
    @pytest.mark.benchmark(group="add")
    def test(benchmark):
        result = benchmark(fn, A, B)
        assert result == C

    return test


test_add_ovld = make_test(make_add(ovld_dispatch))
test_add_plum = make_test(make_add(plum_dispatch))
test_add_multimethod = make_test(make_add(multimethod_dispatch))
test_add_multipledispatch = make_test(make_add(multipledispatch_dispatch))
test_add_runtype = make_test(make_add(runtype_dispatch))
test_add_fastcore = make_test(make_add(fastcore_dispatch))

test_add_custom_isinstance = make_test(add_isinstance)
test_add_custom_match = make_test(add_match)
