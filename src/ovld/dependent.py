import inspect
import re
from collections.abc import Callable as _Callable
from collections.abc import Mapping, Sequence
from functools import partial
from itertools import count
from typing import (
    TYPE_CHECKING,
    Any,
    Collection,
    TypeVar,
)

from .types import (
    Intersection,
    Order,
    clsstring,
    normalize_type,
    subclasscheck,
    typeorder,
)

_current = count()


def generate_checking_code(typ):
    if hasattr(typ, "codegen"):
        return typ.codegen()
    else:
        return CodeGen("isinstance({arg}, {this})", this=typ)


class CodeGen:
    def __init__(self, template, substitutions={}, **substitutions_kw):
        self.template = template
        self.substitutions = {**substitutions, **substitutions_kw}

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
        return CodeGen(self.template.format(**renamings), new_subs)


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
    bound_is_name = False

    def __new__(cls, *args, **kwargs):
        value = super().__new__(cls, cls.__name__, (), {})
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
        return CodeGen("{this}.check({arg})", this=self)

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

    __repr__ = __str__ = clsstring


class ParametrizedDependentType(DependentType):
    def __init__(self, *parameters, bound=None):
        super().__init__(
            self.default_bound(*parameters) if bound is None else bound
        )
        self.__args__ = self.parameters = parameters
        self.__origin__ = None
        self.__post_init__()

    def __post_init__(self):
        pass

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
        if self.bound_is_name:
            origin = self.bound
            bound = ""
        else:
            origin = self
            if self.bound != self.default_bound(*self.parameters):
                bound = f" < {clsstring(self.bound)}"
            else:
                bound = ""
        args = ", ".join(map(clsstring, self.__args__))
        return f"{origin.__name__}[{args}]{bound}"

    __repr__ = __str__


class FuncDependentType(ParametrizedDependentType):
    def default_bound(self, *_):
        return self._default_bound

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


def dependent_check(fn=None, bound_is_name=False):
    if fn is None:
        return partial(dependent_check, bound_is_name=bound_is_name)

    if isinstance(fn, type):
        params = inspect.signature(fn.check).parameters
        bound = normalize_type(
            list(inspect.signature(fn.check).parameters.values())[1].annotation,
            fn.check,
        )
        t = type(
            fn.__name__,
            (FuncDependentType,),
            {
                "bound_is_name": bound_is_name,
                "_default_bound": bound,
                **vars(fn),
            },
        )

    else:
        params = inspect.signature(fn).parameters
        bound = normalize_type(
            list(inspect.signature(fn).parameters.values())[0].annotation, fn
        )
        t = type(
            fn.__name__,
            (FuncDependentType,),
            {
                "func": fn,
                "bound_is_name": bound_is_name,
                "_default_bound": bound,
            },
        )
        if len(params) == 1:
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
            return CodeGen("({arg} == {p})", p=self.parameter)
        else:
            return CodeGen("({arg} in {ps})", ps=self.parameters)


class ProductType(ParametrizedDependentType):
    bound_is_name = True

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


@dependent_check(bound_is_name=True)
def SequenceFastCheck(value: Sequence, typ):
    return not value or isinstance(value[0], typ)


@dependent_check(bound_is_name=True)
def CollectionFastCheck(value: Collection, typ):
    for x in value:
        return isinstance(x, typ)
    else:
        return True


@dependent_check(bound_is_name=True)
def MappingFastCheck(value: Mapping, kt, vt):
    if not value:
        return True
    for k in value:
        break
    return isinstance(k, kt) and isinstance(value[k], vt)


@dependent_check
def Callable(fn: _Callable, argt, rett):
    from .core import Signature

    sig = Signature.extract(fn)
    return (
        sig.max_pos >= len(argt) >= sig.req_pos
        and not sig.req_names
        and all(subclasscheck(t1, t2) for t1, t2 in zip(argt, sig.types))
        and subclasscheck(sig.return_type, rett)
    )


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
class Regexp:
    def __post_init__(self):
        self.rx = re.compile(self.parameter)

    def check(self, value: str):
        return bool(self.rx.search(value))

    def codegen(self):
        return CodeGen("bool({rx}.search({arg}))", rx=self.rx)


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
