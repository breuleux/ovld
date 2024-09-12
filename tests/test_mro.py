try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None

import sys
from typing import Union

from ovld.mro import Order, subclasscheck, typeorder


class A:
    pass


class B(A):
    pass


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
