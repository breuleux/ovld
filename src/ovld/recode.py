import ast
import inspect
import textwrap
from itertools import count
from types import CodeType, FunctionType

from .utils import Unusable

recurse = Unusable(
    "recurse() can only be used from inside an @ovld-registered function."
)
call_next = Unusable(
    "call_next() can only be used from inside an @ovld-registered function."
)


_current = count()


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


class NameConverter(ast.NodeTransformer):
    def __init__(self, recurse_sym, mangled):
        self.recurse_sym = recurse_sym
        self.mangled = mangled

    def visit_Name(self, node):
        if node.id == self.recurse_sym:
            return ast.copy_location(
                old_node=node, new_node=ast.Name(self.mangled, ctx=node.ctx)
            )
        else:
            return node

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == self.recurse_sym:
            new_args = [
                ast.NamedExpr(
                    target=ast.Name(id=f"__TMP{i}", ctx=ast.Store()),
                    value=self.visit(arg),
                )
                for i, arg in enumerate(node.args)
            ]
            method = ast.Subscript(
                value=ast.NamedExpr(
                    target=ast.Name(id="__TMPM", ctx=ast.Store()),
                    value=ast.Attribute(
                        value=self.visit(node.func),
                        attr="map",
                        ctx=ast.Load(),
                    ),
                ),
                slice=ast.Tuple(
                    elts=[
                        ast.Call(
                            # func=ast.Name(id="type", ctx=ast.Load()), args=[arg]
                            func=ast.Attribute(
                                value=ast.Name(id="__TMPM", ctx=ast.Load()),
                                attr="transform",
                                ctx=ast.Load(),
                            ),
                            args=[self.visit(arg)],
                        )
                        for arg in new_args
                    ],
                    ctx=ast.Load(),
                ),
                ctx=ast.Load(),
            )

            new_node = ast.Call(
                func=method,
                args=[
                    ast.Name(id=f"__TMP{i}", ctx=ast.Load())
                    for i, arg in enumerate(node.args)
                ],
                keywords=[self.visit(k) for k in node.keywords],
            )
            return ast.copy_location(old_node=node, new_node=new_node)

        else:
            return self.generic_visit(node)


def _search_name(co, value, glb):
    if isinstance(co, CodeType):
        for name in co.co_names:
            if glb.get(name, None) is value:
                return name
        else:
            for ct in co.co_consts:
                if (result := _search_name(ct, value, glb)) is not None:
                    return result
    return None


def adapt_function(fn, ovld, newname):
    """Create a copy of the function with a different name."""
    if sym := _search_name(fn.__code__, recurse, fn.__globals__):
        return recode(fn, ovld, sym, newname)
    else:
        return rename_function(fn, newname)


def recode(fn, ovld, recurse_sym, newname):
    mangled = f"___OVLD{next(_current)}"
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    new = NameConverter(recurse_sym, mangled).visit(tree)
    new.body[0].decorator_list = []
    ast.fix_missing_locations(new)
    ast.increment_lineno(new, fn.__code__.co_firstlineno - 1)
    res = compile(new, mode="exec", filename=fn.__code__.co_filename)
    (new_code,) = [
        ct for ct in res.co_consts if isinstance(ct, type(fn.__code__))
    ]
    fn.__code__ = new_code
    fn.__globals__[mangled] = ovld
    return rename_function(fn, newname)
