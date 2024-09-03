import math
from typing import TYPE_CHECKING, TypeVar


class DependentType:
    def __init__(self, bound):
        self.bound = bound

    def with_bound(self, new_bound):  # pragma: no cover
        return type(self)(new_bound)

    def check(self, value):  # pragma: no cover
        raise NotImplementedError()

    def codegen(self):
        return "{this}.check({arg})", {"this": self}

    def __lt__(self, other):
        return False


def dependent_match(tup, args):
    for t, a in zip(tup, args):
        if isinstance(t, DependentType) and not t.check(a):
            return False
    return True


class ParametrizedDependentType(DependentType):
    def __init__(self, *parameters, bound=None):
        super().__init__(type(parameters[0]) if bound is None else bound)
        self.parameters = parameters

    @property
    def parameter(self):
        return self.parameters[0]

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


class Equals(ParametrizedDependentType):
    def check(self, value):
        return value == self.parameter

    def codegen(self):
        return "({arg} == {p})", {"p": self.parameter}


class StartsWith(ParametrizedDependentType):
    def check(self, value):
        return value.startswith(self.parameter)


class Bounded(ParametrizedDependentType):
    def check(self, value):
        min, max = self.parameters
        return min <= value <= max

    def __lt__(self, other):
        if type(other) is not type(self):
            return False
        smin, smax = self.parameters
        omin, omax = other.parameters
        return (smin < omin and smax >= omax) or (smin <= omin and smax > omax)


class HasKeys(ParametrizedDependentType):
    def check(self, value):
        return all(k in value for k in self.parameters)


class LengthRange(ParametrizedDependentType):
    def check(self, value):
        min, max = self.parameters
        return min <= len(value) <= max


def Length(n):
    return LengthRange(n, n)


def MinLength(n):
    return LengthRange(n, math.inf)


class dependent_check(DependentType):
    def __init__(self, check, bound=None):
        super().__init__(bound)
        self.check = check

    def with_bound(self, new_bound):
        return type(self)(self.check, new_bound)

    def __str__(self):
        return self.check.__name__

    __repr__ = __str__


@dependent_check
def Nonempty(value):
    return len(value) > 0


@dependent_check
def Truey(value):
    return bool(value)


@dependent_check
def Falsey(value):
    return not bool(value)


class Dependent:
    def __class_getitem__(cls, item):
        bound, dt = item
        if not isinstance(dt, DependentType):
            dt = dependent_check(dt)
        return dt.with_bound(bound)


if TYPE_CHECKING:  # pragma: no cover
    from typing import Annotated, TypeAlias

    T = TypeVar("T")
    A = TypeVar("A")
    Dependent: TypeAlias = Annotated[T, A]


__all__ = [
    "Dependent",
    "DependentType",
    "Equals",
    "StartsWith",
    "HasKeys",
    "LengthRange",
    "Length",
    "MinLength",
    "dependent_check",
    "Nonempty",
    "Truey",
    "Falsey",
]
