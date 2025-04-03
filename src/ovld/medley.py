import functools
import inspect
from copy import copy
from dataclasses import MISSING, dataclass, fields, make_dataclass, replace
from typing import Annotated, TypeVar, get_origin

from .core import Ovld, to_ovld
from .utils import Named

ABSENT = Named("ABSENT")
CODEGEN = Named("CODEGEN")


class Combiner:
    def __init__(self, field=None):
        self.field = field

    def __set_name__(self, obj, field):
        self.field = field

    def get(self):  # pragma: no cover
        raise NotImplementedError()

    def copy(self):
        return type(self)(self.field)

    def include(self, other):
        if type(self) is not type(other):
            raise TypeError("Cannot merge different combiner classes.")
        self.include_sametype(other)

    def include_sametype(self, other):  # pragma: no cover
        pass

    def juxtapose(self, impl):  # pragma: no cover
        raise NotImplementedError()


class KeepLast(Combiner):
    def __init__(self, field=None):
        super().__init__(field)
        self.impl = ABSENT

    def get(self):
        return self.impl

    def include_sametype(self, other):
        self.impl = other.impl

    def juxtapose(self, impl):
        self.impl = impl
        return self.get()


class ImplList(Combiner):
    def __init__(self, field=None, impls=None):
        super().__init__(field)
        self.impls = impls or []

    def copy(self):
        return type(self)(self.field, self.impls)

    def get(self):
        if not self.impls:
            return ABSENT
        rval = self.wrap()
        return functools.wraps(self.impls[0])(rval)

    def wrap(self):  # pragma: no cover
        raise NotImplementedError()

    def include_sametype(self, other):
        self.impls += other.impls

    def juxtapose(self, impl):
        self.impls.append(impl)
        return self.get()


class RunAll(ImplList):
    def wrap(_self):
        def run_all(self, *args, **kwargs):
            for impl in _self.impls:
                impl(self, *args, **kwargs)

        return run_all


class ReduceAll(ImplList):
    def wrap(_self):
        def reduce_all(self, x, *args, **kwargs):
            result = _self.impls[0](self, x, *args, **kwargs)
            for impl in _self.impls[1:]:
                result = impl(self, result, *args, **kwargs)
            return result

        return reduce_all


class ChainAll(ImplList):
    def wrap(_self):
        def chain_all(self, *args, **kwargs):
            self = _self.impls[0](self, *args, **kwargs)
            for impl in _self.impls[1:]:
                self = impl(self, *args, **kwargs)
            return self

        return chain_all


class BuildOvld(Combiner):
    def __init__(self, field=None, ovld=None):
        super().__init__(field)
        self.ovld = ovld or Ovld()
        if field is not None:
            self.__set_name__(None, field)

    def __set_name__(self, obj, field):
        self.ovld.rename(field)

    def get(self):
        if not self.ovld.defns:
            return ABSENT
        return self.ovld.dispatch

    def copy(self):
        return type(self)(self.field, self.ovld.copy())

    def include_sametype(self, other):
        self.ovld.add_mixins(other.ovld)

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
        self._combiners = {}
        self.set_direct("_ovld_combiners", self._combiners)
        self._basic = set()
        for base in bases:
            for attr, combiner in getattr(base, "_ovld_combiners", {}).items():
                if attr in self._combiners:
                    self._combiners[attr].include(combiner)
                else:
                    self._combiners[attr] = combiner.copy()
        for attr, combiner in self._combiners.items():
            self.set_direct(attr, combiner.get())

    def set_direct(self, attr, value):
        if value is ABSENT:
            return
        super().__setitem__(attr, value)

    def __setitem__(self, attr, value):
        if attr == "__init__":
            raise Exception("Do not define __init__ in a Medley, use __post_init__.")

        if isinstance(value, Combiner):
            value.__set_name__(None, attr)
            self._combiners[attr] = value
            self.set_direct(attr, value.get())
            return

        combiner = self._combiners.get(attr, None)
        if combiner is None:
            if inspect.isfunction(value) or isinstance(value, Ovld):
                combiner = BuildOvld(attr)
            else:
                combiner = KeepLast(attr)
            self._combiners[attr] = combiner

        value = combiner.juxtapose(value)
        self.set_direct(attr, value)


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
        cmb = combiner(fn.__name__)
        cmb.juxtapose(fn)
        return cmb

    return deco


class Medley(metaclass=MedleyMC):
    __post_init__ = RunAll()
    __add__ = KeepLast()
    __sub__ = KeepLast()

    def __add__(self, other):
        if isinstance(self, type(other)) and not type(self)._ovld_codegen_fields:
            return replace(self, **vars(other))
        else:
            return meld([self, other])

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
