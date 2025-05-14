from numbers import Number
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
def make_calc(dispatch):
    @dispatch
    def calc(num: Number):
        return num

    @dispatch
    def calc(tup: tuple):
        return calc(*tup)

    @dispatch
    def calc(op: Literal["add"], x: object, y: object):
        return calc(x) + calc(y)

    @dispatch
    def calc(op: Literal["sub"], x: object, y: object):
        return calc(x) - calc(y)

    @dispatch
    def calc(op: Literal["mul"], x: object, y: object):
        return calc(x) * calc(y)

    @dispatch
    def calc(op: Literal["div"], x: object, y: object):
        return calc(x) / calc(y)

    @dispatch
    def calc(op: Literal["pow"], x: object, y: object):
        return calc(x) ** calc(y)

    @dispatch
    def calc(op: Literal["sqrt"], x: object):
        return calc(x) ** 0.5

    return calc


#########
# match #
#########


def calc_match(expr):
    match expr:
        case ("add", x, y):
            return calc_match(x) + calc_match(y)
        case ("sub", x, y):
            return calc_match(x) - calc_match(y)
        case ("mul", x, y):
            return calc_match(x) * calc_match(y)
        case ("div", x, y):
            return calc_match(x) / calc_match(y)
        case ("pow", x, y):
            return calc_match(x) ** calc_match(y)
        case ("sqrt", x):
            return calc_match(x) ** 0.5
        case Number():
            return expr


#########
# dict #
#########


def _add(x, y):
    return calc_dict(x) + calc_dict(y)


def _sub(x, y):
    return calc_dict(x) - calc_dict(y)


def _mul(x, y):
    return calc_dict(x) * calc_dict(y)


def _div(x, y):
    return calc_dict(x) / calc_dict(y)


def _pow(x, y):
    return calc_dict(x) ** calc_dict(y)


def _sqrt(x):
    return calc_dict(x) ** 0.5


ops = {
    "add": _add,
    "sub": _sub,
    "mul": _mul,
    "div": _div,
    "pow": _pow,
    "sqrt": _sqrt,
}


def calc_dict(expr):
    if isinstance(expr, tuple):
        return ops[expr[0]](*expr[1:])
    elif isinstance(expr, Number):
        return expr


####################
# Test definitions #
####################

expr = ("add", ("mul", ("sqrt", 4), 7), ("div", ("add", 6, 4), ("sub", 5, 3)))
expected_result = 19


@pytest.mark.benchmark(group="calc")
@with_functions(
    ovld=make_calc(ovld_dispatch),
    plum=make_calc(plum_dispatch),
    multimethod=make_calc(multimethod_dispatch),
    custom__dict=calc_dict,
    custom__match=calc_match,
)
def test_calc(fn, benchmark):
    result = benchmark(fn, expr)
    assert result == expected_result
