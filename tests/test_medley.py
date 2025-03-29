from typing import Annotated, Counter

import pytest

from ovld import recurse
from ovld.codegen import Code, Lambda, code_generator
from ovld.medley import CODEGEN, Mixer, meld


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
