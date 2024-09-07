
# Dependent types

A dependent type is a **type** that depends on a **value**:

* **`Literal[0]`**: matches 0, but not any other number
* **`Dependent[bound, check]`**: only matches values such that `isinstance(value, bound) and check(value)`.
* **`Regexp[r"^A"]`**: only matches strings that start with the letter A.
* Etc.

For example, you could define a function to calculate factorial numbers like this:

```python
from typing import Literal
from ovld import ovld, recurse, Dependent

@ovld
def fact(n: Literal[0]):
    return 1

@ovld
def fact(n: Dependent[int, lambda n: n > 0]):
    return n * recurse(n - 1)

assert fact(5) == 120
fact(-1)   # Error!
```

The first argument to `Dependent` must be a type bound. The bound must match before the logic is called, which also ensures we don't get a performance hit for unrelated types. For type checking purposes, `Dependent[T, A]` is equivalent to `Annotated[T, A]`.

!!!Important

    In the above, you must write `n > 0` and not `n >= 0`, because in the latter case there will be an ambiguity for `f(0)`, as both rules match `0`. It is of course possible to disambiguate using explicit priorities.

!!!Note

    `Dependent` is considered more specific than the bound *and* any of the bound's subclasses, which means that `Dependent[object, ...]` will be called before `object`, `int`, `Cat`, protocols, and so on. I would argue this is usually the behavior you want, but it may throw you off if you are not careful. In any case, try to provide the tightest bound possible!

## Defining new dependent types

An even easier way to define new dependent types is with the `@dependent_check` decorator:

```python
import re
from ovld import dependent_check, ovld

@dependent_check
def Regexp(value: str, regexp):
    # Make sure to return a boolean.
    return bool(re.search(pattern=regexp, string=value))

@ovld
def f(x: Regexp["^[Hh]ello"]):
    return "greeting"

@ovld
def f(x: Regexp["^[Bb]ye"]):
    return "farewell"

assert f("hello there") == "greeting"
assert f("Bye!") == "farewell"
```

The first parameter is the value to check. The type annotation (e.g. `value: str` above) is interpreted by `ovld` to be the bound for this type, so `Regexp` will only be called on string parameters (bounds can be overrided with `Dependent[new_bound, type]`). Any other parameters can be provided between `[]`s and will be passed along.

## Wildcards

Functions annotated with `@dependent_check` can take `Any` as some of their arguments (you do with them as you please). `Any` is considered more general than specific values for method resolution purposes:

```python
@dependent_check
def Shape(tensor: Tensor, *shape):
    return (
        len(tensor.shape) == len(shape)
        and all(s2 is Any or s1 == s2 for s1, s2 in zip(tensor.shape, shape))
    )

@ovld
def f(tensor: Shape[2, 2]):
    # Only matches 2x2 tensors
    ...

@ovld
def f(tensor: Shape[2, Any]):
    # Matches 2xN tensors, for any N, but Shape[2, 2] is matched preferentially
    ...
```

## Union and Intersection

Dependent types can be combined with `|` (union) and `&` (intersection). For instance, in order to write a function that matches 2x2 pytorch float32 tensors, you could write something like this:

```python
from torch import Tensor

@dependent_check
def Dtype(tensor: Tensor, dtype):
    return tensor.dtype == dtype

@ovld
def f(tensor: Shape[2, 2] & Dtype[torch.float32]):
    # Only matches 2x2 tensors that also have the float32 dtype
    ...
```

The bounds for these composite types are naturally the Union/Intersection of the components' bounds.

