import pytest

from .common import ovld_dispatch

###############################
# multiple dispatch libraries #
###############################


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


def make_test(fn):
    @pytest.mark.benchmark(group="tweaknum")
    def test(benchmark):
        def run():
            return fn(10, add=3), fn(5, mul=7), fn(2, pow=5)

        result = benchmark(run)
        assert result == (13, 35, 32)

    return test


test_tweaknum_ovld = make_test(make_tweaknum(ovld_dispatch))

test_tweaknum_custom_ifs = make_test(tweaknum_ifs)
test_tweaknum_custom_match = make_test(tweaknum_match)
