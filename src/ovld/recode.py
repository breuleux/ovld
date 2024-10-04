import ast
import inspect
import linecache
import textwrap
from ast import _splitlines_no_ff as splitlines
from functools import reduce
from itertools import count
from types import CodeType, FunctionType

from .utils import MISSING, NameDatabase, Unusable, UsageError, subtler_type

recurse = Unusable(
    "recurse() can only be used from inside an @ovld-registered function."
)
call_next = Unusable(
    "call_next() can only be used from inside an @ovld-registered function."
)


def instantiate_code(symbol, code, inject={}):
    virtual_file = f"<ovld:{abs(hash(code)):x}>"
    linecache.cache[virtual_file] = (None, None, splitlines(code), virtual_file)
    code = compile(source=code, filename=virtual_file, mode="exec")
    glb = {**inject}
    exec(code, glb, glb)
    return glb[symbol]


# # Previous version: generate a temporary file
# def instantiate_code(symbol, code, inject={}):
#     tf = tempfile.NamedTemporaryFile("w")
#     _tempfiles.append(tf)
#     tf.write(code)
#     tf.flush()
#     glb = runpy.run_path(tf.name)
#     rval = glb[symbol]
#     rval.__globals__.update(inject)
#     return rval


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
    from .dependent import generate_checking_code, is_dependent

    def to_dict(tup):
        return dict(
            entry if isinstance(entry, tuple) else (i, entry)
            for i, entry in enumerate(tup)
        )

    def argname(x):
        return f"ARG{x}" if isinstance(x, int) else x

    def argprovide(x):
        return f"ARG{x}" if isinstance(x, int) else f"{x}={x}"

    def codegen(typ, arg):
        cg = generate_checking_code(typ)
        return cg.template.format(
            arg=arg, **{k: ndb[v] for k, v in cg.substitutions.items()}
        )

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
                        {key: h for key in types[k].get_keys()}
                        for h, types in handlers
                    ]
                    keyed = reduce(lambda a, b: {**a, **b}, all_keys)
                    if (
                        len(keyed) == sum(map(len, all_keys))
                        and len(featured) < 4
                    ):
                        exclusive = True
                        keyexpr = None
                    else:
                        keyexpr = focus.keygen().format(arg=argname(k))

                else:
                    exclusive = getattr(focus, "exclusive_type", False)

    for i, (h, types) in enumerate(handlers):
        relevant = [k for k in tup if is_dependent(types[k])]
        if len(relevant) > 1:
            # The keyexpr method only works if there is only one condition to check.
            keyexpr = keyed = None
        codes = [codegen(types[k], argname(k)) for k in relevant]
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

    fn = instantiate_code(
        symbol="__DEPENDENT_DISPATCH__", code=code, inject=inject
    )
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
        self,
        anal,
        recurse_sym,
        call_next_sym,
        ovld_mangled,
        map_mangled,
        code_mangled,
    ):
        self.analysis = anal
        self.recurse_sym = recurse_sym
        self.call_next_sym = call_next_sym
        self.ovld_mangled = ovld_mangled
        self.map_mangled = map_mangled
        self.code_mangled = code_mangled
        self.count = count()

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

        if any(isinstance(arg, ast.Starred) for arg in node.args):
            return self.generic_visit(node)

        cn = node.func.id == self.call_next_sym
        tmp = f"__TMP{next(self.count)}_"

        def _make_lookup_call(key, arg):
            name = (
                "__SUBTLER_TYPE"
                if self.analysis.lookup_for(key) is subtler_type
                else "type"
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
        type_parts = [
            _make_lookup_call(i, arg) for i, arg in enumerate(node.args)
        ]

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
            + [
                ast.Name(id=f"{tmp}{i}", ctx=ast.Load())
                for i, arg in enumerate(node.args)
            ],
            keywords=[
                ast.keyword(
                    arg=kw.arg,
                    value=ast.Name(id=f"{tmp}{kw.arg}", ctx=ast.Load()),
                )
                for kw in node.keywords
            ],
        )
        return ast.copy_location(old_node=node, new_node=new_node)


def _search_names(co, values, glb, closure=None):
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
                yield from _search_names(ct, values, glb)


def adapt_function(fn, ovld, newname):
    """Create a copy of the function with a different name."""
    rec_syms = list(
        _search_names(
            fn.__code__,
            (recurse, ovld, ovld.dispatch),
            fn.__globals__,
            fn.__closure__,
        )
    )
    cn_syms = list(
        _search_names(fn.__code__, (call_next,), fn.__globals__, fn.__closure__)
    )
    if rec_syms or cn_syms:
        return recode(
            fn, ovld, rec_syms and rec_syms[0], cn_syms and cn_syms[0], newname
        )
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


def recode(fn, ovld, recurse_sym, call_next_sym, newname):
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
    new = NameConverter(
        anal=ovld.argument_analysis,
        recurse_sym=recurse_sym,
        call_next_sym=call_next_sym,
        ovld_mangled=ovld_mangled,
        map_mangled=map_mangled,
        code_mangled=code_mangled,
    ).visit(tree)
    new.body[0].decorator_list = []
    if fn.__closure__:
        new = closure_wrap(new.body[0], "irrelevant", fn.__code__.co_freevars)
    ast.fix_missing_locations(new)
    ast.increment_lineno(new, fn.__code__.co_firstlineno - 1)
    res = compile(new, mode="exec", filename=fn.__code__.co_filename)
    if fn.__closure__:
        res = [x for x in res.co_consts if isinstance(x, CodeType)][0]
    (*_, new_code) = [ct for ct in res.co_consts if isinstance(ct, CodeType)]
    new_closure = tuple(
        [
            fn.__closure__[fn.__code__.co_freevars.index(name)]
            for name in new_code.co_freevars
        ]
    )
    new_fn = FunctionType(
        new_code, fn.__globals__, newname, fn.__defaults__, new_closure
    )
    new_fn.__kwdefaults__ = fn.__kwdefaults__
    new_fn.__annotations__ = fn.__annotations__
    new_fn = rename_function(new_fn, newname)
    new_fn.__globals__["__SUBTLER_TYPE"] = subtler_type
    new_fn.__globals__[ovld_mangled] = ovld.dispatch
    new_fn.__globals__[map_mangled] = ovld.map
    new_fn.__globals__[code_mangled] = new_fn.__code__
    return new_fn
