
# Ptera

Ptera is a powerful way to instrument your code for logging, debugging and testing purposes. With a simple `ptera.Probe()`, you can:

* Obtain a stream of the values taken by any variable.
* Probe multiple variables from multiple functions in multiple scopes.
* Apply maps, filters, reductions, and much more to the streams.
* Override the values of variables based on complex conditions.
* Create external asserts or conditional breakpoints.
* Et cetera :)

The main interface to ptera are the `Probe` and `probing` functions. The only difference between them is that the first applies globally whereas the second is a context manager and applies only to the code inside a block:

```python
from ptera import Probe, probing

def f(x):
    y = x * x
    return y + 1

Probe("f > y").print()

f(9)  # prints {"y": 81}

with probing("f > y") as probe:
    probe.print("y = {y}")

    f(10)  # prints {"y": 100} and "y = 100"

f(11)  # prints {"y": 121}
```

`print()` is only one of a myriad operators. Ptera's interface is inspired from functional reactive programming and is identical to the interface of [giving](https://github.com/breuleux/giving) (itself based on `rx`). [See here for a more complete list of operators.](https://giving.readthedocs.io/en/latest/ref-operators.html)


Note: reduction operators such as `min` or `sum` are applied at program exit for `Probe` or at the end of the `with` block with `probing`, so it is usually best to use `probing` for these.


## Examples

Ptera is all about providing new ways to inspect what your programs are doing, so all examples will be based on this simple binary search function:

```python
from ptera import Probe, probing

def f(arr, key):
    lo = -1
    hi = len(arr)
    while lo < hi - 1:
        mid = lo + (hi - lo) // 2
        if (elem := arr[mid]) > key:
            hi = mid
        else:
            lo = mid
    return lo + 1

##############################
# THE PROBING CODE GOES HERE #
##############################

f(list(range(1, 350, 7)), 136)
```

To get the output listed in the right column of the table below, the code in the left column should be inserted before the call to `f`, where the big comment is. Most of the methods on `Probe` define the pipeline through which the probed values will be routed (the interface is inspired from functional reactive programming), so it is important to define them before the instrumented functions are called.

<table>
<tr>
<th>Code</th>
<th>Output</th>
</tr>

<!--
####################
####### ROW ########
####################
-->

<tr>
<td>

The `display` method provides a simple way to log values.

```python
Probe("f > mid").display()
```

</td>
<td>

```json
mid: 24
mid: 11
mid: 17
mid: 20
mid: 18
mid: 19
```

</td>
</tr>
<tr></tr>

<!--
####################
####### ROW ########
####################
-->

<tr>
<td>

The `print` method lets you specify a format string.

```python
Probe("f(mid) > elem").print("arr[{mid}] == {elem}")
```

</td>
<td>

```json
arr[24] == 169
arr[11] == 78
arr[17] == 120
arr[20] == 141
arr[18] == 127
arr[19] == 134
```

</td>
</tr>
<tr></tr>

<!--
####################
####### ROW ########
####################
-->

<tr>
<td>

Reductions are easy: extract the key and use `min`, `max`, etc.

```python
Probe("f > lo")["lo"].max().print("max(lo) = {}")
Probe("f > hi")["hi"].min().print("min(hi) = {}")
```

</td>
<td>

```json
max(lo) = 19
min(hi) = 20
```

</td>
</tr>
<tr></tr>

<!--
####################
####### ROW ########
####################
-->

<tr>
<td>

Define assertions with `fail()` (for debugging, also try `.breakpoint()`!)

```python
def unordered(xs):
    return any(x > y for x, y in zip(xs[:-1], xs[1:]))

probe = Probe("f > arr")["arr"]
probe.filter(unordered).fail("List is unordered: {}")

f([1, 6, 30, 7], 18)
```

</td>
<td>

```json
Traceback (most recent call last):
  ...
  File "test.py", line 30, in <module>
    f([1, 6, 30, 7], 18)
  File "<string>", line 3, in f__ptera_redirect
  File "test.py", line 3, in f
    def f(arr, key):
giving.gvn.Failure: List is unordered: [1, 6, 30, 7]
```

</td>
</tr>
<tr></tr>

<!--
####################
####### ROW ########
####################
-->

<tr>
<td>

Accumulate into a list:

```python
results = Probe("f > mid")["mid"].accum()
f(list(range(1, 350, 7)), 136)
print(results)
```

OR

```python
with probing("f > mid")["mid"].values() as results:
    f(list(range(1, 350, 7)), 136)

print(results)
```

</td>
<td>

```json
[24, 11, 17, 20, 18, 19]
```

</td>
</tr>
<tr></tr>

</table>


## probing

Usage: `with ptera.probing(selector) as probe: ...`

The **selector** is a specification of which variables in which functions we want to stream through the probe. One of the variables must be the **focus** of the selector, meaning that the probe is triggered when *that* variable is set. The focus may be indicated either as `f(!x)` or `f > x` (the focus is `x` in both cases).

The **probe** is a wrapper around [rx.Observable](https://github.com/ReactiveX/RxPY) and supports a large number of [operators](https://giving.readthedocs.io/en/latest/ref-operators.html) such as `map`, `filter`, `min`, `average`, `throttle`, etc. (the interface is the same as in [giving](https://github.com/breuleux/giving)).


### Example 1: intermediate variables

Ptera is capable of capturing any variable in a function, not just inputs and return values:

```python
def fact(n):
    curr = 1
    for i in range(n):
        curr = curr * (i + 1)
    return curr

with probing("fact(i, !curr)").print():
    fact(3)
    # {'curr': 1}
    # {'curr': 1, 'i': 0}
    # {'curr': 2, 'i': 1}
    # {'curr': 6, 'i': 2}
```

The "!" in the selector above means that the focus is `curr`. This means it is triggered when `curr` is set. This is why the first result does not have a value for `i`. You can use the selector `fact(!i, curr)` to focus on `i` instead:

```python
with probing("fact(!i, curr)").print():
    fact(3)
    # {'i': 0, 'curr': 1}
    # {'i': 1, 'curr': 1}
    # {'i': 2, 'curr': 2}
```

You can see that the associations are different (curr is 2 when i is 2, whereas it was 6 with the other selector), but this is simply because they are now triggered when `i` is set.

### Example 2: multiple scopes

A selector may act on several nested scopes in a call graph. For example, the selector `f(x) >> g(y) >> h > z` would capture variables `x`, `y` and `z` from the scopes of three different functions, but only when `f` calls `g` and `g` calls `h` (either directly or indirectly). (Note: `f(x) > g(y) > h > z` is also legal and is supposed to represent direct calls, but it may behave in confusing ways depending on which functions are instrumented globally, so avoid it for the time being).

```python
def f(x):
    return g(x + 1) * g(-x - 1)

def g(x):
    return x * 2

# Use "as" to rename a variable if there is a name conflict
with probing("f(x) >> g > x as gx").print():
    f(5)
    # {'gx': 6, 'x': 5}
    # {'gx': -6, 'x': 5}
    g(10)
    # Prints nothing
```

### Example 3: sibling calls

Selectors can also specify variables on different paths in the call graph. For example:

```python
def f(x):
    v = g(x + 1) * h(-x - 1)
    return v

def g(y):
    return y * 2

def h(z):
    return z * 3

with probing("f(x, g(y), h(!z))") as probe:
    probe.print()
    f(10)
    # {'z': -11, 'x': 10, 'y': 11}
```

Remember to set the focus with `!`. It should ideally be on the last variable to be set.

There is currently no error if you don't set a focus, it will simply do nothing, so beware of that for the time being.

### Example 4: tagging variables

Using annotations, variables can be given various tags, and probes can use these tags instead of variable names.

```python
def fishy(x):
    a: "@fish" = x + 1
    b: "@fish & @trout" = x + 2
    return a * b

with probing("fishy > $x:@trout").print():
    fishy(10)
    # {'x': 12}

with probing("fishy > $x:@fish").print():
    fishy(10)
    # {'x': 11}
    # {'x': 12}
```

The `$x` syntax means that we are not matching a variable called `x`, but instead matching any variable that has the right condition (in this case, the tags fish or trout) and offering it under the name `x`. You can pass `raw=True` to `probing` to get `Capture` objects instead of values. The `Capture` object gives access to the variable's actual name. For example:

```python
with probing("fishy > $x:@fish", raw=True) as probe:
    probe["x"].map(lambda x: {x.name: x.value}).print()
    fishy(10)
    # {'a': 11}
    # {'b': 12}
```


### Example 5: overriding variables

It is also possible to override the value of a variable with the `override` (or `koverride`) methods:


```python
def add_ct(x):
    ct = 1
    return x + ct

with probing("add_ct(x) > ct") as probe:
    # The value of other variables can be used to compute the new value of ct
    probe.override(lambda data: data["x"])

    # You can also use koverride, which calls func(**data)
    # probe.koverride(lambda x: x)

    print(add_ct(3))   # sets ct = x = 3; prints 6
    print(add_ct(10))  # sets ct = x = 20; prints 20
```

**Important:** override() only overrides the **focus variable**. As explained earlier, the focus variable is the one to the right of `>`, or the one prefixed with `!`. A Ptera selector is only triggered when the focus variable is set, so realistically it is the only one that it makes sense to override.

This is worth keeping in mind, because otherwise it's not always obvious what override is doing. For example:

```python
with probing("add_ct(x) > ct") as probe:
    # The focus is ct, so override will always set ct
    # Therefore, this sets ct = 10 when x == 3:
    probe.where(x=3).override(10)

    print(add_ct(3))   # sets ct = 10; prints 13
    print(add_ct(10))  # does not override anything; prints 11
```


## Probe

`Probe` works more or less the same way as `probing`, but it is not a context manager: it just works globally from the moment of its creation. This means that streams created with `Probe` only end when the program ends, so operators that wait for the full stream before triggering, such as `min()`, will run at program exit, which limits their usefulness.

```python
Probe("fact() as result").print()
fact(2)
# {'result': 1}
# {'result': 2}
fact(3)
# {'result': 1}
# {'result': 2}
# {'result': 6}
```

## Absolute probes

Here is a notation to probe a function using an "absolute path" in the module system:

```python
Probe("/xyz.submodule/Klass/method > x")

# is essentially equivalent to:

from xyz.submodule import Klass
Probe("Klass.method > x")
```

The slashes represent a physical nesting rather than object attributes. For example, `/module.submodule/x/y` means:

* Go in the file that defines `module.submodule`
* Enter `def x` or `class x` (it will *not* work if `x` is imported from elsewhere)
* Within that definition, enter `def y` or `class y`

Note:

* Unlike the normal notation, the absolute notation bypasses decorators: `/module/function` will probe the function inside the `def function(): ...` in `module.py`, so it will work even if the function was wrapped by a decorator (unless the decorator does not actually call the function).
* Although the `/module/function/closure` notation can theoretically point to closures, **this does not work yet.** (It will, eventually.)
* Use `/module.submodule/func`, *not* `/module/submodule/func`. The former roughly corresponds to `from module.submodule import func` and the latter to `from module import submodule; func = submodule.func`, which can be different in Python. It's a bit odd, but it works that way to properly address Python quirks.


## Operators

All the [operators](https://giving.readthedocs.io/en/latest/ref-operators.html) defined in the `rx` and `giving` packages should be compatible with `Probe` and `probing`. You can also define [custom operators](https://rxpy.readthedocs.io/en/latest/get_started.html#custom-operator).

[Read this operator guide](https://giving.readthedocs.io/en/latest/guide.html#important-methods) for the most useful features (the `gv` variable in the examples has the same interface as probes).


## Query language

**Note:** this section contains some references to a different interface to `ptera` which is still valid, but not documented.

Here is some code annotated with queries that will match various variables. The queries are not exhaustive, just examples.

* The semicolon ";" is used to separate queries and it is not part of any query.
* The hash character "#" *is* part of the query if there is no space after it, otherwise it starts a comment.

```python
from ptera import ptera, tag

Animal = tag.Animal
Thing = tag.Thing

@tooled
def art(a, b):               # art > a ; art > b ; art(!a, b) ; art(a, !b)

    a1: Animal = bee(a)      # a1 ; art > a1 ; art(!a1) ; art > $x
                             # a1:Animal ; $x:Animal
                             # art(!a1) > bee > d  # Focus on a1, also includes d
                             # art > bee  # This refers to the bee function
                             # * > a1 ; *(!a1)

    a2: Thing = cap(b)       # a2 ; art > a2 ; art(!a2) ; art > $x
                             # a2:Thing ; $x:Thing

    return a1 + a2           # art > #value ; art(#value as art_result)
                             # art() as art_result
                             # art > $x


@tooled
def bee(c):
    c1 = c + 1               # bee > c1 ; art >> c1 ; art(a2) > bee > c1
                             # bee > c1 as xyz

    return c1                # bee > #value ; bee(c) as bee_value


@tooled
def cap(d: Thing & int):     # cap > d ; $x:Thing ; cap > $x
                             # art(bee(c)) > cap > d
    return d * d
```

* The `!` operator marks the **focus** of the query. There will be one result for each time the focus is triggered, and when using `tweak` or `rewrite` the focus is what is being tweaked or rewritten.
  * Other variables are supplemental information, available along with the focus in query results. They can also be used to compute a value for the focus *if* they are available by the time the focus is reached.
  * The nesting operators `>` and `>>` automatically set the focus to the right hand side if the rhs is a single variable and the operator is not inside `(...)`.
* The wildcard `*` stands in for any function.
* The `>>` operator represents **deep nesting**. For example, `art >> c1` encompasses the pattern `art > bee > c1`.
  * In general, `a >> z` encompasses `a > z`, `a > b > z`, `a > b > c > z`, `a > * > z`, and so on.
* A function's return value corresponds to a special variable named `#value`.
* `$x` will match any variable name. Getting the variable name for the capture is possible but requires the `map_full` method. For example:
  * Query: `art > $x`
  * Getting the names: `results.map_full(lambda x: x.name) == ["a1", "a2", "#value"]`
  * Other fields accessible from `map_full` are `value`, `names` and `values`, the latter two being needed if multiple results are captured together.
* Variable annotations are preserved and can be filtered on, using the `:` operator. However, *Ptera only recognizes tags* created using `ptera.Tag("XYZ")` or `ptera.tag.XYZ`. It will not filter over types.
* `art(bee(c)) > cap > d` triggers on the variable `d` in calls to `cap`, but it will *also* include the value of `c` for all calls to `bee` inside `art`.
  * If there are multiple calls to `bee`, all values of `c` will be pooled together, and it will be necessary to use `map_all` to retrieve the values (or `map_full`).
