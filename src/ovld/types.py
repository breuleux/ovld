import sys
import typing
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

# from .mro import _issubclass


class Order(Enum):
    LESS = -1
    MORE = 1
    SAME = 0
    NONE = None

    def opposite(self):
        if self is Order.LESS:
            return Order.MORE
        elif self is Order.MORE:
            return Order.LESS
        else:
            return self


def typeorder(t1, t2):
    """Order relation between two types.

    Returns a member of the Order enum.

    * typeorder(t1, t2) is Order.LESS   if t2 is more general than t1
    * typeorder(t1, t2) is Order.SAME   if t1 is equal to t2
    * typeorder(t1, t2) is Order.MORE   if t1 is more general than t2
    * typeorder(t1, t2) is Order.NONE   if they cannot be compared
    """
    if t1 == t2:
        return Order.SAME

    t1 = getattr(t1, "__proxy_for__", t1)
    t2 = getattr(t2, "__proxy_for__", t2)

    if (
        hasattr(t1, "__typeorder__")
        and (result := t1.__typeorder__(t2)) is not NotImplemented
    ):
        return result
    elif (
        hasattr(t2, "__typeorder__")
        and (result := t2.__typeorder__(t1)) is not NotImplemented
    ):
        return result.opposite()

    o1 = getattr(t1, "__origin__", None)
    o2 = getattr(t2, "__origin__", None)

    if o2 is typing.Union:
        compare = [
            x for t in t2.__args__ if (x := typeorder(t1, t)) is not Order.NONE
        ]
        if not compare:
            return Order.NONE
        elif any(x is Order.LESS or x is Order.SAME for x in compare):
            return Order.LESS
        else:
            return Order.MORE

    if o1 is typing.Union:
        return typeorder(t2, t1).opposite()

    if o2 and not o1:
        return typeorder(t2, t1).opposite()

    if o1:
        if not o2 or getattr(t2, "__args__", None) is None:
            order = typeorder(o1, t2)
            if order is order.SAME:
                order = order.LESS
            return order

        if (order := typeorder(o1, o2)) is not Order.SAME:
            return order

        args1 = getattr(t1, "__args__", ())
        args2 = getattr(t2, "__args__", ())

        if len(args1) != len(args2):
            return Order.NONE

        ords = [typeorder(a1, a2) for a1, a2 in zip(args1, args2)]
        if Order.MORE in ords and Order.LESS in ords:
            return Order.NONE
        elif Order.NONE in ords:
            return Order.NONE
        elif Order.MORE in ords:
            return Order.MORE
        elif Order.LESS in ords:
            return Order.LESS
        else:  # pragma: no cover
            # Not sure when t1 != t2 and that happens
            return Order.SAME

    sx = issubclass(t1, t2)
    sy = issubclass(t2, t1)
    if sx and sy:  # pragma: no cover
        # Not sure when t1 != t2 and that happens
        return Order.SAME
    elif sx:
        return Order.LESS
    elif sy:
        return Order.MORE
    else:
        return Order.NONE


class MetaMC(type):
    def __new__(T, name, order):
        return super().__new__(T, name, (), {"order": order})

    def __init__(cls, name, order):
        pass

    def __typeorder__(cls, other):
        order = cls.order(other)
        if isinstance(order, bool):
            return NotImplemented
        else:
            return order

    def __subclasscheck__(cls, sub):
        order = cls.order(sub)
        if isinstance(order, Order):
            return order == Order.MORE or order == Order.SAME
        else:
            return order


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
    return cls is base_cls


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
    compare = [x for t in classes if (x := typeorder(t, cls)) is not Order.NONE]
    if not compare:
        return Order.NONE
    elif any(x is Order.LESS or x is Order.SAME for x in compare):
        return Order.LESS
    else:
        return Order.MORE


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
    "Intersection",
    "StrictSubclass",
    "class_check",
    "parametrized_class_check",
]
