# Ovld documentation

[Repository](https://github.com/breuleux/ovld)

```
pip install ovld
```

ovld implements fast multiple dispatch in Python, with many extra features.

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python's `functools.singledispatch`, it works for multiple arguments.

## Example

Here's a function that adds lists, tuples and dictionaries:

```python
from ovld import ovld, recurse

@ovld
def add(x: list, y: list):
    return [recurse(a, b) for a, b in zip(x, y)]

@ovld
def add(x: tuple, y: tuple):
    return tuple(recurse(a, b) for a, b in zip(x, y))

@ovld
def add(x: dict, y: dict):
    return {k: recurse(v, y[k]) for k, v in x.items()}

@ovld
def add(x: object, y: object):
    return x + y
```

The **`recurse`** function is special: it will recursively call the current ovld object. You may ask: how is it different from simply calling `add`? The difference is that if you create a *variant* of `add`, `recurse` will automatically call the variant:


## Variants

A **variant** of an `ovld` is a copy of the `ovld`, with some methods added or changed. For example, let's take the definition of `add` above and make a variant that multiplies numbers instead:

```python
@add.variant
def mul(self, x: object, y: object):
    return x * y

assert mul([1, 2], [3, 4]) == [3, 8]
```

Simple! This means you can define one `ovld` that recursively walks generic data structures, and then specialize it in various ways.
