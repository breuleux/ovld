from ovld import ovld, recurse

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


_ovld_dispatch_exc = None
try:

    @ovld
    def roesti(x):
        return recurse(x, x)

    @ovld
    def roesti(x: int, y: int):
        return x * y

    @ovld
    def roesti(x: str, y: str):
        return x + y

    @ovld
    def roesti(xs: list, _):
        return [recurse(x) for x in xs]

except Exception as exc:
    _ovld_dispatch_exc = exc


def test_global_ovld():
    if _ovld_exc:
        raise _ovld_exc
    assert pluralize(10) == 11
    assert pluralize("alouette") == "alouettes"


def test_global_ovld_dispatch():
    if _ovld_dispatch_exc:
        raise _ovld_dispatch_exc
    assert roesti(10) == 100
    assert roesti("alouette") == "alouettealouette"
