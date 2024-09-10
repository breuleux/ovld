
# Usage


## Standard usage

Simply decorate each overload with `@ovld`.

```python
from ovld import ovld

@ovld
def add(x: list, y: list):
    return [add(a, b) for a, b in zip(x, y)]

@ovld
def add(x: tuple, y: tuple):
    return tuple(add(a, b) for a, b in zip(x, y))

@ovld
def add(x: dict, y: dict):
    return {k: add(v, y[k]) for k, v in x.items()}

@ovld
def add(x: object, y: object):
    return x + y

assert add([1, 2, 3], [4, 5, 6]) == [5, 7, 9]
```

## Keyword arguments

`ovld` can dispatch on keyword arguments:

```python
@ovld
def tweaknum(n: int, *, add: int):
    return n + add

@ovld
def tweaknum(n: int, *, mul: int):
    return n * mul

@ovld
def tweaknum(n: int, *, pow: int):
    return n**pow

assert tweaknum(10, add=3) == 13
assert tweaknum(pow=3, n=10) == 1000
```

The rough rule to be able to provide an argument as a keyword argument is that:

1. It must be keyword-only, and **must not be found as a positional argument in any other method.** (unless said argument is strictly positional).
2. If every function's positional arguments are named the same, `ovld` will also allow you to provide them as keywords. Otherwise they are treated as strictly positional.

!!!note
    If any argument is named differently at the same position in two methods, ovld considers that it must be positional, therefore all arguments before it must also be positional. There is one additional restriction: if the difference between the minimum number of required positional arguments across all functions and the maximum number of positional arguments (required or not) exceeds 1, then they are all considered to be strictly positional (because I don't want to deal with the situation where argument N is given but not argument N-1).

## Methods

You may use `@ovld` on methods as normal:


```python
from ovld import ovld

class Cat:
    @ovld
    def interact(self, x: Mouse):
        return "catch"

    @ovld
    def interact(self, x: Food):
        return "devour"

    @ovld
    def interact(self, x: PricelessVase):
        return "destroy"
```

Alternatively, you can inherit from `OvldBase` or use the `OvldMC` metaclass to make it automatic:

```python
from ovld import OvldMC

class Cat(metaclass=OvldMC):
    def interact(self, x: Mouse):
        return "catch"

    def interact(self, x: Food):
        return "devour"

    def interact(self, x: PricelessVase):
        return "destroy"
```

### extend_super

Subclasses of classes defined with `OvldBase`/`OvldMC` may define additional overloads for existing methods that are only valid for the subclass by using the `@extend_super` decorator:


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

## Variants

A **variant** of an ovld is a copy of the ovld which has additional features. For instance, you may define a generic set of methods to walk a data structure recursively, and then variants that do different operations at the leaves. Two special functions are useful to take advantage of variants: **`recurse`** and **`call_next`**.


## Special function: `recurse`

`ovld.recurse` is a special object which can be used inside `@ovld` decorated functions. It calls the *current* overload recursively. In a variant, it will therefore call the variant.

```python
from ovld import ovld, recurse

# Generic code

@ovld
def walk(x: list, y: list):
    return [recurse(a, b) for a, b in zip(x, y)]

@ovld
def walk(x: tuple, y: tuple):
    return tuple(recurse(a, b) for a, b in zip(x, y))

@ovld
def walk(x: dict, y: dict):
    return {k: recurse(v, y[k]) for k, v in x.items()}

# Variants

@walk.variant
def add(x: object, y: object):
    return x + y

@walk.variant
def mul(x: object, y: object):
    return x + y

assert add([1, 2, 3], [4, 5, 6]) == [5, 7, 9]
assert mul([1, 2], [3, 4]) == [3, 8]
```

## Special function: `call_next`

`ovld.call_next` is a bit like a `super` call, in the sense that it will call the next method in the method resolution order:

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

In the above, two methods are defined for the same type signature, except one has a higher priority and is called first. By calling `call_next`, it can defer to the method right below it.

!!!note
    It is also possible to call `f.next(...)`, but it is slightly less efficient, and `call_next` also works with variants.

## Mixins

When creating an ovld or variant, you can merge any number of ovlds together:

```python
@ovld
def iterate_over_lists(xs: list):
    return [recurse(x) for x in xs]

@ovld
def iterate_over_dicts(xs: dict):
    return {k: recurse(v) for k, v in xs.items()}

@ovld(mixins=[iterate_over_lists, iterate_over_dicts])
def double(x):
    return x * 2

assert double([1, 2, 3]) == [2, 4, 6]
assert double({"x": 10, "y": 20}) == {"x": 20, "y": 40}
```

Using `@extend_super` on a method in a class defined with `metaclass=OvldMC` (or inheriting from one) will merge all parent methods:

```python
class IOL(metaclass=OvldMC):
    def __call__(self, xs: list):
        return [recurse(x) for x in xs]

class IOD:
    def __call__(self, xs: dict):
        return {k: recurse(v) for k, v in xs.items()}

class Mul(IOL, IOD):
    def __init__(self, n):
        self.n = n

    @extend_super
    def __call__(self, x):
        return x * self.n

assert Mul(2)([1, 2, 3]) == [2, 4, 6]
assert Mul(2)({"x": 10, "y": 20}) == {"x": 20, "y": 40}
```


## Priority

Methods registered with `@ovld` can be given a numeric priority with `@ovld(priority=N)`. Methods with higher priority are called first. The default priority is always `0`.
