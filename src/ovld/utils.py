"""Miscellaneous utilities."""

import functools


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


__all__ = [
    "BOOTSTRAP",
    "MISSING",
    "Named",
    "keyword_decorator",
]
