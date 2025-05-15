import json

from pytest_benchmark import utils

from ovld import ovld, recurse


@ovld
def _cleanup(obj: str | int | float):
    return obj


@ovld
def _cleanup(obj: list):
    return [recurse(x) for x in obj]


@ovld
def _cleanup(obj: dict):
    if type(obj) is not dict:
        return f"UNSERIALIZABLE[{obj}]"
    return {k: recurse(v) for k, v in obj.items()}


@ovld
def _cleanup(obj: object):
    return f"UNSERIALIZABLE[{obj}]"


def safer_dumps(obj, **kwargs):
    # multimethod is not safe for dump of benchmarks because it's a subclass of dict
    # with non-str keys and the json serialization just craps out.
    return json.dumps(_cleanup(obj), **kwargs)


utils._cleanup = _cleanup
utils.safe_dumps.__code__ = safer_dumps.__code__
