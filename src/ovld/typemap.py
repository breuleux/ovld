import inspect
import math
import typing
from dataclasses import dataclass
from itertools import count
from types import CodeType

from .dependent import DependentType
from .mro import sort_types
from .recode import generate_dependent_dispatch
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
        groups = list(sort_types(obj_t, self.types))

        for lvl, grp in enumerate(reversed(groups)):
            for cls in grp:
                handlers = self.entries.get(cls, None)
                if handlers:
                    results.update({h: lvl for h in handlers})

        if results:
            self[obj_t] = results
            return results
        else:
            raise KeyError(obj_t)


@dataclass
class Candidate:
    handler: object
    priority: float
    specificity: tuple
    tiebreak: int

    def sort_key(self):
        return self.priority, sum(self.specificity), self.tiebreak

    def dominates(self, other):
        if self.priority > other.priority:
            return True
        elif self.specificity != other.specificity:
            return all(
                s1 >= s2 for s1, s2 in zip(self.specificity, other.specificity)
            )
        else:
            return self.tiebreak > other.tiebreak


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

    def __init__(self, name="_ovld", key_error=KeyError):
        self.maps = {}
        self.priorities = {}
        self.tiebreaks = {}
        self.dependent = {}
        self.type_tuples = {}
        self.empty = MISSING
        self.key_error = key_error
        self.name = name
        self.dispatch_id = count()
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
        names = {t[0] for t in obj_t_tup if isinstance(t, tuple)}

        for i, cls in enumerate(obj_t_tup):
            if isinstance(cls, tuple):
                i, cls = cls

            try:
                results = self.maps[i][cls]
            except KeyError:
                results = {}

            results = {
                handler: spc
                for (handler, sig), spc in results.items()
                if sig.req_pos
                <= nargs
                <= (math.inf if sig.vararg else sig.max_pos)
                and not (sig.req_names - names)
            }

            try:
                vararg_results = self.maps[-1][cls]
            except KeyError:
                vararg_results = {}

            vararg_results = {
                handler: spc
                for (handler, sig), spc in vararg_results.items()
                if sig.req_pos <= nargs and i >= sig.max_pos
            }

            results.update(vararg_results)

            if candidates is None:
                candidates = set(results.keys())
            else:
                candidates &= results.keys()
            for c in candidates:
                specificities.setdefault(c, []).append(results[c])

        candidates = [
            Candidate(
                handler=c,
                priority=self.priorities.get(c, 0),
                specificity=tuple(specificities[c]),
                tiebreak=self.tiebreaks.get(c, 0),
            )
            for c in candidates
        ]

        # The sort ensures that if candidate A dominates candidate B, A will
        # appear before B in the list. That's because it must dominate all
        # other possibilities on all arguments, so the sum of all specificities
        # has to be greater.
        # Note: priority is always more important than specificity

        candidates.sort(key=Candidate.sort_key, reverse=True)

        self.all[obj_t_tup] = {
            getattr(c.handler, "__code__", None) for c in candidates
        }

        processed = set()

        def _pull(candidates):
            candidates = [c for c in candidates if c.handler not in processed]
            if not candidates:
                return
            rval = [candidates[0]]
            c1 = candidates[0]
            for c2 in candidates[1:]:
                if c1.dominates(c2):
                    # Candidate 1 dominates candidate 2
                    continue
                else:
                    processed.add(c2.handler)
                    # Candidate 1 does not dominate candidate 2, so we add it
                    # to the list.
                    rval.append(c2)
            yield rval
            if len(rval) >= 1:
                yield from _pull(candidates[1:])

        return list(_pull(candidates))

    def register(self, sig, handler):
        """Register a handler for a tuple of argument types.

        Arguments:
            sig: A Signature object.
            handler: A function to handle the tuple.
        """
        self.clear()

        obj_t_tup = sig.types
        entry = (handler, sig)
        if not obj_t_tup:
            self.empty = entry

        self.priorities[handler] = sig.priority
        self.tiebreaks[handler] = sig.tiebreak
        self.type_tuples[handler] = obj_t_tup
        self.dependent[handler] = any(
            isinstance(t[1] if isinstance(t, tuple) else t, DependentType)
            for t in obj_t_tup
        )

        for i, cls in enumerate(obj_t_tup):
            if isinstance(cls, tuple):
                i, cls = cls
            if i not in self.maps:
                self.maps[i] = TypeMap()
            self.maps[i].register(cls, entry)

        if sig.vararg:  # pragma: no cover
            # TODO: either add this back in, or remove it
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

    def display_resolution(self, *args, **kwargs):
        def dependent_match(tup, args):
            for t, a in zip(tup, args):
                if isinstance(t, tuple):
                    t = t[1]
                    a = a[1]
                if isinstance(t, DependentType) and not t.check(a):
                    return False
            return True

        message = "No method will be called."
        argt = [
            *map(self.transform, args),
            *[(k, self.transform(v)) for k, v in kwargs.items()],
        ]
        finished = False
        rank = 1
        for grp in self.mro(tuple(argt)):
            grp.sort(key=lambda x: x.handler.__name__)
            match = [
                dependent_match(
                    self.type_tuples[c.handler], [*args, *kwargs.items()]
                )
                for c in grp
            ]
            ambiguous = len([m for m in match if m]) > 1
            for m, c in zip(match, grp):
                handler = c.handler
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
                spec = ".".join(map(str, c.specificity))
                lvl = f"[{c.priority}:{spec}]"
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

    def wrap_dependent(self, tup, handlers, group, next_call):
        handlers = list(handlers)
        htup = [(h, self.type_tuples[h]) for h in handlers]
        slf = (
            "self, "
            if inspect.getfullargspec(handlers[0]).args[0] == "self"
            else ""
        )
        return generate_dependent_dispatch(
            tup,
            htup,
            next_call,
            slf,
            name=f"{self.name}.specialized_dispatch_{next(self.dispatch_id)}",
            err=self.key_error(tup, group),
            nerr=self.key_error(tup, ()),
        )

    def resolve(self, obj_t_tup):
        results = self.mro(obj_t_tup)
        if not results:
            raise self.key_error(obj_t_tup, ())

        funcs = []
        for group in reversed(results):
            handlers = [c.handler for c in group]
            dependent = any(self.dependent[c.handler] for c in group)
            if dependent:
                nxt = self.wrap_dependent(
                    obj_t_tup, handlers, group, funcs[-1] if funcs else None
                )
            elif len(group) != 1:
                nxt = None
            else:
                nxt = handlers[0]
            codes = [h.__code__ for h in handlers if hasattr(h, "__code__")]
            funcs.append((nxt, codes))

        funcs.reverse()

        parents = []
        for group, (func, codes) in zip(results, funcs):
            tups = (
                [obj_t_tup]
                if not parents
                else [(parent, *obj_t_tup) for parent in parents]
            )
            if func is None:
                for tup in tups:
                    self.errors[tup] = self.key_error(obj_t_tup, group)
                break
            else:
                for tup in tups:
                    self[tup] = func
            if not codes:
                break
            parents = codes

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
            if self.empty is MISSING:  # pragma: no cover
                # Might not be reachable because of codegen
                raise self.key_error(obj_t_tup, ())
            else:
                return self.empty[0]

        self.resolve(obj_t_tup)
        if obj_t_tup in self.errors:
            raise self.errors[obj_t_tup]
        else:
            return self[obj_t_tup]
