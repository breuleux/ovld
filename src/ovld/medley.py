import functools
import inspect
from copy import copy
from dataclasses import MISSING, dataclass, fields, make_dataclass, replace
from typing import Annotated, TypeVar, get_origin

from .core import Ovld, to_ovld
from .types import eval_annotation
from .utils import Named

ABSENT = Named("ABSENT")
CODEGEN = Named("CODEGEN")


class Combiner:
    def __init__(self, field=None):
        self.field = field

    def __set_name__(self, obj, field):
        self.field = field

    def get(self, cls):  # pragma: no cover
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

    def get(self, cls):
        return self.impl

    def include_sametype(self, other):
        self.impl = other.impl

    def juxtapose(self, impl):
        self.impl = impl


class ImplList(Combiner):
    def __init__(self, field=None, impls=None):
        super().__init__(field)
        self.impls = impls or []

    def copy(self):
        return type(self)(self.field, list(self.impls))

    def get(self, cls):
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
        self.ovld = ovld or Ovld(name=field, linkback=True)
        self.pending = []
        if field is not None:
            self.__set_name__(None, field)

    def __set_name__(self, obj, field):
        self.ovld.rename(field)

    def get(self, cls):
        self.ovld.specialization_self = cls
        for f, arg in self.pending:
            f(arg)
        self.pending.clear()
        if self.ovld.empty():
            return ABSENT
        self.ovld.invalidate()
        return self.ovld.dispatch

    def copy(self):
        return type(self)(self.field, self.ovld.copy(linkback=True))

    def include_sametype(self, other):
        self.ovld.add_mixins(other.ovld)

    def juxtapose(self, impl):
        if ov := to_ovld(impl, force=False):
            self.pending.append((self.ovld.add_mixins, ov))
        elif inspect.isfunction(impl):
            self.pending.append((self.ovld.register, impl))
        else:  # pragma: no cover
            raise TypeError("Expected a function or ovld.")


class medley_cls_dict(dict):
    def __init__(self, bases, default_combiner=None):
        if default_combiner is None:
            (default_combiner,) = {b._ovld_default_combiner for b in bases}
        super().__init__()
        self._combiners = {}
        self._default_combiner = default_combiner
        self.set_direct("_ovld_combiners", self._combiners)
        self.set_direct("_ovld_default_combiner", default_combiner)
        self._basic = set()
        for base in bases:
            for attr, combiner in getattr(base, "_ovld_combiners", {}).items():
                if attr in self._combiners:
                    self._combiners[attr].include(combiner)
                else:
                    self._combiners[attr] = combiner.copy()

    def set_direct(self, attr, value):
        super().__setitem__(attr, value)

    def __setitem__(self, attr, value):
        if attr == "__annotations__" or attr == "__annotate_func__":
            self.set_direct(attr, value)
            return

        if attr == "__init__":
            raise Exception("Do not define __init__ in a Medley, use __post_init__.")

        if isinstance(value, Combiner):
            value.__set_name__(None, attr)
            self._combiners[attr] = value
            return

        combiner = self._combiners.get(attr, None)
        if combiner is None:
            if to_ovld(value, force=False):
                combiner = BuildOvld(attr)
            elif inspect.isfunction(value):
                combiner = self._default_combiner(attr)
            else:
                combiner = KeepLast(attr)
            self._combiners[attr] = combiner

        combiner.juxtapose(value)

    def __missing__(self, attr):
        if attr in self._combiners:
            if (value := self._combiners[attr].get(None)) is not ABSENT:
                return value
        raise KeyError(attr)


def codegen_key(*instances):
    rval = {}
    for instance in instances:
        keyd = {name: getattr(instance, name) for name in type(instance)._ovld_codegen_fields}
        rval.update(keyd)
    return rval


def specialize(cls, key):
    ns = medley_cls_dict((cls,))
    new_t = MedleyMC(cls.__name__, (cls,), ns)
    new_t._ovld_specialization_parent = cls
    for k, v in key.items():
        setattr(new_t, k, v)
    cls._ovld_codegen_fields = list(key.keys())
    return new_t


def remap_field(dc_field, require_default=False):
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


class MedleyMC(type):
    def __subclasscheck__(cls, subclass):
        if getattr(cls, "_ovld_medleys", None):
            return all(issubclass(subclass, m) for m in cls._ovld_medleys)
        return super().__subclasscheck__(subclass)

    @classmethod
    def __prepare__(mcls, name, bases, default_combiner=None):
        return medley_cls_dict(bases, default_combiner=default_combiner)

    def __new__(mcls, name, bases, namespace, default_combiner=None):
        result = super().__new__(mcls, name, bases, namespace)
        for attr, combiner in result._ovld_combiners.items():
            if (value := combiner.get(result)) is not ABSENT:
                setattr(result, attr, value)
        dc = dataclass(result)
        dc._ovld_specialization_parent = None
        dc._ovld_specializations = {}
        dc._ovld_codegen_fields = [
            field.name
            for field in fields(dc)
            if (
                (t := eval_annotation(field.type, dc, {}, catch=True))
                and get_origin(t) is Annotated
                and CODEGEN in t.__metadata__
            )
        ]
        return dc

    def extend(cls, *others, extend_subclasses=True):
        if not others:  # pragma: no cover
            return cls
        all_fields = [(f.name, f.type, f) for f in fields(cls)]
        for other in others:
            all_fields += [(f.name, f.type, remap_field(f, True)) for f in fields(other)]
        melded = make_dataclass("_", fields=all_fields)
        for other in others:
            for k, v in vars(other).items():
                if k in ["__module__", "__firstlineno__", "__static_attributes__"]:
                    continue
                elif comb := cls._ovld_combiners.get(k):
                    comb.juxtapose(v)
                    setattr(cls, k, comb.get(cls))
                elif not k.startswith("_ovld_") and not k.startswith("__"):
                    setattr(cls, k, v)
        cls.__init__ = melded.__init__
        if extend_subclasses:
            for subcls in cls.__subclasses__():
                subothers = [o for o in others if not issubclass(subcls, o)]
                subcls.extend(*subothers, extend_subclasses=False)
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
                new_t = specialize(cls, keyd)
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


class Medley(metaclass=MedleyMC, default_combiner=BuildOvld):
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


_meld_classes_cache = {}


def meld_classes(classes):
    def key(cls):
        return getattr(cls, "_ovld_specialization_parent", None) or cls

    medleys = {}
    for cls in classes:
        medleys.update({key(x): x for x in getattr(cls, "_ovld_medleys", [cls])})
    for cls in classes:
        cls = key(cls)
        if not hasattr(cls, "_ovld_medleys"):
            for base in cls.mro():
                if base is not cls and base in medleys:
                    del medleys[base]

    medleys = tuple(medleys.values())
    if len(medleys) == 1:
        return medleys[0]

    cache_key = medleys
    if cache_key in _meld_classes_cache:
        return _meld_classes_cache[cache_key]

    cg_fields = set()
    dc_fields = []

    for base in medleys:
        cg_fields.update(base._ovld_codegen_fields)
        dc_fields.extend(
            (f.name, f.type, remap_field(f)) for f in base.__dataclass_fields__.values()
        )

    merged = medley_cls_dict(medleys)
    merged.set_direct("_ovld_codegen_fields", tuple(cg_fields))
    merged.set_direct("_ovld_medleys", tuple(medleys))
    merged.set_direct("__annotations__", {name: t for name, t, f in dc_fields})

    if "__qualname__" in merged._combiners:
        del merged._combiners["__qualname__"]

    result = make_dataclass(
        cls_name="+".join(sorted(c.__name__ for c in medleys)),
        bases=medleys,
        fields=dc_fields,
        kw_only=True,
        namespace=merged,
    )

    _meld_classes_cache[cache_key] = result
    return result


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
