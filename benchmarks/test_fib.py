from typing import Literal

import pytest

from .common import (
    multimethod_dispatch,
    ovld_dispatch,
    plum_dispatch,
)

###############################
# multiple dispatch libraries #
###############################


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


def make_test(fn):
    @pytest.mark.benchmark(group="fib")
    def test(benchmark):
        result = benchmark(fn, 8)
        assert result == 21

    return test


test_fib_ovld = make_test(make_fib(ovld_dispatch))
test_fib_plum = make_test(make_fib(plum_dispatch))
test_fib_multimethod = make_test(make_fib(multimethod_dispatch))

test_fib_custom = make_test(fib_normal)
