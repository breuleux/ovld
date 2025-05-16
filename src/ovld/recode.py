import ast
import inspect
import textwrap
from functools import reduce
from itertools import count
from types import CodeType, FunctionType

from .codegen import (
    Code,
    instantiate_code,
    rename_code,
    rename_function,
    transfer_function,
)
from .utils import MISSING, NameDatabase, SpecialForm, UsageError, is_dependent, subtler_type

recurse = SpecialForm("recurse")
call_next = SpecialForm("call_next")
resolve = SpecialForm("resolve")
current_code = SpecialForm("current_code")


dispatch_template = """
def __WRAP_DISPATCH__(OVLD):
    def __DISPATCH__({args}):
        {body}

    return __DISPATCH__
"""


call_template = """
{mvar} = OVLD.map[({lookup})]
return {mvar}({posargs})
"""


def generate_checking_code(typ):
    if hasattr(typ, "codegen"):
        return typ.codegen()
    else:
        return Code("isinstance($arg, $this)", this=typ)


def generate_dispatch(ov, arganal):
    def join(li, sep=", ", trail=False):
        li = [x for x in li if x]
        rval = sep.join(li)
        if len(li) == 1 and trail:
            rval += ","
        return rval

    arganal.compile()

    spr = arganal.strict_positional_required
    spo = arganal.strict_positional_optional
    pr = arganal.positional_required
    po = arganal.positional_optional
    kr = arganal.keyword_required
    ko = arganal.keyword_optional

    inits = set()

    kwargsstar = ""
    targsstar = ""

    args = ["self" if arganal.is_method else ""]
    body = [""]
    posargs = ["self" if arganal.is_method else ""]
    lookup = []

    i = 0
    ndb = NameDatabase(default_name="INJECT")

    def lookup_for(x):
        return ndb[arganal.lookup_for(x)]

    for name in spr + spo + pr + po + kr:
        ndb.register(name)

    mv = ndb.gensym(desired_name="method")

    for name in spr + spo:
        if name in spr:
            args.append(name)
        else:
            args.append(f"{name}=MISSING")
        posargs.append(name)
        lookup.append(f"{lookup_for(i)}({name})")
        i += 1

    if len(po) <= 1 and (spr or spo):
        # If there are more than one non-strictly positional optional arguments,
        # then all positional arguments are strictly positional, because if e.g.
        # x and y are optional we want x==MISSING to imply that y==MISSING, but
        # that only works if y cannot be provided as a keyword argument.
        args.append("/")

    for name in pr + po:
        if name in pr:
            args.append(name)
        else:
            args.append(f"{name}=MISSING")
        posargs.append(name)
        lookup.append(f"{lookup_for(i)}({name})")
        i += 1

    if len(po) > 1:
        args.append("/")

    if kr or ko:
        args.append("*")

    for name in kr:
        args.append(f"{name}")
        posargs.append(f"{name}={name}")
        lookup.append(f"({name!r}, {lookup_for(name)}({name}))")

    for name in ko:
        args.append(f"{name}=MISSING")
        kwargsstar = "**KWARGS"
        targsstar = "*TARGS"
        inits.add("KWARGS = {}")
        inits.add("TARGS = []")
        body.append(f"if {name} is not MISSING:")
        body.append(f"    KWARGS[{name!r}] = {name}")
        body.append(f"    TARGS.append(({name!r}, {lookup_for(name)}({name})))")

    posargs.append(kwargsstar)
    lookup.append(targsstar)

    fullcall = call_template.format(
        lookup=join(lookup, trail=True),
        posargs=join(posargs),
        mvar=mv,
    )

    calls = []
    if spo or po:
        req = len(spr + pr)
        for i, arg in enumerate(spo + po):
            call = call_template.format(
                lookup=join(lookup[: req + i], trail=True),
                posargs=join(posargs[: req + i + 1]),
                mvar=mv,
            )
            call = textwrap.indent(call, "        ")
            calls.append(f"\nif {arg} is MISSING:{call}")
    calls.append(fullcall)

    lines = [*inits, *body, textwrap.indent("".join(calls), "        ")]
    code = dispatch_template.format(
        args=join(args),
        body=join(lines, sep="\n        ").lstrip(),
    )
    wr = instantiate_code(
        "__WRAP_DISPATCH__", code, inject={"MISSING": MISSING, **ndb.variables}
    )
    return wr(ov)


def generate_dependent_dispatch(tup, handlers, next_call, slf, name, err, nerr):
    def to_dict(tup):
        return dict(
            entry if isinstance(entry, tuple) else (i, entry) for i, entry in enumerate(tup)
        )

    def argname(x):
        return f"ARG{x}" if isinstance(x, int) else x

    def argprovide(x):
        return f"ARG{x}" if isinstance(x, int) else f"{x}={x}"

    tup = to_dict(tup)
    handlers = [(h, to_dict(types)) for h, types in handlers]
    ndb = NameDatabase(default_name="INJECT")
    conjs = []

    exclusive = False
    keyexpr = None
    keyed = None
    for k in tup:
        featured = set(types[k] for h, types in handlers)
        if len(featured) == len(handlers):
            possibilities = set(type(t) for t in featured)
            focus = possibilities.pop()
            # Possibilities is now empty if only one type of DependentType

            if not possibilities:
                if getattr(focus, "keyable_type", False):
                    all_keys = [
                        {key: h for key in types[k].get_keys()} for h, types in handlers
                    ]
                    keyed = reduce(lambda a, b: {**a, **b}, all_keys)
                    if len(keyed) == sum(map(len, all_keys)) and len(featured) < 4:
                        exclusive = True
                        keyexpr = None
                    else:
                        keyexpr = focus.keygen().sub(arg=Code(argname(k))).fill(ndb)

                else:
                    exclusive = getattr(focus, "exclusive_type", False)

    for i, (h, types) in enumerate(handlers):
        relevant = [k for k in tup if is_dependent(types[k])]
        if len(relevant) > 1:
            # The keyexpr method only works if there is only one condition to check.
            keyexpr = keyed = None
        codes = [
            generate_checking_code(types[k]).sub(arg=Code(argname(k))).fill(ndb)
            for k in relevant
        ]
        conj = " and ".join(codes)
        if not conj:  # pragma: no cover
            # Not sure if this can happen
            conj = "True"
        conjs.append(conj)

    if len(handlers) == 1:
        exclusive = True

    argspec = ", ".join(argname(x) for x in tup)
    argcall = ", ".join(argprovide(x) for x in tup)

    body = []
    if keyexpr:
        body.append(f"HANDLER = {ndb[keyed]}.get({keyexpr}, FALLTHROUGH)")
        body.append(f"return HANDLER({slf}{argcall})")

    elif exclusive:
        for i, conj in enumerate(conjs):
            body.append(f"if {conj}: return HANDLER{i}({slf}{argcall})")
        body.append(f"return FALLTHROUGH({slf}{argcall})")

    else:
        for i, conj in enumerate(conjs):
            body.append(f"MATCH{i} = {conj}")

        summation = " + ".join(f"MATCH{i}" for i in range(len(handlers)))
        body.append(f"SUMMATION = {summation}")
        body.append("if SUMMATION == 1:")
        for i, (h, types) in enumerate(handlers):
            body.append(f"    if MATCH{i}: return HANDLER{i}({slf}{argcall})")
        body.append("elif SUMMATION == 0:")
        body.append(f"    return FALLTHROUGH({slf}{argcall})")
        body.append("else:")
        body.append(f"    raise {ndb[err]}")

    body_text = textwrap.indent("\n".join(body), "    ")
    code = f"def __DEPENDENT_DISPATCH__({slf}{argspec}):\n{body_text}"

    inject = ndb.variables
    for i, (h, types) in enumerate(handlers):
        inject[f"HANDLER{i}"] = h

    def raise_error(*args, **kwargs):
        raise nerr

    inject["FALLTHROUGH"] = (next_call and next_call[0]) or raise_error

    fn = instantiate_code(symbol="__DEPENDENT_DISPATCH__", code=code, inject=inject)
    return rename_function(fn, name)


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
            new_fn = transfer_function(
                func=ofn,
                code=new_code,
            )

        self.ovld.register(new_fn)

        from codefind import code_registry

        code_registry.update_cache_entry(self, self.code, new_code)

        self.code = new_code


class NameConverter(ast.NodeTransformer):
    def __init__(self, anal, special_syms, mapping):
        self.analysis = anal
        self.syms = special_syms
        self.mapping = mapping
        self.ovld_mangled = mapping[recurse]
        self.map_mangled = mapping[resolve]
        self.code_mangled = mapping[current_code]
        self.count = count()

    def is_special(self, name, *kinds):
        return any(name in self.syms[kind] for kind in kinds)

    def visit_Name(self, node):
        if node.id in self.mapping:
            return ast.copy_location(
                old_node=node,
                new_node=ast.Name(self.mapping[node.id], ctx=node.ctx),
            )
        elif self.is_special(node.id, call_next):
            raise UsageError("call_next should be called right away")
        else:
            return node

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or not self.is_special(
            node.func.id, recurse, call_next
        ):
            return self.generic_visit(node)

        if any(isinstance(arg, ast.Starred) for arg in node.args):
            return self.generic_visit(node)

        cn = self.is_special(node.func.id, call_next)
        tmp = f"__TMP{next(self.count)}_"

        def _make_lookup_call(key, arg):
            name = (
                "__SUBTLER_TYPE" if self.analysis.lookup_for(key) is subtler_type else "type"
            )
            value = ast.NamedExpr(
                target=ast.Name(id=f"{tmp}{key}", ctx=ast.Store()),
                value=self.visit(arg),
            )
            func = ast.Name(id=name, ctx=ast.Load())
            return ast.Call(
                func=func,
                args=[value],
                keywords=[],
            )

        # type index for positional arguments
        type_parts = [_make_lookup_call(i, arg) for i, arg in enumerate(node.args)]

        # type index for keyword arguments
        type_parts += [
            ast.Tuple(
                elts=[
                    ast.Constant(value=kw.arg),
                    _make_lookup_call(kw.arg, kw.value),
                ],
                ctx=ast.Load(),
            )
            for kw in node.keywords
        ]

        if cn:
            type_parts.insert(0, ast.Name(id=self.code_mangled, ctx=ast.Load()))
        method = ast.Subscript(
            value=ast.Name(id=self.map_mangled, ctx=ast.Load()),
            slice=ast.Tuple(
                elts=type_parts,
                ctx=ast.Load(),
            ),
            ctx=ast.Load(),
        )
        if self.analysis.is_method:
            selfarg = [ast.Name(id="self", ctx=ast.Load())]
        else:
            selfarg = []

        new_node = ast.Call(
            func=method,
            args=selfarg
            + [ast.Name(id=f"{tmp}{i}", ctx=ast.Load()) for i, arg in enumerate(node.args)],
            keywords=[
                ast.keyword(
                    arg=kw.arg,
                    value=ast.Name(id=f"{tmp}{kw.arg}", ctx=ast.Load()),
                )
                for kw in node.keywords
            ],
        )
        return ast.copy_location(old_node=node, new_node=new_node)


def _search_names(co, specials, glb, closure=None):
    def _search(co, values, glb, closure=None):
        if isinstance(co, CodeType):
            if closure is not None:
                for varname, cell in zip(co.co_freevars, closure):
                    if any(cell.cell_contents is v for v in values):
                        yield varname
            for name in co.co_names:
                if any(glb.get(name, None) is v for v in values):
                    yield name
            else:
                for ct in co.co_consts:
                    yield from _search(ct, values, glb)

    return {k: list(_search(co, v, glb, closure)) for k, v in specials.items()}


def adapt_function(fn, ovld, newname):
    """Create a copy of the function with a different name."""
    syms = _search_names(
        fn.__code__,
        {
            recurse: (recurse, ovld, ovld.dispatch),
            call_next: (call_next,),
            resolve: (resolve,),
            current_code: (current_code,),
        },
        fn.__globals__,
        fn.__closure__,
    )
    if any(syms.values()):
        return recode(fn, ovld, syms, newname)
    else:
        return rename_function(fn, newname)


def closure_wrap(tree, fname, names):
    wrap = ast.copy_location(
        ast.FunctionDef(
            name="##create_closure",
            args=ast.arguments(
                posonlyargs=[],
                args=[ast.arg(arg=name) for name in names],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            body=[
                tree,
                ast.Return(ast.Name(id=fname, ctx=ast.Load())),
            ],
            decorator_list=[],
            returns=None,
        ),
        tree,
    )
    ast.fix_missing_locations(wrap)
    return ast.Module(body=[wrap], type_ignores=[])


def recode(fn, ovld, syms, newname):
    ovld_mangled = f"___OVLD{ovld.id}"
    map_mangled = f"___MAP{ovld.id}"
    code_mangled = f"___CODE{next(_current)}"
    try:
        src = inspect.getsource(fn)
    except OSError:  # pragma: no cover
        raise OSError(
            f"ovld is unable to rewrite {fn} because it cannot read its source code."
            " It may be an issue with __pycache__, so try to either change the source"
            " to force a refresh, or remove __pycache__ altogether. If that does not work,"
            " avoid calling recurse()/call_next()"
        )
    tree = ast.parse(textwrap.dedent(src))

    mapping = {
        recurse: ovld_mangled,
        resolve: map_mangled,
        current_code: code_mangled,
    }
    for special, symbols in syms.items():
        for sym in symbols:
            if special in mapping:
                mapping[sym] = mapping[special]
    new = NameConverter(
        anal=ovld.argument_analysis,
        special_syms=syms,
        mapping=mapping,
    ).visit(tree)

    new.body[0].decorator_list = []
    if fn.__closure__:
        new = closure_wrap(new.body[0], "irrelevant", fn.__code__.co_freevars)
    ast.fix_missing_locations(new)
    line_delta = fn.__code__.co_firstlineno - 1
    col_delta = len(firstline := src.split("\n", 1)[0]) - len(firstline.lstrip())
    for node in ast.walk(new):
        if hasattr(node, "lineno"):
            node.lineno += line_delta
        if hasattr(node, "end_lineno"):
            node.end_lineno += line_delta
        if hasattr(node, "col_offset"):
            node.col_offset += col_delta
        if hasattr(node, "end_col_offset"):
            node.end_col_offset += col_delta

    res = compile(new, mode="exec", filename=fn.__code__.co_filename)
    if fn.__closure__:
        res = [x for x in res.co_consts if isinstance(x, CodeType)][0]
    (*_, new_code) = [ct for ct in res.co_consts if isinstance(ct, CodeType)]
    new_closure = tuple(
        [fn.__closure__[fn.__code__.co_freevars.index(name)] for name in new_code.co_freevars]
    )
    new_fn = transfer_function(
        func=fn,
        code=rename_code(new_code, newname),
        name=newname,
        closure=new_closure,
    )
    new_fn.__globals__["__SUBTLER_TYPE"] = subtler_type
    new_fn.__globals__[ovld_mangled] = ovld.dispatch
    new_fn.__globals__[map_mangled] = ovld.map
    new_fn.__globals__[code_mangled] = new_fn.__code__
    return new_fn
