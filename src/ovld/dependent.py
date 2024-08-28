import math
from typing import TYPE_CHECKING, TypeVar


class DependentType:
    def __init__(self, bound):
        self.bound = bound

    def with_bound(self, new_bound):  # pragma: no cover
        return type(self)(new_bound)

    def check(self, value):  # pragma: no cover
        raise NotImplementedError()


def dependent_match(tup, args):
    for t, a in zip(tup, args):
        if isinstance(t, DependentType) and not t.check(a):
            return False
    return True


class SingleParameterDependentType(DependentType):
    def __init__(self, parameter, bound=None):
        super().__init__(type(parameter) if bound is None else bound)
        self.parameter = parameter

    def with_bound(self, new_bound):
        return type(self)(self.parameter, new_bound)

    def __eq__(self, other):
        return (
            type(self) is type(other)
            and self.parameter == other.parameter
            and self.bound == other.bound
        )

    def __hash__(self):
        return hash(self.parameter) ^ hash(self.bound)

    def __str__(self):
        return f"{type(self).__name__}({self.parameter!r})"

    __repr__ = __str__


class Equals(SingleParameterDependentType):
    def check(self, value):
        return value == self.parameter


class StartsWith(SingleParameterDependentType):
    def check(self, value):
        return value.startswith(self.parameter)


class HasKeys(SingleParameterDependentType):
    def __init__(self, *keys, bound=dict):
        super().__init__(keys, bound)

    def with_bound(self, new_bound):
        return type(self)(*self.parameter, bound=new_bound)

    def check(self, value):
        print(value, self.parameter)
        return all(k in value for k in self.parameter)


class LengthRange(SingleParameterDependentType):
    def __init__(self, min, max, bound=object):
        super().__init__((min, max), bound)

    def with_bound(self, new_bound):
        return type(self)(*self.parameter, new_bound)

    def check(self, value):
        min, max = self.parameter
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
    def __class_getitem__(self, item):
        bound, dt = item
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
