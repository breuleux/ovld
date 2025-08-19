"""Miscellaneous utilities."""

import builtins
import functools
import re
import typing
from abc import ABCMeta
from itertools import count

_builtins_dict = vars(builtins)


try:
    from types import UnionType

    UnionTypes = (type(typing.Union[int, str]), UnionType)

except ImportError:  # pragma: no cover
    UnionType = None
    UnionTypes = (type(typing.Union[int, str]),)


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


class CodegenInProgress(Exception):
    pass


class UsageError(Exception):
    pass


class ResolutionError(TypeError):
    pass


class SpecialForm:
    def __init__(self, name, message=None):
        self.__name = name
        self.__message = (
            message or f"{name}() can only be used from inside an @ovld-registered function."
        )

    def __call__(self, *args, **kwargs):
        raise UsageError(self.__message)

    def __getattr__(self, attr):
        raise UsageError(self.__message)

    def __str__(self):
        return f"<SpecialForm {self.__name}>"

    __repr__ = __str__


class GenericAliasMC(type):
    def __instancecheck__(cls, obj):
        return hasattr(obj, "__origin__")


class GenericAlias(metaclass=GenericAliasMC):
    pass


def clsstring(cls):
    if cls is object:
        return "*"
    elif args := typing.get_args(cls):
        origin = typing.get_origin(cls) or cls
        args = ", ".join(map(clsstring, args))
        return f"{origin.__name__}[{args}]"
    else:
        r = repr(cls)
        if r.startswith("<class ") or r.startswith("<enum "):
            return cls.__name__
        else:
            return r


def typemap_entry_string(cls):
    if isinstance(cls, tuple):
        key, typ = cls
        return f"{key}: {clsstring(typ)}"
    else:
        return clsstring(cls)


def sigstring(types):
    return ", ".join(map(typemap_entry_string, types))


def subtler_type(obj):
    if isinstance(obj, GenericAlias):
        return type[obj]
    elif isinstance(obj, UnionTypes):
        return type[obj]
    elif obj is typing.Any:
        return type[object]
    elif isinstance(obj, type):
        return type[obj]
    else:
        return type(obj)


class NameDatabase:
    def __init__(self, default_name="TMP"):
        self.default_name = default_name
        self.count = count()
        self.variables = {}
        self.names = {}
        self.registered = set()

    def register(self, name):
        self.registered.add(name)

    def gensym(self, desired_name, value=None):
        i = 1
        name = desired_name
        while name in self.registered or (
            name in _builtins_dict and _builtins_dict[name] != value
        ):
            name = f"{desired_name}{i}"
            i += 1
        self.registered.add(name)
        return name

    def get(self, value, suggested_name=None):
        if type(value) in (int, float, str):
            return repr(value)
        if id(value) in self.names:
            return self.names[id(value)]
        dflt = suggested_name or self.default_name
        if (
            isinstance(value, GenericAlias) and typing.get_origin(value) is type
        ):  # pragma: no cover
            name = "t_" + getattr(typing.get_args(value)[0], "__name__", dflt)
        else:
            name = getattr(value, "__name__", dflt)
        if not re.match(string=name, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"):
            name = dflt
        name = self.gensym(name, value)
        self.variables[name] = value
        self.names[id(value)] = name
        return name

    __getitem__ = get


def get_args(tp):
    args = getattr(tp, "__args__", None)
    if not isinstance(args, tuple):
        args = ()
    return args


_standard_instancechecks = {
    type.__instancecheck__,
    GenericAlias.__instancecheck__,
    type(list[object]).__instancecheck__,
    ABCMeta.__instancecheck__,
    type(typing.Protocol).__instancecheck__,
    type(typing.Any).__instancecheck__,
}


def is_dependent(t):
    if any(is_dependent(subt) for subt in get_args(t)):
        return typing.get_origin(t) is not type
    elif hasattr(t, "__dependent__"):
        return t.__dependent__
    elif not isinstance(t, type):
        return False
    elif type(t).__instancecheck__ not in _standard_instancechecks:
        return True
    return False
