import ast
import inspect
import sys
from types import NoneType

import pytest

from .common import (
    function_builder,
    multimethod_dispatch,
    multipledispatch_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
    singledispatch_dispatch,
    with_functions,
)


def foo(xs, ys):
    zs = [x + y for x, y in zip(xs, ys)]
    zs.append("the beginning")
    return zs


def bar(xs, ys):
    zs = [x**y for x, y in zip(xs, ys)]
    zs.append("the end")
    return zs


@pytest.fixture(scope="module")
def foobar():
    return ast.parse(inspect.getsource(foo)), ast.parse(inspect.getsource(bar))


@function_builder
def make_transform(dispatch):
    @dispatch
    def transform(node: list):
        return [transform(x) for x in node]

    @dispatch
    def transform(node: int | str | NoneType):
        return node

    @dispatch
    def transform(node: ast.AST):
        kw = {field: transform(getattr(node, field)) for field in node._fields}
        return type(node)(**kw)

    @dispatch
    def transform(node: ast.BinOp):
        return ast.BinOp(
            op=ast.Pow(),
            left=transform(node.left),
            right=transform(node.right),
        )

    @dispatch
    def transform(node: ast.Constant):
        return ast.Constant(
            value=node.value.replace("beginning", "end")
            if isinstance(node.value, str)
            else node.value,
            kind=node.kind,
        )

    return transform


###################
# NodeTransformer #
###################


class NT(ast.NodeTransformer):
    def visit_BinOp(self, node):
        return ast.BinOp(
            op=ast.Pow(),
            left=self.visit(node.left),
            right=self.visit(node.right),
        )

    def visit_Constant(self, node):
        return ast.Constant(
            value=node.value.replace("beginning", "end")
            if isinstance(node.value, str)
            else node.value,
            kind=node.kind,
        )


####################
# Test definitions #
####################


@pytest.mark.benchmark(group="ast")
@with_functions(
    ovld=make_transform(ovld_dispatch),
    plum=make_transform(plum_dispatch),
    multimethod=make_transform(multimethod_dispatch),
    multipledispatch=make_transform(multipledispatch_dispatch),
    runtype=make_transform(runtype_dispatch),
    singledispatch=make_transform(singledispatch_dispatch),
    custom=NT().visit,
)
def test_ast(fn, foobar, benchmark):
    if (
        sys.version_info < (3, 11)
        and getattr(fn, "_dispatch", None) is singledispatch_dispatch
    ):
        pytest.skip()
    result = benchmark(fn, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace("bar", "foo")
