import functools
import inspect
from collections import defaultdict
from copy import copy
from dataclasses import MISSING, dataclass, fields, make_dataclass
from typing import Annotated, get_origin

from .core import Ovld, is_ovld, to_ovld
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
    "_ovld_is_specialized",
    "_ovld_specializations",
]


class medley_cls_dict(dict):
    def __setitem__(self, attr, value):
        if attr in self and is_ovld(prev := self[attr]):
            prev = to_ovld(prev)
            prev.register(value)
            return
        elif inspect.isfunction(value):
            value = to_ovld(value)
        super().__setitem__(attr, value.dispatch if isinstance(value, Ovld) else value)


def codegen_key(*instances):
    rval = {}
    for instance in instances:
        keyd = {name: getattr(instance, name) for name in type(instance)._ovld_codegen_fields}
        rval.update(keyd)
    return rval


def specialize(cls, key, base=type):
    new_t = base(cls.__name__, (cls,), {})
    new_t._ovld_is_specialized = True
    for k, v in key.items():
        setattr(new_t, k, v)
    for k, v in vars(cls).items():
        if v := to_ovld(v, force=False):
            v = v.copy()
            v.specialization_self = new_t
            setattr(new_t, k, v)
    cls._ovld_codegen_fields = list(key.keys())
    return new_t


class MixerMC(type):
    @classmethod
    def __prepare__(metacls, name, bases):
        return medley_cls_dict()

    def __new__(mcls, name, bases, namespace):
        result = super().__new__(mcls, name, bases, namespace)
        dc = dataclass(result)
        dc._ovld_is_specialized = False
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

    def __call__(cls, *args, **kwargs):
        made = super().__call__(*args, **kwargs)
        if not cls._ovld_is_specialized and (keyd := codegen_key(made)):
            key = tuple(sorted(keyd.items()))
            if key in cls._ovld_specializations:
                new_t = cls._ovld_specializations[key]
            else:
                new_t = specialize(cls, keyd, base=MixerMC)
                cls._ovld_specializations[key] = new_t
            obj = object.__new__(new_t)
            obj.__dict__.update(made.__dict__)
            return obj
        else:
            return made


class Mixer(metaclass=MixerMC):
    def __add__(self, other):
        return meld([self, other])


def merge_implementations(name, impls):
    if name == "__post_init__":

        def __post_init__(self):
            for impl in impls:
                impl(self)

        return __post_init__
    elif all(impl == impls[0] for impl in impls[1:]):
        return impls[0]
    elif all(is_ovld(impl) for impl in impls):
        mixins = [to_ovld(impl) for impl in impls]
        return Ovld(name=name, mixins=mixins)
    else:
        raise TypeError(f"Cannot merge implementations for '{name}'.")


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

    options = defaultdict(list)
    cg_fields = set()
    dc_fields = []

    for base in classes:
        rqdef = require_defaults and base is not classes[0]
        for cls in getattr(base, "_ovld_medley", [base]):
            for fld, obj in vars(cls).items():
                if fld in _ignore:
                    continue
                options[fld].append(obj)
            cg_fields.update(cls._ovld_codegen_fields)
            dc_fields.extend(
                (f.name, f.type, remap_field(f, rqdef))
                for f in cls.__dataclass_fields__.values()
            )

    merged = {}
    for name, impls in options.items():
        merged[name] = merge_implementations(name, impls)

    merged["_ovld_medley"] = classes
    merged["_ovld_codegen_fields"] = tuple(cg_fields)

    return make_dataclass(
        cls_name="+".join(c.__name__ for c in classes),
        bases=(Mixer,),
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
