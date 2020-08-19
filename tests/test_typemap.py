
from ovld import MultiTypeMap
import pytest


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


def _get(tm, *key):
    try:
        return [tm[key]]
    except KeyError as err:
        return err.args[1]


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

    tm.register((object,), "o")
    tm.register((Animal,), "A")
    tm.register((Bird,), "B")

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

    tm.register((object, object), "oo")
    tm.register((Animal, object), "Ao")
    tm.register((Mammal, object), "Mo")
    tm.register((object, Animal), "oA")
    tm.register((object, Mammal), "oM")
    tm.register((Mammal, Mammal), "MM")

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

    tm.register((str, int), "A")
    tm.register((str, int), "B")

    # Could be in either order
    assert set(_get(tm, str, int)) == {"A", "B"}


def test_caching():
    tm = MultiTypeMap()

    tm.register((Mammal, Mammal), "X")

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

    tm.register((Mammal, Mammal), "MM")

    m0 = tm.maps[(2, 0)]
    m1 = tm.maps[(2, 1)]

    assert Cat not in m0
    assert Cat not in m1

    assert _get(tm, Cat, Cat) == ["MM"]

    assert m0[Cat] == {"MM": 2}
    assert m1[Cat] == {"MM": 2}


def test_cache_invalidation():
    tm = MultiTypeMap()

    tm.register((Mammal, Mammal), "MM")
    assert (Cat, Cat) not in tm
    assert _get(tm, Cat, Cat) == ["MM"]

    assert (Cat, Cat) in tm
    tm.register((Cat, Cat), "CC")
    assert (Cat, Cat) not in tm
    assert _get(tm, Cat, Cat) == ["CC"]
