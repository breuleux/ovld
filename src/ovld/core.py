"""Utilities to overload functions for multiple types."""

import inspect
import itertools
import sys
import textwrap
from dataclasses import replace
from functools import partial
from types import FunctionType

from .recode import (
    Conformer,
    adapt_function,
    generate_dispatch,
    rename_code,
)
from .signatures import ArgumentAnalyzer, LazySignature, Signature
from .typemap import MultiTypeMap
from .utils import (
    MISSING,
    ResolutionError,
    UsageError,
    keyword_decorator,
    sigstring,
    subtler_type,
)

_orig_getdoc = inspect.getdoc


def _getdoc(fn):
    if hasattr(fn, "__calculate_doc__"):
        if inspect.ismethod(fn):
            fn = fn.__func__
        fn.__doc__ = fn.__calculate_doc__()
        del fn.__calculate_doc__
    return _orig_getdoc(fn)


inspect.getdoc = _getdoc


_current_id = itertools.count()


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
    dispatch.resolve_for_values = ov.resolve_for_values
    dispatch.resolve = ov.resolve
    dispatch.resolve_all = ov.resolve_all
    dispatch.copy = ov.copy
    dispatch.variant = ov.variant
    dispatch.display_methods = ov.display_methods
    dispatch.display_resolution = ov.display_resolution
    dispatch.add_mixins = ov.add_mixins
    dispatch.unregister = ov.unregister
    dispatch.next = ov.next
    dispatch.first_entry = first_entry
    return dispatch


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
    """

    def __init__(
        self,
        *,
        mixins=[],
        name=None,
        linkback=False,
    ):
        """Initialize an Ovld."""
        self.id = next(_current_id)
        self.specialization_self = MISSING
        self._compiled = False
        self._signatures = None
        self._argument_analysis = None
        self.linkback = linkback
        self.children = []
        self.name = name
        self.shortname = name or f"__OVLD{self.id}"
        self.__name__ = name
        self._regs = {}
        self._locked = False
        self.mixins = []
        self.dispatch = bootstrap_dispatch(self, name=self.shortname)
        self.add_mixins(*mixins)

    def regs(self):
        for mixin in self.mixins:
            yield from mixin.regs()
        yield from self._regs.items()

    def empty(self):
        return not self._regs and all(m.empty() for m in self.mixins)

    def mkdoc(self):
        fns = [f for f, _ in self.regs()]
        try:
            docs = [fn.__doc__ for fn in fns if fn.__doc__]
            if len(docs) == 1:
                maindoc = docs[0]
            else:
                maindoc = f"Ovld with {len(fns)} methods."

            doc = f"{maindoc}\n\n"
            for fn in fns:
                fndef = inspect.signature(fn)
                fdoc = fn.__doc__
                if not fdoc or fdoc == maindoc:
                    doc += f"{self.__name__}{fndef}\n\n"
                else:
                    if not fdoc.strip(" ").endswith("\n"):
                        fdoc += "\n"
                    fdoc = textwrap.indent(fdoc, " " * 4)
                    doc += f"{self.__name__}{fndef}\n{fdoc}\n"
        except Exception as exc:  # pragma: no cover
            doc = f"An exception occurred when calculating the docstring: {exc}"
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
            return ResolutionError(f"No method in {self} for argument types [{typenames}]")
        else:
            hlp = ""
            for c in possibilities:
                hn = getattr(c.handler, "__orig_name__", c.handler.__name__)
                hlp += (
                    f"* {hn}  (priority: {c.priority}, specificity: {list(c.specificity)})\n"
                )
            return ResolutionError(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                f"Candidates are:\n{hlp}"
                "Note: you can use @ovld(priority=X) to give higher priority to an overload."
            )

    def rename(self, name, shortname=None):
        """Rename this Ovld."""
        if name != self.name:
            self.name = name
            self.shortname = shortname or name
            self.__name__ = self.shortname
            self.dispatch = bootstrap_dispatch(self, name=self.shortname)

    def __set_name__(self, inst, name):
        self.rename(name)

    def ensure_compiled(self):
        if not self._compiled:
            self.compile()

    @property
    def signatures(self):
        if self._signatures is None:
            regs = {}
            for fn, priority in self.regs():
                ss = self.specialization_self
                cgf = getattr(ss, "_ovld_codegen_fields", ())
                lcl = {f: getattr(ss, f) for f in cgf}
                sig = replace(Signature.extract(fn, lcl), priority=priority)

                def _set(sig, fn):
                    if sig in regs:
                        # Push down the existing handler with a lower tiebreak
                        msig = replace(sig, tiebreak=sig.tiebreak - 1)
                        _set(msig, regs[sig])
                    regs[sig] = fn

                _set(sig, fn)
            self._signatures = regs
        return self._signatures

    @property
    def argument_analysis(self):
        if self._argument_analysis is None:
            aa = ArgumentAnalyzer()
            for sig in self.signatures:
                aa.add(sig)
            aa.compile()
            self._argument_analysis = aa
        return self._argument_analysis

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
        self.map = MultiTypeMap(name=name, key_error=self._key_error, ovld=self)

        for sig, fn in list(self.signatures.items()):
            self.register_signature(sig, fn)

        dispatch = generate_dispatch(self, self.argument_analysis)
        self.dispatch.__code__ = rename_code(dispatch.__code__, self.shortname)
        self.dispatch.__kwdefaults__ = dispatch.__kwdefaults__
        self.dispatch.__annotations__ = dispatch.__annotations__
        self.dispatch.__defaults__ = dispatch.__defaults__
        self.dispatch.__globals__.update(dispatch.__globals__)
        self.dispatch.map = self.map
        self.dispatch.__generate_doc__ = self.mkdoc

        self._compiled = True

    def resolve_for_values(self, *args):
        """Find the correct method to call for the given arguments."""
        self.ensure_compiled()
        return self.map[tuple(map(subtler_type, args))]

    def resolve(self, *args, after=None):
        """Find the correct method to call for the given argument types."""
        self.ensure_compiled()
        if after:
            return self.map[(getattr(after, "__code__", after), *args)]
        else:
            return self.map[args]

    def resolve_all(self, *args, **kwargs):
        """Yield all methods that match the arguments, in priority order."""
        self.ensure_compiled()
        return self.map.resolve_all(*args, **kwargs)

    def register_signature(self, sig, orig_fn):
        """Register a function for the given signature."""
        fn = adapt_function(orig_fn, self, f"{self.__name__}[{sigstring(sig.types)}]")
        # We just need to keep the Conformer pointer alive for jurigged
        # to find it, if jurigged is used with ovld
        fn._conformer = Conformer(self, orig_fn, fn)
        self.map.register(sig, fn)
        return self

    def register(self, fn=None, priority=0):
        """Register a function."""
        if fn is None:
            return partial(self._register, priority=priority)
        priority = getattr(fn, "priority", priority)
        return self._register(fn, priority)

    def _register(self, fn, priority):
        """Register a function."""

        if not isinstance(priority, tuple):
            priority = (priority,)

        self._attempt_modify()
        if self.name is None:
            self.__qualname__ = fn.__qualname__
            self.__module__ = fn.__module__
            self.rename(f"{fn.__module__}.{fn.__qualname__}", fn.__name__)
        self._regs[fn] = priority

        self.invalidate()
        return self

    def unregister(self, fn):
        """Unregister a function."""
        self._attempt_modify()
        del self._regs[fn]
        self.invalidate()

    def invalidate(self):
        self._signatures = None
        self._argument_analysis = None
        if self._compiled:
            self._compiled = False
            self.dispatch.__code__ = self.dispatch.first_entry.__code__
        for child in self.children:
            child.invalidate()
        if hasattr(self, "dispatch"):
            self.dispatch.__calculate_doc__ = self.mkdoc

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
        return self.dispatch.__get__(obj, cls)

    def __call__(self, *args, **kwargs):  # pragma: no cover
        """Call the overloaded function.

        This should be replaced by an auto-generated function.
        """
        return self.dispatch(*args, **kwargs)

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
    return isinstance(x, Ovld) or isinstance(getattr(x, "__ovld__", False), Ovld)


def to_ovld(x, force=True):
    """Return the argument as an Ovld."""
    x = getattr(x, "__ovld__", x)
    if inspect.isfunction(x):
        return (ovld(x, fresh=True).__ovld__) if force else None
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

        super().__setitem__(attr, value.dispatch if isinstance(value, Ovld) else value)


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
    def __prepare__(metacls, name, bases):
        d = ovld_cls_dict(bases)

        names = set()
        for base in bases:
            names.update(dir(base))

        for name in names:
            values = [getattr(base, name, None) for base in bases]
            ovlds = [v for v in values if is_ovld(v)]
            mixins = [v for v in ovlds[1:] if getattr(v, "_extend_super", False)]
            if mixins:
                o = ovlds[0].copy(mixins=mixins)
                others = [v for v in values if v is not None and not is_ovld(v)]
                for other in others:
                    o.register(other)
                o.rename(name)
                d[name] = o

        return d

    def __init__(cls, name, bases, d):
        for val in d.values():
            if o := to_ovld(val, force=False):
                o.specialization_self = cls
        super().__init__(name, bases, d)


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
