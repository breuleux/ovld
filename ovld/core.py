"""Utilities to overload functions for multiple types."""


import inspect
import textwrap
from types import FunctionType
from functools import reduce

from .utils import BOOTSTRAP, MISSING, keyword_decorator


class TypeMap(dict):
    def __init__(self):
        self.entries = {}

    def register(self, obj_t, handler):
        self.clear()
        s = self.entries.setdefault(obj_t, set())
        s.add(handler)

    def __missing__(self, obj_t):
        """Get the handler for the given type."""

        results = {}
        for lvl, cls in enumerate(reversed(type.mro(obj_t))):
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

    def register(self, obj_t_tup, handler):
        self.clear()
        nargs = len(obj_t_tup)
        if not obj_t_tup:
            self.empty = handler
        for i, cls in enumerate(obj_t_tup):
            tm = self.maps.setdefault((nargs, i), TypeMap())
            tm.register(cls, handler)

    def __missing__(self, obj_t_tup):
        specificities = {}
        candidates = None
        nargs = len(obj_t_tup)

        if not obj_t_tup:
            if self.empty is MISSING:
                raise self.key_error(obj_t_tup, ())
            else:
                return self.empty

        for i, cls in enumerate(obj_t_tup):
            try:
                results = self.maps[(nargs, i)][cls]
            except KeyError:
                raise self.key_error(obj_t_tup, ())
            if candidates is None:
                candidates = set(results.keys())
            else:
                candidates &= results.keys()
            for c in candidates:
                specificities.setdefault(c, []).append(results[c])

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
def _premade(kls, bind, wrapper):
    _premades[(bind, wrapper)] = kls


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
            wrapper=self._wrapper,
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
            res = self.postprocess(res)
        return res


@_premade(bind=False, wrapper=False)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __call__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return method(*args, **kwargs)

    __subcall__ = False


@_premade(bind=False, wrapper=True)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __call__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return self._wrapper(method, *args, **kwargs)

    __subcall__ = False


@_premade(bind=True, wrapper=False)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __subcall__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return method(self.bind_to, *args, **kwargs)


@_premade(bind=True, wrapper=True)
class _(_PremadeGeneric):
    @_setattrs(rename="dispatch")
    def __subcall__(self, *args, **kwargs):
        key = tuple(map(type, args))
        method = self.map[key]
        return self.wrapper(method, self.bind_to, *args, **kwargs)


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
        bootstrap: Whether to bind the first argument to the OvldCall
            object. Forced to True if initial_state or postprocess is not
            None.
        wrapper: A function to use as the entry point. In addition to all
            normal arguments, it will receive as its first argument the
            function to dispatch to.
        dispatch: A function to use as the entry point. It must find the
            function to dispatch to and call it.
        initial_state: A function returning the initial state, or None if
            there is no state.
        postprocess: A function to call on the return value. It is not called
            after recursive calls.
        mixins: A list of Ovld instances that contribute functions to this
            Ovld.
        name: Optional name for the Ovld. If not provided, it will be
            gotten automatically from the first registered function or wrapper.
    """

    def __init__(
        self,
        *,
        bootstrap=None,
        wrapper=None,
        dispatch=None,
        initial_state=None,
        postprocess=None,
        mixins=[],
        name=None,
    ):
        """Initialize an Ovld."""
        self._locked = False
        self._wrapper = wrapper
        self._dispatch = dispatch
        assert wrapper is None or dispatch is None
        self.state = None
        self.maindoc = None
        self.initial_state = initial_state
        self.postprocess = postprocess
        if self.initial_state or self.postprocess:
            assert bootstrap is not False
            self.bootstrap = True
        else:
            self.bootstrap = bootstrap
        self.name = name
        self.__name__ = name
        self.defns = {}
        self.map = MultiTypeMap(key_error=self._key_error)
        for mixin in mixins:
            if mixin.bootstrap is not None:
                self.bootstrap = mixin.bootstrap
            assert mixin.bootstrap is self.bootstrap
            self.defns.update(mixin.defns)
        self.ocls = _fresh(_OvldCall)
        self._make_signature()

    def _sig_string(self, type_tuple):
        return ", ".join(
            "*" if cls is object else cls.__name__ for cls in type_tuple
        )

    def _key_error(self, key, possibilities):
        typenames = self._sig_string(key)
        if not possibilities:
            raise TypeError(
                f"No method in {self} for argument types [{typenames}]"
            )
        else:
            hlp = ""
            for p in possibilities:
                hlp += f"* {p.__name__}\n"
            raise TypeError(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                "Candidates are:\n" + hlp
            )

    def _make_signature(self):
        def modelA(*args, **kwargs):  # pragma: no cover
            pass

        def modelB(self, *args, **kwargs):  # pragma: no cover
            pass

        doc = f"{self.maindoc}\n\n" if self.maindoc else ""
        for key, fn in self.defns.items():
            fndef = inspect.signature(fn)
            fdoc = fn.__doc__
            if not fdoc or fdoc == self.maindoc:
                doc += f"{self.__name__}{fndef}\n\n"
            else:
                fdoc = textwrap.indent(fdoc, "    ")
                doc += f"{self.__name__}{fndef}\n{fdoc}\n\n"
        self.__doc__ = doc
        if self.bootstrap:
            self.__signature__ = inspect.signature(modelB)
        else:
            self.__signature__ = inspect.signature(modelA)

    def _set_attrs_from(self, fn, wrapper=False, dispatch=False):
        if self.bootstrap is None:
            sign = inspect.signature(fn)
            params = list(sign.parameters.values())
            if wrapper:
                params = params[1:]
            if not dispatch:
                if params and params[0].name == "self":
                    self.bootstrap = True
                else:
                    self.bootstrap = False

        if self.name is None:
            self.name = f"{fn.__module__}.{fn.__qualname__}"
            self.maindoc = fn.__doc__
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
        self._locked = True

        cls = type(self)
        if self.name is None:
            self.name = self.__name__ = f"ovld{id(self)}"

        name = self.__name__

        # Replace functions by premade versions that are specialized to the
        # pattern of bootstrap and wrapper
        model = _premades[(self.bootstrap, self._wrapper is not None)]
        for method in ("__get__", "__getitem__", "__call__"):
            setattr(cls, method, self._maybe_rename(getattr(model, method)))
        self.ocls.__call__ = self._maybe_rename(model.__subcall__)
        if self._dispatch:
            if model.__subcall__:
                self.ocls.__call__ = self._dispatch
            else:
                cls.__call__ = self._dispatch

        # Rename the wrapper
        if self._wrapper:
            self._wrapper = rename_function(self._wrapper, f"{name}.wrapper")

        # Rename the dispatch
        if self._dispatch:
            self._dispatch = rename_function(self._dispatch, f"{name}.dispatch")

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

    def wrapper(self, wrapper):
        """Set a wrapper function."""
        if self._wrapper is not None:
            raise TypeError(f"wrapper for {self} is already set")
        if self._dispatch is not None:
            raise TypeError(f"cannot set both wrapper and dispatch")
        self._wrapper = wrapper
        self._set_attrs_from(wrapper, wrapper=True)
        return self

    def dispatch(self, dispatch):
        """Set a dispatch function."""
        if self._dispatch is not None:
            raise TypeError(f"dispatch for {self} is already set")
        if self._wrapper is not None:
            raise TypeError(f"cannot set both wrapper and dispatch")
        self._dispatch = dispatch
        self._set_attrs_from(dispatch, dispatch=True)
        return self

    def resolve(self, *args):
        return self.map[tuple(map(type, args))]

    def register_signature(self, sig, fn):
        """Register a function for the given signature."""
        fn = rename_function(fn, f"{self.__name__}[{self._sig_string(sig)}]")
        self.map.register(sig, fn)
        return self

    def register(self, fn):
        """Register a function."""
        if self._locked:
            raise Exception(
                f"{self} is locked. No more methods can be defined."
            )

        self._set_attrs_from(fn)

        ann = fn.__annotations__
        argnames = inspect.getfullargspec(fn).args
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
                assert not isinstance(t, tuple)
                typelist.append(t)

        self.defns[tuple(typelist)] = fn
        self._make_signature()
        return self

    def copy(
        self,
        wrapper=MISSING,
        dispatch=MISSING,
        initial_state=None,
        postprocess=None,
    ):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return _fresh(_Ovld)(
            bootstrap=self.bootstrap,
            wrapper=self._wrapper if wrapper is MISSING else wrapper,
            dispatch=self._dispatch if dispatch is MISSING else dispatch,
            mixins=[self],
            initial_state=initial_state or self.initial_state,
            postprocess=postprocess or self.postprocess,
        )

    def variant(
        self,
        fn=None,
        *,
        wrapper=MISSING,
        dispatch=MISSING,
        initial_state=None,
        postprocess=None,
    ):
        """Decorator to create a variant of this Ovld.

        New functions can be registered to the variant without affecting the
        original.
        """
        ov = self.copy(wrapper, dispatch, initial_state, postprocess)
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


class _OvldCall:
    """Context for an Ovld call."""

    def __init__(self, map, state, wrapper, bind_to):
        """Initialize an OvldCall."""
        self.map = map
        self.state = state
        self.wrapper = wrapper
        self.bind_to = self if bind_to is BOOTSTRAP else bind_to

    def __getitem__(self, t):
        return self.map[t].__get__(self.bind_to)

    def resolve(self, *args):
        return self[tuple(map(type, args))]


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


def _find_overload(fn, bootstrap, initial_state, postprocess):
    mod = __import__(fn.__module__, fromlist="_")
    dispatch = getattr(mod, fn.__name__, None)
    if dispatch is None:
        dispatch = _fresh(_Ovld)(
            bootstrap=bootstrap,
            initial_state=initial_state,
            postprocess=postprocess,
        )
    else:  # pragma: no cover
        assert bootstrap is None
        assert initial_state is None
        assert postprocess is None
    if not isinstance(dispatch, _Ovld):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    return dispatch


@keyword_decorator
def ovld(fn, *, bootstrap=None, initial_state=None, postprocess=None):
    """Overload a function.

    Overloading is based on the function name.

    The decorated function should have one parameter annotated with a type.
    Any parameter can be annotated, but only one, and every overloading of a
    function should annotate the same parameter.

    The decorator optionally takes keyword arguments, *only* on the first
    use.

    Arguments:
        fn: The function to register.
        bootstrap: Whether to bootstrap this function so that it receives
            itself as its first argument. Useful for recursive functions.
        initial_state: A function with no arguments that returns the initial
            state for top level calls to the overloaded function, or None
            if there is no initial state.
        postprocess: A function to transform the result. Not called on the
            results of recursive calls.

    """
    dispatch = _find_overload(fn, bootstrap, initial_state, postprocess)
    return dispatch.register(fn)


@keyword_decorator
def ovld_wrapper(
    wrapper, *, bootstrap=None, initial_state=None, postprocess=None
):
    """Overload a function using the decorated function as a wrapper.

    The wrapper is the entry point for the function and receives as its
    first argument the method to dispatch to, and then the arguments to
    give to that method.

    Arguments:
        wrapper: Function to wrap the dispatch with.
        bootstrap: Whether to bootstrap this function so that it receives
            itself as its first argument. Useful for recursive functions.
        initial_state: A function with no arguments that returns the initial
            state for top level calls to the overloaded function, or None
            if there is no initial state.
        postprocess: A function to transform the result. Not called on the
            results of recursive calls.

    """
    ov = _find_overload(wrapper, bootstrap, initial_state, postprocess)
    return ov.wrapper(wrapper)


@keyword_decorator
def ovld_dispatch(
    dispatch, *, bootstrap=None, initial_state=None, postprocess=None
):
    """Overload a function using the decorated function as a dispatcher.

    The dispatch is the entry point for the function and receives a `self`
    which is an Ovld or OvldCall instance, and the rest of the arguments.
    It may call `self.resolve(arg1, arg2, ...)` to get the right method to
    call.

    Arguments:
        dispatch: Function to use for dispatching.
        bootstrap: Whether to bootstrap this function so that it receives
            itself as its first argument. Useful for recursive functions.
        initial_state: A function with no arguments that returns the initial
            state for top level calls to the overloaded function, or None
            if there is no initial state.
        postprocess: A function to transform the result. Not called on the
            results of recursive calls.

    """
    ov = _find_overload(dispatch, bootstrap, initial_state, postprocess)
    return ov.dispatch(dispatch)


ovld.wrapper = ovld_wrapper
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
    "Ovld",
    "OvldMC",
    "TypeMap",
    "TypeMapMulti",
    "ovld",
    "ovld_dispatch",
    "ovld_wrapper",
]
