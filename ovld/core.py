"""Utilities to overload functions for multiple types."""


import inspect
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

    # def copy(self, transform):
    #     tm = TypeMap()
    #     tm.entries = {k: {transform(v) if transform is not None else v for v in vs} for k, vs in self.entries.items()}
    #     return tm

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

    # def __missing__(self, obj_t):
    #     """Get the handler for the given type."""
    #     print("=======")
    #     print(obj_t)
    #     results = {}
    #     to_set = []
    #     mro = type.mro(obj_t)
    #     specif = len(mro)

    #     for cls in reversed(mro):
    #         to_set.append(cls)

    #         handlers = super().get(cls, None)
    #         if handlers is not None:
    #             results.update(handlers)
    #             for cls2 in to_set:
    #                 print(cls2, cls, "1<===", results)
    #                 self[cls2] = results
    #             break

    #         else:
    #             handlers = self.entries.get(cls, None)
    #             if handlers is not None:
    #                 results.update({h: specif for h in handlers})
    #                 for cls2 in to_set:
    #                     print(cls2, "2<===", results)
    #                     self[cls2] = results
    #                 results = dict(results)
    #                 to_set = []

    #         specif -= 1

    #     if results:
    #         return results
    #     else:
    #         raise KeyError(obj_t)


class MultiTypeMap(dict):
    def __init__(self, key_error=KeyError):
        self.maps = {}
        self.empty = MISSING
        self.key_error = key_error

    def register(self, obj_t_tup, handler):
        self.clear()
        if not obj_t_tup:
            self.empty = handler
        for i, cls in enumerate(obj_t_tup):
            tm = self.maps.setdefault(i, TypeMap())
            tm.register(cls, handler)

    # def copy(self, transform=None):
    #     tm = MultiTypeMap(key_error=self.key_error)
    #     tm.maps = {k: v.copy(transform=transform)
    #                for k, v in self.maps.items()}
    #     return tm

    def __missing__(self, obj_t_tup):
        specificities = {}
        candidates = None

        if not obj_t_tup:
            if self.empty is MISSING:
                raise self.key_error(obj_t_tup, ())
            else:
                return self.empty

        for i, cls in enumerate(obj_t_tup):
            try:
                results = self.maps[i][cls]
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


@keyword_decorator
def _compile_first(fn, rename=False):
    def wrapper(self, *args, **kwargs):
        self.compile()
        return fn(self, *args, **kwargs)

    wrapper._unwrapped = fn
    wrapper._rename = rename
    return wrapper


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
        bootstrap=False,
        wrapper=None,
        initial_state=None,
        postprocess=None,
        mixins=[],
        name=None,
    ):
        """Initialize an Ovld."""
        self._locked = False
        self._wrapper = wrapper
        self.state = None
        self.initial_state = initial_state
        self.postprocess = postprocess
        self.bootstrap = bool(bootstrap or self.initial_state or self.postprocess)
        self.name = name
        self.__name__ = name
        self.defns = {}
        self.map = MultiTypeMap(key_error=self._key_error)
        for mixin in mixins:
            self.defns.update(mixin.defns)
        self.ocls = _fresh(_OvldCall)

    def _sig_string(self, type_tuple):
        return ", ".join("*" if cls is object else cls.__name__ for cls in type_tuple)

    def _key_error(self, key, possibilities):
        typenames = self._sig_string(key)
        if not possibilities:
            raise TypeError(f"No method in {self} for argument types [{typenames}]")
        else:
            hlp = ""
            for p in possibilities:
                hlp += f"* {p.__name__}\n"
            raise TypeError(
                f"Ambiguous resolution in {self} for"
                f" argument types [{typenames}]\n"
                "Candidates are:\n" + hlp
            )

    def _set_attrs_from(self, fn, wrapper=False):
        if self.name is None:
            self.name = f"{fn.__module__}.{fn.__qualname__}"
            self.__doc__ = fn.__doc__
            self.__name__ = fn.__name__
            self.__qualname__ = fn.__qualname__
            self.__module__ = fn.__module__
            sign = inspect.signature(fn)
            params = list(sign.parameters.values())
            if wrapper:
                params = params[1:]
            if self.bootstrap:
                params = params[1:]
            params = [p.replace(annotation=inspect.Parameter.empty) for p in params]
            self.__signature__ = sign.replace(parameters=params)

    def compile(self):
        """Finalize this overload."""
        self._locked = True

        cls = type(self)
        if self.name is None:
            self.name = self.__name__ = f"ovld{id(self)}"

        name = self.__name__

        # Unwrap key functions so that they don't call compile()
        for name in dir(cls):
            entry = getattr(cls, name)
            if hasattr(entry, "_unwrapped"):
                fn = entry._unwrapped
                if entry._rename:
                    fn = rename_function(fn, f"{name}.{entry._rename}")
                setattr(cls, name, fn)

        # Use the proper dispatch function
        method_name = "__xcall"
        if self.bootstrap:
            method_name += "_bind"
        if self._wrapper is not None:
            method_name += "_wrap"
        method_name += "__"
        callfn = getattr(self.ocls, method_name)
        self.ocls.__call__ = rename_function(callfn, f"{name}.dispatch")

        # Rename the wrapper
        if self._wrapper:
            self._wrapper = rename_function(self._wrapper, f"{name}.wrapper")

        for key, fn in list(self.defns.items()):
            self.register_signature(key, fn)

    def wrapper(self, wrapper):
        """Set a wrapper function."""
        if self._wrapper is not None:
            raise TypeError(f"wrapper for {self} is already set")
        self._wrapper = wrapper
        self._set_attrs_from(wrapper, wrapper=True)
        return self

    def register_signature(self, sig, fn):
        """Register a function for the given signature."""
        fn = rename_function(fn, f"{self.name}[{self._sig_string(sig)}]")
        self.map.register(sig, fn)
        return self

    def register(self, fn):
        """Register a function."""
        if self._locked:
            raise Exception(f"{self} is locked. No more methods can be defined.")
        ann = fn.__annotations__
        argnames = inspect.getfullargspec(fn).args
        if self.bootstrap:
            argnames = argnames[1:]
        typelist = []
        for i, name in enumerate(argnames):
            t = ann.get(name, None)
            if t is None:
                typelist.append(object)
            else:
                assert not isinstance(t, tuple)
                typelist.append(t)

        self._set_attrs_from(fn)
        self.defns[tuple(typelist)] = fn
        return self

    def copy(self, wrapper=MISSING, initial_state=None, postprocess=None):
        """Create a copy of this Ovld.

        New functions can be registered to the copy without affecting the
        original.
        """
        return _fresh(_Ovld)(
            bootstrap=self.bootstrap,
            wrapper=self._wrapper if wrapper is MISSING else wrapper,
            mixins=[self],
            initial_state=initial_state or self.initial_state,
            postprocess=postprocess or self.postprocess,
        )

    def variant(
        self, fn=None, *, wrapper=MISSING, initial_state=None, postprocess=None
    ):
        """Decorator to create a variant of this Ovld.

        New functions can be registered to the variant without affecting the
        original.
        """
        ov = self.copy(wrapper, initial_state, postprocess)
        if fn is None:
            return ov.register
        else:
            ov.register(fn)
            return ov

    @_compile_first
    def __get__(self, obj, cls):
        return self.ocls(
            map=self.map,
            state=self.initial_state() if self.initial_state else None,
            wrapper=self._wrapper,
            bind_to=obj,
        )

    @_compile_first
    def __getitem__(self, t):
        if not isinstance(t, tuple):
            t = (t,)
        assert not self.bootstrap
        return self.map[t]

    @_compile_first(rename="entry")
    def __call__(self, *args, **kwargs):
        """Call the overloaded function."""
        ovc = self.__get__(BOOTSTRAP, None)
        res = ovc(*args, **kwargs)
        if self.postprocess:
            res = self.postprocess(res)
        return res

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
        return self.map[t].__get__(self)

    def __xcall_bind_wrap__(self, *args, **kwargs):
        key = tuple(type(arg) for arg in args)
        method = self.map[key]
        return self.wrapper(method, self.bind_to, *args, **kwargs)

    def __xcall_bind__(self, *args, **kwargs):
        key = tuple(type(arg) for arg in args)
        method = self.map[key]
        return method(self.bind_to, *args, **kwargs)

    def __xcall_wrap__(self, *args, **kwargs):
        key = tuple(type(arg) for arg in args)
        method = self.map[key]
        return self.wrapper(method, *args, **kwargs)

    def __xcall__(self, *args, **kwargs):
        key = tuple(type(arg) for arg in args)
        method = self.map[key]
        return method(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        key = tuple(type(arg) for arg in args)

        fself = self.bind_to
        if fself is not None:
            args = (fself,) + args

        method = self.map[key]

        if self.wrapper is None:
            return method(*args, **kwargs)
        else:
            return self.wrapper(method, *args, **kwargs)


def Ovld(*args, **kwargs):
    return _fresh(_Ovld)(*args, **kwargs)


def _find_overload(fn, bootstrap, initial_state, postprocess):
    mod = __import__(fn.__module__, fromlist="_")
    dispatch = getattr(mod, fn.__name__, None)
    if dispatch is None:
        dispatch = _fresh(_Ovld)(
            bootstrap=bootstrap, initial_state=initial_state, postprocess=postprocess,
        )
    else:  # pragma: no cover
        assert bootstrap is False
        assert initial_state is None
        assert postprocess is None
    if not isinstance(dispatch, _Ovld):  # pragma: no cover
        raise TypeError("@ovld requires Ovld instance")
    return dispatch


@keyword_decorator
def ovld(fn, *, bootstrap=False, initial_state=None, postprocess=None):
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
def ovld_wrapper(wrapper, *, bootstrap=False, initial_state=None, postprocess=None):
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
    dispatch = _find_overload(wrapper, bootstrap, initial_state, postprocess)
    return dispatch.wrapper(wrapper)


ovld.wrapper = ovld_wrapper


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


__all__ = ["Ovld", "TypeMap", "TypeMapMulti", "ovld", "ovld_wrapper"]
