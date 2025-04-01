import sys
from dataclasses import field, replace
from typing import Counter

import pytest

from ovld import recurse
from ovld.codegen import Code, Lambda, code_generator
from ovld.core import ovld
from ovld.medley import CodegenParameter, Medley, meld

# Skip all tests if Python version is less than 3.10
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10), reason="These tests require Python 3.10 or higher"
)


class Zero(Medley):
    def do(self, x: object):
        return 0


class Apple(Medley):
    worms: int = 1

    def do(self, x: int):
        return f"{x * self.worms} worms"


class Banana(Medley):
    rings: int

    def do(self, x: str):
        return " ".join([f"{x}!"] * self.rings)

    def do(self, x: object):
        return "~fallback~"


class CherryBomb(Medley):
    red: CodegenParameter[bool]

    @code_generator
    def do(self, x: str):
        return Lambda(Code("$transform($x)", transform=str.upper if self.red else str.lower))


class Dongle(Medley):
    def do(self, xs: list):
        return [recurse(x) for x in xs]


class DarkApple(Medley):
    worms: str = "worms"

    def do(self, x: int):
        return f"{x} {self.worms}"


def test_simple_mixin():
    a = Apple(worms=5)
    assert a.do(10) == "50 worms"
    with pytest.raises(TypeError, match="No method in <Ovld"):
        a.do("wat")


def test_simple_mixin_2():
    b = Banana(rings=3)
    assert b.do("ring") == "ring! ring! ring!"
    assert b.do(10) == "~fallback~"


def test_codegen():
    bt = CherryBomb(red=True)
    bf = CherryBomb(red=False)

    assert bt.do("Wow") == "WOW"
    assert bf.do("Wow") == "wow"


def test_meld():
    ab = meld([Apple(5), Banana(3)])
    assert ab.worms == 5
    assert ab.rings == 3
    assert ab.do(10) == "50 worms"
    assert ab.do("ring") == "ring! ring! ring!"


def test_recurse():
    ab = meld([Apple(5), Banana(3), Dongle()])
    assert ab.do([10, "ring"]) == ["50 worms", "ring! ring! ring!"]


def test_recurse_codegen():
    ab = meld([Apple(5), CherryBomb(True), Dongle()])
    assert ab.do([10, "ring"]) == ["50 worms", "RING"]


def test_meld_operator():
    ab = Apple(5) + Banana(3) + Dongle()
    assert ab.do([10, "ring"]) == ["50 worms", "ring! ring! ring!"]


def test_codegen_reuse():
    gens = Counter()

    class One(Medley):
        flag: CodegenParameter[bool]
        default: object

        @code_generator
        def do(self, x: str):
            gens[One] += 1
            method = str.upper if self.flag else str.lower
            return Lambda(Code("$method($x)", method=method))

        def do(self, x: object):
            return self.default

    class Two(Medley):
        factor: CodegenParameter[int]

        @code_generator
        def do(self, x: int):
            gens[Two] += 1
            return Lambda(Code("$x * $factor", factor=self.factor))

    obby = object()

    ot1 = meld([One(True, 51), Two(3)])
    ot2 = meld([One(True, "foo"), Two(3)])
    ot3 = meld([One(False, 51), Two(10)])

    assert type(ot1) is type(ot2)
    assert type(ot1) is not type(ot3)

    assert gens[One] == 0
    assert gens[Two] == 0

    assert ot1.do("Hello") == "HELLO"
    assert ot1.do("boop") == "BOOP"
    assert ot1.do(18) == 54
    assert ot1.do(obby) == 51

    assert gens[One] == 1
    assert gens[Two] == 1

    assert ot2.do("Hello") == "HELLO"
    assert ot2.do(18) == 54
    assert ot2.do(obby) == "foo"

    assert gens[One] == 1
    assert gens[Two] == 1

    assert ot3.do("Hello") == "hello"
    assert ot3.do(18) == 180
    assert ot3.do(obby) == 51

    assert gens[One] == 2
    assert gens[Two] == 2


def test_conflict():
    with pytest.raises(TypeError):
        meld([Apple(3), DarkApple(3)])


def test_meld_classes():
    Abba = Apple + Banana
    ab = Abba(worms=5, rings=3)
    assert ab.worms == 5
    assert ab.rings == 3
    assert ab.do(10) == "50 worms"
    assert ab.do("ring") == "ring! ring! ring!"


def test_meld_inplace():
    class One(Medley):
        x: int

        def do(self, x: int):
            return x * self.x

        def do(self, x: object):
            return "fallback"

    class Two(Medley):
        y: str = field(default="?")

        def do(self, x: str):
            return x + self.y

    before = One(x=5)
    assert before.do(10) == 50
    assert before.do("wow") == "fallback"

    One += Two

    # Existing instance should work with the new behavior and the defaults
    assert before.do("wow") == "wow?"

    # New instances can be created with the new fields
    onus = One(x=4, y="!!!!!!")
    assert onus.do(10) == 40
    assert onus.do("wow") == "wow!!!!!!"

    class Three(Medley):
        z: str  # <= should have a default value so that existing code doesn't break

        def do(self, x: str):
            return self.z

    with pytest.raises(TypeError, match="Dataclass field 'z' must have a default value"):
        One += Three

    # Unchanged because the melding failed
    assert onus.do("wow") == "wow!!!!!!"


def test_post_init():
    class One(Medley):
        x: int

        def __post_init__(self):
            self.xx = self.x * self.x

        def do(self, x: int):
            return x * self.xx

    class Two(Medley):
        y: int

        def __post_init__(self):
            self.yy = self.y + self.y

        def do(self, x: str):
            return x + self.yy

    ot = One(3) + Two("v")
    assert ot.xx == 9
    assert ot.yy == "vv"
    assert ot.do(10) == 90
    assert ot.do("z") == "zvv"

    otc = One + Two
    ot2 = otc(x=3, y="v")
    assert ot2.xx == 9
    assert ot2.yy == "vv"
    assert ot2.do(10) == 90
    assert ot2.do("z") == "zvv"


def test_medley_isinstance():
    assert issubclass(Apple + Banana, Apple)
    assert isinstance(Apple(10) + Banana(7), Banana)


def test_medley_replace():
    ab = Apple(10) + Banana(7)
    assert ab.do(8) == "80 worms"

    ab2 = replace(ab, worms=100)
    assert ab2.do(8) == "800 worms"


def test_medley_replace_codegen():
    cb = CherryBomb(red=True)
    assert cb.red
    assert cb.do("Hello") == "HELLO"
    cb2 = replace(cb, red=False)
    assert not cb2.red
    assert cb2.do("Hello") == "hello"


def test_add_same_type():
    aa = Apple(10) + Apple(20)
    assert aa.do(8) == "160 worms"


def test_subtract():
    a = Apple(10)
    b = Banana(20)
    ab = a + b
    assert ab.worms == 10
    assert ab.rings == 20

    a2 = ab - Banana
    assert a2.worms == 10
    assert isinstance(a2, Apple)
    assert not isinstance(a2, Banana)
    assert not hasattr(a2, "rings")

    b2 = ab - Apple
    assert b2.rings == 20
    assert not isinstance(b2, Apple)
    assert isinstance(b2, Banana)
    assert not hasattr(b2, "worms")

    b3 = ab - Apple - Banana
    assert not hasattr(b3, "rings")
    assert not hasattr(b3, "worms")

    with pytest.raises(TypeError, match="unexpected keyword argument 'worms'"):
        ((Apple + Banana) - Apple)(worms=10, rings=20)

    with pytest.raises(TypeError, match="unexpected keyword argument 'rings'"):
        ((Apple + Banana) - Banana)(worms=10, rings=20)


def test_init_not_allowed():
    with pytest.raises(Exception, match="Do not define __init__"):

        class Grapes(Medley):
            def __init__(self, z: int, w=0):
                self.z = z
                self.w = w

            def do(self, x: int):
                return x + self.z + self.w


def test_inheritance():
    class Flapjack(Medley):
        def do(self, x: int):
            return x + 1

    class Cake(Flapjack):
        def do(self, x: str):
            return x + "s"

    assert Cake().do("egg") == "eggs"
    assert Cake().do(6) == 7


def test_priority():
    class Habanero(Medley):
        def do(self, x: int):
            return "A"

        @ovld(priority=1000)
        def do(self, x: int):
            return "B"

        def do(self, x: int):
            return "C"

    assert Habanero().do(3) == "B"
