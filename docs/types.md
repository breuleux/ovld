
# Special types

`ovld` handles a few types specially, and exports a few useful types:


## Type arguments

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


## Intersection

If `Union[A, B]` represents either type `A` or type `B`, `Intersection[A, B]` represents both of them at the same time.

```python
class A: pass
class B: pass
class C(A, B): pass

@ovld
def f(x: A): return "A"

@ovld
def f(x: B): return "B"

@ovld
def f(x: Intersection[A, B]): return "A & B"

@ovld
def f(x):
    return "other"

assert f(A()) == "A"
assert f(B()) == "B"
assert f(C()) == "A & B"
```


## Dataclass

For your convenience, a protocol for dataclasses:

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


## Deferred

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


## Exactly and StrictSubclass

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

## HasMethod

`ovld.types.HasMethod` is just a quick easy way to define a simple protocol.

```python
@ovld
def f(x: HasMethod["__len__"]):
    return len(x)

assert f([1, 2, 3]) == 3
f(123)  # ERROR
```


## Defining new types

With the `@parametrized_class_check` decorator, you can define a new type or protocol extremely easily. For example, here is how to define `HasMethod` yourself:

```python
@parametrized_class_check
def HasMethod(cls, method_name):
    return hasattr(cls, method_name)
```
