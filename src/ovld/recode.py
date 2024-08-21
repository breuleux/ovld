import inspect
from types import FunctionType

recurse = object()


class Conformer:
    __slots__ = ("code", "orig_fn", "renamed_fn", "ovld", "code2")

    def __init__(self, ovld, orig_fn, renamed_fn):
        self.ovld = ovld
        self.orig_fn = orig_fn
        self.renamed_fn = renamed_fn
        self.code = orig_fn.__code__

    def __conform__(self, new):
        if isinstance(new, FunctionType):
            new_fn = new
            new_code = new.__code__
        else:
            new_fn = None
            new_code = new

        if new_code is None:
            self.ovld.unregister(self.orig_fn)

        elif new_fn is None:  # pragma: no cover
            # Not entirely sure if this ever happens
            self.renamed_fn.__code__ = new_code

        elif inspect.signature(self.orig_fn) != inspect.signature(new_fn):
            self.ovld.unregister(self.orig_fn)
            self.ovld.register(new_fn)

        else:
            self.renamed_fn.__code__ = rename_code(
                new_code, self.renamed_fn.__code__.co_name
            )

        from codefind import code_registry

        code_registry.update_cache_entry(self, self.code, new_code)

        self.code = new_code


def rename_code(co, newname):  # pragma: no cover
    if hasattr(co, "replace"):
        if hasattr(co, "co_qualname"):
            return co.replace(co_name=newname, co_qualname=newname)
        else:
            return co.replace(co_name=newname)
    else:
        return type(co)(
            co.co_argcount,
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


def rename_function(fn, newname):
    """Create a copy of the function with a different name."""
    newcode = rename_code(fn.__code__, newname)
    new_fn = FunctionType(
        newcode, fn.__globals__, newname, fn.__defaults__, fn.__closure__
    )
    new_fn.__annotations__ = fn.__annotations__
    return new_fn
