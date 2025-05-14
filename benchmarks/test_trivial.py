from numbers import Number

import pytest

from .common import (
    function_builder,
    multimethod_dispatch,
    multipledispatch_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
    singledispatch_dispatch,
    with_functions,
)


class Animal:
    pass


class Mammal(Animal):
    pass


class Cat(Mammal):
    pass


class Dog(Mammal):
    pass


class Bird(Animal):
    pass


###############################
# multiple dispatch libraries #
###############################


@function_builder
def make_trivial(dispatch):
    @dispatch
    def trivial(x: Number):
        return "A"

    @dispatch
    def trivial(x: str):
        return "B"

    @dispatch
    def trivial(x: dict):
        return "C"

    @dispatch
    def trivial(x: list):
        return "D"

    @dispatch
    def trivial(x: Cat):
        return "E"

    @dispatch
    def trivial(x: Mammal):
        return "F"

    @dispatch
    def trivial(x: Animal):
        return "G"

    return trivial


##############
# isinstance #
##############


def trivial_isinstance(x):
    if isinstance(x, int | float):
        return "A"
    if isinstance(x, str):
        return "B"
    if isinstance(x, dict):
        return "C"
    if isinstance(x, list):
        return "D"
    if isinstance(x, Cat):
        return "E"
    if isinstance(x, Mammal):
        return "F"
    if isinstance(x, Animal):
        return "G"


####################
# Test definitions #
####################


@pytest.mark.benchmark(group="trivial")
@with_functions(
    ovld=make_trivial(ovld_dispatch),
    plum=make_trivial(plum_dispatch),
    multimethod=make_trivial(multimethod_dispatch),
    multipledispatch=make_trivial(multipledispatch_dispatch),
    runtype=make_trivial(runtype_dispatch),
    singledispatch=make_trivial(singledispatch_dispatch),
    custom__isinstance=trivial_isinstance,
)
def test_trivial(fn, benchmark):
    def run():
        return [
            fn(1),
            fn(3.5),
            fn("hello"),
            fn({}),
            fn([1, 2]),
            fn(Cat()),
            fn(Dog()),
            fn(Bird()),
        ]

    result = benchmark(run)
    assert result == list("AABCDEFG")
