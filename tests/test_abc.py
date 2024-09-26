from typing import Any, Callable, Literal, Mapping, Sequence

import pytest

from ovld.core import Ovld, ovld
from ovld.types import All, Whatever


def test_literal():
    @ovld
    def f(x: Literal[0]):
        return "zero"

    @f.register
    def f(x: Literal[1]):
        return "one"

    @f.register
    def f(x: Literal[2, 3]):
        return "two or three"

    @f.register
    def f(x: object):
        return "nah"

    assert f(0) == "zero"
    assert f(1) == "one"
    assert f(2) == "two or three"
    assert f(3) == "two or three"
    assert f(4) == "nah"


def test_many_literals():
    f = Ovld()

    n = 10

    for i in range(n):

        @ovld
        def f(x: Literal[i]):
            return x * x

    for i in range(n):
        assert f(i) == i * i

    with pytest.raises(TypeError, match="No method"):
        f(-1)

    with pytest.raises(TypeError, match="No method"):
        f(n)


def test_tuples():
    @ovld
    def f(t: tuple[()]):
        return 0

    @ovld
    def f(t: tuple[int]):
        return 1

    @ovld
    def f(t: tuple[str]):
        return 2

    @ovld
    def f(t: tuple[int, str]):
        return 3

    @ovld
    def f(t: tuple[Literal["z"]]):
        return 4

    @ovld
    def f(t: tuple[tuple[tuple[int]]]):
        return 5

    assert f(()) == 0
    assert f((1,)) == 1
    assert f(("x",)) == 2
    assert f((2, "y")) == 3
    assert f(("z",)) == 4
    assert f((((1,),),)) == 5


def test_list():
    @ovld
    def f(li: list[int]):
        return 0

    @ovld
    def f(li: list[str]):
        return 1

    @ovld
    def f(li: Sequence[float]):
        return 2

    assert f([1, 2, 3]) == 0
    assert f(["x", "y"]) == 1
    assert f([1.5, 3.5]) == 2
    with pytest.raises(TypeError):
        f([])


def test_dict():
    @ovld
    def f(d: dict[str, int]):
        return 0

    @ovld
    def f(d: dict[int, list[int]]):
        return 1

    @ovld
    def f(d: Mapping[float, float]):
        return 1

    assert f({"x": 1, "y": 2}) == 0
    assert f({1: [0, 3], 3: [9, 0, 7], 4: []}) == 1
    with pytest.raises(TypeError):
        assert f({1: 3})
    with pytest.raises(TypeError):
        assert f({})


def test_set():
    @ovld
    def f(d: set[str]):
        return 0

    @ovld
    def f(d: set[int]):
        return 1

    assert f({"x", "y"}) == 0
    assert f({1, 7, 4}) == 1
    with pytest.raises(TypeError):
        assert f([1, 2, 3])
    with pytest.raises(TypeError):
        assert f(set())


class Animal:
    pass


class Mammal(Animal):
    pass


class Cat(Mammal):
    pass


def test_callable():
    @ovld
    def f(fn: Callable[[Mammal, Mammal], Mammal]):
        return "MM.M"

    @ovld
    def f(fn: Callable[[Cat], Animal]):
        return "C.A"

    @ovld
    def f(fn: object):
        return None

    #########

    def iscase(n):
        def deco(fn):
            assert f(fn) == n

        return deco

    #########

    @iscase("MM.M")
    def _(x: Mammal, y: Mammal) -> Mammal:
        pass

    @iscase("MM.M")
    def _(x: Animal, y: Animal) -> Cat:
        pass

    @iscase("C.A")
    def _(x: Animal) -> Cat:
        pass

    @iscase(None)
    def _(x: Mammal, y: Mammal, z) -> Mammal:
        pass

    @iscase("MM.M")
    def _(x: Mammal, y: Mammal, z=3) -> Mammal:
        pass

    @iscase(None)
    def _(x: Mammal, y: Mammal, *, z) -> Mammal:
        pass

    @iscase("MM.M")
    def _(x: Mammal, y: Mammal, *, z=3) -> Mammal:
        pass


def test_callable_whatever():
    @ovld
    def f(fn: Callable[[Whatever, Whatever], Whatever]):
        return "yes"

    @ovld
    def f(fn: object):
        return "no"

    #########

    def iscase(n):
        def deco(fn):
            assert f(fn) == n

        return deco

    #########

    @iscase("yes")
    def _(x: Mammal, y: Mammal) -> Mammal:
        pass

    @iscase("yes")
    def _(x: int, y: Cat) -> str:
        pass

    @iscase("no")
    def _(x: int) -> str:
        pass


def test_callable_all():
    @ovld
    def f(fn: Callable[[All, All], Any]):
        return "yes"

    @ovld
    def f(fn: object):
        return "no"

    #########

    def iscase(n):
        def deco(fn):
            assert f(fn) == n

        return deco

    #########

    @iscase("yes")
    def _(x: Mammal, y: Mammal) -> Mammal:
        pass

    @iscase("yes")
    def _(x: int, y: Cat) -> str:
        pass

    @iscase("no")
    def _(x: int) -> str:
        pass
