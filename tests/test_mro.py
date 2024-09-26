from dataclasses import dataclass
from typing import Iterable, Mapping

from ovld.dependent import Dependent
from ovld.mro import Order, subclasscheck, typeorder
from ovld.types import (
    All,
    Dataclass,
    Intersection,
    Order,
    Union,
    Whatever,
    typeorder,
)


def identity(x):
    return x


class A:
    pass


class B(A):
    pass


class Prox:
    _cls = object

    def __class_getitem__(cls, other):
        return type(f"Prox[{other.__name__}]", (Prox,), {"_cls": other})

    @classmethod
    def __is_supertype__(cls, other):
        return subclasscheck(other, cls._cls)

    @classmethod
    def __is_subtype__(cls, other):
        return subclasscheck(cls._cls, other)

    @classmethod
    def __type_order__(cls, other):
        return typeorder(cls._cls, other)


@dataclass
class Point:
    x: int
    y: int


def inorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) == Order.MORE
        assert typeorder(b, a) == Order.LESS


def sameorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) is Order.SAME
        assert typeorder(b, a) is Order.SAME


def noorder(*seq):
    for a, b in zip(seq[:-1], seq[1:]):
        assert typeorder(a, b) is Order.NONE
        assert typeorder(b, a) is Order.NONE


def test_merge():
    assert Order.merge([Order.SAME, Order.SAME]) is Order.SAME
    assert Order.merge([Order.SAME, Order.MORE]) is Order.MORE
    assert Order.merge([Order.SAME, Order.LESS]) is Order.LESS
    assert Order.merge([Order.MORE]) is Order.MORE
    assert Order.merge([Order.LESS]) is Order.LESS
    assert Order.merge([Order.LESS, Order.MORE]) is Order.NONE
    assert Order.merge([Order.LESS, Order.LESS, Order.NONE]) is Order.NONE


def test_typeorder():
    inorder(object, int)
    inorder(object, Union[int, str], str)
    inorder(object, Dataclass, Point)
    inorder(object, type, type[Dataclass])
    inorder(type[list], type[list[int]])
    inorder(str, Intersection[int, str])
    inorder(object, Intersection[object, int])
    inorder(object, Iterable, Iterable[int], list[int])
    inorder(Iterable[int], list)
    inorder(list, list[int])

    sameorder(int, int)
    sameorder(Mapping[str, int], Mapping[str, int])

    noorder(tuple[int, int], tuple[int])
    noorder(dict[str, int], dict[int, str])
    noorder(dict[str, object], dict[object, str])
    noorder(type[int], type[Dataclass])
    noorder(float, int)
    noorder(int, str)
    noorder(int, Dataclass)
    noorder(Union[int, str], float)

    inorder(Whatever, object)
    inorder(All, object)


def test_subclasscheck():
    assert subclasscheck(B, A)
    assert not subclasscheck(A, B)
    assert subclasscheck(A, A)
    assert subclasscheck(A, object)
    assert subclasscheck(A, Union[A, int])
    assert subclasscheck(int, Union[A, int])

    assert subclasscheck(All, int)
    assert not subclasscheck(int, All)

    assert subclasscheck(Whatever, int)
    assert subclasscheck(int, Whatever)


def test_subclasscheck_generic():
    assert subclasscheck(list[int], list[int])
    assert subclasscheck(list[int], list[object])
    assert not subclasscheck(list[object], list[int])


def test_subclasscheck_type():
    assert subclasscheck(type[int], type[object])


def test_subclasscheck_type_union():
    assert subclasscheck(type[Union[int, str]], type[Union])
    assert subclasscheck(type[Union], object)
    assert not subclasscheck(object, type[Union])


def test_typeorder_type_union():
    # assert typeorder(type[int | str], type[UnionType]) is Order.LESS
    assert typeorder(type[Union[int, str]], type[Union]) is Order.LESS
    assert typeorder(object, type[Union]) is Order.MORE


def test_subclasscheck_dependent():
    assert subclasscheck(B, Dependent[A, identity])
    assert not subclasscheck(
        Dependent[int, identity], Dependent[float, identity]
    )


def test_typeorder_dependent():
    assert typeorder(Dependent[int, identity], float) is Order.NONE
    assert (
        typeorder(Dependent[int, identity], Dependent[A, identity])
        is Order.NONE
    )
    assert (
        typeorder(Dependent[int, identity], Dependent[float, identity])
        is Order.NONE
    )


def test_subclasscheck_proxy():
    assert subclasscheck(Prox[int], int)
    assert subclasscheck(int, Prox[int])
    assert subclasscheck(Prox[int], Prox)
    assert not subclasscheck(Prox, Prox[int])

    assert subclasscheck(Prox[B], A)
    assert not subclasscheck(Prox[A], B)
    assert subclasscheck(B, Prox[A])
    assert not subclasscheck(A, Prox[B])
    assert subclasscheck(Prox[B], Prox[A])

    assert typeorder(Prox[int], int) is Order.SAME
    assert typeorder(int, Prox[int]) is Order.SAME
    assert typeorder(Prox[int], Prox) is Order.LESS
    assert typeorder(Prox, Prox[int]) is Order.MORE
