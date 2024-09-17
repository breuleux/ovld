try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None

import sys
from typing import Union

from ovld.dependent import Dependent
from ovld.mro import Order, subclasscheck, typeorder


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


def test_subclasscheck():
    assert subclasscheck(B, A)
    assert not subclasscheck(A, B)
    assert subclasscheck(A, A)
    assert subclasscheck(A, object)
    assert subclasscheck(A, Union[A, int])
    assert subclasscheck(int, Union[A, int])


def test_subclasscheck_generic():
    assert subclasscheck(list[int], list[int])
    assert subclasscheck(list[int], list[object])
    assert not subclasscheck(list[object], list[int])


def test_subclasscheck_type():
    assert subclasscheck(type[int], type[object])


def test_subclasscheck_type_union():
    if sys.version_info >= (3, 10):
        assert subclasscheck(type[int | str], type[UnionType])
    assert subclasscheck(type[Union[int, str]], type[Union])
    assert subclasscheck(type[Union], object)
    assert not subclasscheck(object, type[Union])


def test_typeorder_type_union():
    if sys.version_info >= (3, 10):
        assert typeorder(type[int | str], type[UnionType]) is Order.LESS
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
