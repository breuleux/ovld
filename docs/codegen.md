
# Code generation

!!!warning
    These features are **EXPERIMENTAL** and the interface may break at any moment!

`ovld` supports two kinds of code generation to make things faster.

* **Instance checks:** Custom protocols can return code that performs the check. This code is injected directly in dispatch functions to avoid a function call when e.g. a simple equality check would suffice.
* **Specializing functions:** The `@code_generator` decorator on a function means that this function will receive types as arguments and must return *code* that will be called on the real values. The generated code will be cached for the particular type signature.

The `ovld.Code` class should be used to return generated code. Functions and data can be embedded using `Code` and the `$x` syntax. For example, return `Code("$f($x, 3)", f=my_function, x=open(...))` to generate code that will call `my_function` with some file. Note that `ovld` will not necessarily use these specific symbols in the code: to make the generated code easier to read and debug, it will try to use the real names of the functions or classes you embed.


## Instance checks

Here is an example of how to define an efficient `Regexp` check:

```python
@dependent_check
class Regexp:
    def __post_init__(self):
        self.rx = re.compile(self.parameter)

    def check(self, value: str):
        return bool(self.rx.search(value))

    def codegen(self):
        return Code("bool($rx.search($arg))", rx=self.rx)
```

The type's `codegen` method will be called by `ovld` to create code for the relevant dispatch function: instead of running, say, `isinstance(arg, Regexp)` it will run `bool(rx.search(arg))` directly, saving some overhead.

The pre-compiled regexp `rx` can be embedded in the generated code by passing it to `Code`. The special variable `$arg` is filled in by `ovld` and corresponds to the argument we want to check.


## Specialized functions

This feature lets you create specialized code for certain types. For instance, if you are writing a serializer, instead of writing a generic function for dataclasses that loops over the fields, you can generate a specialized function for each dataclass where the loop is unrolled:

**Without codegen:**

```python
@ovld
def serialize(x: Dataclass):
    kwargs = {
        f.name: recurse(getattr(x, f.name))
        for f in fields(type(x))
    }
    return type(x)(**kwargs)
```

**With codegen:**

```python
from ovld import Code, code_generator

@ovld
@code_generator
def serialize(x: Dataclass):
    body = [f"{fld.name}=$recurse(x.{fld.name})," for fld in fields(x)]
    return Code(["return $dataclass(", body, ")"], dataclass=x, recurse=recurse)
```

When the above is called on e.g. a `Person` object, the following code would be generated and called whenever a `Person` is passed to `serialize`:

```python
def __GENERATED__(x):
    return Person(
        name=serialize(x.name),
        hometown=serialize(x.hometown),
        age=serialize(x.age),
    )
```

All other members of the `ovld` work as normal, so you can focus your codegen on specific classes.

If the code generation function returns `None`, nothing is generated and the next matching dispatch function will be used. You may also return a function directly.


## Viewing the code

If you want to look at the code `ovld` will generate, try something like this:

```python
from ovld import Code, NameDatabase

code = Code(
    ["if x == $value:", ["print($txt)", "return True"]],
    value=0,
    txt="It is zero!",
)
ndb = NameDatabase()   # Optional, but fill() will add variable mappings in there
print(code.fill(ndb))  # Code produced
print(ndb.variables)   # Dictionary of globals to pass to eval/exec
```

A list is interpreted as a list of lines, and nested lists will be indented, so you don't have to care about doing that yourself.

You will see that when `value` and `txt` are simple types they will be embedded as literals, otherwise they will be represented as symbols -- the mappings are added to `ndb.variables`, which should be passed as the globals of the eval/execed code.
