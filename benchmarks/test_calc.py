from numbers import Number
from typing import Literal

import pytest
from multimethod import multimethod as multimethod_dispatch
from plum import dispatch as plum_dispatch
from runtype import multidispatch as runtype_dispatch

from ovld import ovld as ovld_dispatch


def make_dispatch(dispatch):
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


expr = ("add", ("mul", ("sqrt", 4), 7), ("div", ("add", 6, 4), ("sub", 5, 3)))
expected_result = 19


@pytest.mark.benchmark(group="calc")
def test_calc_ovld(benchmark):
    calc = make_dispatch(ovld_dispatch)
    result = benchmark(calc, expr)
    assert result == expected_result


@pytest.mark.benchmark(group="calc")
def test_calc_ovld(benchmark):
    calc = make_dispatch(ovld_dispatch)
    result = benchmark(calc, expr)
    assert result == expected_result


@pytest.mark.benchmark(group="calc")
def test_calc_plum(benchmark):
    calc = make_dispatch(plum_dispatch)
    result = benchmark(calc, expr)
    assert result == expected_result


@pytest.mark.benchmark(group="calc")
def test_calc_multimethod(benchmark):
    calc = make_dispatch(multimethod_dispatch)
    result = benchmark(calc, expr)
    assert result == expected_result


@pytest.mark.xfail(reason="runtype has an issue with caching.")
@pytest.mark.benchmark(group="calc")
def test_calc_runtype(benchmark):
    calc = make_dispatch(runtype_dispatch)
    result = benchmark(calc, expr)
    assert result == expected_result


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


@pytest.mark.benchmark(group="calc")
def test_calc_custom_match(benchmark):
    result = benchmark(calc_match, expr)
    assert result == expected_result


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
    elif isinstance(expr, (int, float)):
        return expr


@pytest.mark.benchmark(group="calc")
def test_calc_custom_dict(benchmark):
    result = benchmark(calc_dict, expr)
    assert result == expected_result
