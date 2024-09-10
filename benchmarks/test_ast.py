import ast
import inspect
import sys
from types import NoneType

import pytest

from .common import (
    fastcore_dispatch,
    multimethod_dispatch,
    multipledispatch_dispatch,
    ovld_dispatch,
    plum_dispatch,
    runtype_dispatch,
    singledispatch_dispatch,
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


def make_test(fn):
    @pytest.mark.benchmark(group="ast")
    def test(benchmark, foobar):
        result = benchmark(fn, foobar[0])
        assert ast.dump(result, indent=2) == ast.dump(
            foobar[1], indent=2
        ).replace("bar", "foo")

    return test


test_ast_ovld = make_test(make_transform(ovld_dispatch))
test_ast_plum = make_test(make_transform(plum_dispatch))
test_ast_multimethod = make_test(make_transform(multimethod_dispatch))
test_ast_multipledispatch = make_test(make_transform(multipledispatch_dispatch))
test_ast_runtype = make_test(make_transform(runtype_dispatch))
test_ast_fastcore = make_test(make_transform(fastcore_dispatch))
if sys.version_info >= (3, 11):
    test_ast_singledispatch = make_test(make_transform(singledispatch_dispatch))
test_ast_custom = make_test(NT().visit)
