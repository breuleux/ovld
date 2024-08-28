"""Utilities to overload functions for multiple types."""

import inspect
import itertools
import sys
import textwrap
import typing
from functools import partial

from .recode import Conformer, rename_function
from .typemap import MultiTypeMap, is_type_of_type
from .utils import BOOTSTRAP, keyword_decorator

try:
    from types import UnionType
except ImportError:  # pragma: no cover
    UnionType = None


def _fresh(t):
    """Returns a new subclass of type t.

    Each Ovld corresponds to its own class, which allows for specialization of
    methods.
    """
    return type(t.__name__, (t,), {})


@keyword_decorator
def _setattrs(fn, **kwargs):
    for k, v in kwargs.items():
        setattr(fn, k, v)
    return fn


@keyword_decorator
def _compile_first(fn, rename=None):
    def deco(self, *args, **kwargs):
        self.compile()
        method = getattr(self, fn.__name__)
        assert method is not deco
        return method(*args, **kwargs)

    def setalt(alt):
        deco._alt = alt
        return None

    deco.setalt = setalt
    deco._replace_by = fn
    deco._alt = None
    deco._rename = rename
    return deco


class _Ovld:
    """Overloaded function.

    A function can be added with the `register` method. One of its parameters
    should be annotated with a type, but only one, and every registered
    function should annotate the same parameter.

    Arguments:
        mixins: A list of Ovld instances that contribute functions to this
            Ovld.
        type_error: The error type to raise when no function can be found to
            dispatch to (default: TypeError).
        name: Optional name for the Ovld. If not provided, it will be
            gotten automatically from the first registered function or
            dispatch.
        mapper: Class implementing a mapping interface from a tuple of
            types to a handler (default: MultiTypeMap).
        linkback: Whether to keep a pointer in the parent mixins to this
            ovld so that updates can be propagated. (default: False)
        allow_replacement: Allow replacing a method by another with the
            same signature. (default: True)
    """

    def __init__(
        self,
        *,
        type_error=TypeError,
        mixins=[],
        bootstrap=None,
        name=None,
        mapper=MultiTypeMap,
        linkback=False,
        allow_replacement=True,
    ):
        """Initialize an Ovld."""
        self._compiled = False
        self.maindoc = None
        self.mapper = mapper
        self.linkback = linkback
        self.children = []
        self.type_error = type_error
        self.allow_replacement = allow_replacement
        self.bootstrap_class = OvldCall
        if isinstance(bootstrap, type):
            self.bootstrap_class = bootstrap
            self.bootstrap = True
        else:
            self.bootstrap = bootstrap
        self.name = name
        self.__name__ = name
        self._defns = {}
        self._locked = False
        self.mixins = []
        self.add_mixins(*mixins)
        self.ocls = _fresh(self.bootstrap_class)
        self._make_signature()

    @property
    def defns(self):
        defns = {}
        for mixin in self.mixins:
            defns.update(mixin.defns)
        defns.update(self._defns)
        return defns

    def lock(self):
        self._locked = True

    def _attempt_modify(self):
        if self._locked:
            raise Exception(f"ovld {self} is locked for modifications")

    def add_mixins(self, *mixins):
        self._attempt_modify()
        for mixin in mixins:
            if self.linkback:
                mixin.children.append(self)
            if mixin._defns:
                assert mixin.bootstrap is not None
                if self.bootstrap is None:
                    self.bootstrap = mixin.bootstrap
                assert mixin.bootstrap is self.bootstrap
        self.mixins += mixins

    def _sig_string(self, type_tuple):
        def clsname(cls):
            if cls is object:
                return "*"
            elif is_type_of_type(cls):
                arg = clsname(cls.__args__[0])
                return f"type[{arg}]"
            elif hasattr(cls, "__name__"):
                return cls.__name__
            else:
                return repr(cls)

        return ", ".join(map(clsname, type_tuple))

    def _key_error(self, key, possibilities=None):
        typenames = self._sig_string(key)
        if not possibilities:
            return self.type_error(
                f"No method in {self} for argument types [{typenames}]"
            )
        else:
            hlp = ""
            for p, prio, spc in possibilities:
                hlp += f"* {p.__name__}  (priority: {prio}, specificity: {list(spc)})\n"
            return self.type_error(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                f"Candidates are:\n{hlp}"
                "Note: you can use @ovld(priority=X) to give higher priority to an overload."
            )

    def rename(self, name):
        """Rename this Ovld."""
        self.name = name
        self.__name__ = name
        self._make_signature()

    def _make_signature(self):
        """Make the __doc__ and __signature__."""

        def modelA(*args, **kwargs):  # pragma: no cover
            pass

        def modelB(self, *args, **kwargs):  # pragma: no cover
            pass

        seen = set()
        doc = (
            f"{self.maindoc}\n"
            if self.maindoc
            else f"Ovld with {len(self.defns)} methods.\n\n"
        )
        for key, fn in self.defns.items():
            if fn in seen:
                continue
            seen.add(fn)
            fndef = inspect.signature(fn)
            fdoc = fn.__doc__
            if not fdoc or fdoc == self.maindoc:
                doc += f"    ``{self.__name__}{fndef}``\n\n"
            else:
                if not fdoc.strip(" ").endswith("\n"):
                    fdoc += "\n"
                fdoc = textwrap.indent(fdoc, " " * 8)
                doc += f"    ``{self.__name__}{fndef}``\n{fdoc}\n"
        self.__doc__ = doc
        if self.bootstrap:
            self.__signature__ = inspect.signature(modelB)
        else:
            self.__signature__ = inspect.signature(modelA)

    def _set_attrs_from(self, fn):
        """Inherit relevant attributes from the function."""
        if self.bootstrap is None:
            sign = inspect.signature(fn)
            params = list(sign.parameters.values())
            if params and params[0].name == "self":
                self.bootstrap = True
            else:
                self.bootstrap = False

        if self.name is None:
            self.name = f"{fn.__module__}.{fn.__qualname__}"
            self.maindoc = fn.__doc__
            if self.maindoc and not self.maindoc.strip(" ").endswith("\n"):
                self.maindoc += "\n"
            self.__name__ = fn.__name__
            self.__qualname__ = fn.__qualname__
            self.__module__ = fn.__module__

    def _maybe_rename(self, fn):
        if hasattr(fn, "rename"):
            return rename_function(fn, f"{self.__name__}.{fn.rename}")
        else:
            return fn

    def compile(self):
        """Finalize this overload.

        This will populate the type maps and replace the functions decorated
        with _compile_first (__call__, __get__, etc.) with versions that assume
        the ovld has been compiled.

        This will also lock this ovld's parent mixins to prevent their
        modification.
        """
        for mixin in self.mixins:
            if self not in mixin.children:
                mixin.lock()
        self._compiled = True
        self.map = self.mapper(key_error=self._key_error)

        cls = type(self)
        if self.name is None:
            self.name = self.__name__ = f"ovld{id(self)}"

        name = self.__name__

        # Replace the appropriate functions by their final behavior
        for method in dir(cls):
            value = getattr(cls, method)
            repl = getattr(value, "_replace_by", None)
            if repl:
                if self.bootstrap and value._alt:
                    repl = value._alt
                repl = self._maybe_rename(repl)
                setattr(cls, method, repl)

        target = self.ocls if self.bootstrap else cls

        # Rename the dispatch
        target.__call__ = rename_function(target.__call__, f"{name}.dispatch")

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

    @_compile_first
    def resolve(self, *args):
        """Find the correct method to call for the given arguments."""
        return self.map[tuple(map(self.map.transform, args))]

    def register_signature(self, key, orig_fn):
        """Register a function for the given signature."""
        sig, min, max, vararg, priority = key
        fn = rename_function(
            orig_fn, f"{self.__name__}[{self._sig_string(sig)}]"
        )
        # We just need to keep the Conformer pointer alive for jurigged
        # to find it, if jurigged is used with ovld
        fn._conformer = Conformer(self, orig_fn, fn)
        self.map.register(sig, (min, max, vararg, priority), fn)
        return self

    def register(self, fn=None, priority=0):
        """Register a function."""
        if fn is None:
            return partial(self._register, priority=priority)
        return self._register(fn, priority)

    def _register(self, fn, priority):
        """Register a function."""

        def _normalize_type(t, force_tuple=False):
            if t is type:
                t = type[object]
            origin = getattr(t, "__origin__", None)
            if UnionType and isinstance(t, UnionType):
                return _normalize_type(t.__args__)
            elif origin is type:
                return (t,) if force_tuple else t
            elif origin is typing.Union:
                return _normalize_type(t.__args__)
            elif origin is not None:
                raise TypeError(
                    f"ovld does not accept generic types except type, Union or Optional, not {t}"
                )
            elif isinstance(t, tuple):
                return tuple(_normalize_type(t2) for t2 in t)
            elif force_tuple:
                return (t,)
            else:
                return t

        self._attempt_modify()

        self._set_attrs_from(fn)

        ann = fn.__annotations__
        argspec = inspect.getfullargspec(fn)
        argnames = argspec.args
        if self.bootstrap:
            if argnames[0] != "self":
                raise TypeError(
                    "The first argument of the function must be named `self`"
                )
            argnames = argnames[1:]

        typelist = []
        for i, name in enumerate(argnames):
            t = ann.get(name, None)
            if t is None:
                typelist.append(object)
            else:
                typelist.append(t)

        max_pos = len(argnames)
        req_pos = max_pos - len(argspec.defaults or ())

        typelist_tups = tuple(
            _normalize_type(t, force_tuple=True) for t in typelist
        )
        for tl in itertools.product(*typelist_tups):
            sig = (tuple(tl), req_pos, max_pos, bool(argspec.varargs), priority)
            if not self.allow_replacement and sig in self._defns:
                raise TypeError(f"There is already a method for {tl}")
            self._defns[(*sig,)] = fn

        self._make_signature()
        self._update()
        return self

    def unregister(self, fn):
        """Unregister a function."""
        self._attempt_modify()
        self._defns = {sig: f for sig, f in self._defns.items() if f is not fn}
        self._update()

    def _update(self):
        if self._compiled:
            self.compile()
        for child in self.children:
            child._update()

    def copy(self, mixins=[], linkback=False):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return _fresh(_Ovld)(
            bootstrap=self.bootstrap,
            mixins=[self, *mixins],
            linkback=linkback,
        )

    def variant(self, fn=None, **kwargs):
        """Decorator to create a variant of this Ovld.

        New functions can be registered to the variant without affecting the
        original.
        """
        ov = self.copy(**kwargs)
        if fn is None:
            return ov.register
        else:
            ov.register(fn)
            return ov

    @_compile_first
    def get_map(self):
        return self.map

    @_compile_first
    def __get__(self, obj, cls):
        if obj is None:
            return self
        return self.ocls(
            map=self.map,
            bind_to=obj,
            super=self.mixins[0] if len(self.mixins) == 1 else None,
        )

    @_compile_first
    def __getitem__(self, t):
        if not isinstance(t, tuple):
            t = (t,)
        assert not self.bootstrap
        return self.map[t]

    @_compile_first
    @_setattrs(rename="dispatch")
    def __call__(self, *args, **kwargs):
        """Call the overloaded function.

        This version of __call__ is used when bootstrap is False.

        If bootstrap is False and a dispatch function is provided, it
        replaces this function.
        """
        key = tuple(map(self.map.transform, args))
        method = self.map[key]
        return method(*args, **kwargs)

    @_compile_first
    @_setattrs(rename="next")
    def next(self, *args, **kwargs):
        """Call the next matching method after the caller, in terms of priority or specificity."""
        fr = sys._getframe(1)
        key = (fr.f_code, *map(self.map.transform, args))
        method = self.map[key]
        return method(*args, **kwargs)

    @__call__.setalt
    @_setattrs(rename="entry")
    def __ovldcall__(self, *args, **kwargs):
        """Call the overloaded function.

        This version of __call__ is used when bootstrap is True. This function is
        only called once at the entry point: recursive calls will will be to
        OvldCall.__call__.
        """
        ovc = self.__get__(BOOTSTRAP, None)
        return ovc(*args, **kwargs)

    def __repr__(self):
        return f"<Ovld {self.name or hex(id(self))}>"

    @_compile_first
    def display_methods(self):
        self.map.display_methods()

    @_compile_first
    def display_resolution(self, *args):
        self.map.display_resolution(*args)


def is_ovld(x):
    """Return whether the argument is an ovld function/method."""
    return isinstance(x, _Ovld)


class OvldCall:
    """Context for an Ovld call."""

    def __init__(self, map, bind_to, super=None):
        """Initialize an OvldCall."""
        self.map = map
        self._parent = super
        self.obj = self if bind_to is BOOTSTRAP else bind_to

    def __getitem__(self, t):
        """Find the right method to call given a tuple of types."""
        if not isinstance(t, tuple):
            t = (t,)
        return self.map[t].__get__(self.obj)

    def next(self, *args, **kwargs):
        """Call the next matching method after the caller, in terms of priority or specificity."""
        fr = sys._getframe(1)
        key = (fr.f_code, *map(self.map.transform, args))
        method = self.map[key]
        return method(self.obj, *args, **kwargs)

    def super(self, *args, **kwargs):
        """Use the parent ovld's method for this call."""
        pmap = self._parent.get_map()
        method = pmap[tuple(map(pmap.transform, args))]
        return method.__get__(self.obj)(*args, **kwargs)

    def resolve(self, *args):
        """Find the right method to call for the given arguments."""
        return self[tuple(map(self.map.transform, args))]

    def __call__(self, *args, **kwargs):
        """Call this overloaded function.

        If a dispatch function is provided, it replaces this function.
        """
        key = tuple(map(self.map.transform, args))
        method = self.map[key]
        return method(self.obj, *args, **kwargs)


def Ovld(*args, **kwargs):
    """Returns an instance of a fresh Ovld class."""
    return _fresh(_Ovld)(*args, **kwargs)


def extend_super(fn):
    """Declare that this method extends the super method with more types.

    This produces an ovld using the superclass method of the same name,
    plus this definition and others with the same name.
    """
    if not is_ovld(fn):
        fn = ovld(fn)
    fn._extend_super = True
    return fn


class ovld_cls_dict(dict):
    """A dict for use with OvldMC.__prepare__.

    Setting a key that already corresponds to an Olvd extends that Ovld.
    """

    def __init__(self, bases):
        self._mock = type("MockSuper", bases, {})

    def __setitem__(self, attr, value):
        if attr in self:
            prev = self[attr]
        elif is_ovld(value) and getattr(value, "_extend_super", False):
            prev = getattr(self._mock, attr, None)
            if is_ovld(prev):
                prev = prev.copy()
        else:
            prev = None

        if prev is not None:
            if inspect.isfunction(prev):
                prev = ovld(prev)

            if is_ovld(prev):
                if is_ovld(value):
                    prev.add_mixins(value)
                    value = prev
                elif inspect.isfunction(value):
                    prev.register(value)
                    value = prev

        super().__setitem__(attr, value)


class OvldMC(type):
    """Metaclass that allows overloading.

    A class which uses this metaclass can define multiple functions with
    the same name and different type signatures.
    """

    def create_subclass(cls, *bases, name=None):
        """Create a new subclass with the given extra bases."""
        name = name or "UnnamedOvld"
        bases = (cls, *bases)
        return type(cls)(name, bases, cls.__prepare__(name, bases))

    @classmethod
    def __prepare__(cls, name, bases):
        d = ovld_cls_dict(bases)

        names = set()
        for base in bases:
            names.update(dir(base))

        for name in names:
            values = [getattr(base, name, None) for base in bases]
            ovlds = [v for v in values if is_ovld(v)]
            mixins = [
                v for v in ovlds[1:] if getattr(v, "_extend_super", False)
            ]
            if mixins:
                o = ovlds[0].copy(mixins=mixins)
                others = [v for v in values if v is not None and not is_ovld(v)]
                for other in others:
                    o.register(other)
                o.rename(name)
                d[name] = o

        return d


class OvldBase(metaclass=OvldMC):
    """Base class that allows overloading of methods."""


def _find_overload(fn, **kwargs):
    mod = __import__(fn.__module__, fromlist="_")
    dispatch = getattr(mod, fn.__qualname__, None)
    if dispatch is None:
        dispatch = _fresh(_Ovld)(**kwargs)
    elif kwargs:  # pragma: no cover
        raise TypeError("Cannot configure an overload that already exists")
    if not is_ovld(dispatch):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    return dispatch


@keyword_decorator
def ovld(fn, priority=0, **kwargs):
    """Overload a function.

    Overloading is based on the function name.

    The decorated function should have one parameter annotated with a type.
    Any parameter can be annotated, but only one, and every overloading of a
    function should annotate the same parameter.

    The decorator optionally takes keyword arguments, *only* on the first
    use.

    Arguments:
        fn: The function to register.
        mixins: A list of Ovld instances that contribute functions to this
            Ovld.
        type_error: The error type to raise when no function can be found to
            dispatch to (default: TypeError).
        name: Optional name for the Ovld. If not provided, it will be
            gotten automatically from the first registered function or
            dispatch.
        mapper: Class implementing a mapping interface from a tuple of
            types to a handler (default: MultiTypeMap).
        linkback: Whether to keep a pointer in the parent mixins to this
            ovld so that updates can be propagated. (default: False)
    """
    dispatch = _find_overload(fn, **kwargs)
    return dispatch.register(fn, priority=priority)


__all__ = [
    "Ovld",
    "OvldBase",
    "OvldCall",
    "OvldMC",
    "extend_super",
    "is_ovld",
    "ovld",
]
