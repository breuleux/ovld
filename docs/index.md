# Ovld documentation

[Repository](https://github.com/breuleux/ovld)

```
pip install ovld
```

ovld implements fast multiple dispatch in Python, with many extra features.

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python's `functools.singledispatch`, it works for multiple arguments.

## Example

Define one version of your function for each type signature you want to support. `ovld` supports all basic types, plus literals and value-dependent types such as `Regexp`.

```python
from ovld import ovld
from ovld.dependent import Regexp
from typing import Literal

@ovld
def f(x: str):
    return f"The string {x!r}"

@ovld
def f(x: int):
    return f"The number {x}"

@ovld
def f(x: int, y: int):
    return "Two numbers!"

@ovld
def f(x: Literal[0]):
    return "zero"

@ovld
def f(x: Regexp[r"^X"]):
    return "A string that starts with X"

assert f("hello") == "The string 'hello'"
assert f(3) == "The number 3"
assert f(1, 2) == "Two numbers!"
assert f(0) == "zero"
assert f("XSECRET") == "A string that starts with X"
```


## Recursive example

`ovld` shines particularly with recursive definitions, for example tree maps or serialization. Here we define a function that recursively adds lists of lists and integers:

```python
from ovld import ovld, recurse

@ovld
def add(x: list, y: list):
    return [recurse(a, b) for a, b in zip(x, y)]

@ovld
def add(x: list, y: int):
    return [recurse(a, y) for a in x]

@ovld
def add(x: int, y: list):
    return [recurse(x, a) for a in y]

@ovld
def add(x: int, y: int):
    return x + y

assert add([1, 2], [3, 4]) == [4, 6]
assert add([1, 2, [3]], 7) == [8, 9, [10]]
```

The **`recurse`** function is special: it will recursively call the current ovld object. You may ask: how is it different from simply calling `add`? The difference is that if you create a *variant* of `add`, `recurse` will automatically call the variant:


## Variants

A **variant** of an `ovld` is a copy of the `ovld`, with some methods added or changed. For example, let's take the definition of `add` above and make a variant that multiplies numbers instead:

```python
@add.variant
def mul(x: int, y: int):
    return x * y

assert mul([1, 2], [3, 4]) == [3, 8]
```

Simple! This means you can define one `ovld` that recursively walks generic data structures, and then specialize it in various ways.
