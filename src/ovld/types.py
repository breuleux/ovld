import inspect
import sys
import typing
from dataclasses import dataclass
from functools import partial
from typing import Protocol, runtime_checkable

from .mro import Order, TypeRelationship, subclasscheck, typeorder
from .typemap import TypeMap
from .utils import UsageError, clsstring

try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None


class TypeNormalizer:
    def __init__(self, generic_handlers=None):
        self.generic_handlers = generic_handlers or TypeMap()

    def register_generic(self, generic, handler=None):
        if handler is None:
            return partial(self.register_generic, generic)
        else:
            self.generic_handlers.register(generic, handler)

    def __call__(self, t, fn):
        from .dependent import DependentType

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
            return self(t.__args__, fn)
        elif origin is type:
            return t
        elif origin and getattr(t, "__args__", None) is None:
            return t
        elif origin is not None:
            try:
                results = self.generic_handlers[origin]
                results = list(results.items())
                results.sort(key=lambda x: x[1], reverse=True)
                assert results
                rval = results[0][0](self, t, fn)
                if isinstance(origin, type) and hasattr(rval, "with_bound"):
                    rval = rval.with_bound(origin)
                return rval
            except KeyError:  # pragma: no cover
                raise TypeError(f"ovld does not understand generic type {t}")
        elif isinstance(t, tuple):
            return Union[tuple(self(t2, fn) for t2 in t)]
        elif isinstance(t, DependentType) and not t.bound:
            raise UsageError(
                f"Dependent type {t} has not been given a type bound. Please use Dependent[<bound>, {t}] instead."
            )
        else:
            return t


normalize_type = TypeNormalizer()


@normalize_type.register_generic(typing.Union)
def _(self, t, fn):
    return self(t.__args__, fn)


class MetaMC(type):
    def __new__(T, name, handler):
        return super().__new__(T, name, (), {"_handler": handler})

    def __init__(cls, name, handler):
        cls.__args__ = getattr(handler, "__args__", ())

    def codegen(cls):
        return cls._handler.codegen()

    def __type_order__(cls, other):
        return cls._handler.__type_order__(other)

    def __is_supertype__(cls, other):
        return cls._handler.__is_supertype__(other)

    def __is_subtype__(cls, other):  # pragma: no cover
        return cls._handler.__is_subtype__(other)

    def __subclasscheck__(cls, sub):
        return cls._handler.__subclasscheck__(sub)

    def __instancecheck__(cls, obj):
        return cls._handler.__instancecheck__(obj)

    def __eq__(cls, other):
        return (
            type(cls) is type(other)
            and type(cls._handler) is type(other._handler)
            and cls._handler == other._handler
        )

    def __hash__(cls):
        return hash(cls._handler)

    def __and__(cls, other):
        return Intersection[cls, other]

    def __rand__(cls, other):
        return Intersection[other, cls]

    def __str__(self):
        return str(self._handler)

    __repr__ = __str__


class SingleFunctionHandler:
    def __init__(self, handler, args):
        self.handler = handler
        self.args = self.__args__ = args

    def __type_order__(self, other):
        results = self.handler(other, *self.args)
        if isinstance(results, TypeRelationship):
            return results.order
        else:
            return NotImplemented

    def __is_supertype__(self, other):
        results = self.handler(other, *self.args)
        if isinstance(results, bool):
            return results
        elif isinstance(results, TypeRelationship):
            return results.supertype
        else:  # pragma: no cover
            return NotImplemented

    def __is_subtype__(self, other):  # pragma: no cover
        results = self.handler(other, *self.args)
        if isinstance(results, TypeRelationship):
            return results.subtype
        else:
            return NotImplemented

    def __subclasscheck__(self, sub):
        return self.__is_supertype__(sub)

    def __instancecheck__(self, obj):
        return issubclass(type(obj), self)

    def __str__(self):
        args = ", ".join(map(clsstring, self.__args__))
        return f"{self.handler.__name__}[{args}]"


def class_check(condition):
    """Return a class with a subclassing relation defined by condition.

    For example, a dataclass is a subclass of `class_check(dataclasses.is_dataclass)`,
    and a class which name starts with "X" is a subclass of
    `class_check(lambda cls: cls.__name__.startswith("X"))`.

    Arguments:
        condition: A function that takes a class as an argument and returns
            True or False depending on whether it matches some condition.
    """
    return MetaMC(condition.__name__, SingleFunctionHandler(condition, ()))


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

            if isinstance(fn, type):
                return MetaMC(fn.__name__, fn(*arg))
            else:
                return MetaMC(fn.__name__, SingleFunctionHandler(fn, arg))

    _C.__name__ = fn.__name__
    _C.__qualname__ = fn.__qualname__
    return _C


def _getcls(ref):
    module, *parts = ref.split(".")
    curr = __import__(module)
    for part in parts:
        curr = getattr(curr, part)
    return curr


class AllMC(type):
    def __type_order__(self, other):
        return Order.MORE

    def __is_subtype__(self, other):
        return True

    def __is_supertype__(self, other):
        return False

    def __subclasscheck__(self, other):  # pragma: no cover
        return False

    def __isinstance__(self, other):  # pragma: no cover
        return False


class All(metaclass=AllMC):
    """All is the empty/void/bottom type -- it acts as a subtype of all types.

    It is basically the opposite of Any: nothing is an instance of All. The main
    place you want to use All is as a wildcard in contravariant settings, e.g.
    all 2-argument functions are instances of Callable[[All, All], Any] because
    the arguments are contravariant.
    """


class WhateverMC(AllMC):
    def __is_supertype__(self, other):
        return True

    def __subclasscheck__(self, other):  # pragma: no cover
        return True

    def __isinstance__(self, other):  # pragma: no cover
        return True


class Whatever(metaclass=WhateverMC):
    """This type is a superclass and a subclass of everything.

    It's not a coherent type, more like a convenience.

    It'll match anything anywhere, so you can write e.g.
    Callable[[Whatever, Whatever], Whatever] to match any function of
    two arguments. Any only works in covariant settings, and All only
    works in contravariant settings.
    """


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

        return MetaMC(f"Deferred[{ref}]", SingleFunctionHandler(check, ()))


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
class Union:
    def __init__(self, *types):
        self.__args__ = self.types = types

    def codegen(self):
        from .dependent import combine, generate_checking_code

        template = " or ".join("{}" for t in self.types)
        return combine(
            template, [generate_checking_code(t) for t in self.types]
        )

    def __type_order__(self, other):
        if other is Union:
            return Order.LESS
        classes = self.types
        compare = [
            x for t in classes if (x := typeorder(t, other)) is not Order.NONE
        ]
        if not compare:
            return Order.NONE
        elif any(x is Order.MORE or x is Order.SAME for x in compare):
            return Order.MORE
        else:
            return Order.LESS

    def __is_supertype__(self, other):
        return any(subclasscheck(other, t) for t in self.types)

    def __is_subtype__(self, other):
        if other is Union:
            return True
        return NotImplemented  # pragma: no cover

    def __subclasscheck__(self, sub):
        return self.__is_supertype__(sub)

    def __instancecheck__(self, obj):
        return any(isinstance(obj, t) for t in self.types)

    def __eq__(self, other):
        return self.__args__ == other.__args__

    def __hash__(self):
        return hash(self.__args__)

    def __str__(self):
        return " | ".join(map(clsstring, self.__args__))


@parametrized_class_check
class Intersection:
    def __init__(self, *types):
        self.__args__ = self.types = types

    def codegen(self):
        from .dependent import combine, generate_checking_code

        template = " and ".join("{}" for t in self.types)
        return combine(
            template, [generate_checking_code(t) for t in self.types]
        )

    def __type_order__(self, other):
        if other is Intersection:
            return Order.LESS
        classes = self.types
        compare = [
            x for t in classes if (x := typeorder(t, other)) is not Order.NONE
        ]
        if not compare:
            return Order.NONE
        elif any(x is Order.LESS or x is Order.SAME for x in compare):
            return Order.LESS
        else:
            return Order.MORE

    def __is_supertype__(self, other):
        return all(subclasscheck(other, t) for t in self.types)

    def __is_subtype__(self, other):  # pragma: no cover
        if other is Intersection:
            return True
        return NotImplemented

    def __subclasscheck__(self, sub):
        return self.__is_supertype__(sub)

    def __instancecheck__(self, obj):
        return all(isinstance(obj, t) for t in self.types)

    def __eq__(self, other):
        return self.__args__ == other.__args__

    def __hash__(self):
        return hash(self.__args__)

    def __str__(self):
        return " & ".join(map(clsstring, self.__args__))


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
