import sys
from dataclasses import field
from typing import Annotated, Counter

import pytest

from ovld import recurse
from ovld.codegen import Code, Lambda, code_generator
from ovld.medley import CODEGEN, Mixer, meld

# Skip all tests if Python version is less than 3.10
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 10), reason="These tests require Python 3.10 or higher"
)


class Zero(Mixer):
    def do(self, x: object):
        return 0


class Apple(Mixer):
    worms: int = 1

    def do(self, x: int):
        return f"{x * self.worms} worms"


class Banana(Mixer):
    rings: int

    def do(self, x: str):
        return " ".join([f"{x}!"] * self.rings)

    def do(self, x: object):
        return "~fallback~"


class CherryBomb(Mixer):
    red: Annotated[bool, CODEGEN]

    @code_generator
    def do(self, x: str):
        return Lambda(Code("$transform($x)", transform=str.upper if self.red else str.lower))


class Dongle(Mixer):
    def do(self, xs: list):
        return [recurse(x) for x in xs]


class DarkApple(Mixer):
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

    class One(Mixer):
        flag: Annotated[bool, CODEGEN]
        default: object

        @code_generator
        def do(self, x: str):
            gens[One] += 1
            method = str.upper if self.flag else str.lower
            return Lambda(Code("$method($x)", method=method))

        def do(self, x: object):
            return self.default

    class Two(Mixer):
        factor: Annotated[int, CODEGEN]

        @code_generator
        def do(self, x: int):
            gens[Two] += 1
            return Lambda(Code("$x * $factor", factor=self.factor))

    obby = object()

    ot1 = meld([One(True, 51), Two(3)])
    ot2 = meld([One(True, "foo"), Two(3)])
    ot3 = meld([One(False, 51), Two(10)])

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
    class One(Mixer):
        x: int

        def do(self, x: int):
            return x * self.x

        def do(self, x: object):
            return "fallback"

    class Two(Mixer):
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

    class Three(Mixer):
        z: str  # <= should have a default value so that existing code doesn't break

        def do(self, x: str):
            return self.z

    with pytest.raises(TypeError, match="Dataclass field 'z' must have a default value"):
        One += Three

    # Unchanged because the melding failed
    assert onus.do("wow") == "wow!!!!!!"


def test_post_init():
    class One(Mixer):
        x: int

        def __post_init__(self):
            self.xx = self.x * self.x

        def do(self, x: int):
            return x * self.xx

    class Two(Mixer):
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
