
# Medleys

!!!warning
    This is a new feature and there may be a few rough edges.


**Medleys** are a novel and comprehensive way to define and combine functionality. Classes that inherit from `ovld.Medley` are free-form mixins that you can (almost) arbitrarily combine together.


## Example

```python
from ovld import Medley


class Walk(Medley):
    """This medley walks through lists and dicts."""

    def __call__(self, x: list):
        return [self(item) for item in x]
        
    def __call__(self, x: dict):
        return {k: self(v) for k, v in x.items()}

    def __call__(self, x: object):
        return x


class Punctuate(Medley):
    """This medley punctuates strings."""

    punctuation: str = "."

    def __call__(self, x: str):
        return f"{x}{self.punctuation}"


class Multiply(Medley):
    """This medley multiplies integers by a factor."""

    factor: int = 2

    def __call__(self, x: int):
        return x * self.factor


# You can arbitrarily combine instances
walk = Walk()
assert walk([10, "hello"]) == [10, "hello"]

walkp = Walk() + Punctuate("!!!!")
assert walkp([10, "hello"]) == [10, "hello!!!!"]

walkm = Walk() + Multiply(300)
assert walkm([10, "hello"]) == [3000, "hello"]

walkpm = Walk() + Punctuate("!!!!") + Multiply(300)
assert walkpm([10, "hello"]) == [3000, "hello!!!!"]


# You can also combine classes
walkp = (Walk + Punctuate)(punctuation="!!!!")
assert walkp([10, "hello"]) == [10, "hello!!!!"]

walkm = (Walk + Multiply)(factor=300)
assert walkm([10, "hello"]) == [3000, "hello"]

walkpm = (Walk + Punctuate + Multiply)(punctuation="!!!!", factor=300)
assert walkpm([10, "hello"]) == [3000, "hello!!!!"]
```

## Usage

All medleys are dataclasses and you must define their data fields as you would for a normal dataclass (using `dataclass.field` if needed). When combining medleys, fields are forced to be keyword only except for the first class in the mix.

!!!warning
    You may not define `__init__` in a Medley, because it would interfere with combining them with the `+` operator.

* As with standard dataclasses, define `__post_init__` in order to perform additional tasks after initilization. Melded classes will run **all** `__post_init__` functions.
* There can be multiple implementations of any function. All functions will be wrapped with `ovld`.
* Melding multiple classes together means melding all of their methods.
* If two implementations have the exact same signature, the last one will override the others.

```python
from ovld import Medley

class Counter(Medley):
    start: int = 0

    def __post_init__(self):
        self._current = self.start

    def count(self):
        self._current += 1
        return self._current


class Greeter(Medley):
    name: str = "John"
    username: str = None

    def __post_init__(self):
        self.username = self.name.lower() if self.username is None else self.username

    def greet(self):
        return f"Hello {self.name}, your username is {self.username}"


CountGreet = Counter + Greeter
cg = CountGreet(start=10, name="Barbara")
assert cg.count() == 11
assert cg.count() == 12
assert cg.greet() == "Hello Barbara, your username is barbara"
```


## Combining inplace

It is possible to combine medley classes inplace with `extend` or `+=`. Existing instances will gain the new behaviors and the default values of the new fields (the new fields *must* define default values).

```python
# Continuation of the example up top

walk = Walk()
assert walk([10, "hello"]) == [10, "hello"]

Walk.extend(Punctuate, Multiply)
assert walk([10, "hello"]) == [30, "hello."]
```


## Alternative combiners

Multiple dispatch with `ovld` is the default way multiple implementations of the same method are combined, but there are others, which you can declare like this:

```python
from ovld.medley import KeepLast, RunAll, ReduceAll, ChainAll

class Custom(Medley):
    fn1 = KeepLast()   # Only the last implementation will be valid (default Python behavior)
    fn2 = RunAll()     # All implementations will be run (e.g. __post_init__ = RunAll())
    fn3 = ReduceAll()  # Combine as: impl_C(impl_B(impl_A(arg)))
    fn4 = ChainAll()   # Combine as: obj.impl_A(*args).impl_B(*args).impl_C(*args)

    def fn1(self):
        ...

    ...
```

Setting a field to a Combiner only declares the combiner to use for the field with that name, it does not set the actual attribute. Only the first implementation will do that.


## Code generation

!!!warning
    Code generation is **EXPERIMENTAL** and the interface may break at any moment!

Medleys are compatible with ovlds that generate code. However, code generation happens at the class level, so any field which is used in the context of [code generation](./codegen.md) must be annotated as `CodegenParameter[type]`, to ensure its availability. The first argument to the generator will be a subclass of the original class, tweaked for the particular values of the codegen parameters.

**Only** the `CodegenParameter[]`-annotated fields should be accessed during codegen.

```python
from ovld import Medley, CodegenParameter, Lambda, Code, code_generator

class CaseChanger(Medley):
    upper: CodegenParameter[bool] = True

    @code_generator
    def __call__(cls, x: str):
        method = str.upper if cls.upper else str.lower
        return Lambda(Code("$method($x)", method=method))

to_upper = Walk() + CaseChanger(True)
assert to_upper(["Hello", "World"]) == ["HELLO", "WORLD"]

to_lower = Walk() + CaseChanger(False)
assert to_lower(["Hello", "World"]) == ["hello", "world"]
```
