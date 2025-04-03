import functools
import inspect
from copy import copy
from dataclasses import MISSING, dataclass, fields, make_dataclass, replace
from typing import Annotated, TypeVar, get_origin

from .core import Ovld, to_ovld
from .utils import Named

CODEGEN = Named("CODEGEN")


_ignore = [
    "__annotations__",
    "__class__",
    "__dataclass_fields__",
    "__dataclass_params__",
    "__delattr__",
    "__dict__",
    "__dir__",
    "__doc__",
    "__eq__",
    "__firstlineno__",
    "__format__",
    "__ge__",
    "__getattribute__",
    "__getstate__",
    "__gt__",
    "__hash__",
    "__init__",
    "__init_subclass__",
    "__le__",
    "__lt__",
    "__match_args__",
    "__module__",
    "__ne__",
    "__new__",
    "__reduce__",
    "__reduce_ex__",
    "__replace__",
    "__repr__",
    "__setattr__",
    "__sizeof__",
    "__static_attributes__",
    "__str__",
    "__subclasshook__",
    "__weakref__",
    "_ovld_codegen_fields",
    "_ovld_specialization_parent",
    "_ovld_specializations",
]


class Combiner:
    @staticmethod
    def extract(attr, value):
        combiner = value
        if not isinstance(value, Combiner):
            combiner = getattr(value, "_medley_combiner", None)
            if combiner is None:
                if inspect.isfunction(value) or isinstance(value, Ovld):
                    return OvldCombiner(attr, value)
                else:
                    return KeepLast(attr, value)
        return combiner

    def get(self):  # pragma: no cover
        raise NotImplementedError()

    def copy(self):  # pragma: no cover
        raise NotImplementedError()

    def override(self, new_impl):
        return self.juxtapose(new_impl)

    def juxtapose(self, impl):  # pragma: no cover
        raise NotImplementedError()


class KeepLast(Combiner):
    def __init__(self, field, impl):
        self.field = field
        self.impl = impl

    def get(self):
        return self.impl

    def copy(self):
        return self.impl

    def juxtapose(self, impl):
        return impl


class ImplList(Combiner):
    def __init__(self, field, impl):
        self.field = field
        self.impls = impl if isinstance(impl, list) else [impl]

    def copy(self):
        return type(self)(self.field, list(self.impls)).get()

    def juxtapose(self, impl):
        self.impls.append(impl)
        return self.get()


class RunAll(ImplList):
    def get(_self):
        @functools.wraps(_self.impls[0])
        def run_all(self, *args, **kwargs):
            for impl in _self.impls:
                impl(self, *args, **kwargs)

        run_all._medley_combiner = _self
        return run_all


class ReduceAll(ImplList):
    def get(_self):
        @functools.wraps(_self.impls[0])
        def reduce_all(self, x, *args, **kwargs):
            result = _self.impls[0](self, x, *args, **kwargs)
            for impl in _self.impls[1:]:
                result = impl(self, result, *args, **kwargs)
            return result

        reduce_all._medley_combiner = _self
        return reduce_all


class ChainAll(ImplList):
    def get(_self):
        @functools.wraps(_self.impls[0])
        def chain_all(self, *args, **kwargs):
            self = _self.impls[0](self, *args, **kwargs)
            for impl in _self.impls[1:]:
                self = impl(self, *args, **kwargs)
            return self

        chain_all._medley_combiner = _self
        return chain_all


class OvldCombiner(Combiner):
    def __init__(self, field, impl):
        self.field = field
        self.ovld = Ovld()
        self.ovld.rename(field)
        self.juxtapose(impl)
        self.ovld.dispatch._medley_combiner = self

    def get(self):
        return self.ovld.dispatch

    def copy(self):
        return OvldCombiner(self.field, self.ovld).get()

    def juxtapose(self, impl):
        if ov := to_ovld(impl, force=False):
            self.ovld.add_mixins(ov)
        elif inspect.isfunction(impl):
            self.ovld.register(impl)
        else:  # pragma: no cover
            raise TypeError("Expected a function or ovld.")
        return self.get()


class medley_cls_dict(dict):
    def __init__(self, bases):
        super().__init__()
        self._basic = set()
        for base in bases:
            for k, v in vars(base).items():
                if k not in _ignore:
                    self.set_from_base(k, v)

    def existing(self, attr):
        if attr in self:
            return Combiner.extract(attr, self[attr])
        else:
            return None

    def set_from_base(self, attr, value):
        if existing := self.existing(attr):
            value = existing.juxtapose(value)
        else:
            value = Combiner.extract(attr, value).copy()
        super().__setitem__(attr, value)
        self._basic.add(attr)

    def set_direct(self, attr, value):
        super().__setitem__(attr, value)

    def __setitem__(self, attr, value):
        if attr == "__init__":
            raise Exception("Do not define __init__ in a Medley, use __post_init__.")

        if existing := self.existing(attr):
            if attr in self._basic:
                value = existing.override(value)
            else:
                value = existing.juxtapose(value)
        else:
            value = Combiner.extract(attr, value).get()

        self._basic.discard(attr)
        super().__setitem__(attr, value)


def codegen_key(*instances):
    rval = {}
    for instance in instances:
        keyd = {name: getattr(instance, name) for name in type(instance)._ovld_codegen_fields}
        rval.update(keyd)
    return rval


def specialize(cls, key, base=type):
    new_t = base(cls.__name__, (cls,), {})
    new_t._ovld_specialization_parent = cls
    for k, v in key.items():
        setattr(new_t, k, v)
    for k, v in vars(cls).items():
        if v := to_ovld(v, force=False):
            v = v.copy()
            v.specialization_self = new_t
            setattr(new_t, k, v)
    cls._ovld_codegen_fields = list(key.keys())
    return new_t


class MedleyMC(type):
    @classmethod
    def __prepare__(metacls, name, bases):
        return medley_cls_dict(bases)

    def __new__(mcls, name, bases, namespace):
        result = super().__new__(mcls, name, bases, namespace)
        dc = dataclass(result)
        dc._ovld_specialization_parent = None
        dc._ovld_specializations = {}
        dc._ovld_codegen_fields = [
            field.name
            for field in fields(dc)
            if (
                field.type
                and get_origin(field.type) is Annotated
                and CODEGEN in field.type.__metadata__
            )
        ]
        for val in namespace.values():
            if o := to_ovld(val, force=False):
                o.specialization_self = dc
        return dc

    def extend(cls, *others):
        melded = meld_classes((cls, *others), require_defaults=True)
        for k, v in vars(melded).items():
            setattr(cls, k, v)
        # TODO: invalidate all cache entries involving this class
        return cls

    def __add__(cls, other):
        return meld_classes((cls, other))

    def __iadd__(cls, other):
        return cls.extend(other)

    def __sub__(cls, other):
        return unmeld_classes(cls, other)

    def __call__(cls, *args, **kwargs):
        made = super().__call__(*args, **kwargs)
        if cls._ovld_codegen_fields and (keyd := codegen_key(made)):
            cls = cls._ovld_specialization_parent or cls
            key = tuple(sorted(keyd.items()))
            if key in cls._ovld_specializations:
                new_t = cls._ovld_specializations[key]
            else:
                new_t = specialize(cls, keyd, base=MedleyMC)
                cls._ovld_specializations[key] = new_t
            obj = object.__new__(new_t)
            obj.__dict__.update(made.__dict__)
            return obj
        else:
            return made


def use_combiner(combiner):
    def deco(fn):
        fn._medley_combiner = combiner(fn.__name__, fn)
        return fn

    return deco


class Medley(metaclass=MedleyMC):
    @use_combiner(RunAll)
    def __post_init__(self):
        pass

    @use_combiner(KeepLast)
    def __add__(self, other):
        if isinstance(self, type(other)) and not type(self)._ovld_codegen_fields:
            return replace(self, **vars(other))
        else:
            return meld([self, other])

    @use_combiner(KeepLast)
    def __sub__(self, other):
        return unmeld(self, other)


def unmeld_classes(main: type, exclude: type):
    classes = tuple(c for c in main.__bases__ if c is not exclude)
    return meld_classes(classes)


@functools.cache
def meld_classes(classes, require_defaults=False):
    def remap_field(dc_field, require_default):
        if require_default:
            if dc_field.default is MISSING:
                # NOTE: we do not accept default_factory, because we need the default value to be set
                # in the class so that existing instances of classes[0] can see it.
                raise TypeError(
                    f"Dataclass field '{dc_field.name}' must have a default value (not a default_factory) in order to be melded in."
                )
        dc_field = copy(dc_field)
        dc_field.kw_only = True
        return dc_field

    cg_fields = set()
    dc_fields = []

    for base in classes:
        rqdef = require_defaults and base is not classes[0]
        for cls in getattr(base, "_ovld_medley", [base]):
            cg_fields.update(cls._ovld_codegen_fields)
            dc_fields.extend(
                (f.name, f.type, remap_field(f, rqdef))
                for f in cls.__dataclass_fields__.values()
            )

    merged = medley_cls_dict(classes)
    merged.set_direct("_ovld_medley", classes)
    merged.set_direct("_ovld_codegen_fields", tuple(cg_fields))

    return make_dataclass(
        cls_name="+".join(c.__name__ for c in classes),
        bases=classes,
        fields=dc_fields,
        kw_only=True,
        namespace=merged,
    )


@functools.cache
def meld_classes_with_key(classes, key):
    key = dict(key)
    typ = meld_classes(classes)
    if not key:
        return typ
    else:
        return specialize(typ, key)


def meld(objects):
    key = codegen_key(*objects)
    classes = tuple(type(o) for o in objects)
    cls = meld_classes_with_key(classes, tuple(key.items()))
    obj = object.__new__(cls)
    for o in objects:
        for k, v in vars(o).items():
            setattr(obj, k, v)
    return obj


def unmeld(obj: object, exclude: type):
    if type(obj)._ovld_codegen_fields:  # pragma: no cover
        raise TypeError("Cannot unmeld an object with codegen fields")
    cls = unmeld_classes(type(obj), exclude)
    values = {}
    excluded = exclude.__dataclass_fields__
    for f in cls.__dataclass_fields__.values():
        if f.name not in excluded:
            values[f.name] = getattr(obj, f.name)
    return cls(**values)


T = TypeVar("T")
CodegenParameter = Annotated[T, CODEGEN]
