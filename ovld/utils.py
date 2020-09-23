"""Miscellaneous utilities."""

import functools
import sys


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


class _MetaMC(type):
    def __subclasscheck__(cls, sub):
        return cls.chk(sub)


def meta(condition):
    """Return a class with a subclassing relation defined by condition.

    For example, a dataclass is a subclass of `meta(dataclasses.is_dataclass)`,
    and a class which name starts with "X" is a subclass of
    `meta(lambda cls: cls.__name__.startswith("X"))`.
    """

    class M(metaclass=_MetaMC):
        @classmethod
        def chk(cls, sub):
            return condition(sub)

    return M


def _getcls(ref):
    module, *parts = ref.split(".")
    curr = __import__(module)
    for part in parts:
        curr = getattr(curr, part)
    return curr


def deferred(ref):
    module, _ = ref.split(".", 1)
    if module in sys.modules:
        return _getcls(ref)

    @meta
    def check(cls):
        full_cls_mod = getattr(cls, "__module__", None)
        cls_module = full_cls_mod.split(".", 1)[0] if full_cls_mod else None
        if cls_module == module:
            return issubclass(cls, _getcls(ref))
        else:
            return False

    return check


__all__ = [
    "BOOTSTRAP",
    "MISSING",
    "Named",
    "deferred",
    "meta",
    "keyword_decorator",
]
