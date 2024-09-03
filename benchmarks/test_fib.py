from typing import Literal

import pytest
from multimethod import multimethod as multimethod_dispatch
from plum import dispatch as plum_dispatch

from ovld import ovld as ovld_dispatch, recurse

########
# ovld #
########


@ovld_dispatch
def fib_ovld(n: Literal[0]):
    return 0


@ovld_dispatch
def fib_ovld(n: Literal[1]):
    return 1


@ovld_dispatch
def fib_ovld(n: int):
    return recurse(n - 1) + recurse(n - 2)


@pytest.mark.benchmark(group="fib")
def test_fib_ovld(benchmark):
    result = benchmark(fib_ovld, 8)
    assert result == 21


########
# plum #
########


@plum_dispatch
def fib_plum(n: Literal[0]):
    return 0


@plum_dispatch
def fib_plum(n: Literal[1]):
    return 1


@plum_dispatch
def fib_plum(n: int):
    return fib_plum(n - 1) + fib_plum(n - 2)


@pytest.mark.benchmark(group="fib")
def test_fib_plum(benchmark):
    result = benchmark(fib_plum, 8)
    assert result == 21


###############
# multimethod #
###############


@multimethod_dispatch
def fib_multimethod(n: Literal[0]):
    return 0


@multimethod_dispatch
def fib_multimethod(n: Literal[1]):
    return 1


@multimethod_dispatch
def fib_multimethod(n: int):
    return fib_multimethod(n - 1) + fib_multimethod(n - 2)


@pytest.mark.benchmark(group="fib")
def test_fib_multimethod(benchmark):
    result = benchmark(fib_multimethod, 8)
    assert result == 21


##########
# normal #
##########


def fib_normal(n):
    if n <= 1:
        return n
    else:
        return fib_normal(n - 1) + fib_normal(n - 2)


@pytest.mark.benchmark(group="fib")
def test_fib_custom(benchmark):
    result = benchmark(fib_normal, 8)
    assert result == 21
