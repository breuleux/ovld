"""Miscellaneous utilities."""

import functools
import sys
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class Named:
    """A named object.

    This class can be used to construct objects with a name that will be used
    for the string representation.
    """

    def __init__(self, name):
        """Construct a named object.

        Arguments:
            name: The name of this object.
        """
        self.name = name

    def __repr__(self):
        """Return the object's name."""
        return self.name


BOOTSTRAP = Named("BOOTSTRAP")
MISSING = Named("MISSING")


def keyword_decorator(deco):
    """Wrap a decorator to optionally takes keyword arguments."""

    @functools.wraps(deco)
    def new_deco(fn=None, **kwargs):
        if fn is None:

            @functools.wraps(deco)
            def newer_deco(fn):
                return deco(fn, **kwargs)

            return newer_deco
        else:
            return deco(fn, **kwargs)

    return new_deco


class UsageError(Exception):
    pass


class Unusable:
    def __init__(self, message):
        self.__message = message

    def __call__(self, *args, **kwargs):
        raise UsageError(self.__message)

    def __getattr__(self, attr):
        raise UsageError(self.__message)


class MetaMC(type):
    def __new__(T, name, chk):
        return super().__new__(T, name, (), {"chk": chk})

    def __init__(cls, name, chk):
        pass

    def __subclasscheck__(cls, sub):
        return cls.chk(sub)


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


@runtime_checkable
@dataclass
class Dataclass(Protocol):
    @classmethod
    def __subclasshook__(cls, subclass):
        return hasattr(subclass, "__dataclass_fields__") and hasattr(
            subclass, "__dataclass_params__"
        )


__all__ = [
    "BOOTSTRAP",
    "MISSING",
    "Dataclass",
    "Named",
    "Deferred",
    "Exactly",
    "StrictSubclass",
    "class_check",
    "parametrized_class_check",
    "keyword_decorator",
]
