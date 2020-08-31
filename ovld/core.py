"""Utilities to overload functions for multiple types."""


import inspect
import itertools
import math
import textwrap
from types import FunctionType

from .mro import compose_mro
from .utils import BOOTSTRAP, MISSING, keyword_decorator


class TypeMap(dict):
    def __init__(self):
        self.entries = {}
        self.types = set()

    def register(self, obj_t, handler):
        self.clear()
        self.types.add(obj_t)
        s = self.entries.setdefault(obj_t, set())
        s.add(handler)

    def __missing__(self, obj_t):
        """Get the handler for the given type."""

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
    def __init__(self, key_error=KeyError):
        self.maps = {}
        self.empty = MISSING
        self.key_error = key_error

    def register(self, obj_t_tup, nargs, handler):
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
    return type(t.__name__, (t,), {})


_premades = {}


@keyword_decorator
def _premade(kls, bind):
    _premades[bind] = kls


@keyword_decorator
def _setattrs(fn, **kwargs):
    for k, v in kwargs.items():
        setattr(fn, k, v)
    return fn


class _PremadeGeneric:
    def __get__(self, obj, cls):
        if obj is None:
            raise TypeError(
                f"Cannot get class method: {cls.__name__}::{self.__name__}"
            )
        return self.ocls(
            map=self.map,
            state=self.initial_state() if self.initial_state else None,
            bind_to=obj,
        )

    def __getitem__(self, t):
        if not isinstance(t, tuple):
            t = (t,)
        assert not self.bootstrap
        return self.map[t]

    @_setattrs(rename="entry")
    def __call__(self, *args, **kwargs):
        """Call the overloaded function."""
        ovc = self.__get__(BOOTSTRAP, None)
        res = ovc(*args, **kwargs)
        if self.postprocess:
            res = self.postprocess(self, res)
        return res


@_premade(bind=False)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __call__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return method(*args, **kwargs)

    __subcall__ = False


@_premade(bind=True)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __subcall__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return method(self.bind_to, *args, **kwargs)


def _compile_first(name):
    def deco(self, *args, **kwargs):
        self.compile()
        fn = getattr(self, name)
        assert fn is not deco
        return fn(*args, **kwargs)

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
    ):
        """Initialize an Ovld."""
        self._compiled = False
        self._dispatch = dispatch
        self.state = None
        self.maindoc = None
        self.type_error = type_error
        self.initial_state = initial_state
        self.postprocess = postprocess
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
        self.defns = {}
        for mixin in mixins:
            if mixin.bootstrap is not None:
                self.bootstrap = mixin.bootstrap
            assert mixin.bootstrap is self.bootstrap
            self.defns.update(mixin.defns)
        self.ocls = _fresh(self.bootstrap_class)
        self._make_signature()

    def _sig_string(self, type_tuple):
        def clsname(cls):
            if cls is object:
                return "*"
            else:
                return cls.__name__

        return ", ".join(map(clsname, type_tuple))

    def _key_error(self, key, possibilities):
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

    def _make_signature(self):
        def modelA(*args, **kwargs):  # pragma: no cover
            pass

        def modelB(self, *args, **kwargs):  # pragma: no cover
            pass

        doc = f"{self.maindoc}\n" if self.maindoc else ""
        for key, fn in self.defns.items():
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
        """Finalize this overload."""
        self._compiled = True
        self.map = MultiTypeMap(key_error=self._key_error)

        cls = type(self)
        if self.name is None:
            self.name = self.__name__ = f"ovld{id(self)}"

        name = self.__name__

        # Replace functions by premade versions that are specialized to the
        # pattern of bootstrap
        model = _premades[self.bootstrap]
        for method in ("__get__", "__getitem__", "__call__"):
            setattr(cls, method, self._maybe_rename(getattr(model, method)))
        self.ocls.__call__ = self._maybe_rename(model.__subcall__)
        if self._dispatch:
            if model.__subcall__:
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
        return self.map[tuple(map(type, args))]

    def register_signature(self, key, fn):
        """Register a function for the given signature."""
        sig, min, max, vararg = key
        fn = rename_function(fn, f"{self.__name__}[{self._sig_string(sig)}]")
        self.map.register(sig, (min, max, vararg), fn)
        return self

    def register(self, fn):
        """Register a function."""
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
            self.defns[tuple(tl), req_pos, max_pos, bool(argspec.varargs)] = fn

        self._make_signature()
        if self._compiled:
            self.compile()
        return self

    def copy(
        self, dispatch=MISSING, initial_state=None, postprocess=None,
    ):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return _fresh(_Ovld)(
            bootstrap=self.bootstrap,
            dispatch=self._dispatch if dispatch is MISSING else dispatch,
            mixins=[self],
            initial_state=initial_state or self.initial_state,
            postprocess=postprocess or self.postprocess,
        )

    def variant(
        self,
        fn=None,
        *,
        dispatch=MISSING,
        initial_state=None,
        postprocess=None,
    ):
        """Decorator to create a variant of this Ovld.

        New functions can be registered to the variant without affecting the
        original.
        """
        ov = self.copy(dispatch, initial_state, postprocess)
        if fn is None:
            return ov.register
        else:
            ov.register(fn)
            return ov

    __get__ = _compile_first("__get__")
    __getitem__ = _compile_first("__getitem__")
    __call__ = _compile_first("__call__")

    def __repr__(self):
        return f"<Ovld {self.name or hex(id(self))}>"


class OvldCall:
    """Context for an Ovld call."""

    def __init__(self, map, state, bind_to):
        """Initialize an OvldCall."""
        self.map = map
        self.state = state
        self.bind_to = self if bind_to is BOOTSTRAP else bind_to

    def __getitem__(self, t):
        if not isinstance(t, tuple):
            t = (t,)
        return self.map[t].__get__(self.bind_to)

    def resolve(self, *args):
        return self[tuple(map(type, args))]

    def with_state(self, state):
        return type(self)(self.map, state, BOOTSTRAP)


def Ovld(*args, **kwargs):
    return _fresh(_Ovld)(*args, **kwargs)


class ovld_cls_dict(dict):
    """A dict for use with OvldMC.__prepare__.

    Setting the same key more than once creates an Ovld that can dispatch
    to any of the values.
    """

    def __setitem__(self, attr, value):
        if attr in self:
            prev = self[attr]
            if isinstance(prev, _Ovld):
                o = prev
            else:
                o = Ovld()
                o.register(self[attr])
            o.register(value)
            value = o
        super().__setitem__(attr, value)


class OvldMC(type):
    """Metaclass that allows overloading.

    A class which uses this metaclass can define multiple functions with
    the same name and different type signatures.
    """

    def __prepare__(self, cls):
        return ovld_cls_dict()


def _find_overload(fn, **kwargs):
    mod = __import__(fn.__module__, fromlist="_")
    dispatch = getattr(mod, fn.__name__, None)
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
    """
    ov = _find_overload(dispatch, **kwargs)
    return ov.dispatch(dispatch)


ovld.dispatch = ovld_dispatch


def rename_function(fn, newname):
    """Create a copy of the function with a different name."""
    co = fn.__code__

    extra_args = []
    if hasattr(co, "co_posonlyargcount"):  # pragma: no cover
        extra_args.append(co.co_posonlyargcount)

    newcode = type(co)(
        co.co_argcount,
        *extra_args,
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
    return FunctionType(
        newcode, fn.__globals__, newname, fn.__defaults__, fn.__closure__
    )


__all__ = [
    "MultiTypeMap",
    "Ovld",
    "OvldCall",
    "OvldMC",
    "TypeMap",
    "ovld",
    "ovld_dispatch",
]
