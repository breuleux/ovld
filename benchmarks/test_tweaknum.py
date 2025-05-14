import pytest

from .common import function_builder, ovld_dispatch, with_functions

###############################
# multiple dispatch libraries #
###############################


@function_builder
def make_tweaknum(dispatch):
    @dispatch
    def tweaknum(n: int, *, add: int):
        return n + add

    @dispatch
    def tweaknum(n: int, *, mul: int):
        return n * mul

    @dispatch
    def tweaknum(n: int, *, pow: int):
        return n**pow

    return tweaknum


#######
# ifs #
#######


def tweaknum_ifs(n, *, add=None, mul=None, pow=None):
    assert isinstance(n, int)
    assert (add is not None) + (mul is not None) + (pow is not None) == 1
    if add is not None:
        assert isinstance(add, int)
        return n + add
    if mul is not None:
        assert isinstance(mul, int)
        return n * mul
    if pow is not None:
        assert isinstance(pow, int)
        return n**pow


###################
# match statement #
###################


def tweaknum_match(n, **kwargs):
    match kwargs:
        case {"add": int(x)}:
            return n + x
        case {"mul": int(x)}:
            return n * x
        case {"pow": int(x)}:
            return n**x


####################
# Test definitions #
####################


@pytest.mark.benchmark(group="tweaknum")
@with_functions(
    ovld=make_tweaknum(ovld_dispatch),
    custom__ifs=tweaknum_ifs,
    custom__match=tweaknum_match,
)
def test_tweaknum(fn, benchmark):
    def run():
        return fn(10, add=3), fn(5, mul=7), fn(2, pow=5)

    result = benchmark(run)
    assert result == (13, 35, 32)
