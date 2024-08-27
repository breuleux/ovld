from itertools import product

from graphlib import TopologicalSorter

from .dependent import DependentType


def _issubclass(c1, c2):
    if isinstance(c1, DependentType) and isinstance(c2, DependentType):
        return c1.bound != c2.bound and _issubclass(c1.bound, c2.bound)
    elif isinstance(c1, DependentType) or isinstance(c2, DependentType):
        return False
    c1 = getattr(c1, "__proxy_for__", c1)
    c2 = getattr(c2, "__proxy_for__", c2)
    if hasattr(c1, "__origin__") or hasattr(c2, "__origin__"):
        o1 = getattr(c1, "__origin__", c1)
        o2 = getattr(c2, "__origin__", c2)
        if issubclass(o1, o2):
            if o2 is c2:  # pragma: no cover
                return True
            else:
                args1 = getattr(c1, "__args__", ())
                args2 = getattr(c2, "__args__", ())
                if len(args1) != len(args2):
                    return False
                return all(_issubclass(a1, a2) for a1, a2 in zip(args1, args2))
        else:
            return False
    else:
        return issubclass(c1, c2)


def _may_cover(c1, c2):
    if isinstance(c1, DependentType):
        if isinstance(c2, DependentType):
            return False
        return _issubclass(c2, c1.bound)
    return False


def _refines(c1, c2):
    return _issubclass(c1, c2) or _may_cover(c1, c2)


def sort_types(cls, avail):
    # We filter everything except subclasses and dependent types that *might* cover
    # the object represented by cls.
    avail = [t for t in avail if _refines(cls, t) or _may_cover(t, cls)]
    deps = {t: set() for t in avail}
    for t1, t2 in product(avail, avail):
        if t1 is not t2 and _refines(t1, t2):
            deps[t2].add(t1)
    sorter = TopologicalSorter(deps)
    sorter.prepare()
    while sorter.is_active():
        nodes = sorter.get_ready()
        yield nodes
        for n in nodes:
            sorter.done(n)
