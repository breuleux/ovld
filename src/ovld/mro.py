from graphlib import TopologicalSorter
from itertools import product

from .dependent import DependentType
from .types import Order, typeorder


def _issubclass(c1, c2, strict=False):
    order = typeorder(c1, c2)
    if strict:
        return order is Order.LESS
    else:
        return order is Order.LESS or order is Order.SAME


def _refines(c1, c2):
    return _issubclass(c1, c2, strict=True) or _may_cover(c1, c2)


def _may_cover(c1, c2):
    if isinstance(c1, DependentType):
        if isinstance(c2, DependentType):
            return False
        return _issubclass(c2, c1.bound) or _issubclass(c1.bound, c2)
    return False


def sort_types(cls, avail):
    # We filter everything except subclasses and dependent types that *might* cover
    # the object represented by cls.
    avail = [
        t
        for t in avail
        if _issubclass(cls, t)
        or (isinstance(t, DependentType) and _issubclass(cls, t.bound))
    ]
    deps = {t: set() for t in avail}
    for t1, t2 in product(avail, avail):
        if _refines(t1, t2):
            deps[t2].add(t1)
    sorter = TopologicalSorter(deps)
    sorter.prepare()
    while sorter.is_active():
        nodes = sorter.get_ready()
        yield nodes
        for n in nodes:
            sorter.done(n)
