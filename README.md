
# Ptera

**Note**: This is super alpha. A lot of the features are implemented very inefficiently and the error reporting is not very good. That will be fixed in due time, and then this note will disappear into the mists of git history.


## What is Ptera?

Ptera is a way to probe arbitrary variables in arbitrary functions in your program, for instance to plot their values over time, to get the maximum or minimum value during execution.

* **Keep your program clean**: Queries can be defined outside of your main function, so there is no need to pollute your code with logging or debug code.
* **Debug and analyze across scopes**: Easily write queries that collect variables at various points in the call stack, or even across different calls. Then, you can analyze them all together.
* **Tag variables and functions**: Categorize parts of your program to make more general queries.

```python
from ptera import probing, op

def fact(n):
    if n <= 1:
        return n
    else:
        return n * fact(n - 1)

with probing("fact(n) as v") as probe:
    probe.pipe(op.format("fact({n}) = {v}")).subscribe(print)
    fact(3)
    # prints fact(1) = 1; fact(2) = 2; fact(3) = 6
```


## probing

Usage: `with ptera.probing(selector) as probe: ...`

The **selector** is a specification of which variables in which functions we want to stream through the probe. One of the variables must be the *focus* of the selector, meaning that the probe is triggered when *that* variable is set. The focus may be indicated either as `f(!x)` or `f > x`.

The **probe** is an instance of [rx.Observable](https://github.com/ReactiveX/RxPY). All of the `rx` [operators](https://rxpy.readthedocs.io/en/latest/reference_operators.html) should therefore work with ptera's probes (map, reduce, min, max, debounce, etc.)


### Example 1: intermediate variables

Ptera is capable of capturing any variable in a function, not just inputs and return values:

```python
def fact2(n):
    curr = 1
    for i in range(n):
        curr = curr * (i + 1)
    return curr

with probing("fact2(i, !curr)") as probe:
    probe.subscribe(print)
    fact2(3)
    # {'curr': 1}
    # {'curr': 1, 'i': 0}
    # {'curr': 2, 'i': 1}
    # {'curr': 6, 'i': 2}
```

The "!" in the selector above means that the focus is `curr`. This means it is triggered when `curr` is set. This is why the first result does not have a value for `i`. You can use the selector `fact2(!i, curr)` to focus on `i` instead:

```python
with probing("fact2(!i, curr)") as probe:
    probe.subscribe(print)
    fact2(3)
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
with probing("f(x) >> g > x as gx") as probe:
    probe.subscribe(print)
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
    probe.subscribe(print)
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

with probing("fishy > $x:@trout") as probe:
    probe.subscribe(print)
    fishy(10)
    # {'x': 12}

with probing("fishy > $x:@fish") as probe:
    probe.subscribe(print)
    fishy(10)
    # {'x': 11}
    # {'x': 12}
```


## Probe

`Probe` works more or less the same way as `probing`, but it is not a context manager: it just works globally from the moment of its creation. This means that streams created with `Probe` never actually end, so operators that wait for the full stream before triggering, such as `ptera.op.min`, will not work.

```python
Probe("fact() as result").subscribe(print)
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

# is mostly equivalent to:

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

All the existing [operators](https://rxpy.readthedocs.io/en/latest/reference_operators.html) defined in the `rx` package should be compatible with `Probe` and `probing`. They may be imported as `ptera.operators` or `ptera.op` *In addition to this*, `ptera.operators` defines the following operators:

### Utility

* **`format(string)`**: format each item of the stream (like str.format)
* **`getitem(name)`**: extract an item from a stream of dicts
* **`keymap(fn)`**: calls a function using kwargs from a stream of dicts
* **`throttle(duration)`**: alias for `rx.operators.throttle_first`

### Arithmetic

* **`roll(n, reduce=None, key_mapper=None, seed=None)`**: transform a stream into rolling windows of size at most n. Successive windows overlap completely except for the first and last elements.
  * If reduce is provided, it is called with arguments `(last, add, drop, last_size, current_size)`
  * If transform is provided, it is called on each element
* **`rolling_average(n, key_mapper=None)`**: efficient implementation of a rolling average (mean of the last n elements)
* **`rolling_average_and_variance(n, key_mapper=None)`**: efficient implementation of a rolling average and (sample) variance of the last n elements, returned as a tuple.


## Query language

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
