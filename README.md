
# Ovld

Fast multiple dispatch in Python, with many extra features.

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python `singledispatch`, it works for multiple arguments.

Other features of `ovld`:

* **Fast:** Thanks to some automatic code rewriting, `ovld` is very fast.
* **Extensible:** Easily define variants of recursive functions.
* **Dependent types:** Overloaded functions can depend on more than argument types: they can depend on actual values.
* **Nice stack traces:** Functions are renamed to reflect their type signature.
* Multiple dispatch for **methods** (with `OvldBase` or `metaclass=ovld.OvldMC`)

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

In order to determine which of its methods to call on a list of arguments, `ovld` proceeds as follows:

1. The matching method with highest user-defined **priority** is called first.
2. In case of equal user-defined priority, the more **specific** method is called. In order of specificity, if `Cat` subclass of `Mammal` subclass of `Animal`, and `Meower` and `Woofer` are protocols:
   * Single argument: `Cat > Mammal > Animal`
   * Multiple arguments: `(Cat, Cat) > (Cat, Mammal) > (Animal, Mammal)`
   * Multiple arguments: `(Cat, Mammal) <> (Animal, Cat)` (one argument more specific, the other less specific: unordered!)
   * `Cat > Meower`, but `Meower <> Woofer` (protocols are unordered)
   * If matching methods are unordered, an error will be raised
3. If a method calls the special function `call_next`, they will call the next method in the list.

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

**Note:** It is important to write `n > 0` above and not `n >= 0`, because in the latter case there will be an ambiguity for `f(0)`, as both rules match `0`. It is of course possible to disambiguate using explicit priorities.

**Note 2:** `Dependent` is considered more specific than the bound *and* any of the bound's subclasses, which means that `Dependent[object, ...]` will be called before `object`, `int`, `Cat`, protocols, and so on. I would argue this is usually the behavior you want, but it may throw you off if you are not careful. In any case, try to provide the tightest bound possible!


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

## Ambiguous calls

The following definitions will cause a TypeError at runtime when called with two ints, because it is unclear which function is the right match:

```python
@ovld
def ambig(x: int, y: object):
    print("io")

@ovld
def ambig(x: object, y: int):
    print("oi")

ambig(8, 8)  # ???
```

You may define an additional function with signature (int, int) to disambiguate, or define one of them with a higher priority:

```python
@ovld
def ambig(x: int, y: int):
    print("ii")
```

Other ambiguity situations are:

* If multiple Protocols match the same type (and there is nothing more specific)
* If multiple Dependent match
* Multiple inheritance: a class that inherits from X and Y will ambiguously match rules for X and Y. Yes, Python's full mro order says X comes before Y, but `ovld` does not use it. This may change in the future or if this causes legitimate issues.


## Other features

### Dataclass

For your convenience, `ovld` exports `Dataclass` as a protocol:

```python
from dataclasses import dataclass
from ovld.types import Dataclass

@dataclass
class Point:
    x: int
    y: int

@ovld
def f(x: Dataclass):
    return "dataclass"

assert f(Point(1, 2)) == "dataclass"
```

### Type arguments

Use `type[t]` as an argument's type in order to match types given as arguments.

```python
@ovld
def f(cls: type[list[object]], xs: list):
    return [recurse(cls.__args__[0], x) for x in xs]

@ovld
def f(cls: type[int], x: int):
    return x * 2

assert f(list[int], [1, 2, 3]) == [2, 4, 6]
f(list[int], [1, "X", 3])  # type error!
```

This lets you implement things like serialization based on type annotations, etc.


### Deferred

You may define overloads for certain classes from external packages without
having to import them:

```python
from ovld import ovld, Deferred

@ovld
def f(x: Deferred["numpy.ndarray"]):
    return "ndarray"

# numpy is not imported
assert "numpy" not in sys.modules

# But once we import it, the ovld works:
import numpy
assert f(numpy.arange(10)) == "ndarray"
```


### Exactly and StrictSubclass

You can prevent matching of subclasses with `Exactly`, or prevent matching the bound with `StrictSubclass`:

```python
from ovld.types import Exactly, StrictSubclass

@ovld
def f(x: Exactly[BaseException]):
    return "=BaseException"

@ovld
def f(x: StrictSubclass[Exception]):
    return ">Exception"

assert f(TypeError()) == ">Exception"
assert f(BaseException()) == "=BaseException"

f(Exception())  # ERROR!
```


### Tracebacks

`ovld` automagically renames functions so that the stack trace is more informative. For instance, running the `add` function defined earlier on bad inputs:

```python
add([[[1]]], [[[[2]]]])
```

Will produce the following traceback (Python 3.12):

```
Traceback (most recent call last):
  File "/Users/olivier/code/ovld/example.py", line 37, in <module>
    add([[[1]]], [[[[2]]]])
  File "/Users/olivier/code/ovld/src/ovld/core.py", line 46, in first_entry
    return method(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/olivier/code/ovld/src/ovld/core.py", line 409, in add.dispatch
    return method(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/olivier/code/ovld/example.py", line 18, in add[list, list]
    return [recurse(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^^^^^
  File "/Users/olivier/code/ovld/example.py", line 18, in add[list, list]
    return [recurse(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^^^^^
  File "/Users/olivier/code/ovld/example.py", line 18, in add[list, list]
    return [recurse(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^^^^^
  File "/Users/olivier/code/ovld/example.py", line 30, in add[*, *]
    return x + y
           ~~^~~
TypeError: unsupported operand type(s) for +: 'int' and 'list'
```

* The functions on the stack have names like `add.dispatch`, `add[list, list]` and `add[*, *]` (`*` stands for `object`), which lets you better understand what happened just from the stack trace. It also helps distinguish various paths when profiling.
* When calling `recurse` or `call_next`, the dispatch logic is inlined, leading to a flatter and less noisy stack. (This inlining also reduces `ovld`'s overhead.)

Note: `first_entry` is only called the very first time you call the `ovld` and performs some setup, then it replaces itself with `add.dispatch`.
