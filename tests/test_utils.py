import os
import sys
from dataclasses import dataclass

import pytest
from ovld import (
    call_next,
    ovld,
    recurse,
)
from ovld.utils import (
    Dataclass,
    Deferred,
    Exactly,
    StrictSubclass,
    UsageError,
    class_check,
    parametrized_class_check,
)


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
    @dataclass
    class Point:
        x: int
        y: int

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


def test_unusable():
    with pytest.raises(
        UsageError, match="recurse.. can only be used from inside an @ovld"
    ):
        recurse()

    with pytest.raises(
        UsageError, match="call_next.. can only be used from inside an @ovld"
    ):
        call_next()

    with pytest.raises(
        UsageError, match="recurse.. can only be used from inside an @ovld"
    ):
        recurse.next
