import ast
import inspect
import runpy
import tempfile
import textwrap
from collections import defaultdict
from itertools import count, takewhile
from types import CodeType, FunctionType, GenericAlias

from .utils import Unusable, UsageError

recurse = Unusable(
    "recurse() can only be used from inside an @ovld-registered function."
)
call_next = Unusable(
    "call_next() can only be used from inside an @ovld-registered function."
)


_tempfiles = []


dispatch_template = """
class MISSING:
    pass

def __DISPATCH__(self, {args}):
    {inits}
    {body}

    method = self.map[({lookup})]
    return method({slf}{posargs})
"""


class ArgumentAnalyzer:
    def __init__(self):
        self.name_to_positions = defaultdict(set)
        self.position_to_names = defaultdict(set)
        self.counts = defaultdict(lambda: [0, 0])
        self.complex_transforms = set()
        self.total = 0
        self.is_method = None

    def add(self, fn):
        sig = inspect.signature(fn)
        is_method = False
        for i, (name, param) in enumerate(sig.parameters.items()):
            if name == "self":
                assert i == 0
                is_method = True
                continue
            ann = param.annotation
            if isinstance(ann, str):
                ann = eval(ann, getattr(fn, "__globals__", {}))
            is_complex = isinstance(ann, GenericAlias)
            if param.kind is inspect._POSITIONAL_ONLY:
                cnt = self.counts[i]
                self.position_to_names[i].add(None)
                key = i
            elif param.kind is inspect._POSITIONAL_OR_KEYWORD:
                cnt = self.counts[i]
                self.position_to_names[i].add(param.name)
                self.name_to_positions[param.name].add(i)
                key = i
            elif param.kind is inspect._KEYWORD_ONLY:
                cnt = self.counts[param.name]
                self.name_to_positions[param.name].add(param.name)
                key = param.name
            elif param.kind is inspect._VAR_POSITIONAL:
                raise TypeError("ovld does not support *args")
            elif param.kind is inspect._VAR_KEYWORD:
                raise TypeError("ovld does not support **kwargs")

            if is_complex:
                self.complex_transforms.add(key)

            cnt[0] += 1 if param.default is inspect._empty else 0
            cnt[1] += 1

        self.total += 1

        if self.is_method is None:
            self.is_method = is_method
        elif self.is_method != is_method:
            raise TypeError(
                "Some, but not all registered methods define `self`. It should be all or none."
            )

    def compile(self):
        if any(
            len(pos) != 1
            for _name, pos in self.name_to_positions.items()
            if (name := _name) is not None
        ):
            raise TypeError(
                f"Argument {name} is found both in a positional and keyword setting."
            )

        p_to_n = [
            list(names) for _, names in sorted(self.position_to_names.items())
        ]

        positional = list(
            takewhile(
                lambda names: len(names) == 1 and isinstance(names[0], str),
                reversed(p_to_n),
            )
        )
        positional.reverse()
        strict_positional = p_to_n[: len(p_to_n) - len(positional)]

        assert strict_positional + positional == p_to_n

        strict_positional_required = [
            f"_ovld_arg{pos}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] == self.total
        ]
        strict_positional_optional = [
            f"_ovld_arg{pos}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] != self.total
        ]

        positional_required = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos][0] == self.total
        ]
        positional_optional = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos][0] != self.total
        ]

        keywords = [
            name
            for _, (name,) in self.name_to_positions.items()
            if not isinstance(name, int)
        ]
        keyword_required = [
            name for name in keywords if self.counts[name][0] == self.total
        ]
        keyword_optional = [
            name for name in keywords if self.counts[name][0] != self.total
        ]

        return (
            strict_positional_required,
            strict_positional_optional,
            positional_required,
            positional_optional,
            keyword_required,
            keyword_optional,
        )

    def generate_dispatch(self):
        spr, spo, pr, po, kr, ko = self.compile()

        lookup_fn = "self.map.transform"

        inits = set()

        argsstar = ""
        kwargsstar = ""
        targsstar = ""

        args = []
        body = [""]
        posargs = []
        lookup = []

        i = 0

        for name in spr:
            lookup_fn = (
                "self.map.transform" if i in self.complex_transforms else "type"
            )
            args.append(name)
            posargs.append(name)
            lookup.append(f"{lookup_fn}({name})")
            i += 1

        for name in spo:
            lookup_fn = (
                "self.map.transform" if i in self.complex_transforms else "type"
            )
            args.append(f"{name}=MISSING")
            argsstar = "*ARGS"
            targsstar = "*TARGS"
            inits.add("ARGS = []")
            inits.add("TARGS = []")
            body.append(f"if {name} is not MISSING:")
            body.append(f"    ARGS.append({name})")
            body.append(f"    TARGS.append({lookup_fn}({name}))")
            i += 1

        args.append("/")

        for name in pr:
            lookup_fn = (
                "self.map.transform" if i in self.complex_transforms else "type"
            )
            args.append(name)
            posargs.append(name)
            lookup.append(f"{lookup_fn}({name})")
            i += 1

        for name in po:
            lookup_fn = (
                "self.map.transform" if i in self.complex_transforms else "type"
            )
            args.append(f"{name}=MISSING")
            argsstar = "*ARGS"
            targsstar = "*TARGS"
            inits.add("ARGS = []")
            inits.add("TARGS = []")
            body.append(f"if {name} is not MISSING:")
            body.append(f"    ARGS.append({name})")
            body.append(f"    TARGS.append({lookup_fn}({name}))")
            i += 1

        if kr or ko:
            args.append("*")

        for name in kr:
            lookup_fn = (
                "self.map.transform"
                if name in self.complex_transforms
                else "type"
            )
            args.append(f"{name}")
            posargs.append(f"{name}={name}")
            lookup.append(f"({name!r}, {lookup_fn}({name}))")

        for name in ko:
            lookup_fn = (
                "self.map.transform"
                if name in self.complex_transforms
                else "type"
            )
            args.append(f"{name}=MISSING")
            kwargsstar = "**KWARGS"
            targsstar = "*TARGS"
            inits.add("KWARGS = {}")
            inits.add("TARGS = []")
            body.append(f"if {name} is not MISSING:")
            body.append(f"    KWARGS[{name!r}] = {name}")
            body.append(f"    TARGS.append(({name!r}, {lookup_fn}({name})))")

        posargs.append(argsstar)
        posargs.append(kwargsstar)
        lookup.append(targsstar)

        code = dispatch_template.format(
            inits="\n    ".join(inits),
            args=", ".join(x for x in args if x),
            posargs=", ".join(x for x in posargs if x),
            body="\n    ".join(x for x in body if x),
            lookup=", ".join(x for x in lookup if x) + ",",
            slf="self.obj, " if self.is_method else "",
        )
        return self.instantiate_code("__DISPATCH__", code)

    def instantiate_code(self, symbol, code):
        tf = tempfile.NamedTemporaryFile("w")
        _tempfiles.append(tf)
        tf.write(code)
        tf.flush()
        glb = runpy.run_path(tf.name)
        return glb[symbol]


_current = count()


class Conformer:
    __slots__ = ("code", "orig_fn", "renamed_fn", "ovld")

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

        self.ovld.unregister(self.orig_fn)

        if new_fn is None:  # pragma: no cover
            if new_code is None:
                return
            ofn = self.orig_fn
            new_fn = FunctionType(
                new_code,
                ofn.__globals__,
                ofn.__name__,
                ofn.__defaults__,
                ofn.__closure__,
            )
            new_fn.__annotations__ = ofn.__annotations__

        self.ovld.register(new_fn)

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
    new_fn.__kwdefaults__ = fn.__kwdefaults__
    new_fn.__annotations__ = fn.__annotations__
    return new_fn


class NameConverter(ast.NodeTransformer):
    def __init__(
        self, has_self, recurse_sym, call_next_sym, ovld_mangled, code_mangled
    ):
        self.has_self = has_self
        self.recurse_sym = recurse_sym
        self.call_next_sym = call_next_sym
        self.ovld_mangled = ovld_mangled
        self.code_mangled = code_mangled

    def visit_Name(self, node):
        if node.id == self.recurse_sym:
            return ast.copy_location(
                old_node=node,
                new_node=ast.Name(self.ovld_mangled, ctx=node.ctx),
            )
        elif node.id == self.call_next_sym:
            raise UsageError("call_next should be called right away")
        else:
            return node

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in (
            self.recurse_sym,
            self.call_next_sym,
        ):
            return self.generic_visit(node)

        cn = node.func.id == self.call_next_sym

        new_args = [
            ast.NamedExpr(
                target=ast.Name(id=f"__TMP{i}", ctx=ast.Store()),
                value=self.visit(arg),
            )
            for i, arg in enumerate(node.args)
        ]
        type_parts = [
            ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="__TMPM", ctx=ast.Load()),
                    attr="transform",
                    ctx=ast.Load(),
                ),
                args=[self.visit(arg)],
                keywords=[],
            )
            for arg in new_args
        ]
        if cn:
            type_parts.insert(0, ast.Name(id=self.code_mangled, ctx=ast.Load()))
        method = ast.Subscript(
            value=ast.NamedExpr(
                target=ast.Name(id="__TMPM", ctx=ast.Store()),
                value=ast.Attribute(
                    # value=self.visit(node.func),
                    value=ast.Name(id=self.ovld_mangled, ctx=ast.Load()),
                    attr="map",
                    ctx=ast.Load(),
                ),
            ),
            slice=ast.Tuple(
                elts=type_parts,
                ctx=ast.Load(),
            ),
            ctx=ast.Load(),
        )
        if self.has_self:
            method = ast.Call(
                func=ast.Attribute(
                    value=method,
                    attr="__get__",
                    ctx=ast.Load(),
                ),
                args=[ast.Name(id="self", ctx=ast.Load())],
                keywords=[],
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
    rec_sym = _search_name(fn.__code__, recurse, fn.__globals__)
    cn_sym = _search_name(fn.__code__, call_next, fn.__globals__)
    if rec_sym or cn_sym:
        return recode(fn, ovld, rec_sym, cn_sym, newname)
    else:
        return rename_function(fn, newname)


def recode(fn, ovld, recurse_sym, call_next_sym, newname):
    ovld_mangled = f"___OVLD{ovld.id}"
    code_mangled = f"___CODE{next(_current)}"
    try:
        src = inspect.getsource(fn)
    except OSError:
        raise OSError(
            f"ovld is unable to rewrite {fn} because it cannot read its source code."
            " It may be an issue with __pycache__, so try to either change the source"
            " to force a refresh, or remove __pycache__ altogether. If that does not work,"
            " avoid calling recurse()/call_next()"
        )
    tree = ast.parse(textwrap.dedent(src))
    argspec = inspect.getfullargspec(fn).args
    new = NameConverter(
        has_self=argspec and argspec[0] == "self",
        recurse_sym=recurse_sym,
        call_next_sym=call_next_sym,
        ovld_mangled=ovld_mangled,
        code_mangled=code_mangled,
    ).visit(tree)
    new.body[0].decorator_list = []
    ast.fix_missing_locations(new)
    ast.increment_lineno(new, fn.__code__.co_firstlineno - 1)
    res = compile(new, mode="exec", filename=fn.__code__.co_filename)
    (*_, new_code) = [
        ct for ct in res.co_consts if isinstance(ct, type(fn.__code__))
    ]
    new_fn = FunctionType(
        new_code, fn.__globals__, newname, fn.__defaults__, fn.__closure__
    )
    new_fn.__kwdefaults__ = fn.__kwdefaults__
    new_fn.__annotations__ = fn.__annotations__
    new_fn = rename_function(new_fn, newname)
    new_fn.__globals__[ovld_mangled] = ovld
    new_fn.__globals__[code_mangled] = new_fn.__code__
    return new_fn
