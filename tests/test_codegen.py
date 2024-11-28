import inspect
from dataclasses import dataclass, fields

from ovld import recurse
from ovld.codegen import CodeGen, code_generator
from ovld.core import OvldBase, OvldPerInstanceBase, ovld
from ovld.dependent import Regexp
from ovld.types import Dataclass
from ovld.utils import MISSING


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
        body = [f"{fld.name}=$recurse(x.{fld.name})," for fld in fields(x)]
        return CodeGen(["return $cons(", body, ")"], cons=x, recurse=recurse)

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
            assert self is MISSING
            return CodeGen("return thing + $cls(self.number)", cls=thing)

    plus = Plusser(5)
    assert plus.f(3) == 8
    assert plus.f("wow") == "wow5"

    file_regression.check(getcodes(Plusser.f, int, str))


def test_method_metaclass(file_regression):
    class Plusser(OvldBase):
        def __init__(self, number):
            self.number = number

        @ovld
        @code_generator
        def f(self, thing: object):
            assert self is Plusser
            return CodeGen("return thing + $cls(self.number)", cls=thing)

    plus = Plusser(5)
    assert plus.f(3) == 8
    assert plus.f("wow") == "wow5"

    file_regression.check(getcodes(Plusser.f, int, str))


def test_method_per_instance(file_regression):
    class Plusser(OvldPerInstanceBase):
        def __init__(self, number):
            self.number = number

        @ovld
        @code_generator
        def f(self, thing: object):
            assert isinstance(self, Plusser)
            return CodeGen(
                "return thing + $cls($num)", cls=thing, num=self.number
            )

    plus5 = Plusser(5)
    plus77 = Plusser(77)

    assert type(plus5) is not type(plus77)

    assert plus5.f(3) == 8
    assert plus5.f("wow") == "wow5"

    assert plus77.f(3) == 80
    assert plus77.f("wow") == "wow77"

    assert plus5.f(3) == 8
    assert plus5.f("wow") == "wow5"

    file_regression.check(
        getcodes(type(plus5).f, int, str)
        + SEP
        + getcodes(type(plus77).f, int, str)
    )


def test_variant_generation(file_regression):
    def normal(fn):
        fn.normal = True
        return fn

    @ovld
    @code_generator
    def f(obj: Dataclass):
        lines = ["return $cons("]
        for fld in fields(obj):
            existing = recurse.resolve_for_types(fld.type)
            if getattr(existing, "normal", False):
                expr = f"obj.{fld.name}"
            else:
                expr = f"$recurse(obj.{fld.name})"
            lines.append(f"    {fld.name}={expr},")
        lines.append(")")
        return CodeGen("\n".join(lines), cons=obj, recurse=recurse)

    @ovld
    @normal
    def f(obj: object):
        return obj

    @f.variant
    def g(obj: int):
        return obj + 1

    file_regression.check(getcodes(f, Person) + SEP + getcodes(g, Person))


def test_nogen():
    @ovld
    @code_generator
    def f(x: Dataclass):
        if any(fld.type is not int for fld in fields(x)):
            return None
        body = [f"{fld.name}=$recurse(x.{fld.name})," for fld in fields(x)]
        return CodeGen(["return $cons(", body, ")"], cons=x, recurse=recurse)

    @ovld
    def f(x: int):
        return x + 1

    @ovld
    def f(x: object):
        return False

    assert f(Point(1, 2)) == Point(2, 3)
    assert f(Person("Robert", "Montreal", 21)) is False


def test_dependent_generation():
    @ovld
    @code_generator
    def f(obj: Regexp[r"^A"]):
        return "return 'rx'"

    @ovld
    def f(obj: str):
        return "s"

    assert f("Allo") == "rx"
    assert f("Banana") == "s"


def test_generate_function_directly():
    @ovld
    @code_generator
    def f(x: object):
        xt = x
        return lambda x: (xt, x)

    assert f("coconut") == (str, "coconut")
