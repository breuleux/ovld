
# Ovld

Fast multiple dispatch in Python, with many extra features.

[📋 Documentation](https://ovld.readthedocs.io/en/latest/)

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python's `singledispatch`, it works for multiple arguments.

* ⚡️ **[Fast](https://ovld.readthedocs.io/en/latest/compare/#results):** ovld is the fastest multiple dispatch library around, by some margin.
* 🚀 [**Variants**](https://ovld.readthedocs.io/en/latest/usage/#variants), [**mixins**](https://ovld.readthedocs.io/en/latest/usage/#mixins) and [**medleys**](https://ovld.readthedocs.io/en/latest/medley) of functions and methods.
* 🦄 **[Value-based dispatch](https://ovld.readthedocs.io/en/latest/dependent/):** Overloaded functions can depend on more than argument types: they can depend on actual values.
* 🔑 **[Extensive](https://ovld.readthedocs.io/en/latest/usage/#keyword-arguments):** Dispatch on functions, methods, positional arguments and even keyword arguments (with some restrictions).
* ⚙️ **[Codegen](https://ovld.readthedocs.io/en/latest/codegen/):** (Experimental) For advanced use cases, you can generate custom code for overloads.

Install with `pip install ovld`


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

The `recurse` function is special: it will recursively call the current ovld object. You may ask: how is it different from simply calling `add`? The difference is that if you create a *variant* of `add`, `recurse` will automatically call the variant.

For example:


## Variants

A *variant* of an `ovld` is a copy of the `ovld`, with some methods added or changed. For example, let's take the definition of `add` above and make a variant that multiplies numbers instead:

```python
@add.variant
def mul(x: int, y: int):
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

However, that does not mean there is no way to call the second one. Indeed, when the first function calls the special function `call_next(x + 1)`, it will call the next function in line, in order of priority and specificity.

The pattern you see above is how you may wrap each call with some generic behavior. For instance, if you did something like this:

```python
@f.variant(priority=1000)
def f2(x: object)
    print(f"f({x!r})")
    return call_next(x)
```

The above is effectively a clone of `f` that traces every call. Useful for debugging.


## Dependent types

A dependent type is a type that depends on a value. This enables dispatching based on the actual value of an argument. The simplest example of a dependent type is `typing.Literal[value]`, which matches one single value. `ovld` also supports `Dependent[bound, check]` for arbitrary checks. For example, this definition of factorial:

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

## Medleys

Inheriting from [`ovld.Medley`](https://ovld.readthedocs.io/en/latest/medley/) lets you combine functionality in a new way. Classes created that way are free-form medleys that you can (almost) arbitrarily combine together.

All medleys are dataclasses and you must define their data fields as you would for a normal dataclass (using `dataclass.field` if needed).

```python
from ovld import Medley

class Punctuator(Medley):
    punctuation: str = "."

    def __call__(self, x: str):
        return f"{x}{self.punctuation}"

class Multiplier(Medley):
    factor: int = 3

    def __call__(self, x: int):
        return x * self.factor

# You can add the classes together to merge their methods and fields using ovld
PuMu = Punctuator + Multiplier
f = PuMu(punctuation="!", factor=3)

# You can also combine existing instances!
f2 = Punctuator("!") + Multiplier(3)

assert f("hello") == f2("hello") == "hello!"
assert f(10) == f2(10) == 30

# You can also meld medleys inplace, but only if all new fields have defaults
class Total(Medley):
    pass

Total.extend(Punctuator, Multiplier)
f3 = Total(punctuation="!", factor=3)
```


# Code generation

(Experimental) For advanced use cases, you can generate custom code for type checkers or overloads. [See here](https://ovld.readthedocs.io/en/latest/codegen/).


# Benchmarks

`ovld` is pretty fast: the overhead is comparable to `isinstance` or `match`, and only 2-3x slower when dispatching on `Literal` types. Compared to other multiple dispatch libraries, it has 1.5x to 100x less overhead.

Time relative to the fastest implementation (1.00) (lower is better).

| Benchmark | custom | [ovld](https://github.com/breuleux/ovld) | [plum](https://github.com/beartype/plum) | [multim](https://github.com/coady/multimethod) | [multid](https://github.com/mrocklin/multipledispatch/) | [runtype](https://github.com/erezsh/runtype) | [sd](https://docs.python.org/3/library/functools.html#functools.singledispatch) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
|[trivial](https://github.com/breuleux/ovld/tree/master/benchmarks/test_trivial.py)|1.56|1.00|3.38|4.92|2.00|2.38|2.15|
|[multer](https://github.com/breuleux/ovld/tree/master/benchmarks/test_multer.py)|1.22|1.00|11.06|4.67|9.22|2.24|3.92|
|[add](https://github.com/breuleux/ovld/tree/master/benchmarks/test_add.py)|1.27|1.00|3.61|4.93|2.24|2.62|x|
|[ast](https://github.com/breuleux/ovld/tree/master/benchmarks/test_ast.py)|1.01|1.00|22.98|2.72|1.52|1.70|1.57|
|[calc](https://github.com/breuleux/ovld/tree/master/benchmarks/test_calc.py)|1.00|1.28|57.86|29.79|x|x|x|
|[regexp](https://github.com/breuleux/ovld/tree/master/benchmarks/test_regexp.py)|1.00|2.28|22.71|x|x|x|x|
|[fib](https://github.com/breuleux/ovld/tree/master/benchmarks/test_fib.py)|1.00|3.39|403.38|114.69|x|x|x|
|[tweaknum](https://github.com/breuleux/ovld/tree/master/benchmarks/test_tweaknum.py)|1.00|1.86|x|x|x|x|x||[tweaknum](https://github.com/breuleux/ovld/tree/master/benchmarks/test_tweaknum.py)|1.00|1.86|x|x|x|x|x|
