"""Utilities to overload functions for multiple types."""

import inspect
import itertools
import math
import textwrap
from types import FunctionType

from .mro import compose_mro
from .utils import BOOTSTRAP, MISSING, keyword_decorator


class TypeMap(dict):
    """Represents a mapping from types to handlers.

    The mro of a type is considered when getting the handler, so setting the
    [object] key creates a default for all objects.

    typemap[some_type] returns a tuple of a handler and a "level" that
    represents the distance from the handler to the type `object`. Essentially,
    the level is the index of the type for which the handler was registered
    in the mro of `some_type`. So for example, `object` has level 0, a class
    that inherits directly from `object` has level 1, and so on.
    """

    def __init__(self):
        self.entries = {}
        self.types = set()

    def register(self, obj_t, handler):
        """Register a handler for the given object type."""
        self.clear()
        self.types.add(obj_t)
        s = self.entries.setdefault(obj_t, set())
        s.add(handler)

    def __missing__(self, obj_t):
        """Get the handler for the given type.

        The result is cached so that the normal dict getitem will find it
        the next time getitem is called.
        """
        results = {}
        mro = compose_mro(obj_t, self.types)
        for lvl, cls in enumerate(reversed(mro)):
            handlers = self.entries.get(cls, None)
            if handlers:
                results.update({h: lvl for h in handlers})

        if results:
            self[obj_t] = results
            return results
        else:
            raise KeyError(obj_t)


class MultiTypeMap(dict):
    """Represents a mapping from tuples of types to handlers.

    The mro is taken into account to find a match. If multiple registered
    handlers match the tuple of types that's given, if one of the handlers is
    more specific than every other handler, that handler is returned.
    Otherwise, the resolution is considered ambiguous and an error is raised.

    Handler A, registered for types (A1, A2, ..., An), is more specific than
    handler B, registered for types (B1, B2, ..., Bn), if there exists n such
    that An is more specific than Bn, and for all n, either An == Bn or An is
    more specific than Bn. An is more specific than Bn if An is a direct or
    indirect subclass of Bn.

    In other words, [int, object] is more specific than [object, object] and
    less specific than [int, int], but it is neither less specific nor more
    specific than [object, int] (which means there is an ambiguity).
    """

    def __init__(self, key_error=KeyError):
        self.maps = {}
        self.empty = MISSING
        self.transform = type
        self.key_error = key_error

    def register(self, obj_t_tup, nargs, handler):
        """Register a handler for a tuple of argument types.

        Arguments:
            obj_t_tup: A tuple of argument types.
            nargs: A (amin, amax, varargs) tuple where amin is the minimum
                number of arguments needed to match this tuple (if there are
                default arguments, it is possible that amin < len(obj_t_tup)),
                amax is the maximum number of arguments, and varargs is a
                boolean indicating whether there can be an arbitrary number
                of arguments.
            handler: A function to handle the tuple.
        """
        self.clear()

        amin, amax, vararg = nargs

        entry = (handler, amin, amax, vararg)
        if not obj_t_tup:
            self.empty = entry

        for i, cls in enumerate(obj_t_tup):
            tm = self.maps.setdefault(i, TypeMap())
            tm.register(cls, entry)
        if vararg:
            tm = self.maps.setdefault(-1, TypeMap())
            tm.register(object, entry)

    def __missing__(self, obj_t_tup):
        specificities = {}
        candidates = None
        nargs = len(obj_t_tup)

        if not obj_t_tup:
            if self.empty is MISSING:
                raise self.key_error(obj_t_tup, ())
            else:
                return self.empty[0]

        for i, cls in enumerate(obj_t_tup):
            try:
                results = self.maps[i][cls]
            except KeyError:
                results = {}

            results = {
                handler: spc
                for (handler, min, max, va), spc in results.items()
                if min <= nargs <= (math.inf if va else max)
            }

            try:
                vararg_results = self.maps[-1][cls]
            except KeyError:
                vararg_results = {}

            vararg_results = {
                handler: spc
                for (handler, min, max, va), spc in vararg_results.items()
                if min <= nargs and i >= max
            }

            results.update(vararg_results)

            if candidates is None:
                candidates = set(results.keys())
            else:
                candidates &= results.keys()
            for c in candidates:
                specificities.setdefault(c, []).append(results[c])

        if not candidates:
            raise self.key_error(obj_t_tup, ())

        candidates = [(c, tuple(specificities[c])) for c in candidates]

        # The sort ensures that if candidate A dominates candidate B, A will
        # appear before B in the list. That's because it must dominate all
        # other possibilities on all arguments, so the sum of all specificities
        # has to be greater.
        candidates.sort(key=lambda cspc: sum(cspc[1]), reverse=True)

        results = [candidates[0]]
        for c2, spc2 in candidates[1:]:
            # Evaluate candidate 2
            for c1, spc1 in results:
                if spc1 != spc2 and all(s1 >= s2 for s1, s2 in zip(spc1, spc2)):
                    # Candidate 1 dominates candidate 2, therefore we can
                    # reject candidate 2.
                    break
            else:
                # Candidate 2 cannot be dominated, so we move it to the results
                # list
                results.append((c2, spc2))

        if len(results) != 1:
            # No candidate dominates all the others => key_error
            # As second argument, we provide the minimal set of candidates
            # that no other candidate can dominate
            raise self.key_error(obj_t_tup, [result for result, _ in results])
        else:
            ((result, _),) = results
            self[obj_t_tup] = result
            return result


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
        dispatch: A function to use as the entry point. It must find the
            function to dispatch to and call it.
        initial_state: A function returning the initial state, or None if
            there is no state.
        postprocess: A function to call on the return value. It is not called
            after recursive calls.
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
        dispatch=None,
        initial_state=None,
        postprocess=None,
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
        self._dispatch = dispatch
        self.maindoc = None
        self.mapper = mapper
        self.linkback = linkback
        self.children = []
        self.type_error = type_error
        self.initial_state = initial_state
        self.postprocess = postprocess
        self.allow_replacement = allow_replacement
        self.bootstrap_class = OvldCall
        if self.initial_state or self.postprocess:
            assert bootstrap is not False
            self.bootstrap = True
        elif isinstance(bootstrap, type):
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
            assert mixin.bootstrap is not None
            if self.bootstrap is None:
                self.bootstrap = mixin.bootstrap
            assert mixin.bootstrap is self.bootstrap
        self.mixins += mixins

    def _sig_string(self, type_tuple):
        def clsname(cls):
            if cls is object:
                return "*"
            elif hasattr(cls, "__name__"):
                return cls.__name__
            else:
                return repr(cls)

        return ", ".join(map(clsname, type_tuple))

    def _key_error(self, key, possibilities=None):
        typenames = self._sig_string(key)
        if not possibilities:
            raise self.type_error(
                f"No method in {self} for argument types [{typenames}]"
            )
        else:
            hlp = ""
            for p in possibilities:
                hlp += f"* {p.__name__}\n"
            raise self.type_error(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                "Candidates are:\n" + hlp
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

    def _set_attrs_from(self, fn, dispatch=False):
        """Inherit relevant attributes from the function."""
        if self.bootstrap is None:
            sign = inspect.signature(fn)
            params = list(sign.parameters.values())
            if not dispatch:
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

        if self._dispatch:
            if self.bootstrap:
                self.ocls.__call__ = self._dispatch
            else:
                cls.__call__ = self._dispatch

        # Rename the dispatch
        if self._dispatch:
            self._dispatch = rename_function(self._dispatch, f"{name}.dispatch")

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

    def dispatch(self, dispatch):
        """Set a dispatch function."""
        if self._dispatch is not None:
            raise TypeError(f"dispatch for {self} is already set")
        self._dispatch = dispatch
        self._set_attrs_from(dispatch, dispatch=True)
        return self

    def resolve(self, *args):
        """Find the correct method to call for the given arguments."""
        return self.map[tuple(map(self.map.transform, args))]

    def register_signature(self, key, orig_fn):
        """Register a function for the given signature."""
        sig, min, max, vararg = key
        fn = rename_function(
            orig_fn, f"{self.__name__}[{self._sig_string(sig)}]"
        )
        # We just need to keep the Conformer pointer alive for jurigged
        # to find it, if jurigged is used with ovld
        fn._conformer = Conformer(self, orig_fn, fn)
        self.map.register(sig, (min, max, vararg), fn)
        return self

    def register(self, fn):
        """Register a function."""
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
            t if isinstance(t, tuple) else (t,) for t in typelist
        )
        for tl in itertools.product(*typelist_tups):
            sig = (tuple(tl), req_pos, max_pos, bool(argspec.varargs))
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

    def copy(
        self,
        dispatch=MISSING,
        initial_state=None,
        postprocess=None,
        mixins=[],
        linkback=False,
    ):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return _fresh(_Ovld)(
            bootstrap=self.bootstrap,
            dispatch=self._dispatch if dispatch is MISSING else dispatch,
            mixins=[self, *mixins],
            initial_state=initial_state or self.initial_state,
            postprocess=postprocess or self.postprocess,
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
    def instantiate(self, **state):
        return self.ocls(map=self.map, state=state, bind_to=BOOTSTRAP)

    @_compile_first
    def __get__(self, obj, cls):
        if obj is None:
            return self
        if self.initial_state is None or isinstance(self.initial_state, dict):
            state = self.initial_state
        else:
            state = self.initial_state()
        return self.ocls(
            map=self.map,
            state=state,
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

    @__call__.setalt
    @_setattrs(rename="entry")
    def __ovldcall__(self, *args, **kwargs):
        """Call the overloaded function.

        This version of __call__ is used when bootstrap is True. It creates an
        OvldCall instance to contain the state. This function is only called
        once at the entry point: recursive calls will will be to
        OvldCall.__call__.
        """
        ovc = self.__get__(BOOTSTRAP, None)
        res = ovc(*args, **kwargs)
        if self.postprocess:
            res = self.postprocess(self, res)
        return res

    def __repr__(self):
        return f"<Ovld {self.name or hex(id(self))}>"


class OvldCall:
    """Context for an Ovld call."""

    def __init__(self, map, state, bind_to, super=None):
        """Initialize an OvldCall."""
        self.map = map
        self._parent = super
        if state is not None:
            self.__dict__.update(state)
        self.obj = self if bind_to is BOOTSTRAP else bind_to

    def __getitem__(self, t):
        """Find the right method to call given a tuple of types."""
        if not isinstance(t, tuple):
            t = (t,)
        return self.map[t].__get__(self.obj)

    def super(self, *args, **kwargs):
        """Use the parent ovld's method for this call."""
        pmap = self._parent.get_map()
        method = pmap[tuple(map(pmap.transform, args))]
        return method.__get__(self.obj)(*args, **kwargs)

    def resolve(self, *args):
        """Find the right method to call for the given arguments."""
        return self[tuple(map(self.map.transform, args))]

    def call(self, *args):
        """Call the right method for the given arguments."""
        return self[tuple(map(self.map.transform, args))](*args)

    def with_state(self, **state):
        """Return a new OvldCall using the given state."""
        return type(self)(self.map, state, BOOTSTRAP)

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


class ovld_cls_dict(dict):
    """A dict for use with OvldMC.__prepare__.

    Setting a key that already corresponds to an Olvd extends that Ovld.
    """

    def __setitem__(self, attr, value):
        if attr in self:
            prev = self[attr]
            if isinstance(prev, _Ovld):
                if isinstance(value, _Ovld):
                    value.add_mixins(prev)
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
        d = ovld_cls_dict()

        names = set()
        for base in bases:
            names.update(dir(base))

        for name in names:
            values = [getattr(base, name, None) for base in bases]
            mixins = [v for v in values if isinstance(v, _Ovld)]
            if mixins:
                o = mixins[0].copy(mixins=mixins[1:])
                others = [
                    v
                    for v in values
                    if v is not None and not isinstance(v, _Ovld)
                ]
                for other in others:
                    o.register(other)
                o.rename(name)
                d[name] = o

        return d


def _find_overload(fn, **kwargs):
    mod = __import__(fn.__module__, fromlist="_")
    dispatch = getattr(mod, fn.__qualname__, None)
    if dispatch is None:
        dispatch = _fresh(_Ovld)(**kwargs)
    elif kwargs:  # pragma: no cover
        raise TypeError("Cannot configure an overload that already exists")
    if not isinstance(dispatch, _Ovld):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    return dispatch


@keyword_decorator
def ovld(fn, **kwargs):
    """Overload a function.

    Overloading is based on the function name.

    The decorated function should have one parameter annotated with a type.
    Any parameter can be annotated, but only one, and every overloading of a
    function should annotate the same parameter.

    The decorator optionally takes keyword arguments, *only* on the first
    use.

    Arguments:
        fn: The function to register.
        dispatch: A function to use as the entry point. It must find the
            function to dispatch to and call it.
        initial_state: A function returning the initial state, or None if
            there is no state.
        postprocess: A function to call on the return value. It is not called
            after recursive calls.
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
    return dispatch.register(fn)


@keyword_decorator
def ovld_dispatch(dispatch, **kwargs):
    """Overload a function using the decorated function as a dispatcher.

    The dispatch is the entry point for the function and receives a `self`
    which is an Ovld or OvldCall instance, and the rest of the arguments.
    It may call `self.resolve(arg1, arg2, ...)` to get the right method to
    call.

    The decorator optionally takes keyword arguments, *only* on the first
    use.

    Arguments:
        dispatch: The function to use as the entry point. It must find the
            function to dispatch to and call it.
        initial_state: A function returning the initial state, or None if
            there is no state.
        postprocess: A function to call on the return value. It is not called
            after recursive calls.
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
    ov = _find_overload(dispatch, **kwargs)
    return ov.dispatch(dispatch)


ovld.dispatch = ovld_dispatch


class Conformer:
    __slots__ = ("code", "orig_fn", "renamed_fn", "ovld", "code2")

    def __init__(self, ovld, orig_fn, renamed_fn):
        self.ovld = ovld
        self.orig_fn = orig_fn
        self.renamed_fn = renamed_fn
        self.code = orig_fn.__code__

    def __conform__(self, new):
        if isinstance(new, FunctionType):
            new_fn = new
            new_code = new.__code__
        else:
            new_fn = None
            new_code = new

        if new_code is None:
            self.ovld.unregister(self.orig_fn)

        elif new_fn is None:  # pragma: no cover
            # Not entirely sure if this ever happens
            self.renamed_fn.__code__ = new_code

        elif inspect.signature(self.orig_fn) != inspect.signature(new_fn):
            self.ovld.unregister(self.orig_fn)
            self.ovld.register(new_fn)

        else:
            self.renamed_fn.__code__ = rename_code(
                new_code, self.renamed_fn.__code__.co_name
            )

        try:  # pragma: no cover
            from jurigged import db

            db.update_cache_entry(self, self.code, new_code)
        except ImportError:
            pass

        self.code = new_code


def rename_code(co, newname):  # pragma: no cover
    if hasattr(co, "replace"):
        return co.replace(co_name=newname)
    else:
        return type(co)(
            co.co_argcount,
            co.co_kwonlyargcount,
            co.co_nlocals,
            co.co_stacksize,
            co.co_flags,
            co.co_code,
            co.co_consts,
            co.co_names,
            co.co_varnames,
            co.co_filename,
            newname,
            co.co_firstlineno,
            co.co_lnotab,
            co.co_freevars,
            co.co_cellvars,
        )


def rename_function(fn, newname):
    """Create a copy of the function with a different name."""
    newcode = rename_code(fn.__code__, newname)
    new_fn = FunctionType(
        newcode, fn.__globals__, newname, fn.__defaults__, fn.__closure__
    )
    new_fn.__annotations__ = fn.__annotations__
    return new_fn


__all__ = [
    "MultiTypeMap",
    "Ovld",
    "OvldCall",
    "OvldMC",
    "TypeMap",
    "ovld",
    "ovld_dispatch",
]
