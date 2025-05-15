import inspect
import linecache
import re
import textwrap
from ast import _splitlines_no_ff as splitlines
from itertools import count
from types import FunctionType

from .utils import MISSING, NameDatabase, keyword_decorator, sigstring

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
    closure = func.__closure__ if closure is MISSING else closure
    if closure:
        new_fn = FunctionType(
            argdefs=func.__defaults__ if argdefs is MISSING else argdefs,
            closure=func.__closure__ if closure is MISSING else closure,
            code=func.__code__ if code is MISSING else code,
            globals=func.__globals__ if globals is MISSING else globals,
            name=func.__name__ if name is MISSING else name,
        )
    else:
        new_fn = FunctionType(
            argdefs=func.__defaults__ if argdefs is MISSING else argdefs,
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


subr = re.compile(r"\$(|=|:)(|\[[^\[\]]+\])([a-zA-Z0-9_]+)")
symr = re.compile(r"[a-zA-Z0-9_]")


def sub(template, subs):
    idx = next(_current)

    def repl_fn(m):
        prefix, sep, name = m.groups()
        value = subs(name, bool(sep))
        if value is None:
            return m.group()
        if sep:
            value = sep[1:-1].join(value)
        if prefix == "=" and not symr.fullmatch(value):
            return f"{name}__{idx}"
        if prefix == ":" and not symr.fullmatch(value):
            return f"({name}__{idx} := {value})"
        return value

    return subr.sub(string=template, repl=repl_fn)


def format_code(code, indent=0, nl=False):
    if isinstance(code, str):
        return f"{code}\n" if nl and not code.endswith("\n") else code
    elif isinstance(code, (list, tuple)):
        lines = [format_code(line, indent + 4, True) for line in code]
        block = "".join(lines)
        return textwrap.indent(block, " " * indent)
    else:  # pragma: no cover
        raise TypeError(f"Cannot format code from type {type(code)}")


def _gensym():
    return f"__G{next(_current)}"


class Code:
    def __init__(self, template, substitutions={}, **substitutions_kw):
        self.template = template
        self.substitutions = {**substitutions, **substitutions_kw}

    def sub(self, **subs):
        return Code(self.template, self.substitutions, **subs)

    def defaults(self, subs):
        return Code(self.template, subs, **self.substitutions)

    def _mapsub(self, template, code_recurse, getsub):
        if isinstance(template, (list, tuple)):
            return [self._mapsub(t, code_recurse, getsub) for t in template]

        if isinstance(template, Code):
            return code_recurse(template)

        return sub(template, getsub)

    def rename(self, subs):
        def getsub(name, sep=False):
            return f"${renaming[name]}" if name in renaming else None

        subs = {k: v for k, v in subs.items() if k not in self.substitutions}

        renaming = {k: _gensym() for k in subs}
        new_subs = {renaming[k]: v for k, v in subs.items()}

        def _rename_step(v):
            if isinstance(v, Code):
                return v.rename(subs)
            elif isinstance(v, (list, tuple)):
                if any(isinstance(x, Code) for x in v):
                    return [_rename_step(x) for x in v]
                else:
                    return v
            else:
                return v

        new_subs.update({k: _rename_step(v) for k, v in self.substitutions.items()})
        new_template = self._mapsub(self.template, lambda c: c.rename(subs), getsub)
        return Code(new_template, new_subs)

    def fill(self, ndb=None):
        if ndb is None:
            ndb = NameDatabase()

        def make(name, v, sep):
            if isinstance(v, Code):
                return v.defaults(self.substitutions).fill(ndb)
            elif sep:
                return [make(name, x, sep) for x in v]
            else:
                return ndb.get(v, suggested_name=name)

        def getsub(name, sep=False):
            if name in self.substitutions:
                return make(name, self.substitutions[name], sep)
            else:  # pragma: no cover
                return None

        result = self._mapsub(
            self.template, lambda c: c.defaults(self.substitutions).fill(ndb), getsub
        )
        return format_code(result)


class Function:
    def __init__(self, args, code=None, **subs):
        if code is None:
            code = args
            args = ...
        self.args = args
        if subs:
            self.code = code.sub(**subs) if isinstance(code, Code) else Code(code, subs)
        else:
            self.code = code if isinstance(code, Code) else Code(code)

    def rename(self, *args):
        return self.code.rename(dict(zip(self.args, args)))

    def __call__(self, *args):
        self.args = args if self.args is ... else self.args
        args = [Code(name) if isinstance(name, str) else name for name in args]
        return self.rename(*args)


class Def(Function):
    def create_body(self, argnames):
        return self(*argnames)

    def create_expression(self, argnames):
        raise ValueError("Cannot convert Def to expression")


class Lambda(Function):
    def create_body(self, argnames):
        return Code("return $body", body=self(*argnames))

    def create_expression(self, argnames):
        return self(*argnames)


def regen_signature(fn, ndb):  # pragma: no cover
    sig = inspect.signature(fn)
    args = []
    ko_flag = False
    po_flag = False
    for argname, arg in sig.parameters.items():
        if argname == "cls":
            argname = "self"
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
    body = fn(typemap.ovld.specialization_self, *tup) if is_method else fn(*tup)
    cg = None
    if isinstance(body, Function):
        cg = body
        argnames = [
            "self" if arg == "cls" else arg for arg in inspect.signature(fn).parameters
        ]
        body = body.create_body(argnames)
    if isinstance(body, Code):
        body = body.fill(ndb)
    elif isinstance(body, str):
        pass
    elif isinstance(body, FunctionType):
        return body
    elif body is None:
        return None
    body = textwrap.indent(body, "    ")
    code = fgen_template.format(fn="__GENERATED__", args=args, body=body)
    func = instantiate_code("__GENERATED__", code, inject=ndb.variables)
    adjusted_name = f"{fn.__name__.split('[')[0]}[{sigstring(tup)}]"
    func = rename_function(func, adjusted_name)
    func.__codegen__ = cg
    func.__orig_name__ = fn.__name__
    return func


@keyword_decorator
def code_generator(fn, priority=0):
    fn.specializer = codegen_specializer
    if priority:
        fn.priority = priority
    return fn
