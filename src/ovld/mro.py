from dataclasses import dataclass
from enum import Enum
from graphlib import TopologicalSorter
from typing import Annotated, Any, get_args, get_origin

from .utils import UnionTypes, is_dependent


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

    @staticmethod
    def merge(orders):
        orders = set(orders)
        if orders == {Order.SAME}:
            return Order.SAME
        elif not (orders - {Order.LESS, Order.SAME}):
            return Order.LESS
        elif not (orders - {Order.MORE, Order.SAME}):
            return Order.MORE
        else:
            return Order.NONE


@dataclass
class TypeRelationship:
    order: Order
    supertype: bool = NotImplemented
    subtype: bool = NotImplemented


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
    if t1 is Any:
        return Order.MORE
    if t2 is Any:
        return Order.LESS

    if (
        hasattr(t1, "__type_order__")
        and (result := t1.__type_order__(t2)) is not NotImplemented
    ):
        return result
    elif (
        hasattr(t2, "__type_order__")
        and (result := t2.__type_order__(t1)) is not NotImplemented
    ):
        return result.opposite()

    o1 = get_origin(t1)
    o2 = get_origin(t2)

    if o1 is Annotated and o2 is Annotated:
        t1, *a1 = get_args(t1)
        t2, *a2 = get_args(t2)
        p1 = max([getattr(ann, "annotation_priority", 0) for ann in a1], default=0)
        p2 = max([getattr(ann, "annotation_priority", 0) for ann in a2], default=0)
        if p1 < p2:
            return Order.MORE
        elif p2 < p1:
            return Order.LESS
        else:
            return typeorder(t1, t2)

    if o1 is Annotated:
        if t2 is Annotated:
            return Order.LESS
        return typeorder(get_args(t1)[0], t2)
    if o2 is Annotated:
        if t1 is Annotated:
            return Order.MORE
        return typeorder(t1, get_args(t2)[0])

    if o2 and not o1:
        return typeorder(t2, t1).opposite()

    if o1:
        if not o2:
            order = typeorder(o1, t2)
            if order is Order.SAME:
                order = Order.LESS
            return order

        if (order := typeorder(o1, o2)) is not Order.SAME:
            return order

        args1 = get_args(t1)
        args2 = get_args(t2)

        if args1 and not args2:
            return Order.LESS
        if args2 and not args1:
            return Order.MORE
        if len(args1) != len(args2):
            return Order.NONE

        ords = [typeorder(a1, a2) for a1, a2 in zip(args1, args2)]
        return Order.merge(ords)

    if not isinstance(t1, type) or not isinstance(t2, type):
        return Order.NONE

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


def _find_ann(main, others):
    if main in others:
        return True
    elif isinstance(main, type):
        return any(isinstance(x, main) for x in others)
    else:
        return False


def subclasscheck(t1, t2):
    """Check whether t1 is a "subclass" of t2."""
    if t1 == t2 or t2 is Any:
        return True

    if (
        hasattr(t2, "__is_supertype__")
        and (result := t2.__is_supertype__(t1)) is not NotImplemented
    ):
        return result

    if (
        hasattr(t1, "__is_subtype__")
        and (result := t1.__is_subtype__(t2)) is not NotImplemented
    ):
        return result

    if is_dependent(t2):
        # t2's instancecheck could return anything, and unless it defines
        # __is_supertype__ or __is_subtype__ the bound devolves to object
        return True

    if t2 in UnionTypes:
        return isinstance(t1, t2)

    o1 = get_origin(t1)
    o2 = get_origin(t2)

    if o1 is Annotated and o2 is Annotated:
        t1, *a1 = get_args(t1)
        t2, *a2 = get_args(t2)
        return subclasscheck(t1, t2) and any(_find_ann(main, a1) for main in a2)

    if o1 is Annotated:
        return t2 is Annotated

    if not isinstance(o1, type):
        o1 = None
    if not isinstance(o2, type):
        o2 = None

    if (o1 or o2) and o2 not in UnionTypes:
        o1 = o1 or t1
        o2 = o2 or t2
        if isinstance(o1, type) and isinstance(o2, type) and issubclass(o1, o2):
            if o2 is t2:  # pragma: no cover
                return True
            else:
                args1 = get_args(t1)
                args2 = get_args(t2)
                if len(args1) != len(args2):
                    return False
                return all(subclasscheck(a1, a2) for a1, a2 in zip(args1, args2))
        else:
            return False
    else:
        try:
            return issubclass(t1, t2)
        except TypeError:
            return False


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
