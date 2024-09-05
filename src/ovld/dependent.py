import math
from typing import TYPE_CHECKING, TypeVar


class DependentType:
    exclusive_type = False
    keyable_type = False

    def __init__(self, bound):
        self.bound = bound

    def with_bound(self, new_bound):  # pragma: no cover
        return type(self)(new_bound)

    def check(self, value):  # pragma: no cover
        raise NotImplementedError()

    def codegen(self):
        return "{this}.check({arg})", {"this": self}

    def __typeorder__(self, other):
        if not isinstance(other, DependentType):
            return Order.NONE
        order = typeorder(self.bound, other.bound)
        if order is Order.SAME:
            if self < other:
                return Order.MORE
            elif other < self:
                return Order.LESS
            else:
                return Order.NONE
        else:
            return order

    def __lt__(self, other):
        return False


def dependent_match(tup, args):
    for t, a in zip(tup, args):
        if isinstance(t, tuple):
            t = t[1]
            a = a[1]
        if isinstance(t, DependentType) and not t.check(a):
            return False
    return True


class ParametrizedDependentType(DependentType):
    def __init__(self, *parameters, bound=None):
        super().__init__(
            self.default_bound(*parameters) if bound is None else bound
        )
        self.parameters = parameters

    def __class_getitem__(cls, item):
        items = (item,) if not isinstance(item, tuple) else item
        return cls(*items)

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


class Equals(ParametrizedDependentType):
    # exclusive_type = True
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


class StartsWith(ParametrizedDependentType):
    def default_bound(self, *parameters):
        return type(parameters[0])

    def check(self, value):
        return value.startswith(self.parameter)


class Bounded(ParametrizedDependentType):
    def default_bound(self, *parameters):
        return type(parameters[0])

    def check(self, value):
        min, max = self.parameters
        return min <= value <= max

    def __lt__(self, other):
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
