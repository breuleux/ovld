from numbers import Number
from typing import Literal

import pytest

from ovld.core import OvldBase, ovld
from ovld.dependent import (
    Dependent,
    EndsWith,
    Equals,
    HasKey,
    ParametrizedDependentType,
    Regexp,
    StartsWith,
    dependent_check,
)
from ovld.types import HasMethod, Union
from ovld.utils import UsageError


class Bounded(ParametrizedDependentType):
    def default_bound(self, *parameters):
        return type(parameters[0])

    def check(self, value):
        min, max = self.parameters
        return min <= value <= max

    def __lt__(self, other):
        smin, smax = self.parameters
        omin, omax = other.parameters
        return (omin < smin and omax >= smax) or (omin <= smin and omax > smax)


def test_equality():
    assert Equals[0] == Equals[0]
    assert Equals[0] != Equals[1]
    assert Bounded[0, 10] == Bounded[0, 10]


def test_dependent_type():
    @ovld
    def f(x: Equals[0]):
        return "zero"

    @f.register
    def f(x: Equals[1]):
        return "one"

    @f.register
    def f(x: int):
        return "nah"

    assert f(0) == "zero"
    assert f(1) == "one"
    assert f(2) == "nah"


def test_dependent_func():
    @ovld
    def f(x: Dependent[int, lambda x: x >= 0]):
        return "positive"

    @f.register
    def f(x: Dependent[int, lambda x: x < 0]):
        return "negative"

    assert f(0) == "positive"
    assert f(1) == "positive"
    assert f(2) == "positive"
    assert f(-2) == "negative"


def test_dependent_func():
    @dependent_check
    def InBetween(value: Number, min, max):
        return min <= value <= max

    @ovld
    def f(x: InBetween[1, 10]):
        return "A"

    @ovld
    def f(x: Number):
        return "B"

    @f.register
    def f(x):
        return "C"

    assert f(0) == "B"
    assert f(5) == "A"
    assert f("x") == "C"


def test_dependent_method():
    class Candy(OvldBase):
        def __init__(self, n):
            self.n = n

        @ovld
        def f(self, x: Equals[0]):
            return "zero"

        def f(self, x: Equals[1]):
            return "one"

        def f(self, x: int):
            return "nah"

    c = Candy(3)

    assert c.f(0) == "zero"
    assert c.f(1) == "one"
    assert c.f(2) == "nah"


def test_dependent_ambiguity():
    @ovld
    def f(s: Dependent[str, StartsWith["hell"]]):
        return "A"

    @f.register
    def f(s: Dependent[str, EndsWith["ello"]]):
        return "B"

    assert f("hell") == "A"
    with pytest.raises(TypeError, match="Ambiguous resolution"):
        f("hello")


def test_regexp_isinstance():
    assert isinstance("hello", Regexp[r"[ehl]+"])


def test_regexp():
    @ovld
    def f(s: Regexp[r"hell+o"]):
        return "hello"

    @ovld
    def f(s: str):
        return "bye"

    assert f("hello") == "hello"
    assert f("helllllllllo") == "hello"
    assert f("helllllllll") == "bye"
    assert f("oh helllllo there") == "hello"


def test_has_key():
    @ovld
    def f(d: Dependent[dict, HasKey["a"]]):
        return "a"

    @f.register
    def f(d: Dependent[dict, HasKey["b", "c"]]):
        return "b|c"

    @f.register
    def f(d: dict):
        return "other"

    assert f({"a": 1}) == "a"
    assert f({"b": 2}) == "other"
    assert f({"b": 2, "c": 8}) == "b|c"
    with pytest.raises(TypeError):
        f({"a": 9, "b": 2, "c": 8})


def test_has_key_isinstance():
    assert isinstance({"a": 3}, HasKey["a"])
    assert not isinstance({"b": 3}, HasKey["a"])
    assert isinstance({"a": 7, "b": 3}, HasKey["a", "b"])
    assert not isinstance({"b": 3}, HasKey["a", "b"])


def test_dependent_lists():
    HasLen = HasMethod["__len__"]

    @dependent_check
    def Nonempty(x: HasLen):
        return len(x) > 0

    @dependent_check
    def Length(x: HasLen, n):
        return len(x) == n

    @dependent_check
    def MinLength(x: HasLen, n):
        return len(x) >= n

    @ovld
    def f(li: Nonempty):
        return "nonempty"

    @f.register(priority=1)
    def f(li: Length[3]):
        return "three"

    @f.register(priority=1)
    def f(li: MinLength[5]):
        return ">=five"

    @f.register
    def f(li: HasLen):
        return "other"

    assert f([]) == "other"
    assert f([1]) == "nonempty"
    assert f([1, 2, 3]) == "three"
    assert f([1, 2, 3, 4]) == "nonempty"
    assert f([1, 2, 3, 4, 5]) == ">=five"
    assert f([1, 2, 3, 4, 5, 6, 7, 8]) == ">=five"


def test_bounded():
    @ovld
    def f(x: Dependent[Number, Bounded(0, 10)]):
        return "0-10"

    @f.register
    def f(x: Dependent[Number, Bounded(2, 6)]):
        return "2-6"

    assert Bounded(0, 10) > Bounded(2, 6)
    assert f(1) == "0-10"
    assert f(5) == "2-6"


def test_bound():
    @ovld
    def f(x: Dependent[int, lambda x: 1 / 0]):
        return 123

    @ovld
    def f(x):
        return x

    o = object()
    assert f(o) is o


def test_no_type_bound():
    class XXX(ParametrizedDependentType):
        pass

    with pytest.raises(UsageError):

        @ovld
        def f(x: XXX[1, 2, 3]):
            return "123"

        f(123)


def test_vs_catchall():
    @ovld
    def f(x: Dependent[Number, Bounded[0, 10]]):
        return "0-10"

    @f.register
    def f(x):
        return "other"

    assert f(1) == "0-10"
    assert f(25) == "other"
    assert f("zazz") == "other"


def test_or():
    o = Union[Equals[0], Equals[1]]
    assert isinstance(0, o)
    assert isinstance(1, o)
    assert not isinstance(2, o)

    @ovld
    def f(x: o):
        return 2

    assert f(0) == 2
    assert f(1) == 2


def test_or_mix():
    o = Union[str, Equals[0]]

    assert isinstance("x", o)
    assert isinstance(0, o)
    assert not isinstance(1, o)

    @ovld
    def f(x: o):
        return x

    assert f(0) == 0
    assert f("x") == "x"
    with pytest.raises(TypeError):
        f(1)


def test_and():
    a = Bounded[0, 100] & Bounded[-50, 50]
    assert not isinstance(-50, a)
    assert isinstance(1, a)
    assert not isinstance(100, a)

    @ovld
    def f(x: a):
        return "yes"

    @ovld
    def f(x: object):
        return "no"

    assert f(-50) == "no"
    assert f(1) == "yes"
    assert f(100) == "no"


def test_and_with_static_type():
    @ovld
    def f(x: str & Dependent[object, lambda obj: bool(obj)]):  # type: ignore
        return "yes"

    @ovld
    def f(x: object):
        return "no"

    assert f("hello") == "yes"
    assert f("") == "no"
    assert f([1, 2, 3]) == "no"
    assert f(100) == "no"


def test_keyed_plus_other():
    # Tests a failure mode of generating dispatch code like HANDLER = HANDLERS[x]
    # if you also have to check a condition on y.

    for i in range(10):

        @ovld
        def f(x: Literal[i], y: Bounded[0, 100]):
            return "yes"

    @ovld
    def f(x: int, y: int):
        return "no"

    assert f(0, 50) == "yes"
    assert f(3, 50) == "yes"
    assert f(0, 150) == "no"


class Lettered(type):
    def __instancecheck__(cls, x):
        return cls.letter in (getattr(x, "__name__", None) or str(x))


LetterF = Lettered("LetterF", (), {"letter": "f"})
LetterX = Lettered("LetterX", (), {"letter": "x"})


def test_arbitrary_instancecheck():
    @ovld
    def f(x: LetterX):
        return "X-TREME"

    @ovld
    def f(x: LetterF):
        return "fudged"

    @ovld
    def f(x: object):
        return False

    assert f(next) == "X-TREME"
    assert f("wow") is False
    assert f("extreme") == "X-TREME"
    assert f(filter) == "fudged"
