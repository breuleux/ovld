import sys

from ovld import deferred, meta, ovld


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

    @meta
    def B_(cls):
        return cls.__name__.startswith("B")

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

    assert f(Apple()) == "no B"
    assert f(Banana()) == "B!"
    assert f(Brownie()) == "Brownie"
    assert f(Butterscotch()) == "Butterscotch"
    assert f(Cherry()) == "no B"


def test_deferred_builtins():
    assert deferred("builtins.object") is object
    assert deferred("builtins.TypeError") is TypeError


def test_deferred():
    assert "blessed" not in sys.modules

    @ovld
    def f(x: deferred("blessed.Terminal")):
        return "Terminal"

    @f.register
    def f(x):
        return "object"

    assert "blessed" not in sys.modules

    # This is an arbitrary choice of an external module that has a class in it
    # that we can load just to test deferred.
    import blessed

    assert f(blessed.Terminal()) == "Terminal"

    assert "blessed" in sys.modules
