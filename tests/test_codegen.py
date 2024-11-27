import inspect
from dataclasses import dataclass, fields

from ovld import recurse
from ovld.codegen import CodeGen, code_generator
from ovld.core import ovld
from ovld.types import Dataclass


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Person:
    name: str
    hometown: str
    age: int


SEP = """
==========
"""


def getcodes(fn, *sigs):
    sigs = [(sig if isinstance(sig, tuple) else (sig,)) for sig in sigs]
    codes = [inspect.getsource(fn.resolve_for_types(*sig)) for sig in sigs]
    return SEP.join(codes)


def test_simple(file_regression):
    @ovld
    @code_generator
    def f(x: object):
        return CodeGen("return $cls", cls=x)

    assert f(int) is type
    assert f(123) is int
    assert f("wow") is str
    assert f(Point(1, 2)) is Point
    assert f("zazz") is str
    assert f(123) is int

    file_regression.check(getcodes(f, type, int, str, Point))


def test_dataclass_gen(file_regression):
    @ovld
    @code_generator
    def f(x: Dataclass):
        lines = ["return $cons("]
        for fld in fields(x):
            lines.append(f"    {fld.name}=$recurse(x.{fld.name}),")
        lines.append(")")
        return CodeGen("\n".join(lines), cons=x, recurse=recurse)

    @ovld
    def f(x: int):
        return x + 1

    @ovld
    def f(x: str):
        return x[1:].capitalize()

    assert f(Point(1, 2)) == Point(2, 3)
    assert f(Person("Robert", "Montreal", 21)) == Person("Obert", "Ontreal", 22)

    file_regression.check(getcodes(f, Point, Person))


def test_method(file_regression):
    class Plusser:
        def __init__(self, number):
            self.number = number

        @ovld
        @code_generator
        def f(self, thing: object):
            return CodeGen("return thing + $cls(self.number)", cls=thing)

    plus = Plusser(5)
    assert plus.f(3) == 8
    assert plus.f("wow") == "wow5"

    file_regression.check(getcodes(Plusser.f, int, str))
