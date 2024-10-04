"""Utilities to overload functions for multiple types."""

import inspect
import itertools
import sys
import textwrap
import typing
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field, replace
from functools import cached_property, partial
from types import FunctionType, GenericAlias

from .recode import (
    Conformer,
    adapt_function,
    generate_dispatch,
    rename_code,
)
from .typemap import MultiTypeMap
from .types import clsstring, normalize_type
from .utils import MISSING, UsageError, keyword_decorator, subtler_type

_current_id = itertools.count()


@keyword_decorator
def _setattrs(fn, **kwargs):
    for k, v in kwargs.items():
        setattr(fn, k, v)
    return fn


class LazySignature(inspect.Signature):
    def __init__(self, ovld):
        super().__init__([])
        self.ovld = ovld

    def replace(
        self, *, parameters=inspect._void, return_annotation=inspect._void
    ):  # pragma: no cover
        if parameters is inspect._void:
            parameters = self.parameters.values()

        if return_annotation is inspect._void:
            return_annotation = self._return_annotation

        return inspect.Signature(
            parameters, return_annotation=return_annotation
        )

    @property
    def parameters(self):
        anal = self.ovld.analyze_arguments()
        parameters = []
        if anal.is_method:
            parameters.append(
                inspect.Parameter(
                    name="self",
                    kind=inspect._POSITIONAL_ONLY,
                )
            )
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_ONLY,
            )
            for p in anal.strict_positional_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_ONLY,
                default=MISSING,
            )
            for p in anal.strict_positional_optional
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_OR_KEYWORD,
            )
            for p in anal.positional_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_OR_KEYWORD,
                default=MISSING,
            )
            for p in anal.positional_optional
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._KEYWORD_ONLY,
            )
            for p in anal.keyword_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._KEYWORD_ONLY,
                default=MISSING,
            )
            for p in anal.keyword_optional
        ]
        return OrderedDict({p.name: p for p in parameters})


def bootstrap_dispatch(ov, name):
    def first_entry(*args, **kwargs):
        ov.compile()
        return ov.dispatch(*args, **kwargs)

    dispatch = FunctionType(
        rename_code(first_entry.__code__, name),
        {},
        name,
        (),
        first_entry.__closure__,
    )
    dispatch.__signature__ = LazySignature(ov)
    dispatch.__ovld__ = ov
    dispatch.register = ov.register
    dispatch.resolve = ov.resolve
    dispatch.copy = ov.copy
    dispatch.variant = ov.variant
    dispatch.display_methods = ov.display_methods
    dispatch.display_resolution = ov.display_resolution
    dispatch.add_mixins = ov.add_mixins
    dispatch.unregister = ov.unregister
    dispatch.next = ov.next
    return dispatch


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
    return_type: type
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
            return_type=normalize_type(sig.return_annotation, fn),
            req_pos=req_pos,
            max_pos=max_pos,
            req_names=frozenset(req_names),
            vararg=False,
            is_method=is_method,
            priority=None,
            arginfo=arginfo,
        )


def typemap_entry_string(cls):
    if isinstance(cls, tuple):
        key, typ = cls
        return f"{key}: {clsstring(typ)}"
    else:
        return clsstring(cls)


def sigstring(types):
    return ", ".join(map(typemap_entry_string, types))


class ArgumentAnalyzer:
    def __init__(self):
        self.name_to_positions = defaultdict(set)
        self.position_to_names = defaultdict(set)
        self.counts = defaultdict(lambda: [0, 0])
        self.complex_transforms = set()
        self.total = 0
        self.is_method = None
        self.done = False

    def add(self, fn):
        self.done = False
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
        if self.done:
            return
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

        self.strict_positional_required = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] == self.total
        ]
        self.strict_positional_optional = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] != self.total
        ]

        self.positional_required = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] == self.total
        ]
        self.positional_optional = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] != self.total
        ]

        keywords = [
            name
            for _, (name,) in self.name_to_positions.items()
            if not isinstance(name, int)
        ]
        self.keyword_required = [
            name for name in keywords if self.counts[name][0] == self.total
        ]
        self.keyword_optional = [
            name for name in keywords if self.counts[name][0] != self.total
        ]
        self.done = True

    def lookup_for(self, key):
        return subtler_type if key in self.complex_transforms else type


class Ovld:
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
        self.name = name
        self.shortname = name or f"__OVLD{self.id}"
        self.__name__ = name
        self._defns = {}
        self._locked = False
        self.mixins = []
        self.argument_analysis = ArgumentAnalyzer()
        self.add_mixins(*mixins)

    @property
    def defns(self):
        defns = {}
        for mixin in self.mixins:
            defns.update(mixin.defns)
        defns.update(self._defns)
        return defns

    def analyze_arguments(self):
        self.argument_analysis = ArgumentAnalyzer()
        for key, fn in list(self.defns.items()):
            self.argument_analysis.add(fn)
        self.argument_analysis.compile()
        return self.argument_analysis

    def mkdoc(self):
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
    def __doc__(self):
        self.ensure_compiled()
        return self.mkdoc()

    @property
    def __signature__(self):
        return self.dispatch.__signature__

    def lock(self):
        self._locked = True

    def _attempt_modify(self):
        if self._locked:
            raise Exception(f"ovld {self} is locked for modifications")

    def add_mixins(self, *mixins):
        self._attempt_modify()
        mixins = [o for m in mixins if (o := to_ovld(m)) is not self]
        for mixin in mixins:
            if self.linkback:
                mixin.children.append(self)
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

    def rename(self, name, shortname=None):
        """Rename this Ovld."""
        self.name = name
        self.shortname = shortname or name
        self.__name__ = shortname
        self.dispatch = bootstrap_dispatch(self, name=self.shortname)

    def _set_attrs_from(self, fn):
        """Inherit relevant attributes from the function."""
        if self.name is None:
            self.__qualname__ = fn.__qualname__
            self.__module__ = fn.__module__
            self.rename(f"{fn.__module__}.{fn.__qualname__}", fn.__name__)

    def ensure_compiled(self):
        if not self._compiled:
            self.compile()

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

        if self.name is None:
            self.name = self.__name__ = f"ovld{self.id}"

        name = self.__name__
        self.map = MultiTypeMap(name=name, key_error=self._key_error)

        self.analyze_arguments()
        dispatch = generate_dispatch(self, self.argument_analysis)
        if not hasattr(self, "dispatch"):
            self.dispatch = bootstrap_dispatch(self, name=self.shortname)
        self.dispatch.__code__ = rename_code(dispatch.__code__, self.shortname)
        self.dispatch.__kwdefaults__ = dispatch.__kwdefaults__
        self.dispatch.__annotations__ = dispatch.__annotations__
        self.dispatch.__defaults__ = dispatch.__defaults__
        self.dispatch.__globals__.update(dispatch.__globals__)
        self.dispatch.map = self.map
        self.dispatch.__doc__ = self.mkdoc()

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

        self._compiled = True

    def resolve(self, *args):
        """Find the correct method to call for the given arguments."""
        self.ensure_compiled()
        return self.map[tuple(map(subtler_type, args))]

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
        if hasattr(self, "dispatch"):
            self.dispatch.__doc__ = self.mkdoc()

    def copy(self, mixins=[], linkback=False):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return Ovld(mixins=[self, *mixins], linkback=linkback)

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

    def __get__(self, obj, cls):
        if not self._compiled:
            self.compile()
        return self.dispatch.__get__(obj, cls)

    @_setattrs(rename="dispatch")
    def __call__(self, *args, **kwargs):  # pragma: no cover
        """Call the overloaded function.

        This should be replaced by an auto-generated function.
        """
        if not self._compiled:
            self.compile()
        return self.dispatch(*args, **kwargs)

    @_setattrs(rename="next")
    def next(self, *args):
        """Call the next matching method after the caller, in terms of priority or specificity."""
        fr = sys._getframe(1)
        key = (fr.f_code, *map(subtler_type, args))
        method = self.map[key]
        return method(*args)

    def __repr__(self):
        return f"<Ovld {self.name or hex(id(self))}>"

    def display_methods(self):
        self.ensure_compiled()
        self.map.display_methods()

    def display_resolution(self, *args, **kwargs):
        self.ensure_compiled()
        self.map.display_resolution(*args, **kwargs)


def is_ovld(x):
    """Return whether the argument is an ovld function/method."""
    return isinstance(x, Ovld) or isinstance(
        getattr(x, "__ovld__", False), Ovld
    )


def to_ovld(x):
    """Return whether the argument is an ovld function/method."""
    x = getattr(x, "__ovld__", x)
    if inspect.isfunction(x):
        return ovld(x, fresh=True)
    else:
        return x if isinstance(x, Ovld) else None


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
            prev = to_ovld(self[attr])
        elif is_ovld(value) and getattr(value, "_extend_super", False):
            mixins = []
            for base in self._bases:
                if (candidate := getattr(base, attr, None)) is not None:
                    if mixin := to_ovld(candidate):
                        mixins.append(mixin)
            if mixins:
                prev, *others = mixins
                prev = prev.copy()
                for other in others:
                    prev.add_mixins(other)
        else:
            prev = None

        if prev is not None:
            if is_ovld(value) and prev is not value:
                value = getattr(value, "__ovld__", value)
                if prev.name is None:
                    prev.rename(value.name)
                prev.add_mixins(value)
                value = prev
            elif inspect.isfunction(value):
                prev.register(value)
                value = prev

        super().__setitem__(
            attr, value.dispatch if isinstance(value, Ovld) else value
        )


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
        dispatch = Ovld(**kwargs)
    elif not is_ovld(dispatch):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    elif kwargs:  # pragma: no cover
        raise TypeError("Cannot configure an overload that already exists")
    return getattr(dispatch, "__ovld__", dispatch)


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
        dispatch = Ovld(**kwargs)
    else:
        dispatch = _find_overload(fn, **kwargs)
    dispatch.register(fn, priority=priority)
    return dispatch.dispatch


__all__ = [
    "Ovld",
    "OvldBase",
    "OvldMC",
    "extend_super",
    "is_ovld",
    "ovld",
]
