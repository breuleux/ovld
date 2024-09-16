"""Utilities to overload functions for multiple types."""

import inspect
import itertools
import sys
import textwrap
import typing
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property, partial
from types import GenericAlias

from .recode import (
    Conformer,
    adapt_function,
    generate_dispatch,
    rename_function,
)
from .typemap import MultiTypeMap, is_type_of_type
from .types import normalize_type
from .utils import UsageError, keyword_decorator

_current_id = itertools.count()


def _fresh(t):
    """Returns a new subclass of type t.

    Each Ovld corresponds to its own class, which allows for specialization of
    methods.
    """
    methods = {}
    if not isinstance(getattr(t, "__doc__", None), str):
        methods["__doc__"] = t.__doc__
    return type(t.__name__, (t,), methods)


@keyword_decorator
def _setattrs(fn, **kwargs):
    for k, v in kwargs.items():
        setattr(fn, k, v)
    return fn


@keyword_decorator
def _compile_first(fn, rename=None):
    def first_entry(self, *args, **kwargs):
        self.compile()
        method = getattr(self, fn.__name__)
        assert method is not first_entry
        return method(*args, **kwargs)

    first_entry._replace_by = fn
    first_entry._rename = rename
    return first_entry


def arg0_is_self(fn):
    sgn = inspect.signature(fn)
    params = list(sgn.parameters.values())
    return params and params[0].name == "self"


@dataclass(frozen=True)
class Arginfo:
    position: typing.Optional[int]
    name: typing.Optional[str]
    required: bool
    ann: type

    @cached_property
    def is_complex(self):
        return isinstance(self.ann, GenericAlias)

    @cached_property
    def canonical(self):
        return self.name if self.position is None else self.position


@dataclass(frozen=True)
class Signature:
    types: tuple
    req_pos: int
    max_pos: int
    req_names: frozenset
    vararg: bool
    priority: float
    tiebreak: int = 0
    is_method: bool = False
    arginfo: list[Arginfo] = field(
        default_factory=list, hash=False, compare=False
    )

    @classmethod
    def extract(cls, fn):
        typelist = []
        sig = inspect.signature(fn)
        max_pos = 0
        req_pos = 0
        req_names = set()
        is_method = False

        arginfo = []
        for i, (name, param) in enumerate(sig.parameters.items()):
            if name == "self":
                assert i == 0
                is_method = True
                continue
            pos = nm = None
            ann = normalize_type(param.annotation, fn)
            if param.kind is inspect._POSITIONAL_ONLY:
                pos = i - is_method
                typelist.append(ann)
                req_pos += param.default is inspect._empty
                max_pos += 1
            elif param.kind is inspect._POSITIONAL_OR_KEYWORD:
                pos = i - is_method
                nm = param.name
                typelist.append(ann)
                req_pos += param.default is inspect._empty
                max_pos += 1
            elif param.kind is inspect._KEYWORD_ONLY:
                nm = param.name
                typelist.append((param.name, ann))
                if param.default is inspect._empty:
                    req_names.add(param.name)
            elif param.kind is inspect._VAR_POSITIONAL:
                raise TypeError("ovld does not support *args")
            elif param.kind is inspect._VAR_KEYWORD:
                raise TypeError("ovld does not support **kwargs")
            arginfo.append(
                Arginfo(
                    position=pos,
                    name=nm,
                    required=param.default is inspect._empty,
                    ann=normalize_type(param.annotation, fn),
                )
            )

        return cls(
            types=tuple(typelist),
            req_pos=req_pos,
            max_pos=max_pos,
            req_names=frozenset(req_names),
            vararg=False,
            is_method=is_method,
            priority=None,
            arginfo=arginfo,
        )


def clsstring(cls):
    if cls is object:
        return "*"
    elif isinstance(cls, tuple):
        key, typ = cls
        return f"{key}: {clsstring(typ)}"
    elif is_type_of_type(cls):
        arg = clsstring(cls.__args__[0])
        return f"type[{arg}]"
    elif hasattr(cls, "__origin__"):
        if cls.__origin__ is typing.Union:
            return "|".join(map(clsstring, cls.__args__))
        else:
            return repr(cls)
    elif hasattr(cls, "__name__"):
        return cls.__name__
    else:
        return repr(cls)


def sigstring(types):
    return ", ".join(map(clsstring, types))


class ArgumentAnalyzer:
    def __init__(self):
        self.name_to_positions = defaultdict(set)
        self.position_to_names = defaultdict(set)
        self.counts = defaultdict(lambda: [0, 0])
        self.complex_transforms = set()
        self.total = 0
        self.is_method = None

    def add(self, fn):
        sig = Signature.extract(fn)
        self.complex_transforms.update(
            arg.canonical for arg in sig.arginfo if arg.is_complex
        )
        for arg in sig.arginfo:
            if arg.position is not None:
                self.position_to_names[arg.position].add(arg.name)
            if arg.name is not None:
                self.name_to_positions[arg.name].add(arg.canonical)

            cnt = self.counts[arg.canonical]
            cnt[0] += arg.required
            cnt[1] += 1

        self.total += 1

        if self.is_method is None:
            self.is_method = sig.is_method
        elif self.is_method != sig.is_method:  # pragma: no cover
            raise TypeError(
                "Some, but not all registered methods define `self`. It should be all or none."
            )

    def compile(self):
        for name, pos in self.name_to_positions.items():
            if len(pos) != 1:
                if all(isinstance(p, int) for p in pos):
                    raise TypeError(
                        f"Argument '{name}' is declared in different positions by different methods. The same argument name should always be in the same position unless it is strictly positional."
                    )
                else:
                    raise TypeError(
                        f"Argument '{name}' is declared in a positional and keyword setting by different methods. It should be either."
                    )

        p_to_n = [
            list(names) for _, names in sorted(self.position_to_names.items())
        ]

        positional = list(
            itertools.takewhile(
                lambda names: len(names) == 1 and isinstance(names[0], str),
                reversed(p_to_n),
            )
        )
        positional.reverse()
        strict_positional = p_to_n[: len(p_to_n) - len(positional)]

        assert strict_positional + positional == p_to_n

        strict_positional_required = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] == self.total
        ]
        strict_positional_optional = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] != self.total
        ]

        positional_required = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] == self.total
        ]
        positional_optional = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] != self.total
        ]

        keywords = [
            name
            for _, (name,) in self.name_to_positions.items()
            if not isinstance(name, int)
        ]
        keyword_required = [
            name for name in keywords if self.counts[name][0] == self.total
        ]
        keyword_optional = [
            name for name in keywords if self.counts[name][0] != self.total
        ]

        return (
            strict_positional_required,
            strict_positional_optional,
            positional_required,
            positional_optional,
            keyword_required,
            keyword_optional,
        )

    def lookup_for(self, key):
        return (
            "self.map.transform" if key in self.complex_transforms else "type"
        )


class _Ovld:
    """Overloaded function.

    A function can be added with the `register` method. One of its parameters
    should be annotated with a type, but only one, and every registered
    function should annotate the same parameter.

    Arguments:
        mixins: A list of Ovld instances that contribute functions to this
            Ovld.
        name: Optional name for the Ovld. If not provided, it will be
            gotten automatically from the first registered function or
            dispatch.
        linkback: Whether to keep a pointer in the parent mixins to this
            ovld so that updates can be propagated. (default: False)
        allow_replacement: Allow replacing a method by another with the
            same signature. (default: True)
    """

    def __init__(
        self,
        *,
        mixins=[],
        bootstrap=None,
        name=None,
        linkback=False,
        allow_replacement=True,
    ):
        """Initialize an Ovld."""
        self.id = next(_current_id)
        self._compiled = False
        self.linkback = linkback
        self.children = []
        self.allow_replacement = allow_replacement
        self.bootstrap = bootstrap
        self.name = name
        self.shortname = name or f"__OVLD{self.id}"
        self.__name__ = name
        self._defns = {}
        self._locked = False
        self.mixins = []
        self.add_mixins(*mixins)
        self.ocls = _fresh(OvldCall)

    @property
    def defns(self):
        defns = {}
        for mixin in self.mixins:
            defns.update(mixin.defns)
        defns.update(self._defns)
        return defns

    @property
    def __doc__(self):
        if not self._compiled:
            self.compile()

        docs = [fn.__doc__ for fn in self.defns.values() if fn.__doc__]
        if len(docs) == 1:
            maindoc = docs[0]
        else:
            maindoc = f"Ovld with {len(self.defns)} methods."

        doc = f"{maindoc}\n\n"
        for fn in self.defns.values():
            fndef = inspect.signature(fn)
            fdoc = fn.__doc__
            if not fdoc or fdoc == maindoc:
                doc += f"{self.__name__}{fndef}\n\n"
            else:
                if not fdoc.strip(" ").endswith("\n"):
                    fdoc += "\n"
                fdoc = textwrap.indent(fdoc, " " * 4)
                doc += f"{self.__name__}{fndef}\n{fdoc}\n"
        return doc

    @property
    def __signature__(self):
        if not self._compiled:
            self.compile()

        sig = inspect.signature(self._dispatch)
        if not self.argument_analysis.is_method:
            sig = inspect.Signature(
                [v for k, v in sig.parameters.items() if k != "self"]
            )
        return sig

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
            if mixin._defns and self.bootstrap is None:
                self.bootstrap = mixin.bootstrap
        self.mixins += mixins

    def _key_error(self, key, possibilities=None):
        typenames = sigstring(key)
        if not possibilities:
            return TypeError(
                f"No method in {self} for argument types [{typenames}]"
            )
        else:
            hlp = ""
            for c in possibilities:
                hlp += f"* {c.handler.__name__}  (priority: {c.priority}, specificity: {list(c.specificity)})\n"
            return TypeError(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                f"Candidates are:\n{hlp}"
                "Note: you can use @ovld(priority=X) to give higher priority to an overload."
            )

    def rename(self, name):
        """Rename this Ovld."""
        self.name = name
        self.__name__ = name

    def _set_attrs_from(self, fn):
        """Inherit relevant attributes from the function."""
        if self.bootstrap is None:
            self.bootstrap = arg0_is_self(fn)

        if self.name is None:
            self.name = f"{fn.__module__}.{fn.__qualname__}"
            self.shortname = fn.__name__
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

        cls = type(self)
        if self.name is None:
            self.name = self.__name__ = f"ovld{self.id}"

        name = self.__name__
        self.map = MultiTypeMap(name=name, key_error=self._key_error)

        # Replace the appropriate functions by their final behavior
        for method in dir(cls):
            value = getattr(cls, method)
            repl = getattr(value, "_replace_by", None)
            if repl:
                repl = self._maybe_rename(repl)
                setattr(cls, method, repl)

        target = self.ocls if self.bootstrap else cls

        anal = ArgumentAnalyzer()
        for key, fn in list(self.defns.items()):
            anal.add(fn)
        self.argument_analysis = anal
        dispatch = generate_dispatch(anal)
        self._dispatch = dispatch
        target.__call__ = rename_function(dispatch, f"{name}.dispatch")

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

        self._compiled = True

    @_compile_first
    def resolve(self, *args):
        """Find the correct method to call for the given arguments."""
        return self.map[tuple(map(self.map.transform, args))]

    def register_signature(self, sig, orig_fn):
        """Register a function for the given signature."""
        fn = adapt_function(
            orig_fn, self, f"{self.__name__}[{sigstring(sig.types)}]"
        )
        # We just need to keep the Conformer pointer alive for jurigged
        # to find it, if jurigged is used with ovld
        fn._conformer = Conformer(self, orig_fn, fn)
        self.map.register(sig, fn)
        return self

    def register(self, fn=None, priority=0):
        """Register a function."""
        if fn is None:
            return partial(self._register, priority=priority)
        return self._register(fn, priority)

    def _register(self, fn, priority):
        """Register a function."""

        self._attempt_modify()

        self._set_attrs_from(fn)

        sig = replace(Signature.extract(fn), priority=priority)
        if not self.allow_replacement and sig in self._defns:
            raise TypeError(
                f"There is already a method for {sigstring(sig.types)}"
            )

        def _set(sig, fn):
            if sig in self._defns:
                # Push down the existing handler with a lower tiebreak
                msig = replace(sig, tiebreak=sig.tiebreak - 1)
                _set(msig, self._defns[sig])
            self._defns[sig] = fn

        _set(sig, fn)

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

    def variant(self, fn=None, priority=0, **kwargs):
        """Decorator to create a variant of this Ovld.

        New functions can be registered to the variant without affecting the
        original.
        """
        ov = self.copy(**kwargs)
        if fn is None:
            return partial(ov.register, priority=priority)
        else:
            ov.register(fn, priority=priority)
            return ov

    @_compile_first
    def __get__(self, obj, cls):
        if obj is None:
            return self
        key = self.shortname
        rval = obj.__dict__.get(key, None)
        if rval is None:
            obj.__dict__[key] = rval = self.ocls(self, obj)
        return rval

    @_compile_first
    def __getitem__(self, t):
        if not isinstance(t, tuple):
            t = (t,)
        return self.map[t]

    @_compile_first
    @_setattrs(rename="dispatch")
    def __call__(self, *args):  # pragma: no cover
        """Call the overloaded function.

        This should be replaced by an auto-generated function.
        """
        key = tuple(map(self.map.transform, args))
        method = self.map[key]
        return method(*args)

    @_compile_first
    @_setattrs(rename="next")
    def next(self, *args):
        """Call the next matching method after the caller, in terms of priority or specificity."""
        fr = sys._getframe(1)
        key = (fr.f_code, *map(self.map.transform, args))
        method = self.map[key]
        return method(*args)

    def __repr__(self):
        return f"<Ovld {self.name or hex(id(self))}>"

    @_compile_first
    def display_methods(self):
        self.map.display_methods()

    @_compile_first
    def display_resolution(self, *args, **kwargs):
        self.map.display_resolution(*args, **kwargs)


def is_ovld(x):
    """Return whether the argument is an ovld function/method."""
    return isinstance(x, _Ovld)


class OvldCall:
    """Context for an Ovld call."""

    def __init__(self, ovld, bind_to):
        """Initialize an OvldCall."""
        self.ovld = ovld
        self.map = ovld.map
        self.obj = bind_to

    @property
    def __name__(self):
        return self.ovld.__name__

    @property
    def __doc__(self):
        return self.ovld.__doc__

    @property
    def __signature__(self):
        return self.ovld.__signature__

    def next(self, *args):
        """Call the next matching method after the caller, in terms of priority or specificity."""
        fr = sys._getframe(1)
        key = (fr.f_code, *map(self.map.transform, args))
        method = self.map[key]
        return method(self.obj, *args)

    def resolve(self, *args):
        """Find the right method to call for the given arguments."""
        return self.map[tuple(map(self.map.transform, args))].__get__(self.obj)

    def __call__(self, *args):  # pragma: no cover
        """Call this overloaded function.

        This should be replaced by an auto-generated function.
        """
        key = tuple(map(self.map.transform, args))
        method = self.map[key]
        return method(self.obj, *args)


def Ovld(*args, **kwargs):
    """Returns an instance of a fresh Ovld class."""
    return _fresh(_Ovld)(*args, **kwargs)


def extend_super(fn):
    """Declare that this method extends the super method with more types.

    This produces an ovld using the superclass method of the same name,
    plus this definition and others with the same name.
    """
    if not is_ovld(fn):
        fn = ovld(fn, fresh=True)
    fn._extend_super = True
    return fn


class ovld_cls_dict(dict):
    """A dict for use with OvldMC.__prepare__.

    Setting a key that already corresponds to an Olvd extends that Ovld.
    """

    def __init__(self, bases):
        self._bases = bases

    def __setitem__(self, attr, value):
        prev = None
        if attr in self:
            prev = self[attr]
            if inspect.isfunction(prev):
                prev = ovld(prev, fresh=True)
            elif not is_ovld(prev):  # pragma: no cover
                prev = None
        elif is_ovld(value) and getattr(value, "_extend_super", False):
            mixins = []
            for base in self._bases:
                if (candidate := getattr(base, attr, None)) is not None:
                    if is_ovld(candidate) or inspect.isfunction(candidate):
                        mixins.append(candidate)
            if mixins:
                prev, *others = mixins
                if is_ovld(prev):
                    prev = prev.copy()
                else:
                    prev = ovld(prev, fresh=True)
                for other in others:
                    if is_ovld(other):
                        prev.add_mixins(other)
                    else:
                        prev.register(other)
        else:
            prev = None

        if prev is not None:
            if is_ovld(value) and prev is not value:
                if prev.name is None:
                    prev.rename(value.name)
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
    fr = sys._getframe(1)  # We typically expect to get to frame 3.
    while fr and fn.__code__ not in fr.f_code.co_consts:
        # We are basically searching for the function's code object in the stack.
        # When a class/function A is nested in a class/function B, the former's
        # code object is in the latter's co_consts. If ovld is used as a decorator,
        # on A, then necessarily we are inside the execution of B, so B should be
        # on the stack and we should be able to find A's code object in there.
        fr = fr.f_back

    if not fr:
        raise UsageError("@ovld only works as a decorator.")

    dispatch = fr.f_locals.get(fn.__name__, None)

    if dispatch is None:
        dispatch = _fresh(_Ovld)(**kwargs)
    elif not is_ovld(dispatch):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    elif kwargs:  # pragma: no cover
        raise TypeError("Cannot configure an overload that already exists")
    return dispatch


@keyword_decorator
def ovld(fn, priority=0, fresh=False, **kwargs):
    """Overload a function.

    Overloading is based on the function name.

    The decorated function should have one parameter annotated with a type.
    Any parameter can be annotated, but only one, and every overloading of a
    function should annotate the same parameter.

    The decorator optionally takes keyword arguments, *only* on the first
    use.

    Arguments:
        fn: The function to register.
        priority: The priority of the function in the resolution order.
        fresh: Whether to create a new ovld or try to reuse an existing one.
        mixins: A list of Ovld instances that contribute functions to this
            Ovld.
        name: Optional name for the Ovld. If not provided, it will be
            gotten automatically from the first registered function or
            dispatch.
        linkback: Whether to keep a pointer in the parent mixins to this
            ovld so that updates can be propagated. (default: False)
    """
    if fresh:
        dispatch = _fresh(_Ovld)(**kwargs)
    else:
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
