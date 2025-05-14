
# Comparisons / Benchmarks

## Unique features

Current as of May 2025: I have investigated and benchmarked five other multiple/single dispatch libraries. Performance-wise, `ovld` is faster than all of them, ranging from 1.5x to 100x less overhead. Feature-wise, `ovld` is among the most featureful. Some features I could not find elsewhere:

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

Time relative to the fastest implementation (1.00) (lower is better). Python version: 3.13.0

The **custom** column represents custom implementations using isinstance, match, a dispatch dict, etc. They are usually the fastest, but that should not be surprising. ovld's performance ranges from 1.5x faster to 3.3x slower.

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


## Comments

A big part of ovld's advantage comes from generating custom dispatch methods depending on the set of signatures that were registered. If you can avoid looping over `*args`, you're basically halving your overhead. Regarding dispatch on `Literal`, ovld also generates custom dispatch methods that unroll a series of specific if/else statements, which is the only way you'll ever get spitting distance from a normal implementation.

I haven't benchmarked the overhead of registering and compiling the methods, nor cache miss resolves, but I expect ovld will do pretty badly in that regard. That'll be the next big push, probably.
