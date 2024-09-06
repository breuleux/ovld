import inspect
import re
from typing import TYPE_CHECKING, Mapping, TypeVar, Union

from .types import (
    Intersection,
    Order,
    TypeRelationship,
    normalize_type,
    subclasscheck,
    typeorder,
)


class DependentType:
    exclusive_type = False
    keyable_type = False

    def __init__(self, bound):
        self.bound = bound

    def __class_getitem__(cls, item):
        items = (item,) if not isinstance(item, tuple) else item
        return cls(*items)

    def with_bound(self, new_bound):  # pragma: no cover
        return type(self)(new_bound)

    def check(self, value):  # pragma: no cover
        raise NotImplementedError()

    def codegen(self):
        return "{this}.check({arg})", {"this": self}

    def __typeorder__(self, other):
        if isinstance(other, DependentType):
            order = typeorder(self.bound, other.bound)
            if order is Order.SAME:
                if self < other:
                    return TypeRelationship(Order.MORE, matches=False)
                elif other < self:
                    return TypeRelationship(Order.LESS, matches=False)
                else:
                    return TypeRelationship(Order.NONE, matches=False)
            else:  # pragma: no cover
                return TypeRelationship(order, matches=False)
        elif (matches := subclasscheck(other, self.bound)) or subclasscheck(
            self.bound, other
        ):
            return TypeRelationship(Order.LESS, matches=matches)
        else:
            return TypeRelationship(Order.NONE, matches=False)

    def __lt__(self, other):
        return False

    def __or__(self, other):
        if not isinstance(other, DependentType):
            return NotImplemented
        return Or(self, other)

    def __and__(self, other):
        if not isinstance(other, DependentType):
            return NotImplemented
        return And(self, other)


class ParametrizedDependentType(DependentType):
    def __init__(self, *parameters, bound=None):
        super().__init__(
            self.default_bound(*parameters) if bound is None else bound
        )
        self.parameters = parameters

    @property
    def parameter(self):
        return self.parameters[0]

    def default_bound(self, *parameters):
        return None

    def with_bound(self, new_bound):
        return type(self)(*self.parameters, bound=new_bound)

    def __eq__(self, other):
        return (
            type(self) is type(other)
            and self.parameters == other.parameters
            and self.bound == other.bound
        )

    def __hash__(self):
        return hash(self.parameters) ^ hash(self.bound)

    def __str__(self):
        params = ", ".join(map(repr, self.parameters))
        return f"{type(self).__name__}({params})"

    __repr__ = __str__


class FuncDependentType(ParametrizedDependentType):
    def default_bound(self, *_):
        fn = type(self).func
        return normalize_type(
            list(inspect.signature(fn).parameters.values())[0].annotation, fn
        )

    def check(self, value):
        return type(self).func(value, *self.parameters)


def dependent_check(fn):
    t = type(fn.__name__, (FuncDependentType,), {"func": fn})
    if len(inspect.signature(fn).parameters) == 1:
        t = t()
    return t


class Equals(ParametrizedDependentType):
    keyable_type = True

    def default_bound(self, *parameters):
        return type(parameters[0])

    def check(self, value):
        return value in self.parameters

    @classmethod
    def keygen(cls):
        return "{arg}"

    def get_keys(self):
        return [self.parameter]

    def codegen(self):
        if len(self.parameters) == 1:
            return "({arg} == {p})", {"p": self.parameter}
        else:
            return "({arg} in {ps})", {"ps": self.parameters}


@dependent_check
def HasKeys(value: Mapping, *keys):
    return all(k in value for k in keys)


@dependent_check
def StartsWith(value: str, prefix):
    return value.startswith(prefix)


@dependent_check
def EndsWith(value: str, suffix):
    return value.endswith(suffix)


@dependent_check
def Regexp(value: str, regexp):
    return bool(re.search(pattern=regexp, string=value))


class Dependent:
    def __class_getitem__(cls, item):
        bound, dt = item
        if not isinstance(dt, DependentType):
            dt = dependent_check(dt)
        return dt.with_bound(bound)


class Or(DependentType):
    def __init__(self, *types, bound=None):
        self.types = types
        super().__init__(bound or self.default_bound())

    def default_bound(self):
        return Union[tuple([t.bound for t in self.types])]

    def check(self, value):
        return any(t.check(value) for t in self.types)


class And(DependentType):
    def __init__(self, *types, bound=None):
        self.types = types
        super().__init__(bound or self.default_bound())

    def default_bound(self):
        bounds = frozenset(t.bound for t in self.types)
        return Intersection[tuple(bounds)]

    def check(self, value):
        return all(t.check(value) for t in self.types)

    def __str__(self):
        return " & ".join(map(repr, self.types))

    __repr__ = __str__


if TYPE_CHECKING:  # pragma: no cover
    from typing import Annotated, TypeAlias

    T = TypeVar("T")
    A = TypeVar("A")
    Dependent: TypeAlias = Annotated[T, A]


__all__ = [
    "Dependent",
    "DependentType",
    "Equals",
    "HasKeys",
    "StartsWith",
    "EndsWith",
    "dependent_check",
]
