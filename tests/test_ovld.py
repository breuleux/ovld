import sys
import typing

import pytest
from ovld import Ovld, OvldBase, OvldCall, OvldMC, extend_super, is_ovld, ovld
from ovld.utils import MISSING

from .test_typemap import Animal, Bird, Mammal


def test_Ovld():
    o = Ovld()

    @o.register
    def f(x: int):
        """Integers!"""
        return "int"

    @o.register  # noqa: F811
    def f(x: float):
        """Floats!"""
        return "float"

    assert is_ovld(o)

    assert f(2) == "int"
    assert f(2.0) == "float"

    with pytest.raises(TypeError):
        f(object())

    with pytest.raises(TypeError):
        f()


def test_nargs():
    o = Ovld()

    @o.register
    def f():
        return 0

    @o.register
    def f(x: int):
        return 1

    @o.register
    def f(x: int, y: int):
        return 2

    @o.register
    def f(x: int, y: int, z: int):
        return 3

    assert f() == 0
    assert f(0) == 1
    assert f(0, 0) == 2
    assert f(0, 0, 0) == 3


def test_getitem():
    o = Ovld(name="f")

    @o.register
    def f(x: int):
        return "int"

    @o.register  # noqa: F811
    def f(x: float):
        return "float"

    assert f[int].__name__ == "f[int]"
    assert f[float].__name__ == "f[float]"


def test_bootstrap_getitem():
    o = Ovld(name="f")

    @o.register
    def f(self, x: int):
        return self[float]

    @o.register  # noqa: F811
    def f(self, x: float):
        return self[int]

    assert "f[int]" in str(f(1.0))
    assert "f[float]" in str(f(111))


def test_multimethod():
    o = Ovld()

    @o.register
    def f(x: object, y: object):
        return "oo"

    @o.register
    def f(x: int, y):
        return "io"

    @o.register
    def f(x, y: int):
        return "oi"

    @o.register
    def f(x: str, y: str):
        return "ss"

    assert f(1.0, 1.0) == "oo"

    assert f(1, object()) == "io"
    assert f(1, "x") == "io"

    assert f("x", 1) == "oi"
    assert f(object(), 1) == "oi"

    assert f("a", "b") == "ss"

    with pytest.raises(TypeError):
        # Ambiguous
        f(1, 2)

    @o.register
    def f(x: int, y: int):
        return "ii"

    assert f(1, 2) == "ii"


def test_redefine():
    o = Ovld()

    @o.register
    def f(x: int):
        return x + x

    assert f(10) == 20

    @o.register
    def f(x: int):
        return x * x

    assert f(10) == 100


def test_redefine_2():
    o = Ovld()

    @o.register
    def f(x: Animal):
        return "animal"

    assert f(Bird()) == "animal"
    assert f(Mammal()) == "animal"

    @o.register
    def f(x: Mammal):
        return "mammal"

    assert f(Bird()) == "animal"
    assert f(Mammal()) == "mammal"


def test_redefine_parent():
    o = Ovld(bootstrap=False)
    o2 = o.copy()

    @o.register
    def f(x: Animal):
        return "animal"

    @o2.register
    def f2(x: Bird):
        return "a bird"

    assert f(Bird()) == "animal"
    assert f(Mammal()) == "animal"

    @o.register
    def f(x: Mammal):
        return "mammal"

    assert f2(Bird()) == "a bird"
    assert f2(Mammal()) == "mammal"

    with pytest.raises(Exception):

        @o.register
        def f(x: Bird):
            return "b bird"


def test_redefine_parent_with_linkback():
    o = Ovld(bootstrap=False)
    o2 = o.copy(linkback=True)

    @o.register
    def f(x: Animal):
        return "animal"

    @o2.register
    def f2(x: Bird):
        return "a bird"

    assert f(Bird()) == "animal"
    assert f(Mammal()) == "animal"

    @o.register
    def f(x: Mammal):
        return "mammal"

    assert f2(Bird()) == "a bird"
    assert f2(Mammal()) == "mammal"

    @o.register
    def f(x: Bird):
        return "b bird"

    assert f(Bird()) == "b bird"
    assert f2(Bird()) == "a bird"


def test_typetuple():
    o = Ovld()

    @o.register
    def f(x, y):
        return "oo"

    @o.register
    def f(x: (int, float), y):
        return "io"

    @o.register
    def f(x, y: (int, float)):
        return "oi"

    @o.register
    def f(x: (int, float), y: (int, float)):
        return "ii"

    assert f(1, 1) == "ii"
    assert f(1.0, 1.0) == "ii"

    assert f(1, "x") == "io"
    assert f("x", 1) == "oi"


def test_typetuple_override():
    o = Ovld()

    @o.register
    def f(x: (int, float)):
        return "if"

    @o.register
    def f(x: int):
        return "i"

    assert f(1) == "i"
    assert f(1.0) == "if"


def test_union():
    o = Ovld()

    @o.register
    def f(x, y):
        return "oo"

    @o.register
    def f(x: typing.Union[int, float], y):
        return "io"

    @o.register
    def f(x, y: typing.Union[int, float]):
        return "oi"

    @o.register
    def f(x: typing.Union[int, float], y: typing.Union[int, float]):
        return "ii"

    assert f(1, 1) == "ii"
    assert f(1.0, 1.0) == "ii"

    assert f(1, "x") == "io"
    assert f("x", 1) == "oi"


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="union syntax requires python3.10 or higher",
)
def test_union_pipe_syntax():
    o = Ovld()

    @o.register
    def f(x, y):
        return "oo"

    @o.register
    def f(x: int | float, y):
        return "io"

    @o.register
    def f(x, y: int | float):
        return "oi"

    @o.register
    def f(x: int | float, y: int | float):
        return "ii"

    assert f(1, 1) == "ii"
    assert f(1.0, 1.0) == "ii"

    assert f(1, "x") == "io"
    assert f("x", 1) == "oi"


def test_optional():
    o = Ovld()

    @o.register
    def f(x: typing.Optional[int]):
        return "iN"

    @o.register
    def f(x: float):
        return "f"

    @o.register
    def f(x: object):
        return "o"

    assert f(1) == "iN"
    assert f(None) == "iN"
    assert f(1.0) == "f"


def test_no_generics():
    o = Ovld()

    with pytest.raises(TypeError):

        @o.register
        def f(x: typing.List[int]):
            return "hmm"


@pytest.mark.skipif(
    sys.version_info < (3, 7),
    reason="subclasscheck on Iterable seems to require python3.7 or higher",
)
def test_abstract_types():
    from collections.abc import Iterable

    o = Ovld()

    @o.register
    def f(x: object):
        return "o"

    @o.register
    def f(xs: Iterable):
        return type(xs)(f(x) for x in xs)

    assert f(1) == "o"
    assert f([1, 2, 3]) == ["o", "o", "o"]
    assert f((1, [2, 3])) == ("o", ["o", "o"])


def test_varargs():
    o = Ovld()

    @o.register
    def f(*args):
        return "A"

    @o.register
    def f(x: int, *args):
        return "B"

    @o.register
    def f(x: int, y: int, *args):
        return "C"

    assert f() == "A"
    assert f("X") == "A"

    assert f(1) == "B"
    assert f(1, "x", "y") == "B"

    assert f(1, 2) == "C"
    assert f(1, 2, 3) == "C"


def test_default_args():
    o = Ovld()

    @o.register
    def f(x: int):
        return "A"

    @o.register
    def f(x: str, y: int = 3):
        return y

    @o.register
    def f(x: float, y=7):
        return x + y

    assert f(1) == "A"
    assert f("X") == 3
    assert f("X", 24) == 24
    with pytest.raises(TypeError):
        f("X", "Y")

    assert f(3.7) == 10.7


def test_mixins():
    f = Ovld()

    @f.register
    def f(t: int):
        return t + 1

    g = Ovld()

    @g.register
    def g(t: str):
        return t.upper()

    h = Ovld(mixins=[f, g])

    assert f(15) == 16
    with pytest.raises(TypeError):
        f("hello")

    assert g("hello") == "HELLO"
    with pytest.raises(TypeError):
        g(15)

    assert h(15) == 16
    assert h("hello") == "HELLO"


def test_bootstrap():
    f = Ovld()

    @f.register
    def f(self, xs: list):
        return [self(x) for x in xs]

    @f.register
    def f(self, x: int):
        return x + 1

    with pytest.raises(TypeError):

        @f.register
        def f(x: object):
            return "missing self!"

    @f.register
    def f(self, x: object):
        return "A"

    assert f([1, 2, "xxx", [3, 4]]) == [2, 3, "A", [4, 5]]

    @f.variant
    def g(self, x: object):
        return "B"

    # This does not interfere with f
    assert f([1, 2, "xxx", [3, 4]]) == [2, 3, "A", [4, 5]]

    # The new method in g is used
    assert g([1, 2, "xxx", [3, 4]]) == [2, 3, "B", [4, 5]]

    @f.variant(postprocess=lambda self, x: {"result": x})
    def h(self, x: object):
        return "C"

    # Only the end result is postprocessed
    assert h([1, 2, "xxx", [3, 4]]) == {"result": [2, 3, "C", [4, 5]]}

    @h.variant
    def i(self, x: object):
        return "D"

    # Postprocessor is kept
    assert i([1, 2, "xxx", [3, 4]]) == {"result": [2, 3, "D", [4, 5]]}


class CustomCall(OvldCall):
    def inc(self, x):
        return x + 1


def test_bootstrap_custom_ovcall():
    f = Ovld(bootstrap=CustomCall)

    @f.register
    def f(self, xs: list):
        return [self(x) for x in xs]

    @f.register
    def f(self, x: int):
        return self.inc(x)

    assert f([1, 2, 3]) == [2, 3, 4]


def test_Ovld_dispatch():
    f = Ovld()

    @f.dispatch
    def f(self, x):
        f1 = self.resolve(x, x)
        f2 = self[type(x), type(x)]
        assert f1 == f2
        return f1(x, x)

    with pytest.raises(TypeError):

        @f.dispatch
        def f(self, x):
            return self.map[(type(x), type(x))](x, x)

    @f.register
    def f(x: int, y: int):
        return x + y

    @f.register
    def f(xs: tuple, ys: tuple):
        return tuple(f(x) for x in xs)

    assert f(1) == 2
    assert f((4, 5)) == (8, 10)


def test_Ovld_dispatch_bootstrap():
    f = Ovld()

    @f.dispatch
    def f(self, x):
        f1 = self.resolve(x, x)
        f2 = self[type(x), type(x)]
        assert f1 == f2
        return f1(x, x)

    @f.register
    def f(self, x: int, y: int):
        return x + y

    @f.register
    def f(self, xs: tuple, ys: tuple):
        return tuple(self(x) for x in xs)

    assert f(1) == 2
    assert f((4, 5)) == (8, 10)


def test_stateful():
    f = Ovld(initial_state=lambda: {"state": -1})

    @f.dispatch
    def f(self, x):
        fn = self.resolve(x)
        self.state += 1
        return fn(x)

    @f.register
    def f(self, x: type(None)):
        return self.state

    @f.register
    def f(self, xs: tuple):
        return tuple(self(x) for x in xs)

    assert f((None, None)) == (1, 2)
    assert f((None, (None, None))) == (1, (3, 4))
    assert f((None, (None, None))) == (1, (3, 4))

    @f.variant
    def g(self, x: type(None)):
        return self.state * 10

    assert g((None, None)) == (10, 20)
    assert g((None, (None, None))) == (10, (30, 40))
    assert g((None, (None, None))) == (10, (30, 40))

    @f.variant(initial_state=lambda: {"state": 0})
    def h(self, x: type(None)):
        return self.state * 100

    assert h((None, None)) == (200, 300)
    assert h((None, (None, None))) == (200, (400, 500))
    assert h((None, (None, None))) == (200, (400, 500))


def test_with_state():
    f = Ovld(initial_state=lambda: {"state": 0})

    @f.register
    def f(self, x):
        return self.state

    @f.register
    def f(self, xs: (list, tuple)):
        self2 = self.with_state(state=self.state + 1)
        return type(xs)(self2(x) for x in xs)

    assert f((0, 0, [[[0]], 0])) == (1, 1, [[[4]], 2])


def test_instantiate():
    f = Ovld()

    @f.register
    def f(self, x):
        return self.state

    @f.register
    def f(self, xs: (list, tuple)):
        self2 = self.with_state(state=self.state + 1)
        return type(xs)(self2(x) for x in xs)

    ff = f.instantiate(state=0)
    assert ff((0, 0, [[[0]], 0])) == (1, 1, [[[4]], 2])

    ff = f.instantiate(state=1)
    assert ff((0, 0, [[[0]], 0])) == (2, 2, [[[5]], 3])


def test_method():
    class Greatifier:
        def __init__(self, n):
            self.n = n

        perform = Ovld()

        @perform.register
        def perform(self, x: int):
            return x + self.n

        @perform.register
        def perform(self, x: str):
            return x + "s" * self.n

    g = Greatifier(2)
    assert g.perform(7) == 9
    assert g.perform("cheese") == "cheesess"

    with pytest.raises(TypeError):
        assert Greatifier.perform(g, "cheese") == "cheesess"


def test_metaclass():
    class Greatifier(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

        def perform(self, x: int):
            return x + self.n

        def perform(self, x: str):
            return x + "s" * self.n

        def perform(self, x: object):
            return x

    g = Greatifier(2)
    assert g.perform(7) == 9
    assert g.perform("cheese") == "cheesess"
    assert g.perform(g) is g

    with pytest.raises(TypeError):
        assert Greatifier.perform(g, "cheese") == "cheesess"


def test_metaclass_inherit():
    class Greatifier(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

        def perform(self, x: int):
            return x + self.n

    class Greatestifier(Greatifier):
        @extend_super
        def perform(self, x: str):
            return x + "s" * self.n

        def perform(self, x: object):
            return x

    g = Greatifier(2)
    assert g.perform(7) == 9
    with pytest.raises(TypeError):
        g.perform("cheese")

    gg = Greatestifier(2)
    assert gg.perform(7) == 9
    assert gg.perform("cheese") == "cheesess"


def test_metaclass_multiple_inherit():
    class One(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

    class Two(One):
        @extend_super
        def perform(self, x: int):
            return x + self.n

        def perform(self, x: float):
            return x * self.n

    class Three(One):
        @extend_super
        def perform(self, x: str):
            return x + "s" * self.n

    class Four(Two, Three):
        pass

    g = Four(2)
    assert g.perform(7) == 9
    assert g.perform(7.0) == 14
    assert g.perform("cheese") == "cheesess"

    with pytest.raises(TypeError):
        Two(2).perform("cheese")

    with pytest.raises(TypeError):
        Three(2).perform(7)


def test_multiple_inherit_2():
    class One(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

        def perform(self, x: int):
            return x + self.n

    class M1:
        @extend_super
        def perform(self, x: float):
            return x * self.n

    class M2:
        @extend_super
        def perform(self, x: str):
            return x + "s" * self.n

    cls = One.create_subclass(M1, M2, name="Test")

    g = cls(2)
    assert g.perform(7) == 9
    assert g.perform(7.0) == 14
    assert g.perform("cheese") == "cheesess"


def test_metaclass_dispatch():
    class One(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

        @ovld.dispatch
        def perform(ovld_call, x):
            return ovld_call.call(x) * 2

        def perform(self, x: int):
            return x + self.n

        def perform(self, xs: list):
            return [self.perform(x) for x in xs]

    x = One(1)
    assert x.perform([1, 2, 3]) == [4, 6, 8, 4, 6, 8]

    class Two(One):
        @extend_super
        def perform(self, x: float):
            return x * self.n

    x2 = Two(2)
    assert x2.perform([1, 2, 3]) == [6, 8, 10, 6, 8, 10]
    assert x2.perform([1.5, 2.5]) == [6.0, 10.0, 6.0, 10.0]


def test_metaclass_dispatch_2():
    class One(metaclass=OvldMC):
        def __init__(self, n):
            self.n = n

        @ovld.dispatch
        def perform(ovld_call, x):
            return ovld_call.call(x)

        def perform(self, x: int):
            return x + self.n

        def perform(self, xs: list):
            return [self.perform(x) for x in xs]

    x = One(1)
    assert x.perform([1, 2, 3]) == [2, 3, 4]

    class Two(One):
        @extend_super
        @ovld.dispatch
        def perform(ovld_call, x):
            return ovld_call.call(x) * 2

    x2 = Two(1)
    assert x2.perform([1, 2, 3]) == [4, 6, 8, 4, 6, 8]


def test_multiple_dispatch_3():
    class One(OvldBase):
        def __init__(self, n):
            self.n = n

        @ovld.dispatch
        def perform(ovld_call, x):
            return ovld_call.call(x) * 2

        def perform(self, xs: list):
            return [self.perform(x) for x in xs]

    class M1:
        @extend_super
        def perform(self, x: int):
            return x + self.n

    class M2(OvldBase):
        @extend_super
        def perform(self, x: float):
            return x * self.n

        def perform(self, x: str):
            return x + "s" * self.n

    cls = One.create_subclass(M1, M2, name="Test")

    g = cls(2)
    assert g.perform(7) == 18
    assert g.perform(7.0) == 28
    assert g.perform("cheese") == "cheesesscheesess"
    assert g.perform([1, 2.0]) == [6, 8.0, 6, 8.0]


def test_error():
    o = Ovld(type_error=FileNotFoundError)

    @o.register
    def f(x: int, y: int):
        return x + y

    with pytest.raises(FileNotFoundError):
        o("hello")


def test_repr():
    humptydumpty = Ovld()

    @humptydumpty.register
    def humptydumpty(x: int):
        return x

    @humptydumpty.register
    def ignore_this_name(x: str):
        return x

    assert humptydumpty.name.endswith(".humptydumpty")
    r = repr(humptydumpty)
    assert r.startswith("<Ovld ")
    assert r.endswith(".humptydumpty>")


def test_repr_misc():
    assert repr(MISSING) == "MISSING"


def test_bizarre_bug():
    # Don't ask

    class A:
        pass

    class B(A, metaclass=OvldMC):
        pass

    assert not isinstance(B(), type)


def test_custom_mapper():
    class StringPrefixMap:
        def __init__(self, key_error):
            self.key_error = key_error
            self.transform = lambda x: x
            self.members = {}

        def register(self, tup, nargs, handler):
            (pfx,) = tup
            self.members[pfx] = handler

        def __getitem__(self, key):
            (key,) = key
            for pfx, h in self.members.items():
                if key.startswith(pfx):
                    return h
            raise self.key_error(key)

    @ovld(mapper=StringPrefixMap)
    def f(x: "A"):
        return x.lower()

    @f.register
    def f(x: "Ba"):
        return x * 2

    assert f("ApplE") == "apple"
    assert f("Banana") == "BananaBanana"
    with pytest.raises(TypeError):
        f("Brains")


def test_replacement():
    @ovld
    def f(x: int):
        return 1

    @f.register
    def f2(x: int):
        return 2

    assert f(5) == 2


def test_disallow_replacement():
    @ovld(allow_replacement=False)
    def f(x: int):
        pass

    with pytest.raises(TypeError):

        @f.register
        def f2(x: int):
            pass


def test_super():
    @ovld
    def f(self, xs: list):
        return [self(x) for x in xs]

    @f.register
    def f(self, x: int):
        return x * x

    @f.variant
    def f2(self, x: int):
        return 0 if x < 0 else self.super(x)

    @f2.variant
    def f3(self, xs: list):
        return ["=>", *self.super(xs)]

    @f3.register
    def f3(self, x: int):
        return x

    assert f3([-2, -1, 0, 1, 2, 3]) == ["=>", -2, -1, 0, 1, 2, 3]
    assert f2([-2, -1, 0, 1, 2, 3]) == [0, 0, 0, 1, 4, 9]
    assert f([-2, -1, 0, 1, 2, 3]) == [4, 1, 0, 1, 4, 9]


def test_unregister():
    @ovld
    def f(self, xs: list):
        return [self(x) for x in xs]

    def intf(self, x: int):
        return x * x

    f.register(intf)
    assert f([-2, -1, 0, 1, 2, 3]) == [4, 1, 0, 1, 4, 9]
    f.unregister(intf)

    with pytest.raises(TypeError):
        f([-2, -1, 0, 1, 2, 3])


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_conform():
    @ovld
    def f(xs: list):
        return [f(x) for x in xs]

    def intf(x: int):
        return x * x

    def intf2(x: int):
        return x * x if x > 0 else 0

    f.register(intf)
    assert f([-2, -1, 0, 1, 2, 3]) == [4, 1, 0, 1, 4, 9]

    f[int]._conformer.__conform__(intf2)
    assert f([-2, -1, 0, 1, 2, 3]) == [0, 0, 0, 1, 4, 9]

    f[int]._conformer.__conform__(None)
    with pytest.raises(TypeError):
        f([-2, -1, 0, 1, 2, 3])


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_conform_2():
    @ovld
    def f(xs: list):
        return [f(x) for x in xs]

    def intf(x: int):
        return x * x

    def floatf(x: float):
        return x - 1

    f.register(intf)
    assert f([-2, -1, 0, 1, 2, 3]) == [4, 1, 0, 1, 4, 9]

    with pytest.raises(TypeError):
        f([-2.0, 5.5])

    f[int]._conformer.__conform__(floatf)

    with pytest.raises(TypeError):
        f([-2, -1, 0, 1, 2, 3])

    assert f([-2.0, 5.5]) == [-3.0, 4.5]


@pytest.mark.skipif(
    sys.version_info < (3, 9),
    reason="type[...] syntax requires python3.9 or higher",
)
def test_type_argument():
    class One:
        pass

    class Two(One):
        pass

    class Three(One):
        pass

    @ovld
    def f(t: type[int], x):
        return x * x

    @f.register
    def _f(t: type[str], x):
        return f"hello, {x}"

    @f.register
    def _f(t: type[One], x):
        return 1

    @f.register
    def _f(t: type[Three], x):
        return 3

    assert f(int, 5) == 25
    assert f(str, 5) == "hello, 5"
    assert f(Three, 5) == 3
    assert f(Two, 5) == 1
    assert f(One, 5) == 1


@pytest.mark.skipif(
    sys.version_info < (3, 9),
    reason="type[...] syntax requires python3.9 or higher",
)
def test_generic_type_argument():
    @ovld
    def f(t: type[list]):
        return "list"

    @f.register
    def f(t: type[dict]):
        return "dict"

    assert f(list) == "list"
    assert f(list[int]) == "list"

    assert f(dict) == "dict"
    assert f(dict[str, int]) == "dict"


@pytest.mark.skipif(
    sys.version_info < (3, 9),
    reason="type[...] syntax requires python3.9 or higher",
)
def test_plain_type_argument():
    @ovld
    def f(t: type[list]):
        return "list"

    @f.register
    def f(t: type):
        return "other type"

    @f.register
    def f(t: object):
        return "other anything"

    assert f(list) == "list"
    assert f(list[int]) == "list"
    assert f(dict) == "other type"
    assert f(1234) == "other anything"


class Booboo:
    pass


def test_string_annotation():
    @ovld
    def f(t: "int"):
        return "int"

    @f.register
    def f(t: "list"):
        return "list"

    @f.register
    def f(t: "Booboo"):
        return "boo"

    assert f(1234) == "int"
    assert f([1, 2, 3, 4]) == "list"
    assert f(Booboo()) == "boo"
