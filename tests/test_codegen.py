import inspect
import sys
from dataclasses import dataclass, fields
from itertools import count

import pytest

from ovld import codegen, recurse
from ovld.codegen import Code, Def, Lambda, code_generator
from ovld.core import OvldBase, ovld
from ovld.dependent import Regexp
from ovld.types import All, Dataclass
from ovld.utils import MISSING, CodegenInProgress


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


def test_code_gensym():
    codegen._current = count()
    co = Code("$=x if $:x else $y", x=Code("f(1, 2, 3)"), y=123)
    assert co.fill() == "x__0 if (x__0 := f(1, 2, 3)) else 123"


def test_code_gensym_simple():
    codegen._current = count()
    obj = object()
    co = Code("$=x if $:x else $y", x=obj, y=123)
    assert co.fill() == "x if x else 123"


def test_rename():
    lbda = Lambda(["x"], "$x + 1")
    expr = lbda(Code("($x * 2)"))

    assert expr.sub(x=123).fill() == "(123 * 2) + 1"


def test_rename_closure():
    lbda = Lambda(["x"], "$x + $y + $z", y=Code("$x", x=5), z=Code("$x"))
    expr = lbda(20)

    assert expr.fill() == "20 + 5 + 20"


def getcodes(fn, *sigs):
    sigs = [(sig if isinstance(sig, tuple) else (sig,)) for sig in sigs]
    codes = [inspect.getsource(fn.resolve(*sig)) for sig in sigs]
    return SEP.join(codes)


def test_simple(file_regression):
    @ovld
    @code_generator
    def f(x: object):
        return Code("return $cls", cls=x)

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
        return Code(["return $cons(", body, ")"], cons=x, recurse=recurse)

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
            return Code("return thing + $cls(self.number)", cls=thing)

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
            return Code("return thing + $cls(self.number)", cls=thing)

    plus = Plusser(5)
    assert plus.f(3) == 8
    assert plus.f("wow") == "wow5"

    file_regression.check(getcodes(Plusser.f, int, str))


def test_variant_generation(file_regression):
    def normal(fn):
        fn.normal = True
        return fn

    @ovld
    @code_generator
    def f(obj: Dataclass):
        lines = ["return $cons("]
        for fld in fields(obj):
            existing = recurse.resolve(fld.type)
            if getattr(existing, "normal", False):
                expr = f"obj.{fld.name}"
            else:
                expr = f"$recurse(obj.{fld.name})"
            lines.append(f"    {fld.name}={expr},")
        lines.append(")")
        return Code("\n".join(lines), cons=obj, recurse=recurse)

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
        return Code(["return $cons(", body, ")"], cons=x, recurse=recurse)

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


@dataclass
class Tree:
    left: "Tree | int"
    right: "Tree | int"


@dataclass
class Point:
    x: int
    y: int


@dataclass
class TwoPoints:
    a: Point
    b: Point


@dataclass
class Empty:
    pass


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10+ for UnionType")
def test_inlining_generator():
    from types import UnionType

    def resolve_subcode(t, f):
        try:
            fn = f.resolve(type[t], All)
            lbda = getattr(fn, "__codegen__", None)
            if lbda:
                return lbda
        except CodegenInProgress:
            pass
        return Lambda(["typ", "x"], Code("$recurse($typ, $x)", recurse=f))

    @ovld
    @code_generator
    def f(typ: type[int], x: int):
        return Lambda(["typ", "x"], "$x + 1")

    @ovld
    @code_generator
    def f(typ: type[UnionType], x: object):
        (typ,) = typ.__args__
        subcodes = [(t, resolve_subcode(t, recurse)) for t in typ.__args__]
        assert len(subcodes) == 2
        return Lambda(
            ["typ", "x"],
            Code(
                "$s1 if isinstance($x, $t1) else $s2",
                s1=subcodes[0][1].code,
                s2=subcodes[1][1].code,
                t1=subcodes[0][0],
            ),
        )

    @ovld
    @code_generator
    def f(typ: type[Dataclass], x: Dataclass):
        if x is not All:
            return recurse.resolve(typ, All)
        (typ,) = typ.__args__
        parts = []
        for field in fields(typ):
            lbda = resolve_subcode(
                eval(field.type) if isinstance(field.type, str) else field.type,
                recurse,
            )
            subcode = lbda(Code("UNUSED"), Code(f"$x.{field.name}"))
            parts.append(subcode)
        code = Code("$cons($[, ]parts)", cons=typ, parts=parts, recurse=recurse)
        return Lambda(["typ", "x"], code)

    assert f(int, 3) == 4
    assert f(Point, Point(7, 8)) == Point(8, 9)
    assert f(Tree, Tree(1, 2)) == Tree(2, 3)
    assert f(TwoPoints, TwoPoints(Point(1, 2), Point(7, 8))) == TwoPoints(
        Point(2, 3), Point(8, 9)
    )
    assert f(Empty, Empty()) == Empty()


def test_scoped_subcodes():
    c = Code([Code("a = $x", x=1234), Code("b = $x + $y", x=4321)], y=666)
    assert c.fill() == "a = 1234\nb = 4321 + 666\n"


def test_lambda():
    df = Lambda(Code("$x + $body"), body=1234)
    assert df.create_body(["x", "y"]).fill() == "return x + 1234"
    assert df.create_expression(["x", "y"]).fill() == "x + 1234"


def test_def():
    df = Def(Code("return $x + $body"), body=1234)
    assert df.create_body(["x", "y"]).fill() == "return x + 1234"
    with pytest.raises(ValueError):
        df.create_expression(["x", "y"])


def test_codegen_priority():
    @ovld
    @code_generator
    def f(x: int):
        return Lambda(..., "'A'")

    @ovld
    @code_generator(priority=1)
    def f(x: object):
        return Lambda(..., "'B'")

    assert f(2) == "B"
