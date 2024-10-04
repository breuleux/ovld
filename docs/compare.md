
# Comparisons / Benchmarks

## Unique features

Current as of October 2024: I have investigated and benchmarked six other multiple/single dispatch libraries. Performance-wise, `ovld` is faster than all of them, ranging from 1.5x to 100x less overhead. Feature-wise, `ovld` is among the most featureful. Some features I could not find elsewhere:

* Support for [keyword arguments](usage.md#keyword-arguments).
* [Variants](usage.md#variants), especially working with recursion.
* [`call_next`](usage.md#special-function-call_next), to call down in the resolution order.
* Proper performance when using Literal/dependent types.
* Very easy definition of new types (it can also be done with `plum`).


## Other libraries

* [**plum**](https://github.com/beartype/plum): The most featureful alternative. Supports convert/promote functionality. Unfortunately, plum's code paths for Literal or Union appear to have massive overhead. `ovld` is *much* faster.
* [**multimethod**](https://github.com/coady/multimethod): Also pretty featureful. Performs a bit worse than plum in simple cases, but better in more complicated cases.
* [**multipledispatch**](https://github.com/mrocklin/multipledispatch/): Fair performance, interface is a bit dated, does not support dependent types.
* [**runtype**](https://github.com/erezsh/runtype): Fair performance. Runtype supports Literal in theory, but it unfortunately bugged out on the calc and fib benchmarks.
* [**fastcore**](https://github.com/fastai/fastcore): Somewhat limited (seems like it only dispatches on two arguments at most), and for a library with "fast" in its name, I must say it is impressively slow.
* [**singledispatch**](https://docs.python.org/3/library/functools.html#functools.singledispatch): Comes native in Python, but only supports dispatch on a single argument.


## Benchmarks

Applicable libraries were tested on the following problems:

* [trivial](https://github.com/breuleux/ovld/tree/master/benchmarks/test_trivial.py): Basic single dispatch test with a bunch of types.
* [multer](https://github.com/breuleux/ovld/tree/master/benchmarks/test_multer.py): Recursively multiply lists and dictionaries element-wise by a number, but using a class. This tests dispatch on methods.
* [add](https://github.com/breuleux/ovld/tree/master/benchmarks/test_add.py): Recursively add lists and dictionaries element-wise.
* [ast](https://github.com/breuleux/ovld/tree/master/benchmarks/test_ast.py): Simple transform on a Python AST.
* [calc](https://github.com/breuleux/ovld/tree/master/benchmarks/test_calc.py): Calculator implementation. Dispatches using `op: Literal[<opname>]`.
* [regexp](https://github.com/breuleux/ovld/tree/master/benchmarks/test_regexp.py): Dispatch based on a regular expression (`ovld.dependent.Regexp[<regex>]`).
* [fib](https://github.com/breuleux/ovld/tree/master/benchmarks/test_fib.py): Fibonacci numbers. The base cases are implemented by dispatching on `n: Literal[0]` and `n: Literal[1]`.
* [tweaknum](https://github.com/breuleux/ovld/tree/master/benchmarks/test_tweaknum.py): Dispatching on keyword arguments.


## Results

Time relative to the fastest implementation (1.00) (lower is better). Python version: 3.12.4

The **custom** column represents custom implementations using isinstance, match, a dispatch dict, etc. They are usually the fastest, but that should not be surprising. ovld's performance ranges from 1.5x faster to 3.3x slower.

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

## Comments

A big part of ovld's advantage comes from generating custom dispatch methods depending on the set of signatures that were registered. If you can avoid looping over `*args`, you're basically halving your overhead. Regarding dispatch on `Literal`, ovld also generates custom dispatch methods that unroll a series of specific if/else statements, which is the only way you'll ever get spitting distance from a normal implementation.

I haven't benchmarked the overhead of registering and compiling the methods, nor cache miss resolves, but I expect ovld will do pretty badly in that regard. That'll be the next big push, probably.
