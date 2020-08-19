from ovld import ovld, ovld_dispatch, ovld_wrapper

_ovld_exc = None
try:
    @ovld
    def pluralize(x: int):
        return x + 1

    @ovld
    def pluralize(x: str):
        return x + "s"

except Exception as exc:
    _ovld_exc = exc


_ovld_wrapper_exc = None
try:
    @ovld_wrapper(bootstrap=True)
    def frittata(fn, self, x, _):
        return fn(self, x, x)

    @ovld
    def frittata(self, x: int, y):
        return x * y

    @ovld
    def frittata(self, x: str, y):
        return x + y

    @ovld
    def frittata(self, xs: list, _):
        return [self(x) for x in xs]

except Exception as exc:
    _ovld_wrapper_exc = exc


_ovld_dispatch_exc = None
try:
    @ovld_dispatch
    def roesti(self, x):
        return self.resolve(x, x)(x, x)

    @ovld
    def roesti(self, x: int, y: int):
        return x * y

    @ovld
    def roesti(self, x: str, y: str):
        return x + y

    @ovld
    def roesti(self, xs: list, _):
        return [self(x) for x in xs]

except Exception as exc:
    _ovld_wrapper_exc = exc


def test_global_ovld():
    if _ovld_exc:
        raise _ovld_exc
    assert pluralize(10) == 11
    assert pluralize("alouette") == "alouettes"


def test_global_ovld_wrapper():
    if _ovld_wrapper_exc:
        raise _ovld_wrapper_exc
    assert frittata(10, 4) == 100
    assert frittata("alouette", 4) == "alouettealouette"


def test_global_ovld_dispatch():
    if _ovld_dispatch_exc:
        raise _ovld_dispatch_exc
    assert roesti(10) == 100
    assert roesti("alouette") == "alouettealouette"
