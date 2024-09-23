import sys
from dataclasses import dataclass, fields
from numbers import Number
from typing import Literal, Union

import pytest

from ovld import ovld, recurse
from ovld.types import Dataclass


@ovld
def calc(num: Number):
    return num


@ovld
def calc(tup: tuple):
    return calc(*tup)


@ovld
def calc(op: Literal["add"], x: object, y: object):
    return calc(x) + calc(y)


@ovld
def calc(op: Literal["sub"], x: object, y: object):
    return calc(x) - calc(y)


@ovld
def calc(op: Literal["mul"], x: object, y: object):
    return calc(x) * calc(y)


@ovld
def calc(op: Literal["div"], x: object, y: object):
    return calc(x) / calc(y)


@ovld
def calc(op: Literal["pow"], x: object, y: object):
    return calc(x) ** calc(y)


@ovld
def calc(op: Literal["sqrt"], x: object):
    return calc(x) ** 0.5


def test_calc():
    expr = (
        "add",
        ("mul", ("sqrt", 4), 7),
        ("div", ("add", 6, 4), ("sub", 5, 3)),
    )
    expected_result = 19
    assert calc(expr) == expected_result


@dataclass
class Citizen:
    name: str
    birthyear: int
    hometown: str


@dataclass
class Country:
    languages: list[str]
    capital: str
    population: int
    citizens: list[Citizen]


@dataclass
class World:
    countries: dict[str, Country]


@ovld
def deserialize(t: type[Dataclass], data: dict):
    kwargs = {
        f.name: recurse(f.type, data[f.name])
        for f in fields(t)
        if f.name in data
    }
    return t(**kwargs)


@ovld
def deserialize(t: type[list], data: list):
    (lt,) = t.__args__
    return [recurse(lt, x) for x in data]


@ovld
def deserialize(t: type[dict], data: dict):
    (
        kt,
        vt,
    ) = t.__args__
    return {recurse(kt, k): recurse(vt, v) for k, v in data.items()}


@ovld
def deserialize(t: type[Union[int, str]], data: Union[int, str]):
    assert isinstance(data, t)
    return data


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="doesn't work, not worth fixing",
)
def test_deserialize():
    data = {
        "countries": {
            "canada": {
                "languages": ["English", "French"],
                "capital": "Ottawa",
                "population": 39_000_000,
                "citizens": [
                    {
                        "name": "Olivier",
                        "birthyear": 1985,
                        "hometown": "Montreal",
                    },
                    {
                        "name": "Abraham",
                        "birthyear": 2018,
                        "hometown": "Shawinigan",
                    },
                ],
            }
        }
    }

    expected = World(
        countries={
            "canada": Country(
                languages=["English", "French"],
                capital="Ottawa",
                population=39_000_000,
                citizens=[
                    Citizen(
                        name="Olivier",
                        birthyear=1985,
                        hometown="Montreal",
                    ),
                    Citizen(
                        name="Abraham",
                        birthyear=2018,
                        hometown="Shawinigan",
                    ),
                ],
            )
        }
    )

    assert deserialize(World, data) == expected
