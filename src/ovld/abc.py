import typing
from collections.abc import Callable, Collection, Mapping, Sequence

from .dependent import Callable as OvldCallable
from .dependent import (
    CollectionFastCheck,
    Equals,
    MappingFastCheck,
    ProductType,
    SequenceFastCheck,
)
from .types import normalize_type


@normalize_type.register_generic(typing.Literal)
def _(self, t, fn):
    return Equals[t.__args__]


@normalize_type.register_generic(tuple)
def _(self, t, fn):
    args = tuple(self(arg, fn) for arg in t.__args__)
    return ProductType[args]


@normalize_type.register_generic(Sequence)
def _(self, t, fn):
    args = tuple(self(arg, fn) for arg in t.__args__)
    return SequenceFastCheck[args]


@normalize_type.register_generic(Collection)
def _(self, t, fn):
    args = tuple(self(arg, fn) for arg in t.__args__)
    return CollectionFastCheck[args]


@normalize_type.register_generic(Mapping)
def _(self, t, fn):
    args = tuple(self(arg, fn) for arg in t.__args__)
    return MappingFastCheck[args]


@normalize_type.register_generic(Callable)
def _(self, t, fn):
    *at, rt = t.__args__
    at = tuple(self(arg, fn) for arg in at)
    return OvldCallable[at, self(rt, fn)]
