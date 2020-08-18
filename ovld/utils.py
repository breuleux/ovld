"""Miscellaneous utilities."""

import functools


class Named:
    """A named object.

    This class can be used to construct objects with a name that will be used
    for the string representation.

    """

    def __init__(self, name):
        """Construct a named object.

        Arguments:
            name: The name of this object.

        """
        self.name = name

    def __repr__(self):
        """Return the object's name."""
        return self.name


BOOTSTRAP = Named("BOOTSTRAP")
MISSING = Named("MISSING")


def keyword_decorator(deco):
    """Wrap a decorator to optionally takes keyword arguments."""

    @functools.wraps(deco)
    def new_deco(fn=None, **kwargs):
        if fn is None:

            @functools.wraps(deco)
            def newer_deco(fn):
                return deco(fn, **kwargs)

            return newer_deco
        else:
            return deco(fn, **kwargs)

    return new_deco


__all__ = [
    "BOOTSTRAP",
    "MISSING",
    "Named",
    "keyword_decorator",
]


# # Copied from Python 3.8's functools.singledispatch implementation

# def _c3_merge(sequences):
#     """Merges MROs in *sequences* to a single MRO using the C3 algorithm.

#     Adapted from http://www.python.org/download/releases/2.3/mro/.

#     """
#     result = []
#     while True:
#         sequences = [s for s in sequences if s]   # purge empty sequences
#         if not sequences:
#             return result
#         for s1 in sequences:   # find merge candidates among seq heads
#             candidate = s1[0]
#             for s2 in sequences:
#                 if candidate in s2[1:]:
#                     candidate = None
#                     break      # reject the current head, it appears later
#             else:
#                 break
#         if candidate is None:
#             raise RuntimeError("Inconsistent hierarchy")
#         result.append(candidate)
#         # remove the chosen candidate
#         for seq in sequences:
#             if seq[0] == candidate:
#                 del seq[0]

# def _c3_mro(cls, abcs=None):
#     """Computes the method resolution order using extended C3 linearization.

#     If no *abcs* are given, the algorithm works exactly like the built-in C3
#     linearization used for method resolution.

#     If given, *abcs* is a list of abstract base classes that should be inserted
#     into the resulting MRO. Unrelated ABCs are ignored and don't end up in the
#     result. The algorithm inserts ABCs where their functionality is introduced,
#     i.e. issubclass(cls, abc) returns True for the class itself but returns
#     False for all its direct base classes. Implicit ABCs for a given class
#     (either registered or inferred from the presence of a special method like
#     __len__) are inserted directly after the last ABC explicitly listed in the
#     MRO of said class. If two implicit ABCs end up next to each other in the
#     resulting MRO, their ordering depends on the order of types in *abcs*.

#     """
#     for i, base in enumerate(reversed(cls.__bases__)):
#         if hasattr(base, '__abstractmethods__'):
#             boundary = len(cls.__bases__) - i
#             break   # Bases up to the last explicit ABC are considered first.
#     else:
#         boundary = 0
#     abcs = list(abcs) if abcs else []
#     explicit_bases = list(cls.__bases__[:boundary])
#     abstract_bases = []
#     other_bases = list(cls.__bases__[boundary:])
#     for base in abcs:
#         if issubclass(cls, base) and not any(
#                 issubclass(b, base) for b in cls.__bases__
#             ):
#             # If *cls* is the class that introduces behaviour described by
#             # an ABC *base*, insert said ABC to its MRO.
#             abstract_bases.append(base)
#     for base in abstract_bases:
#         abcs.remove(base)
#     explicit_c3_mros = [_c3_mro(base, abcs=abcs) for base in explicit_bases]
#     abstract_c3_mros = [_c3_mro(base, abcs=abcs) for base in abstract_bases]
#     other_c3_mros = [_c3_mro(base, abcs=abcs) for base in other_bases]
#     return _c3_merge(
#         [[cls]] +
#         explicit_c3_mros + abstract_c3_mros + other_c3_mros +
#         [explicit_bases] + [abstract_bases] + [other_bases]
#     )

# def _compose_mro(cls, types):
#     """Calculates the method resolution order for a given class *cls*.

#     Includes relevant abstract base classes (with their respective bases) from
#     the *types* iterable. Uses a modified C3 linearization algorithm.

#     """
#     bases = set(cls.__mro__)
#     # Remove entries which are already present in the __mro__ or unrelated.
#     def is_related(typ):
#         return (typ not in bases and hasattr(typ, '__mro__')
#                                  and issubclass(cls, typ))
#     types = [n for n in types if is_related(n)]
#     # Remove entries which are strict bases of other entries (they will end up
#     # in the MRO anyway.
#     def is_strict_base(typ):
#         for other in types:
#             if typ != other and typ in other.__mro__:
#                 return True
#         return False
#     types = [n for n in types if not is_strict_base(n)]
#     # Subclasses of the ABCs in *types* which are also implemented by
#     # *cls* can be used to stabilize ABC ordering.
#     type_set = set(types)
#     mro = []
#     for typ in types:
#         found = []
#         for sub in typ.__subclasses__():
#             if sub not in bases and issubclass(cls, sub):
#                 found.append([s for s in sub.__mro__ if s in type_set])
#         if not found:
#             mro.append(typ)
#             continue
#         # Favor subclasses with the biggest number of useful bases
#         found.sort(key=len, reverse=True)
#         for sub in found:
#             for subcls in sub:
#                 if subcls not in mro:
#                     mro.append(subcls)
#     return _c3_mro(cls, abcs=mro)
