from typing import Literal

import pytest
from ovld.core import OvldBase, ovld
from ovld.dependent import (
    Dependent,
    Equals,
    Falsey,
    HasKeys,
    Length,
    MinLength,
    Nonempty,
    StartsWith,
    Truey,
)


def test_dependent_type():
    @ovld
    def f(x: Equals(0)):
        return "zero"

    @f.register
    def f(x: Equals(1)):
        return "one"

    @f.register
    def f(x: int):
        return "nah"

    assert f(0) == "zero"
    assert f(1) == "one"
    assert f(2) == "nah"


def test_literal():
    @ovld
    def f(x: Literal[0]):
        return "zero"

    @f.register
    def f(x: Literal[1]):
        return "one"

    @f.register
    def f(x: int):
        return "nah"

    assert f(0) == "zero"
    assert f(1) == "one"
    assert f(2) == "nah"


def test_dependent_method():
    class Candy(OvldBase):
        def __init__(self, n):
            self.n = n

        @ovld
        def f(self, x: Equals(0)):
            return "zero"

        def f(self, x: Equals(1)):
            return "one"

        def f(self, x: int):
            return "nah"

    c = Candy(3)

    assert c.f(0) == "zero"
    assert c.f(1) == "one"
    assert c.f(2) == "nah"


def test_dependent_ambiguity():
    @ovld
    def f(s: Dependent[str, StartsWith("hell")]):
        return "A"

    @f.register
    def f(s: Dependent[str, StartsWith("hello")]):
        return "B"

    assert f("hell") == "A"
    with pytest.raises(TypeError, match="Ambiguous resolution"):
        f("hello")


def test_with_keys():
    @ovld
    def f(d: Dependent[dict, HasKeys("a")]):
        return "a"

    @f.register
    def f(d: Dependent[dict, HasKeys("b", "c")]):
        return "b|c"

    @f.register
    def f(d: dict):
        return "other"

    assert f({"a": 1}) == "a"
    assert f({"b": 2}) == "other"
    assert f({"b": 2, "c": 8}) == "b|c"
    with pytest.raises(TypeError):
        f({"a": 9, "b": 2, "c": 8})


def test_dependent_lists():
    @ovld
    def f(li: Dependent[list, Nonempty]):
        return "nonempty"

    @f.register(priority=1)
    def f(li: Dependent[list, Length(3)]):
        return "three"

    @f.register(priority=1)
    def f(li: Dependent[list, MinLength(5)]):
        return ">=five"

    @f.register
    def f(li: list):
        return "other"

    assert f([]) == "other"
    assert f([1]) == "nonempty"
    assert f([1, 2, 3]) == "three"
    assert f([1, 2, 3, 4]) == "nonempty"
    assert f([1, 2, 3, 4, 5]) == ">=five"
    assert f([1, 2, 3, 4, 5, 6, 7, 8]) == ">=five"


def test_truey_falsey():
    @ovld
    def f(x: Dependent[object, Truey]):
        return "yay"

    @f.register
    def f(x: Dependent[object, Falsey]):
        return "nay"

    @f.register
    def f(x: Dependent[int, Falsey]):
        return "zero"

    @f.register
    def f(x: object):
        return "other"

    assert f(0) == "zero"
    assert f(1) == "yay"
    assert f([]) == "nay"
    assert f({}) == "nay"
    assert f([1]) == "yay"
