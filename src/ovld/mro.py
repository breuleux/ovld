import typing
from dataclasses import dataclass
from enum import Enum
from graphlib import TopologicalSorter


class Order(Enum):
    LESS = -1
    MORE = 1
    SAME = 0
    NONE = None

    def opposite(self):
        if self is Order.LESS:
            return Order.MORE
        elif self is Order.MORE:
            return Order.LESS
        else:
            return self


@dataclass
class TypeRelationship:
    order: Order
    matches: bool = None


def typeorder(t1, t2):
    """Order relation between two types.

    Returns a member of the Order enum.

    * typeorder(t1, t2) is Order.LESS   if t2 is more general than t1
    * typeorder(t1, t2) is Order.SAME   if t1 is equal to t2
    * typeorder(t1, t2) is Order.MORE   if t1 is more general than t2
    * typeorder(t1, t2) is Order.NONE   if they cannot be compared
    """
    if t1 == t2:
        return Order.SAME

    t1 = getattr(t1, "__proxy_for__", t1)
    t2 = getattr(t2, "__proxy_for__", t2)

    if (
        hasattr(t1, "__typeorder__")
        and (result := t1.__typeorder__(t2)) is not NotImplemented
    ):
        return result.order
    elif (
        hasattr(t2, "__typeorder__")
        and (result := t2.__typeorder__(t1)) is not NotImplemented
    ):
        return result.order.opposite()

    o1 = getattr(t1, "__origin__", None)
    o2 = getattr(t2, "__origin__", None)

    if o2 is typing.Union:
        compare = [
            x for t in t2.__args__ if (x := typeorder(t1, t)) is not Order.NONE
        ]
        if not compare:
            return Order.NONE
        elif any(x is Order.LESS or x is Order.SAME for x in compare):
            return Order.LESS
        else:
            return Order.MORE

    if o1 is typing.Union:
        return typeorder(t2, t1).opposite()

    if o2 and not o1:
        return typeorder(t2, t1).opposite()

    if o1:
        if not o2:  # or getattr(t2, "__args__", None) is None:
            order = typeorder(o1, t2)
            if order is order.SAME:
                order = order.LESS
            return order

        if (order := typeorder(o1, o2)) is not Order.SAME:
            return order

        args1 = getattr(t1, "__args__", ())
        args2 = getattr(t2, "__args__", ())

        if args1 and not args2:
            return Order.LESS
        if args2 and not args1:
            return Order.MORE
        if len(args1) != len(args2):
            return Order.NONE

        ords = [typeorder(a1, a2) for a1, a2 in zip(args1, args2)]
        if Order.MORE in ords and Order.LESS in ords:
            return Order.NONE
        elif Order.NONE in ords:
            return Order.NONE
        elif Order.MORE in ords:
            return Order.MORE
        elif Order.LESS in ords:
            return Order.LESS
        else:  # pragma: no cover
            # Not sure when t1 != t2 and that happens
            return Order.SAME

    sx = issubclass(t1, t2)
    sy = issubclass(t2, t1)
    if sx and sy:  # pragma: no cover
        # Not sure when t1 != t2 and that happens
        return Order.SAME
    elif sx:
        return Order.LESS
    elif sy:
        return Order.MORE
    else:
        return Order.NONE


def subclasscheck(t1, t2):
    """Check whether t1 is a "subclass" of t2."""
    if t1 == t2:
        return True

    t1 = getattr(t1, "__proxy_for__", t1)
    t2 = getattr(t2, "__proxy_for__", t2)

    if (
        hasattr(t2, "__typeorder__")
        and (result := t2.__typeorder__(t1)) is not NotImplemented
    ):
        return result.matches

    o1 = getattr(t1, "__origin__", None)
    o2 = getattr(t2, "__origin__", None)

    if o2 is typing.Union:
        return any(subclasscheck(t1, t) for t in t2.__args__)
    elif o1 is typing.Union:
        return all(subclasscheck(t, t2) for t in t1.__args__)

    if o1 or o2:
        o1 = o1 or t1
        o2 = o2 or t2
        if issubclass(o1, o2):
            if o2 is t2:  # pragma: no cover
                return True
            else:
                args1 = getattr(t1, "__args__", ())
                args2 = getattr(t2, "__args__", ())
                if len(args1) != len(args2):
                    return False
                return all(
                    subclasscheck(a1, a2) for a1, a2 in zip(args1, args2)
                )
        else:
            return False
    else:
        return issubclass(t1, t2)


def sort_types(cls, avail):
    # We filter everything except subclasses and dependent types that *might* cover
    # the object represented by cls.
    avail = [t for t in avail if subclasscheck(cls, t)]
    deps = {t: set() for t in avail}
    for i, t1 in enumerate(avail):
        for t2 in avail[i + 1 :]:
            # NOTE: this is going to scale poorly when there's a hundred Literal in the pool
            order = typeorder(t1, t2)
            if order is Order.LESS:
                deps[t2].add(t1)
            elif order is Order.MORE:
                deps[t1].add(t2)
    sorter = TopologicalSorter(deps)
    sorter.prepare()
    while sorter.is_active():
        nodes = sorter.get_ready()
        yield nodes
        for n in nodes:
            sorter.done(n)
