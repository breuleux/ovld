import inspect
import linecache
import re
import textwrap
from ast import _splitlines_no_ff as splitlines
from itertools import count
from types import FunctionType

from .utils import MISSING, NameDatabase, sigstring

_current = count()


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


def transfer_function(
    func,
    argdefs=MISSING,
    closure=MISSING,
    code=MISSING,
    globals=MISSING,
    name=MISSING,
):
    new_fn = FunctionType(
        argdefs=func.__defaults__ if argdefs is MISSING else argdefs,
        closure=func.__closure__ if closure is MISSING else closure,
        code=func.__code__ if code is MISSING else code,
        globals=func.__globals__ if globals is MISSING else globals,
        name=func.__name__ if name is MISSING else name,
    )
    new_fn.__kwdefaults__ = func.__kwdefaults__
    new_fn.__annotations__ = func.__annotations__
    new_fn.__dict__.update(func.__dict__)
    return new_fn


def rename_function(fn, newname):
    """Create a copy of the function with a different name."""
    return transfer_function(
        func=fn,
        code=rename_code(fn.__code__, newname),
        name=newname,
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


def generate_checking_code(typ):
    if hasattr(typ, "codegen"):
        return typ.codegen()
    else:
        return CodeGen("isinstance($arg, $this)", this=typ)


subr = re.compile(r"\$([a-zA-Z0-9_]+)")


def sub(template, subs):
    def repl_fn(m):
        return subs[m.groups()[0]]

    return subr.sub(string=template, repl=repl_fn)


def combine(master_template, args):
    fmts = []
    subs = {}
    for cg in args:
        mangled = cg.mangle()
        fmts.append(mangled.template)
        subs.update(mangled.substitutions)
    return CodeGen(master_template.format(*fmts), subs)


def format_code(code, indent=0, nl=False):
    if isinstance(code, str):
        return f"{code}\n" if nl and not code.endswith("\n") else code
    elif isinstance(code, (list, tuple)):
        lines = [format_code(line, indent + 4, True) for line in code]
        block = "".join(lines)
        return textwrap.indent(block, " " * indent)
    else:  # pragma: no cover
        raise TypeError(f"Cannot format code from type {type(code)}")


class CodeGen:
    def __init__(self, template, substitutions={}, **substitutions_kw):
        self.template = format_code(template)
        self.substitutions = {**substitutions, **substitutions_kw}

    def fill(self, ndb, **subs):
        subs = {
            **subs,
            **{
                k: ndb.get(v, suggested_name=k)
                for k, v in self.substitutions.items()
            },
        }
        return sub(self.template, subs)

    def mangle(self):
        renamings = {k: f"${k}__{next(_current)}" for k in self.substitutions}
        renamings["arg"] = "$arg"
        new_subs = {
            newk[1:]: self.substitutions[k]
            for k, newk in renamings.items()
            if k in self.substitutions
        }
        return CodeGen(sub(self.template, renamings), new_subs)


def regen_signature(fn, ndb):  # pragma: no cover
    sig = inspect.signature(fn)
    args = []
    ko_flag = False
    po_flag = False
    for argname, arg in sig.parameters.items():
        ndb.register(argname)
        argstring = argname
        if arg.default is not inspect._empty:
            argstring += f" = {ndb[arg.default]}"

        if arg.kind is inspect._KEYWORD_ONLY:
            if not ko_flag:
                ko_flag = True
                args.append("*")
        elif arg.kind is inspect._VAR_POSITIONAL:
            ko_flag = True
        elif arg.kind is inspect._VAR_KEYWORD:
            raise TypeError("**kwargs are not accepted")
        elif arg.kind is inspect._POSITIONAL_OR_KEYWORD:
            if po_flag:
                args.append("/")
                po_flag = False
        elif arg.kind is inspect._POSITIONAL_ONLY:
            po_flag = True
        args.append(argstring)

    if po_flag:
        args.append("/")

    return ", ".join(args)


fgen_template = """
def {fn}({args}):
{body}
"""


def codegen_specializer(typemap, fn, tup):
    is_method = typemap.ovld.argument_analysis.is_method
    ndb = NameDatabase(default_name="INJECT")
    args = regen_signature(fn, ndb)
    body = fn(MISSING, *tup) if is_method else fn(*tup)
    if isinstance(body, CodeGen):
        body = body.fill(ndb)
    body = textwrap.indent(body, "    ")
    code = fgen_template.format(fn="__GENERATED__", args=args, body=body)
    func = instantiate_code("__GENERATED__", code, inject=ndb.variables)
    adjusted_name = f"{fn.__name__.split('[')[0]}[{sigstring(tup)}]"
    func = rename_function(func, adjusted_name)
    return func


def code_generator(fn):
    fn.specializer = codegen_specializer
    return fn


__all__ = [
    "CodeGen",
    "code_generator",
]
