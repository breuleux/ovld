
import pytest
from ovld import ovld, Ovld, OvldMC
from ovld.utils import MISSING


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


def test_lock():
    o = Ovld()

    @o.register
    def f(x: int):
        return "int"

    f(1234)

    with pytest.raises(Exception):
        @o.register  # noqa: F811
        def f(x: float):
            return "float"


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
        return self[(float,)]

    @o.register  # noqa: F811
    def f(self, x: float):
        return self[(int,)]

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

    @f.variant(postprocess=lambda x: {"result": x})
    def h(self, x: object):
        return "C"

    # Only the end result is postprocessed
    assert h([1, 2, "xxx", [3, 4]]) == {"result": [2, 3, "C", [4, 5]]}

    @h.variant
    def i(self, x: object):
        return "D"

    # Postprocessor is kept
    assert i([1, 2, "xxx", [3, 4]]) == {"result": [2, 3, "D", [4, 5]]}


def test_Overload_wrapper():

    f = Ovld()

    @f.wrapper
    def f(fn, x):
        return [fn(x)]

    with pytest.raises(TypeError):

        @f.wrapper
        def f(fn, x):
            return [fn(x)]

    with pytest.raises(TypeError):

        @f.dispatch
        def f(self, x):
            return "bad"

    @f.register
    def f(x: int):
        return x + 1

    @f.register
    def f(xs: tuple):
        return tuple(f(x) for x in xs)

    assert f(1) == [2]
    assert f((1, 2, (3, 4))) == [([2], [3], [([4], [5])])]


def test_Overload_dispatch():

    f = Ovld()

    @f.dispatch
    def f(self, x):
        return self.resolve(x, x)(x, x)

    with pytest.raises(TypeError):

        @f.dispatch
        def f(self, x):
            return self.map[(type(x), type(x))](x, x)

    with pytest.raises(TypeError):

        @f.wrapper
        def f(self, x):
            return "bad"

    @f.register
    def f(x: int, y: int):
        return x + y

    @f.register
    def f(xs: tuple, ys: tuple):
        return tuple(f(x) for x in xs)

    assert f(1) == 2
    assert f((4, 5)) == (8, 10)


def test_Overload_dispatch_bootstrap():

    f = Ovld()

    @f.dispatch
    def f(self, x):
        return self.resolve(x, x)(x, x)

    @f.register
    def f(self, x: int, y: int):
        return x + y

    @f.register
    def f(self, xs: tuple, ys: tuple):
        return tuple(self(x) for x in xs)

    assert f(1) == 2
    assert f((4, 5)) == (8, 10)


def test_stateful():

    f = Ovld(initial_state=lambda: -1)

    @f.wrapper
    def f(fn, self, x):
        self.state += 1
        return fn(self, x)

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

    @f.variant(initial_state=lambda: 0)
    def h(self, x: type(None)):
        return self.state * 100

    assert h((None, None)) == (200, 300)
    assert h((None, (None, None))) == (200, (400, 500))
    assert h((None, (None, None))) == (200, (400, 500))


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
