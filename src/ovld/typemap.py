import inspect
import math
import typing
from types import CodeType

from .dependent import DependentType, dependent_match
from .mro import sort_types
from .utils import MISSING


class GenericAliasMC(type):
    def __instancecheck__(cls, obj):
        return hasattr(obj, "__origin__")


class GenericAlias(metaclass=GenericAliasMC):
    pass


def is_type_of_type(t):
    return getattr(t, "__origin__", None) is type


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
        if isinstance(obj_t, str):
            obj_t = eval(obj_t, getattr(handler[0], "__globals__", {}))

        self.clear()
        if is_type_of_type(obj_t):
            self.types.add(obj_t.__args__[0])
        else:
            self.types.add(obj_t)
        s = self.entries.setdefault(obj_t, set())
        s.add(handler)

    def __missing__(self, obj_t):
        """Get the handler for the given type.

        The result is cached so that the normal dict getitem will find it
        the next time getitem is called.
        """
        results = {}
        if itot := is_type_of_type(obj_t):
            groups = list(sort_types(obj_t.__args__[0], self.types))
        else:
            groups = list(sort_types(obj_t, self.types))

        for lvl, grp in enumerate(reversed(groups)):
            for cls in grp:
                if itot:
                    cls = type[cls]
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
        self.priorities = {}
        self.dependent = {}
        self.type_tuples = {}
        self.empty = MISSING
        self.key_error = key_error
        self.all = {}
        self.errors = {}

    def transform(self, obj):
        if isinstance(obj, GenericAlias):
            return type[obj]
        elif obj is typing.Any:
            return type[object]
        elif isinstance(obj, type):
            return type[obj]
        else:
            return type(obj)

    def mro(self, obj_t_tup):
        specificities = {}
        candidates = None
        nargs = len([t for t in obj_t_tup if not isinstance(t, tuple)])

        for i, cls in enumerate(obj_t_tup):
            if isinstance(cls, tuple):
                i, cls = cls

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

        candidates = [
            (c, self.priorities.get(c, 0), tuple(specificities[c]))
            for c in candidates
        ]

        # The sort ensures that if candidate A dominates candidate B, A will
        # appear before B in the list. That's because it must dominate all
        # other possibilities on all arguments, so the sum of all specificities
        # has to be greater.
        # Note: priority is always more important than specificity
        candidates.sort(key=lambda cspc: (cspc[1], sum(cspc[2])), reverse=True)

        self.all[obj_t_tup] = {
            getattr(c[0], "__code__", None) for c in candidates
        }

        processed = set()

        def _pull(candidates):
            candidates = [
                (c, a, b) for (c, a, b) in candidates if c not in processed
            ]
            if not candidates:
                return
            rval = [candidates[0]]
            c1, p1, spc1 = candidates[0]
            for c2, p2, spc2 in candidates[1:]:
                if p1 > p2 or (
                    spc1 != spc2 and all(s1 >= s2 for s1, s2 in zip(spc1, spc2))
                ):
                    # Candidate 1 dominates candidate 2
                    continue
                else:
                    processed.add(c2)
                    # Candidate 1 does not dominate candidate 2, so we add it
                    # to the list.
                    rval.append((c2, p2, spc2))
            yield rval
            if len(rval) >= 1:
                yield from _pull(candidates[1:])

        return list(_pull(candidates))

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

        amin, amax, vararg, priority = nargs

        entry = (handler, amin, amax, vararg)
        if not obj_t_tup:
            self.empty = entry

        self.priorities[handler] = priority
        self.type_tuples[handler] = obj_t_tup
        self.dependent[handler] = any(
            isinstance(t, DependentType) for t in obj_t_tup
        )

        for i, cls in enumerate(obj_t_tup):
            if isinstance(cls, tuple):
                i, cls = cls
            if i not in self.maps:
                self.maps[i] = TypeMap()
            self.maps[i].register(cls, entry)

        if vararg:
            if -1 not in self.maps:
                self.maps[-1] = TypeMap()
            self.maps[-1].register(object, entry)

    def display_methods(self):
        for h, prio in sorted(self.priorities.items(), key=lambda kv: -kv[1]):
            prio = f"[{prio}]"
            width = 6
            print(f"{prio:{width}} \033[1m{h.__name__}\033[0m")
            co = h.__code__
            print(f"{'':{width-2}} @ {co.co_filename}:{co.co_firstlineno}")

    def display_resolution(self, *args):
        message = "No method will be called."
        argt = map(self.transform, args)
        finished = False
        rank = 1
        for grp in self.mro(tuple(argt)):
            grp.sort(key=lambda x: x[0].__name__)
            match = [
                dependent_match(self.type_tuples[handler], args)
                for handler, _, _ in grp
            ]
            ambiguous = len([m for m in match if m]) > 1
            for m, (handler, prio, spec) in zip(match, grp):
                color = "\033[0m"
                if finished:
                    bullet = "--"
                    color = "\033[1;90m"
                elif not m:
                    bullet = "!="
                    color = "\033[1;90m"
                elif ambiguous:
                    bullet = "=="
                    color = "\033[1;31m"
                else:
                    bullet = f"#{rank}"
                    if rank == 1:
                        message = f"{handler.__name__} will be called first."
                        color = "\033[1;32m"
                    rank += 1
                spec = ".".join(map(str, spec))
                lvl = f"[{prio}:{spec}]"
                width = 2 * len(args) + 6
                print(f"{color}{bullet} {lvl:{width}} {handler.__name__}")
                co = handler.__code__
                print(
                    f"   {'':{width-1}}@ {co.co_filename}:{co.co_firstlineno}\033[0m"
                )
            if ambiguous:
                message += " There is ambiguity between multiple matching methods, marked '=='."
                finished = True
        print("Resolution:", message)

    def wrap_dependent(self, tup, handlers, group):
        handlers = list(handlers)
        htup = [(h, self.type_tuples[h]) for h in handlers]
        nxt_key = (handlers[0].__code__, *tup)

        def dependent_find_method(args):
            matches = [h for h, tup in htup if dependent_match(tup, args)]
            if len(matches) == 1:
                return matches[0]
            elif len(matches) == 0:
                return self[nxt_key]
            else:
                raise self.key_error(tup, group)

        if inspect.getfullargspec(handlers[0]).args[0] == "self":

            def dependent_dispatch(slf, *args):
                return dependent_find_method(args)(slf, *args)
        else:

            def dependent_dispatch(*args):
                return dependent_find_method(args)(*args)

        return dependent_dispatch

    def resolve(self, obj_t_tup):
        results = self.mro(obj_t_tup)
        if not results:
            raise self.key_error(obj_t_tup, ())
        parents = []
        for group in results:
            tups = (
                [obj_t_tup]
                if not parents
                else [(parent, *obj_t_tup) for parent in parents]
            )
            dependent = any(self.dependent[fn] for (fn, _, _) in group)
            if dependent:
                handlers = [fn for (fn, _, _) in group]
                wrapped = self.wrap_dependent(obj_t_tup, handlers, group)
                for tup in tups:
                    self[tup] = wrapped
                parents = [h.__code__ for h in handlers]
            elif len(group) != 1:
                for tup in tups:
                    self.errors[tup] = self.key_error(obj_t_tup, group)
                break
            else:
                ((fn, _, _),) = group
                for tup in tups:
                    self[tup] = fn
                if hasattr(fn, "__code__"):
                    parents = [fn.__code__]
                else:
                    break

        return True

    def __missing__(self, obj_t_tup):
        if obj_t_tup and isinstance(obj_t_tup[0], CodeType):
            real_tup = obj_t_tup[1:]
            self[real_tup]
            if obj_t_tup[0] not in self.all[real_tup]:
                return self[real_tup]
            elif obj_t_tup in self.errors:
                raise self.errors[obj_t_tup]
            elif obj_t_tup in self:  # pragma: no cover
                # PROBABLY not reachable
                return self[obj_t_tup]
            else:
                raise self.key_error(real_tup, ())

        if not obj_t_tup:
            if self.empty is MISSING:
                raise self.key_error(obj_t_tup, ())
            else:
                return self.empty[0]

        self.resolve(obj_t_tup)
        if obj_t_tup in self.errors:
            raise self.errors[obj_t_tup]
        else:
            return self[obj_t_tup]
