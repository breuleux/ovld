import ast
import inspect
from types import NoneType

import pytest
from multimethod import multimethod as multimethod_dispatch
from multipledispatch import dispatch as multipledispatch_dispatch
from plum import dispatch as plum_dispatch
from runtype import multidispatch as runtype_dispatch

from ovld import ovld as ovld_dispatch
from ovld import recurse


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


########
# ovld #
########


@ovld_dispatch
def transform_ovld(node: list):
    return [recurse(x) for x in node]


@ovld_dispatch
def transform_ovld(node: int | str | NoneType):
    return node


@ovld_dispatch
def transform_ovld(node: ast.AST):
    kw = {field: recurse(getattr(node, field)) for field in node._fields}
    return type(node)(**kw)


@ovld_dispatch
def transform_ovld(node: ast.BinOp):
    return ast.BinOp(
        op=ast.Pow(),
        left=recurse(node.left),
        right=recurse(node.right),
    )


@ovld_dispatch
def transform_ovld(node: ast.Constant):
    return ast.Constant(
        value=node.value.replace("beginning", "end")
        if isinstance(node.value, str)
        else node.value,
        kind=node.kind,
    )


@pytest.mark.benchmark(group="ast")
def test_transform_ovld(benchmark, foobar):
    result = benchmark(transform_ovld, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )


########
# plum #
########


@plum_dispatch
def transform_plum(node: list):
    return [transform_plum(x) for x in node]


@plum_dispatch
def transform_plum(node: int | str | NoneType):
    return node


@plum_dispatch
def transform_plum(node: ast.AST):
    kw = {field: transform_plum(getattr(node, field)) for field in node._fields}
    return type(node)(**kw)


@plum_dispatch
def transform_plum(node: ast.BinOp):
    return ast.BinOp(
        op=ast.Pow(),
        left=transform_plum(node.left),
        right=transform_plum(node.right),
    )


@plum_dispatch
def transform_plum(node: ast.Constant):
    return ast.Constant(
        value=node.value.replace("beginning", "end")
        if isinstance(node.value, str)
        else node.value,
        kind=node.kind,
    )


@pytest.mark.benchmark(group="ast")
def test_transform_plum(benchmark, foobar):
    result = benchmark(transform_plum, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )


###############
# multimethod #
###############


@multimethod_dispatch
def transform_multimethod(node: list):
    return [transform_multimethod(x) for x in node]


@multimethod_dispatch
def transform_multimethod(node: int | str | NoneType):
    return node


@multimethod_dispatch
def transform_multimethod(node: ast.AST):
    kw = {
        field: transform_multimethod(getattr(node, field))
        for field in node._fields
    }
    return type(node)(**kw)


@multimethod_dispatch
def transform_multimethod(node: ast.BinOp):
    return ast.BinOp(
        op=ast.Pow(),
        left=transform_multimethod(node.left),
        right=transform_multimethod(node.right),
    )


@multimethod_dispatch
def transform_multimethod(node: ast.Constant):
    return ast.Constant(
        value=node.value.replace("beginning", "end")
        if isinstance(node.value, str)
        else node.value,
        kind=node.kind,
    )


@pytest.mark.benchmark(group="ast")
def test_transform_multimethod(benchmark, foobar):
    result = benchmark(transform_multimethod, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )


###########
# runtype #
###########


@runtype_dispatch
def transform_runtype(node: list):
    return [transform_runtype(x) for x in node]


@runtype_dispatch
def transform_runtype(node: int | str | NoneType):
    return node


@runtype_dispatch
def transform_runtype(node: ast.AST):
    kw = {
        field: transform_runtype(getattr(node, field)) for field in node._fields
    }
    return type(node)(**kw)


@runtype_dispatch
def transform_runtype(node: ast.BinOp):
    return ast.BinOp(
        op=ast.Pow(),
        left=transform_runtype(node.left),
        right=transform_runtype(node.right),
    )


@runtype_dispatch
def transform_runtype(node: ast.Constant):
    return ast.Constant(
        value=node.value.replace("beginning", "end")
        if isinstance(node.value, str)
        else node.value,
        kind=node.kind,
    )


@pytest.mark.benchmark(group="ast")
def test_transform_runtype(benchmark, foobar):
    result = benchmark(transform_runtype, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )


####################
# multipledispatch #
####################


@multipledispatch_dispatch(list)
def transform_multipledispatch(node: list):
    return [transform_multipledispatch(x) for x in node]


@multipledispatch_dispatch((int, str, NoneType))
def transform_multipledispatch(node: int | str | NoneType):
    return node


@multipledispatch_dispatch(ast.AST)
def transform_multipledispatch(node: ast.AST):
    kw = {
        field: transform_multipledispatch(getattr(node, field))
        for field in node._fields
    }
    return type(node)(**kw)


@multipledispatch_dispatch(ast.BinOp)
def transform_multipledispatch(node: ast.BinOp):
    return ast.BinOp(
        op=ast.Pow(),
        left=transform_multipledispatch(node.left),
        right=transform_multipledispatch(node.right),
    )


@multipledispatch_dispatch(ast.Constant)
def transform_multipledispatch(node: ast.Constant):
    return ast.Constant(
        value=node.value.replace("beginning", "end")
        if isinstance(node.value, str)
        else node.value,
        kind=node.kind,
    )


@pytest.mark.benchmark(group="ast")
def test_transform_multipledispatch(benchmark, foobar):
    result = benchmark(transform_multipledispatch, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )


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


@pytest.mark.benchmark(group="ast")
def test_node_transformer(benchmark, foobar):
    result = benchmark(NT().visit, foobar[0])
    assert ast.dump(result, indent=2) == ast.dump(foobar[1], indent=2).replace(
        "bar", "foo"
    )
