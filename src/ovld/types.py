import inspect
import sys
import typing
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ovld.utils import UsageError

from .mro import Order, TypeRelationship, subclasscheck, typeorder

try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None


def normalize_type(t, fn):
    from .dependent import DependentType, Equals

    if isinstance(t, str):
        t = eval(t, getattr(fn, "__globals__", {}))

    if t is type:
        t = type[object]
    elif t is typing.Any:
        t = object
    elif t is inspect._empty:
        t = object
    elif isinstance(t, typing._AnnotatedAlias):
        t = t.__origin__

    origin = getattr(t, "__origin__", None)
    if UnionType and isinstance(t, UnionType):
        return normalize_type(t.__args__, fn)
    elif origin is type:
        return t
    elif origin is typing.Union:
        return normalize_type(t.__args__, fn)
    elif origin is typing.Literal:
        return Equals(*t.__args__)
    elif origin and not getattr(t, "__args__", None):
        return t
    elif origin is not None:
        raise TypeError(
            f"ovld does not accept generic types except type, Union, Optional, Literal, but not: {t}"
        )
    elif isinstance(t, tuple):
        return typing.Union[tuple(normalize_type(t2, fn) for t2 in t)]
    elif isinstance(t, DependentType) and not t.bound:
        raise UsageError(
            f"Dependent type {t} has not been given a type bound. Please use Dependent[<bound>, {t}] instead."
        )
    else:
        return t


class MetaMC(type):
    def __new__(T, name, order):
        return super().__new__(T, name, (), {"order": order})

    def __init__(cls, name, order):
        pass

    def __type_order__(cls, other):
        results = cls.order(other)
        if isinstance(results, TypeRelationship):
            return results.order
        else:
            return NotImplemented

    def __is_supertype__(cls, other):
        results = cls.order(other)
        if isinstance(results, bool):
            return results
        elif isinstance(results, TypeRelationship):
            return results.supertype
        else:  # pragma: no cover
            return NotImplemented

    def __is_subtype__(cls, other):
        results = cls.order(other)
        if isinstance(results, TypeRelationship):
            return results.subtype
        else:  # pragma: no cover
            return NotImplemented

    def __subclasscheck__(cls, sub):
        return cls.__is_supertype__(sub)


def class_check(condition):
    """Return a class with a subclassing relation defined by condition.

    For example, a dataclass is a subclass of `class_check(dataclasses.is_dataclass)`,
    and a class which name starts with "X" is a subclass of
    `class_check(lambda cls: cls.__name__.startswith("X"))`.

    Arguments:
        condition: A function that takes a class as an argument and returns
            True or False depending on whether it matches some condition.
    """
    return MetaMC(condition.__name__, condition)


def parametrized_class_check(fn):
    """Return a parametrized class checker.

    In essence, parametrized_class_check(fn)[X] will call fn(cls, X) in order
    to check whether cls matches the condition defined by fn and X.

    Arguments:
        fn: A function that takes a class and one or more additional arguments,
            and returns True or False depending on whether the class matches.
    """

    class _C:
        def __class_getitem__(_, arg):
            if not isinstance(arg, tuple):
                arg = (arg,)

            def arg_to_str(x):
                if isinstance(x, type):
                    return x.__name__
                else:
                    return repr(x)

            name = f"{fn.__name__}[{', '.join(map(arg_to_str, arg))}]"
            return MetaMC(name, lambda sub: fn(sub, *arg))

    _C.__name__ = fn.__name__
    _C.__qualname__ = fn.__qualname__
    return _C


def _getcls(ref):
    module, *parts = ref.split(".")
    curr = __import__(module)
    for part in parts:
        curr = getattr(curr, part)
    return curr


class Deferred:
    """Represent a class from an external module without importing it.

    For instance, `Deferred["numpy.ndarray"]` matches instances of
    numpy.ndarray, but it does not import numpy. When tested against a
    class, if the first part of class's `__module__` is `numpy`, then
    we do get the class and perform a normal issubclass check.

    If the module is already loaded, `Deferred` returns the class directly.

    Arguments:
        ref: A string starting with a module name representing the path
            to import a class.
    """

    def __class_getitem__(cls, ref):
        module, _ = ref.split(".", 1)
        if module in sys.modules:
            return _getcls(ref)

        def check(cls):
            full_cls_mod = getattr(cls, "__module__", None)
            cls_module = full_cls_mod.split(".", 1)[0] if full_cls_mod else None
            if cls_module == module:
                return issubclass(cls, _getcls(ref))
            else:
                return False

        return MetaMC(f"Deferred[{ref}]", check)


@parametrized_class_check
def Exactly(cls, base_cls):
    """Match the class but not its subclasses."""
    return TypeRelationship(
        order=Order.LESS if cls is base_cls else typeorder(base_cls, cls),
        supertype=cls is base_cls,
    )


@parametrized_class_check
def StrictSubclass(cls, base_cls):
    """Match subclasses but not the base class."""
    return (
        isinstance(cls, type)
        and issubclass(cls, base_cls)
        and cls is not base_cls
    )


@parametrized_class_check
def Intersection(cls, *classes):
    """Match all classes."""
    matches = all(subclasscheck(cls, t) for t in classes)
    compare = [x for t in classes if (x := typeorder(t, cls)) is not Order.NONE]
    if not compare:
        return TypeRelationship(Order.NONE, supertype=matches)
    elif any(x is Order.LESS or x is Order.SAME for x in compare):
        return TypeRelationship(Order.LESS, supertype=matches)
    else:
        return TypeRelationship(Order.MORE, supertype=matches)


@parametrized_class_check
def HasMethod(cls, method_name):
    """Match classes that have a specific method."""
    return hasattr(cls, method_name)


@runtime_checkable
@dataclass
class Dataclass(Protocol):
    @classmethod
    def __subclasshook__(cls, subclass):
        return hasattr(subclass, "__dataclass_fields__") and hasattr(
            subclass, "__dataclass_params__"
        )


__all__ = [
    "Dataclass",
    "Deferred",
    "Exactly",
    "HasMethod",
    "Intersection",
    "StrictSubclass",
    "class_check",
    "parametrized_class_check",
]
