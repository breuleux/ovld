
# Other features

## Introspection

### display_resolution

You can check how a call will be resolved with `f.display_resolution(*args, **kwargs)`:

```python
from numbers import Number
from ovld import ovld, Dependent


@ovld(priority=1000)
def f(x: object): ...

@ovld
def f(x: Number): ...

@ovld
def f(x: Dependent[int, lambda x: x < 0]): ...

@ovld
def f(x: int): ...

@ovld
def f(x: str): ...

@ovld(priority=-1)
def f(x: object): ...

f.display_resolution(123)
print("=" * 50)
f.display_resolution("hello")
```

Displays this:

```text
#1 [1000:0] f[*]
          @ /Users/olivier/code/ovld/resolve.py:6      #1: High priority function called FIRST
!= [0:3]    f[<lambda>()]
          @ /Users/olivier/code/ovld/resolve.py:14     #!=: Fall THROUGH this because 123 is not negative
#2 [0:2]    f[int]
          @ /Users/olivier/code/ovld/resolve.py:18     #2: int is more specific than Number
#3 [0:1]    f[Number]
          @ /Users/olivier/code/ovld/resolve.py:10     #3: Number is more specific than object
#4 [-1:0]   f[*]
          @ /Users/olivier/code/ovld/resolve.py:26     #4: Lesser priority
Resolution: f[*] will be called first.
==================================================
#1 [1000:0] f[*]
          @ /Users/olivier/code/ovld/resolve.py:6
#2 [0:1]    f[str]
          @ /Users/olivier/code/ovld/resolve.py:22
#3 [-1:0]   f[*]
          @ /Users/olivier/code/ovld/resolve.py:26
Resolution: f[*] will be called first.
```

`display_resolution` will also show any ambiguous resolutions.

### display_methods

Use `f.display_methods()` to print out the complete list of registered methods.


## Tracebacks

`ovld` automagically renames functions so that the stack trace is more informative. For instance, running the `add` function defined earlier on bad inputs:

```python
add([[[1]]], [[[[2]]]])
```

Will produce the following traceback (Python 3.12):

```text
Traceback (most recent call last):
  File "/Users/olivier/code/ovld/add.py", line 24, in <module>
    add([[[1]]], [[[[2]]]])
  File "/Users/olivier/code/ovld/src/ovld/core.py", line 57, in first_entry
    return method(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "<ovld-1426249837422956194>", line 9, in add.dispatch
  File "/Users/olivier/code/ovld/add.py", line 6, in add[list, list]
    return [add(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^
  File "/Users/olivier/code/ovld/add.py", line 6, in add[list, list]
    return [add(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^
  File "/Users/olivier/code/ovld/add.py", line 6, in add[list, list]
    return [add(a, b) for a, b in zip(x, y)]
            ^^^^^^^^^
  File "/Users/olivier/code/ovld/add.py", line 21, in add[*, *]
    return x + y
           ~~^~~
TypeError: unsupported operand type(s) for +: 'int' and 'list'
```

* The functions on the stack have names like `add.dispatch`, `add[list, list]` and `add[*, *]` (`*` stands for `object`), which lets you better understand what happened just from the stack trace. It also helps distinguish various paths when profiling.
* When calling the function recursively, or with `recurse` or `call_next`, the dispatch logic is inlined, leading to a flatter and less noisy stack. (This inlining also reduces `ovld`'s overhead.)

!!!note
    * `add.dispatch` is an auto-generated function. It doesn't appear on tracebacks for some reason, but the code *is* in the linecache, so you can step into it with pdb.
    * `first_entry` is only called the very first time you call the `ovld` and performs some setup, then it replaces itself with `add.dispatch`.
