import pytest

from ovld import MultiTypeMap
from ovld.core import Signature


class Animal:
    pass


class Mammal(Animal):
    pass


class Bird(Animal):
    pass


class Cat(Mammal):
    pass


class Robin(Bird):
    pass


nada = frozenset()


def mksig(
    types,
    req_pos,
    max_pos,
    req_names=nada,
    vararg=False,
    priority=0,
):
    return Signature(
        types=types,
        return_type=None,
        req_pos=req_pos,
        max_pos=max_pos,
        req_names=req_names,
        vararg=vararg,
        priority=priority,
    )


def _get(tm, *key):
    try:
        return [tm[key]]
    except KeyError as err:
        return [x.handler for x in err.args[1]]


def test_empty():
    tm = MultiTypeMap()

    with pytest.raises(KeyError):
        tm[(object, object)]


def test_not_found():
    tm = MultiTypeMap()

    tm[(int,)] = "X"

    with pytest.raises(KeyError):
        tm[(object,)]


def test_inheritance():
    tm = MultiTypeMap()

    tm.register(mksig((object,), 1, 1), "o")
    tm.register(mksig((Animal,), 1, 1), "A")
    tm.register(mksig((Bird,), 1, 1), "B")

    assert _get(tm, object) == ["o"]
    assert _get(tm, int) == ["o"]
    assert _get(tm, str) == ["o"]

    assert _get(tm, Bird) == ["B"]
    assert _get(tm, Robin) == ["B"]

    assert _get(tm, Animal) == ["A"]
    assert _get(tm, Mammal) == ["A"]
    assert _get(tm, Cat) == ["A"]


def test_multiple_dispatch():
    tm = MultiTypeMap()

    tm.register(mksig((object, object), 2, 2), "oo")
    tm.register(mksig((Animal, object), 2, 2), "Ao")
    tm.register(mksig((Mammal, object), 2, 2), "Mo")
    tm.register(mksig((object, Animal), 2, 2), "oA")
    tm.register(mksig((object, Mammal), 2, 2), "oM")
    tm.register(mksig((Mammal, Mammal), 2, 2), "MM")

    assert _get(tm, int, int) == ["oo"]
    assert _get(tm, Cat, int) == ["Mo"]
    assert _get(tm, int, Cat) == ["oM"]
    assert _get(tm, Cat, Cat) == ["MM"]
    assert _get(tm, Cat, Cat) == ["MM"]
    assert _get(tm, Robin, int) == ["Ao"]
    assert _get(tm, Cat, Robin) == ["Mo", "oA"]
    assert set(_get(tm, Robin, Robin)) == {"Ao", "oA"}


def test_direct_ambiguity():
    tm = MultiTypeMap()

    tm.register(mksig((str, int), 2, 2), "A")
    tm.register(mksig((str, int), 2, 2), "B")

    # Could be in either order
    assert set(_get(tm, str, int)) == {"A", "B"}


def test_priority_same_signature():
    tm = MultiTypeMap()

    tm.register(mksig((str, int), 2, 2, nada, False, 1), "A")
    tm.register(mksig((str, int), 2, 2), "B")

    assert _get(tm, str, int) == ["A"]


def test_priority():
    tm = MultiTypeMap()

    tm.register(mksig((object,), 1, 1), "o")
    tm.register(mksig((Animal,), 1, 1), "A")
    tm.register(mksig((Mammal,), 1, 1), "M")
    tm.register(mksig((Cat,), 1, 1), "C")
    tm.register(mksig((Bird,), 1, 1, nada, False, 1), "B")  # <= higher priority
    tm.register(mksig((Robin,), 1, 1), "R")

    assert _get(tm, object) == ["o"]
    assert _get(tm, int) == ["o"]
    assert _get(tm, str) == ["o"]

    assert _get(tm, Bird) == ["B"]
    assert _get(tm, Robin) == ["B"]  # <= Bird's higher priority matters here

    assert _get(tm, Animal) == ["A"]
    assert _get(tm, Mammal) == ["M"]
    assert _get(tm, Cat) == ["C"]


def test_caching():
    tm = MultiTypeMap()

    tm.register(mksig((Mammal, Mammal), 2, 2), "X")

    assert (Mammal, Mammal) not in tm
    assert (Cat, Cat) not in tm

    assert _get(tm, Cat, Cat) == ["X"]
    # Second one should be cached and should return the same thing
    assert _get(tm, Cat, Cat) == ["X"]

    assert (Cat, Cat) in tm

    assert _get(tm, Mammal, Mammal) == ["X"]
    # Second one should be cached and should return the same thing
    assert _get(tm, Mammal, Mammal) == ["X"]

    assert (Mammal, Mammal) in tm


def test_deeper_caching():
    tm = MultiTypeMap()

    sig = mksig((Mammal, Mammal), 2, 2)
    tm.register(sig, "MM")

    m0 = tm.maps[0]
    m1 = tm.maps[1]

    assert Cat not in m0
    assert Cat not in m1

    assert _get(tm, Cat, Cat) == ["MM"]

    assert m0[Cat] == {("MM", sig): 0}
    assert m1[Cat] == {("MM", sig): 0}


def test_cache_invalidation():
    tm = MultiTypeMap()

    tm.register(mksig((Mammal, Mammal), 2, 2), "MM")
    assert (Cat, Cat) not in tm
    assert _get(tm, Cat, Cat) == ["MM"]

    assert (Cat, Cat) in tm
    tm.register(mksig((Cat, Cat), 2, 2), "CC")
    assert (Cat, Cat) not in tm
    assert _get(tm, Cat, Cat) == ["CC"]
