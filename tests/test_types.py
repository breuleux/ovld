import os
import sys
from dataclasses import dataclass

from ovld import ovld
from ovld.types import (
    Dataclass,
    Deferred,
    Exactly,
    HasMethod,
    Intersection,
    Order,
    StrictSubclass,
    Union,
    class_check,
    parametrized_class_check,
    typeorder,
)


@dataclass
class Point:
    x: int
    y: int


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

    assert str(Exactly[Fruit]) == "Exactly[Fruit]"

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


def test_hasmethod():
    assert isinstance([1, 2, 3], HasMethod["__len__"])


def test_intersection_operator():
    class Base:
        def f(self):
            pass

    class X(Base):
        def g(self):
            pass

    class Y(Base):
        def h(self):
            pass

    @ovld
    def f(x: HasMethod["f"] & HasMethod["g"]):  # type: ignore
        return "yes"

    @ovld
    def f(x: Base & HasMethod["h"]):  # type: ignore
        return "yeah"

    @ovld
    def f(x: object):
        return "no"

    assert f(X()) == "yes"
    assert f(Y()) == "yeah"


def test_intersection_issubclass():
    assert not issubclass(int, Intersection[int, str])


def test_intersection_isinstance():
    assert not isinstance(1234, Intersection[int, str])
    assert isinstance(1234, Intersection[int])


def test_intersection_typeorder():
    assert typeorder(Intersection[int, str], str) is Order.LESS
    assert typeorder(str, Intersection[int, str]) is Order.MORE
    assert typeorder(float, Intersection[int, str]) is Order.NONE
    assert typeorder(Intersection[float], Intersection[int, str]) is Order.NONE
    assert typeorder(Intersection[str], Intersection[int, str]) is Order.MORE
    assert typeorder(Intersection, Intersection[int, str]) is Order.MORE


def test_union_issubclass():
    assert issubclass(int, Union[int, str])


def test_union_isinstance():
    assert isinstance(1234, Union[int, str])
    assert not isinstance(1234, Union[float, str])


def test_union_typeorder():
    assert typeorder(Union[int, str], str) is Order.MORE
    assert typeorder(str, Union[int, str]) is Order.LESS
    assert typeorder(float, Union[int, str]) is Order.NONE
    assert typeorder(Union[float], Union[int, str]) is Order.NONE
    assert typeorder(Union[str], Union[int, str]) is Order.LESS
    assert typeorder(Union, Union[int, str]) is Order.MORE
