
# Ovld

Fast multiple dispatch in Python, with many extra features.

[📋 Documentation](https://ovld.readthedocs.io/en/latest/)

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python's `singledispatch`, it works for multiple arguments.

* ⚡️ **[Fast](https://ovld.readthedocs.io/en/latest/compare/#results):** `ovld` is the fastest multiple dispatch library around, by some margin.
* 🚀 [**Variants**](https://ovld.readthedocs.io/en/latest/usage/#variants) and [**mixins**](https://ovld.readthedocs.io/en/latest/usage/#mixins) of functions and methods.
* 🦄 **[Dependent types](https://ovld.readthedocs.io/en/latest/dependent/):** Overloaded functions can depend on more than argument types: they can depend on actual values.
* 🔑 **Extensive:** Dispatch on functions, methods, positional arguments and even [keyword arguments](https://ovld.readthedocs.io/en/latest/usage/#keyword-arguments) (with some restrictions).

## Example

Here's a function that recursively adds lists, tuples and dictionaries:

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

assert add([1, 2], [3, 4]) == [4, 6]
```

The `recurse` function is special: it will recursively call the current ovld object. You may ask: how is it different from simply calling `add`? The difference is that if you create a *variant* of `add`, `recurse` will automatically call the variant.

For example:


## Variants

A *variant* of an `ovld` is a copy of the `ovld`, with some methods added or changed. For example, let's take the definition of `add` above and make a variant that multiplies numbers instead:

```python
@add.variant
def mul(self, x: object, y: object):
    return x * y

assert mul([1, 2], [3, 4]) == [3, 8]
```

Simple! This means you can define one `ovld` that recursively walks generic data structures, and then specialize it in various ways.


## Priority and call_next

You can define a numeric priority for each method (the default priority is 0):

```python
from ovld import call_next

@ovld(priority=1000)
def f(x: int):
    return call_next(x + 1)

@ovld
def f(x: int):
    return x * x

assert f(10) == 121
```

Both definitions above have the same type signature, but since the first has higher priority, that is the one that will be called.

However, that does not mean there is no way to call the second one. Indeed, when the first function calls the special function `call_next(x + 1)`, it will call the next function in the list below itself.

The pattern you see above is how you may wrap each call with some generic behavior. For instance, if you did something like that:

```python
@f.variant(priority=1000)
def f2(x: object)
    print(f"f({x!r})")
    return call_next(x)
```

You would effectively be creating a clone of `f` that traces every call.


## Dependent types

A dependent type is a type that depends on a value. `ovld` supports this, either through `Literal[value]` or `Dependent[bound, check]`. For example, this definition of factorial:

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

### dependent_check

Define your own types with the `@dependent_check` decorator:

```python
import torch
from ovld import ovld, dependent_check

@dependent_check
def Shape(tensor: torch.Tensor, *shape):
    return (
        len(tensor.shape) == len(shape)
        and all(s2 is Any or s1 == s2 for s1, s2 in zip(tensor.shape, shape))
    )

@dependent_check
def Dtype(tensor: torch.Tensor, dtype):
    return tensor.dtype == dtype

@ovld
def f(tensor: Shape[3, Any]):
    # Matches 3xN tensors
    ...

@ovld
def f(tensor: Shape[2, 2] & Dtype[torch.float32]):
    # Only matches 2x2 tensors that also have the float32 dtype
    ...
```

The first parameter is the value to check. The type annotation (e.g. `value: torch.Tensor` above) is interpreted by `ovld` to be the bound for this type, so `Shape` will only be called on parameters of type `torch.Tensor`.

## Methods

Either inherit from `OvldBase` or use the `OvldMC` metaclass to use multiple dispatch on methods.

```python
from ovld import OvldBase, OvldMC

# class Cat(OvldBase):  <= Also an option
class Cat(metaclass=OvldMC):
    def interact(self, x: Mouse):
        return "catch"

    def interact(self, x: Food):
        return "devour"

    def interact(self, x: PricelessVase):
        return "destroy"
```

### Subclasses

Subclasses inherit overloaded methods. They may define additional overloads for these methods which will only be valid for the subclass, but they need to use the `@extend_super` decorator (this is required for clarity):


```python
from ovld import OvldMC, extend_super

class One(metaclass=OvldMC):
    def f(self, x: int):
        return "an integer"

class Two(One):
    @extend_super
    def f(self, x: str):
        return "a string"

assert Two().f(1) == "an integer"
assert Two().f("s") == "a string"
```

# Benchmarks

`ovld` is pretty fast: the overhead is comparable to `isinstance` or `match`, and only 2-3x slower when dispatching on `Literal` types. Compared to other multiple dispatch libraries, it has 1.5x to 100x less overhead.

Time relative to the fastest implementation (1.00) (lower is better).

| Benchmark | custom | [ovld](https://github.com/breuleux/ovld) | [plum](https://github.com/beartype/plum) | [multim](https://github.com/coady/multimethod) | [multid](https://github.com/mrocklin/multipledispatch/) | [runtype](https://github.com/erezsh/runtype) | [fastcore](https://github.com/fastai/fastcore) | [sd](https://docs.python.org/3/library/functools.html#functools.singledispatch) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
|[trivial](https://github.com/breuleux/ovld/tree/master/benchmarks/test_trivial.py)|1.45|1.00|3.32|4.63|2.04|2.41|51.93|1.91|
|[multer](https://github.com/breuleux/ovld/tree/master/benchmarks/test_multer.py)|1.13|1.00|11.05|4.53|8.31|2.19|46.74|7.32|
|[add](https://github.com/breuleux/ovld/tree/master/benchmarks/test_add.py)|1.08|1.00|3.73|5.21|2.37|2.79|59.31|x|
|[ast](https://github.com/breuleux/ovld/tree/master/benchmarks/test_ast.py)|1.00|1.08|23.14|3.09|1.68|1.91|28.39|1.66|
|[calc](https://github.com/breuleux/ovld/tree/master/benchmarks/test_calc.py)|1.00|1.23|54.61|29.32|x|x|x|x|
|[regexp](https://github.com/breuleux/ovld/tree/master/benchmarks/test_regexp.py)|1.00|1.87|19.18|x|x|x|x|x|
|[fib](https://github.com/breuleux/ovld/tree/master/benchmarks/test_fib.py)|1.00|3.30|444.31|125.77|x|x|x|x|
|[tweaknum](https://github.com/breuleux/ovld/tree/master/benchmarks/test_tweaknum.py)|1.00|2.09|x|x|x|x|x|x|
