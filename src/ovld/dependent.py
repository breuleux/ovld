import inspect
import re
from dataclasses import dataclass
from itertools import count
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Mapping,
    Sequence,
    TypeVar,
    get_args,
)

from .types import (
    Intersection,
    Order,
    normalize_type,
    subclasscheck,
    typeorder,
)

_current = count()


def generate_checking_code(typ):
    if hasattr(typ, "codegen"):
        return typ.codegen()
    elif isinstance(typ, UnionType):
        template = " or ".join("{}" for t in get_args(typ))
        return combine(
            template, [generate_checking_code(t) for t in get_args(typ)]
        )
    else:
        return CodeGen("isinstance({arg}, {this})", {"this": typ})


@dataclass
class CodeGen:
    template: str
    substitutions: dict

    def mangle(self):
        renamings = {
            k: f"{{{k}__{next(_current)}}}" for k in self.substitutions
        }
        renamings["arg"] = "{arg}"
        new_subs = {
            newk[1:-1]: self.substitutions[k]
            for k, newk in renamings.items()
            if k in self.substitutions
        }
        return CodeGen(
            template=self.template.format(**renamings),
            substitutions=new_subs,
        )


def combine(master_template, args):
    fmts = []
    subs = {}
    for cg in args:
        mangled = cg.mangle()
        fmts.append(mangled.template)
        subs.update(mangled.substitutions)
    return CodeGen(master_template.format(*fmts), subs)


def is_dependent(t):
    if isinstance(t, DependentType):
        return True
    elif any(is_dependent(subt) for subt in getattr(t, "__args__", ())):
        return True
    return False


class DependentType(type):
    exclusive_type = False
    keyable_type = False

    @classmethod
    def make_name(cls, *args, **kwargs):  # pragma: no cover
        return cls.__name__

    def __new__(cls, *args, **kwargs):
        name = cls.make_name(*args, **kwargs)
        value = super().__new__(cls, name, (), {})
        return value

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
        return CodeGen("{this}.check({arg})", {"this": self})

    def __type_order__(self, other):
        if isinstance(other, DependentType):
            order = typeorder(self.bound, other.bound)
            if order is Order.SAME:
                # It isn't fully deterministic which of these will be called
                # because of set ordering between the types we compare
                if self < other:  # pragma: no cover
                    return Order.LESS
                elif other < self:  # pragma: no cover
                    return Order.MORE
                else:
                    return Order.NONE
            else:  # pragma: no cover
                return order
        elif subclasscheck(other, self.bound) or subclasscheck(
            self.bound, other
        ):
            return Order.LESS
        else:
            return Order.NONE

    def __is_supertype__(self, other):
        if isinstance(other, DependentType):
            return False
        elif subclasscheck(other, self.bound):
            return True
        else:
            return False

    def __instancecheck__(self, other):
        return isinstance(other, self.bound) and self.check(other)

    def __lt__(self, other):
        return False

    def __and__(self, other):
        return Intersection[self, other]

    def __rand__(self, other):
        return Intersection[other, self]


class ParametrizedDependentType(DependentType):
    @classmethod
    def make_name(cls, *parameters, bound=None):
        params = ", ".join(map(repr, parameters))
        return f"{cls.__name__}({params})"

    def __init__(self, *parameters, bound=None):
        super().__init__(
            self.default_bound(*parameters) if bound is None else bound
        )
        self.__args__ = self.parameters = parameters

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

    def __lt__(self, other):
        if len(self.parameters) != len(other.parameters):
            return False
        p1g = sum(
            p1 is Any and p2 is not Any
            for p1, p2 in zip(self.parameters, other.parameters)
        )
        p2g = sum(
            p2 is Any and p1 is not Any
            for p1, p2 in zip(self.parameters, other.parameters)
        )
        return p2g and not p1g

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
            return CodeGen("({arg} == {p})", {"p": self.parameter})
        else:
            return CodeGen("({arg} in {ps})", {"ps": self.parameters})


class ProductType(ParametrizedDependentType):
    def default_bound(self, *subtypes):
        return tuple

    def check(self, value):
        return (
            isinstance(value, tuple)
            and len(value) == len(self.parameters)
            and all(isinstance(x, t) for x, t in zip(value, self.parameters))
        )

    def codegen(self):
        checks = ["len({arg}) == {n}"]
        params = {"n": len(self.parameters)}
        for i, p in enumerate(self.parameters):
            checks.append(f"isinstance({{arg}}[{i}], {{p{i}}})")
            params[f"p{i}"] = p
        return CodeGen(" and ".join(checks), params)

    def __type_order__(self, other):
        if isinstance(other, ProductType):
            if len(other.parameters) == len(self.parameters):
                return Order.merge(
                    typeorder(a, b)
                    for a, b in zip(self.parameters, other.parameters)
                )
            else:
                return Order.NONE
        else:
            return NotImplemented


@dependent_check
def SequenceFastCheck(value: Sequence, typ):
    return isinstance(value, Sequence) and (
        not value or isinstance(value[0], typ)
    )


@dependent_check
def MappingFastCheck(value: Mapping, kt, vt):
    if not isinstance(value, Mapping):
        return False
    if not value:
        return True
    for k in value:
        break
    return isinstance(k, kt) and isinstance(value[k], vt)


@dependent_check
def HasKey(value: Mapping, *keys):
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


if TYPE_CHECKING:  # pragma: no cover
    from typing import Annotated, TypeAlias

    T = TypeVar("T")
    A = TypeVar("A")
    Dependent: TypeAlias = Annotated[T, A]


__all__ = [
    "Dependent",
    "DependentType",
    "Equals",
    "HasKey",
    "StartsWith",
    "EndsWith",
    "dependent_check",
]
