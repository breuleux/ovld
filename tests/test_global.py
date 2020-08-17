from ovld import ovld, ovld_wrapper

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
    def frittata(fn, self, x: int):
        return fn(self, x, x)

    @ovld
    def frittata(self, x: int, y):
        return x + y

    @ovld
    def frittata(self, x: str, y):
        return x + y

    @ovld
    def frittata(self, xs: list, _):
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
    assert frittata(10) == 20
    assert frittata("alouette") == "alouettealouette"
