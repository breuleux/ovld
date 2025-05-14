import re

import pytest

from ovld.dependent import Regexp

from .common import (
    function_builder,
    ovld_dispatch,
    plum_dispatch,
    with_functions,
)

###############################
# multiple dispatch libraries #
###############################


@function_builder
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


@pytest.mark.benchmark(group="regexp")
@with_functions(
    ovld=make_regexp(ovld_dispatch),
    plum=make_regexp(plum_dispatch),
    custom__search=regexp_search,
    custom__compiled=regexp_compiled,
    custom__compiled_nx=regexp_compiled_nonexclusive,
)
def test_regexp(fn, benchmark):
    def run():
        return [
            fn("allo"),
            fn("canada"),
            fn("the end"),
        ]

    result = benchmark(run)
    assert result == ["one", "two", "three"]
