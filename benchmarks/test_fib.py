from typing import Literal

import pytest

from .common import (
    function_builder,
    multimethod_dispatch,
    ovld_dispatch,
    plum_dispatch,
    with_functions,
)

###############################
# multiple dispatch libraries #
###############################


@function_builder
def make_fib(dispatch):
    @dispatch
    def fib(n: Literal[0]):
        return 0

    @dispatch
    def fib(n: Literal[1]):
        return 1

    @dispatch
    def fib(n: int):
        return fib(n - 1) + fib(n - 2)

    return fib


##########
# normal #
##########


def fib_normal(n):
    if n <= 1:
        return n
    else:
        return fib_normal(n - 1) + fib_normal(n - 2)


####################
# Test definitions #
####################


@pytest.mark.benchmark(group="fib")
@with_functions(
    ovld=make_fib(ovld_dispatch),
    plum=make_fib(plum_dispatch),
    multimethod=make_fib(multimethod_dispatch),
    custom=fib_normal,
)
def test_fib(fn, benchmark):
    result = benchmark(fn, 8)
    assert result == 21
