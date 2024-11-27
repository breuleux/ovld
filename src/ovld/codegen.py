import inspect
import linecache
import re
from ast import _splitlines_no_ff as splitlines
from itertools import count
from textwrap import indent

from .utils import MISSING, NameDatabase

_current = count()


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


class CodeGen:
    def __init__(self, template, substitutions={}, **substitutions_kw):
        self.template = template
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


def regen_signature(fn, ndb):
    sig = inspect.signature(fn)
    args = []
    ko_flag = False
    po_flag = False
    for argname, arg in sig.parameters.items():
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
        ndb.register(argname)

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
    body = indent(body, "    ")
    code = fgen_template.format(fn="__GENERATED__", args=args, body=body)
    return instantiate_code("__GENERATED__", code, inject=ndb.variables)


def code_generator(fn):
    fn.specializer = codegen_specializer
    return fn
