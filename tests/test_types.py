import os
import sys
from dataclasses import dataclass
from typing import Iterable, Union

from ovld import ovld
from ovld.types import (
    Dataclass,
    Deferred,
    Exactly,
    Intersection,
    Order,
    StrictSubclass,
    class_check,
    parametrized_class_check,
    typeorder,
)


@dataclass
class Point:
    x: int
    y: int


def inorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) == Order.MORE
        assert typeorder(b, a) == Order.LESS


def sameorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) is Order.SAME
        assert typeorder(b, a) is Order.SAME


def noorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) is Order.NONE
        assert typeorder(b, a) is Order.NONE


def test_typeorder():
    inorder(object, int)
    inorder(object, Union[int, str], str)
    inorder(object, Dataclass, Point)
    inorder(object, type, type[Dataclass])
    inorder(type[list], type[list[int]])
    inorder(str, Intersection[int, str])
    inorder(object, Intersection[object, int])
    inorder(object, Iterable, Iterable[int], list[int])
    inorder(Iterable[int], list)
    inorder(list, list[int])

    sameorder(int, int)

    noorder(tuple[int, int], tuple[int])
    noorder(dict[str, int], dict[int, str])
    noorder(dict[str, object], dict[object, str])
    noorder(type[int], type[Dataclass])
    noorder(float, int)
    noorder(int, str)
    noorder(int, Dataclass)
    noorder(Union[int, str], float)


def test_meta():
    class Apple:
        pass

    class Banana:
        pass

    class Brownie:
        pass

    class Butterscotch:
        pass

    class Cherry:
        pass

    @class_check
    def B_(cls):
        return cls.__name__.startswith("B")

    @parametrized_class_check
    def ClassPrefix(cls, prefix):
        return cls.__name__.startswith(prefix)

    @ovld
    def f(x):
        return "no B"

    @f.register
    def f(x: Brownie):
        return "Brownie"

    @f.register
    def f(x: B_):
        return "B!"

    @f.register
    def f(x: Butterscotch):
        return "Butterscotch"

    @f.register
    def f(x: ClassPrefix["A"]):
        return "Almost B"

    assert f(Apple()) == "Almost B"
    assert f(Banana()) == "B!"
    assert f(Brownie()) == "Brownie"
    assert f(Butterscotch()) == "Butterscotch"
    assert f(Cherry()) == "no B"


def test_deferred_builtins():
    assert Deferred["builtins.object"] is object
    assert Deferred["builtins.TypeError"] is TypeError


def test_deferred():
    assert "gingerbread" not in sys.modules
    sys.path.append(os.path.join(os.path.dirname(__file__), "modules"))

    @ovld
    def f(x: Deferred["gingerbread.House"]):
        return "Gingerbread house!"

    @f.register
    def f(x):
        return "object"

    assert "gingerbread" not in sys.modules

    import gingerbread

    assert f(gingerbread.House()) == "Gingerbread house!"

    assert "gingerbread" in sys.modules


def test_exactly():
    class Fruit:
        pass

    class Apple(Fruit):
        pass

    assert Exactly[Fruit].__name__ == "Exactly[Fruit]"

    @ovld
    def f(x: Exactly[Fruit]):
        return "yes"

    @f.register
    def f(x: object):
        return "no"

    assert f(Fruit()) == "yes"
    assert f(Apple()) == "no"


def test_strict_subclass():
    class Fruit:
        pass

    class Apple(Fruit):
        pass

    @ovld
    def f(x: StrictSubclass[Fruit]):
        return "yes"

    @f.register
    def f(x: object):
        return "no"

    assert f(Fruit()) == "no"
    assert f(Apple()) == "yes"


def test_Dataclass():
    @ovld
    def f(x: Dataclass):
        return "yes"

    @f.register
    def f(x: object):
        return "no"

    @f.register
    def f(x: type[Dataclass]):
        return "type, yes"

    @f.register
    def f(x: type[object]):
        return "type, no"

    assert f(Point(1, 2)) == "yes"
    assert f(1234) == "no"
    assert f(Point) == "type, yes"
    assert f(int) == "type, no"


def test_intersection():
    class A:
        pass

    class B:
        pass

    class C(A, B):
        pass

    @ovld
    def f(x: A):
        return "A"

    @ovld
    def f(x: B):
        return "B"

    @ovld
    def f(x: Union[A, B]):
        return "A | B"

    @ovld
    def f(x: Intersection[A, B]):
        return "A & B"

    @ovld
    def f(x):
        return "other"

    assert f(A()) == "A"
    assert f(B()) == "B"
    assert f(C()) == "A & B"
    assert f(object()) == "other"
    assert f(1.5) == "other"


def test_intersection_issubclass():
    assert not issubclass(int, Intersection[int, str])
