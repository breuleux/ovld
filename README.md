
# Ovld

Multiple dispatch in Python, with some extra features.

With ovld, you can write a version of the same function for every type signature using annotations instead of writing an awkward sequence of `isinstance` statements. Unlike Python `singledispatch`, it works for multiple arguments.

Other features of `ovld`:

* Multiple dispatch for methods (with `metaclass=ovld.OvldMC`)
* Create variants of functions
* Built-in support for extensible, stateful recursion
* Function wrappers
* Function postprocessors
* Nice stack traces

## Example

Here's a function that adds lists, tuples and dictionaries:

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
```

## Bootstrapping and variants

Now, there is another way to do this using ovld's *auto-bootstrapping*. Simply list `self` as the first argument to the function, and `self` will be bound to the function itself, so you can call `self(x, y)` for the recursion instead of `add(x, y)`:


```python
@ovld
def add(self, x: list, y: list):
    return [self(a, b) for a, b in zip(x, y)]

@ovld
def add(self, x: tuple, y: tuple):
    return tuple(self(a, b) for a, b in zip(x, y))

@ovld
def add(self, x: dict, y: dict):
    return {k: self(v, y[k]) for k, v in x.items()}

@ovld
def add(self, x: object, y: object):
    return x + y
```

Why is this useful, though? Observe:

```python
@add.variant
def mul(self, x: object, y: object):
    return x * y

assert add([1, 2], [3, 4]) == [4, 6]
assert mul([1, 2], [3, 4]) == [3, 8]
```

A `variant` of a function is a copy which inherits all of the original's implementations but may define new ones. And because `self` is bound to the function that's called at the top level, the implementations for `list`, `tuple` and `dict` will bind `self` to `add` or `mul` depending on which one was called. You may also call `self.super(*args)` to invoke the parent implementation for that type.

## State

You can pass `initial_state` to `@ovld` or `variant`. The initial state must be a function that takes no arguments. Its return value will be available in `self.state`. The state is initialized at the top level call, but recursive calls to `self` will preserve it.

In other words, you can do something like this:

```python
@add.variant(initial_state=lambda: 0)
def count(self, x, y):
    self.state += 1
    return (f"#{self.state}", x + y)

assert count([1, 2, 3], [4, 5, 6]) == [("#1", 5), ("#2", 7), ("#3", 9)]
```

The initial_state function can return any object and you can use the state to any purpose (e.g. cache or memoization).

## Custom dispatch

You can define your own dispatching function. The dispatcher's first argument is always `self`.

* `self.resolve(x, y)` to get the right function for the types of x and y
* `self[type(x), type(y)]` will also return the right function for these types, but it works directly with the types.

For example, here is how you might define a function such that f(x) <=> f(x, x):

```python
@ovld.dispatch
def add_default(self, x, y=None):
    if y is None:
        y = x
    return self.resolve(x, y)(x, y)

@ovld
def add_default(x: int, y: int):
    return x + y

@ovld
def add_default(x: str, y: str):
    return x + y

@ovld
def add_default(xs: list, ys: list):
    return [add_default(x, y) for x, y in zip(xs, ys)]

assert add_default([1, 2, "alouette"]) == [2, 4, "alouettealouette"]
```

There are other uses for this feature, e.g. memoization.

The normal functions may also have a `self`, which works the same as bootstrapping, and you can give an `initial_state` to `@ovld.dispatch` as well.

## Postprocess

`@ovld`, `@ovld.dispatch`, etc. take a `postprocess` argument which should be a function of one argument. That function will be called with the result of the call and must return the final result of the call.

Note that intermediate, bootstrapped recursive calls (recursive calls using `self()`) will **not** be postprocessed (if you want to wrap these calls, you can do so otherwise, like defining a custom dispatch). Only the result of the top level call is postprocessed.

## Methods

Use the `OvldMC` metaclass to use multiple dispatch on methods. In this case there is no bootstrapping as described above and `self` is simply bound to the class instance.

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

Subclasses of `Cat` will inherit the overloaded `interact` and it may define additional overloaded methods which will only be valid for the subclass.

**Note:** It is possible to use `ovld.dispatch` on methods, but in this case be aware that the first argument for the dispatch method will not be the usual `self` but an `OvldCall` object. The `self` can be retrived as `ovldcall.obj`. Here's an example to make it all clear:

```python
class Stuff(metaclass=OvldMC):
    def __init__(self, mul):
        self.mul = mul

    @ovld.dispatch
    def calc(ovldcall, x):
        # Wraps every call to self.calc, but we receive ovldcall instead of self
        # ovldcall[type(x)] returns the right method to call
        # ovldcall.obj is the self (the actual instance of Stuff)
        return ovldcall[type(x)](x) * ovldcall.obj.mul

    def calc(self, x: int):
        return x + 1

    def calc(self, xs: list):
        return [self.calc(x) for x in xs]

print(Stuff(2).calc([1, 2, 3]))  # [4, 6, 8, 4, 6, 8]
```

### Mixins in subclasses

The `@extend_super` decorator on a method will combine the method with the definition on the superclass:

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

You may define an additional function with signature (int, int) to disambiguate:

```python
@ovld
def ambig(x: int, y: int):
    print("ii")
```

## Other features

### meta

To test arbitrary conditions, you can use `meta`:

```python
from ovld import ovld, meta

@meta
def StartsWithT(cls):
    return cls.__name__.startswith("T")

@ovld
def f(x: StartsWithT):
    return "T"

assert f(TypeError("xyz")) == "T"


# Or: a useful example, since dataclasses have no common superclass:

from dataclasses import dataclass, is_dataclass

@dataclass
class Point:
    x: int
    y: int

@ovld
def f(x: meta(is_dataclass)):
    return "dataclass"

assert f(Point(1, 2)) == "dataclass"
```


### deferred

You may define overloads for certain classes from external packages without
having to import them:


```python
from ovld import ovld, deferred

@ovld
def f(x: deferred("numpy.ndarray")):
    return "ndarray"

# numpy is not imported
assert "numpy" not in sys.modules

# But once we import it, the ovld works:
import numpy
assert f(numpy.arange(10)) == "ndarray"
```


### Tracebacks

`ovld` automagically renames functions so that the stack trace is more informative:

```python
@add.variant
def bad(self, x: object, y: object):
    raise Exception("Bad.")

bad([1], [2])

"""
  File "/Users/breuleuo/code/ovld/ovld/core.py", line 148, in bad.entry
    res = ovc(*args, **kwargs)
  File "/Users/breuleuo/code/ovld/ovld/core.py", line 182, in bad.dispatch
    return method(self.bind_to, *args, **kwargs)
  File "example.py", line 6, in bad[list, list]
    return [self(a, b) for a, b in zip(x, y)]
  File "example.py", line 6, in <listcomp>
    return [self(a, b) for a, b in zip(x, y)]
  File "/Users/breuleuo/code/ovld/ovld/core.py", line 182, in bad.dispatch
    return method(self.bind_to, *args, **kwargs)
  File "example.py", line 26, in bad[*, *]
    raise Exception("Bad.")
  Exception: Bad.
"""
```

The functions on the stack have names like `bad.entry`, `bad.dispatch`, `bad[list, list]` and `bad[*, *]` (`*` stands for `object`), which lets you better understand what happened just from the stack trace.

This also means profilers will be able to differentiate between these paths and between variants, even if they share code paths.
