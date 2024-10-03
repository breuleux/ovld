import re

import pytest

from ovld.dependent import Regexp

from .common import ovld_dispatch, plum_dispatch

###############################
# multiple dispatch libraries #
###############################


def make_regexp(dispatch):
    @dispatch
    def regexp(x: Regexp[r"^a"]):
        return "one"

    @dispatch
    def regexp(x: Regexp[r"^[bcd]"]):
        return "two"

    @dispatch
    def regexp(x: Regexp[r"end$"]):
        return "three"

    return regexp


##############
# isinstance #
##############


def regexp_search(x):
    if re.search(string=x, pattern=r"^a"):
        return "one"
    if re.search(string=x, pattern=r"^[bcd]"):
        return "two"
    if re.search(string=x, pattern=r"end$"):
        return "three"


re1 = re.compile(r"^a")
re2 = re.compile(r"^[bcd]")
re3 = re.compile(r"end$")


def regexp_compiled(x):
    if re1.search(x):
        return "one"
    if re2.search(x):
        return "two"
    if re3.search(x):
        return "three"


def regexp_compiled_nonexclusive(x):
    r1 = bool(re1.search(x))
    r2 = bool(re2.search(x))
    r3 = bool(re3.search(x))
    if r1:
        return "one"
    if r2:
        return "two"
    if r3:
        return "three"


####################
# Test definitions #
####################


def make_test(fn):
    @pytest.mark.benchmark(group="regexp")
    def test(benchmark):
        def run():
            return [
                fn("allo"),
                fn("canada"),
                fn("the end"),
            ]

        result = benchmark(run)
        assert result == ["one", "two", "three"]

    return test


test_regexp_ovld = make_test(make_regexp(ovld_dispatch))
test_regexp_plum = make_test(make_regexp(plum_dispatch))

test_regexp_custom_search = make_test(regexp_search)
test_regexp_custom_compiled = make_test(regexp_compiled)
# test_regexp_custom_compiled_nx = make_test(regexp_compiled_nonexclusive)
