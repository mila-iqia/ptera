
# Ptera

**Note**: This is super alpha. A lot of the features are implemented very inefficiently and the error reporting is not very good. That will be fixed in due time, and then this note will disappear into the mists of git history.


## What is Ptera?

Ptera is a bit like a tracer, a bit like aspect-oriented programming, a bit like a new way to program. It chiefly aims to facilitate algorithm research, especially machine learning.

**Features!**

* **"Selfless objects"** are objects that are defined as functions. The fields of these objects are simply the variables used in the function.
* **Execution trace queries** lets you address any variable anywhere in functions decorated with `@ptera`, at arbitrary depths in the call tree, and either collect the values of these variables, or set these values.
* **Automatic CLI** will create a command-line interface from any properly annotated variable anywhere in the code.

Although they can be used independently, selfless objects and trace queries interact together in Ptera in order to form a new programming paradigm.

* Define parameterized functions with basically no boilerplate.
* Interfere with carefully selected parts of your program to test edge cases or variants.
* Plot the values of some variable deep in the execution of a program.

Ptera can also be combined with other libraries to make certain tasks very easy:

* [Using Ptera with PyTorch](https://github.com/mila-iqia/ptera/blob/master/ML-README.md), it is easy to get the gradient of any quantity with respect to any other quantity. These quantities can be *anywhere* in the program! They don't need to be in the same scope!


## Selfless objects

A selfless object is defined as a simple function. Any function can be a selfless object, but of particular interest are those that contain uninitialized variables. For example:

```python
@ptera.defaults(debug=False)
def bagel(x, y):
    z: int
    if debug:
        print(x, y, z)
    return x + y + z
```

Note that in this function, `z` is declared, but not initialized. We can instantiate a function with `new`:

```python
bagel3 = bagel.new(z=3)
assert bagel3(1, 2) == 6
```

But this is not all we can do. We can also set the `debug` variable to True:

```python
bagel3_debug = bagel.new(z=3, debug=True)
assert bagel3(1, 2) == 6   # This prints "1 2 3"
```

And that's not all! We can set *any* variable, if we so wish. We can set `print`:

```python
bagel3_newprint = bagel.new(
    z=3, debug=True, print=lambda *args: print(sum(args))
)
assert bagel3(1, 2) == 6   # This prints "6"
```

We can set default arguments:

```python
bagel3_defaults = bagel.new(z=3, y=2)
assert bagel3(1) == 6
```

We can *force* an argument to have a certain value:

```python
bagel3_forcex = bagel.new(z=3, x=ptera.Override(5))
assert bagel3(1, 2) == 10
```


## Trace queries

Trace queries provide the same power, but over a whole call tree. They also allow you to extract any variables you want.

Suppose you have this program:

```python
@ptera
def square(x):
    rval = x * x
    return rval

@ptera
def sumsquares(x, y):
    xx = square(x)
    yy = square(y)
    rval = xx + yy
    return rval
```

What can you do?


**Q**: What values can `x` take?

**A**: The `using` method lets you extract these values. We give our query the name `q` in what follows so that we can access it, but you can give any name you want to the query:

```python
results = sumsquares.using(q="x")(3, 4)
assert results.q.map("x") == [3, 4, 3]
```


**Q**: Hold on, why is `3` listed twice?

**A**: Because `x == 3` in the call to `sumsquares`, and `x == 3` in the first  call to `square`. These are two distinct `x`.


**Q**: What if I just want the value of `x` in `square`?

**A**: The expression `square > x` represents the value of the variable `x` inside a call to `square`.

```python
results = sumsquares.using(q="square > x")(3, 4)
assert results.q.map("x") == [3, 4]
```


**Q**: Can I also see the output of `square`?

**A**: Yes. Variables inside `{}` will also be captured.

```python
results = sumsquares.using(q="square{rval} > x")(3, 4)
assert results.q.map("x", "rval") == [(3, 9), (4, 16)]
```


**Q**: Can I also see the inputs of `sumsquare` along with these?

**A**: Yes, but there is a name conflict, so you need to rename them, which you can do in the query, like this:

```python
results = sumsquares.using(
    q="sumsquares{x as ssx, y as ssy} > square{rval} > x"
)(3, 4)
assert results.q.map("ssx", "ssy", "x", "rval") == [(3, 4, 3, 9), (3, 4, 4, 16)]
```


**Q**: I would like to have one entry for each call to `sumsquares`, not one entry for each call to `square`.

**A**: Each query has one variable which is the *focus*. There will be one result for each value the focus takes. You can set the focus with the `!` operator. So here's something you can do:

```python
results = sumsquares.using(
    q="sumsquares{!x as ssx, y as ssy} > square{rval, x}"
)(3, 4)
assert (results.q.map_all("ssx", "ssy", "x", "rval")
        == [([3], [4], [3, 4], [9, 16])])
```

Notice that you need to call `map_all` here, because some variables have multiple values with respect to the focus: we focus on the `x` argument to `sumsquares`, which calls `square` twice, so for each `sumsquares{x}` we get two `square{x, rval}`. The `map` method assumes there is only one value for each variable, so it will raise an exception.

Note that this view on the data does not necessarily preserve the correspondance between `square{x}` and `square{rval}`: you can't assume that the first `x` is in the same scope as the first `rval`, and so on.

Also notice that the expression does not end with `> x`. That's because `square > x` is the same as `square{!x}`: it sets the focus on `x`. However, we can only have one focus, therefore if we ended the query with `> x` it would be invalid.


**Q**: I want to do something crazy. I want `square` to always return 0.

**A**: Uhh... okay? Are you sure? You can use the `tweak` method to do this:

```python
result = sumsquares.tweak({"square > rval": 0})(3, 4)
assert result == 0
```

This will apply to all calls to `square` within the execution of `sumsquares`. And yes, `sumsquares.new(square=lambda x: 0)` would also work in this case, but there is a difference: using the `tweak` method will apply to all calls at all call depths, recursively. The `new` method will only change `square` directly in the body of `sumsquares`.


**Q**: I want to do something else crazy. I want `square` to return x + 1.

**A**: Use the `rewrite` method.

```python
result = sumsquares.rewrite({"square{x} > rval": lambda x: x + 1})(3, 4)
assert result == 9
```

## Automatic CLI

Ptera can automatically create a command-line interface from variables annotated with a certain category. The main advantage of `ptera.auto_cli` relative to other solutions is that the arguments are declared wherever you actually use them. Consider the following program, for example:

```python
def main():
    for i in range(1000):
        do_something()

if __name__ == "__main__":
    main()
```

It would be nice to be able to configure the number of iterations instead of using the hard-coded number 1000. Enter `ptera.auto_cli`:

```python
from ptera import auto_cli, cat, default, ptera

@ptera
def main():
    # Number of iterations
    n: cat.CliArgument = default(1000)
    for i in range(n):
        do_something()

if __name__ == "__main__":
    auto_cli(main, category=cat.CliArgument)
```

Then you can run it like this, for example:

```bash
$ python script.py --n 15
```

* Ptera will look for any variable annotated with the specified category within `@ptera` functions that are accessible from `main`.
  * There is no need to pass an options object around. If you need to add an argument to any function in any file, you can just plop it in there and ptera should find it and allow you to set it on the command line.
  * You can declare multiple CLI arguments in multiple places with the same name. They will all be set to the same value.
* The comment right above the declaration of the variable, if there is one, is used as documentation.
* The `default` function provides a default value for the argument.
  * You don't have to provide one.
  * Ptera uses a priority system to determine which value to choose and `default` sets a low priority. If you set a value but don't wrap it with `default`, you will get a `ConflictError` when trying to set the variable on the command line. This is the intended behavior.

In the future, `auto_cli` will also support environment variables, configuration files, and extra options to catalogue all the variables that can be queried. For example, a planned feature is to be able to display where in the code each variable with a given category is declared and used.

Another future feature: since it is within ptera's ability to set different values for the parameter `param` depending on the call context (e.g. with the `tweak` method), the ability to do this in a configuration file will be added at some point (just need to figure out the format).


## Query language

Here is some code annotated with queries that will match various variables. The queries are not exhaustive, just examples.

* The semicolon ";" is used to separate queries and it is not part of any query.
* The hash character "#" *is* part of the query if there is no space after it, otherwise it starts a comment.

```python
from ptera import cat, ptera


@ptera
def art(a, b):               # art > a ; art > b ; art{!a, b} ; art{a, !b}

    a1: cat.Animal = bee(a)  # a1 ; art > a1 ; art{!a1} ; art > $x
                             # a1:Animal ; $x:Animal
                             # art{!a1} > bee > d  # Focus on a1, also includes d
                             # art > bee  # This refers to the bee function
                             # * > a1 ; *{!a1}

    a2: cat.Thing = cap(b)   # a2 ; art > a2 ; art{!a2} ; art > $x
                             # a2:Thing ; $x:Thing

    return a1 + a2           # art > #value ; art{#value as art_result}
                             # art{} as art_result
                             # art > $x


@ptera
def bee(c):
    c1 = c + 1               # bee > c1 ; art >> c1 ; art{a2} > bee > c1
                             # bee > c1 as xyz

    return c1                # bee > #value ; bee{c} as bee_value


@ptera
def cap(d: cat.Thing & int): # cap > d ; $x:Thing ; $x:int ; cap > $x
                             # art{bee{c}} > cap > d
    return d * d
```

* The `!` operator marks the **focus** of the query. There will be one result for each time the focus is triggered, and when using `tweak` or `rewrite` the focus is what is being tweaked or rewritten.
  * Other variables are supplemental information, available along with the focus in query results. They can also be used to compute a value for the focus *if* they are available by the time the focus is reached.
  * The nesting operators `>` and `>>` automatically set the focus to the right hand side if the rhs is a single variable and the operator is not inside `{...}`.
* The wildcard `*` stands in for any function.
* The `>>` operator represents **deep nesting**. For example, `art >> c1` encompasses the pattern `art > bee > c1`.
  * In general, `a >> z` encompasses `a > z`, `a > b > z`, `a > b > c > z`, `a > * > z`, and so on.
* A function's return value corresponds to a special variable named `#value`.
* `$x` will match any variable name. Getting the variable name for the capture is possible but requires the `map_full` method. For example:
  * Query: `art > $x`
  * Getting the names: `results.map_full(lambda x: x.name) == ["a1", "a2", "#value"]`
  * Other fields accessible from `map_full` are `value`, `names` and `values`, the latter two being needed if multiple results are captured together.
* Variable annotations are preserved and can be filtered on, using the `:` operator. They may be types or "categories" (created using `ptera.Category("XYZ")` or `ptera.cat.XYZ`).
* `art{bee{c}} > cap > d` triggers on the variable `d` in calls to `cap`, but it will *also* include the value of `c` for all calls to `bee` inside `art`.
  * If there are multiple calls to `bee`, all values of `c` will be pooled together, and it will be necessary to use `map_all` to retrieve the values (or `map_full`).


### Equivalencies

Ptera's query language syntax includes a lot of expressions, but it reduces to a relatively simple core:


```
# A lone symbol becomes a match for a variable in a wildcard function
a               <=>  *{!a}

# Nesting operator > is sugar for {...}
a > b           <=>  a{!b}
a > b > c       <=>  a{b{!c}}

# Infix >> is sugar for prefix >>
a >> b > c      <=>  a{>> b{!c}}
a >> b          <=>  a{>> !b}   <~>  a{>> *{!b}}  (see note)

# $x is shorthand for as
f{$x}           <=>  f{* as x}

# Indexing is sugar for #key
a[0]            <=>  a{#key=0}
a[0] as a0      <=>  a{#key=0, #value as a0}
a[$i] as a      <=>  a{#key as i, #value as a}

# Shorthand for #value
a{x, y} as b    <=>  a{x, y, #value as b}
a{} as b        <=>  a{#value as b}
```

Note: `a{>> b}` and `a{>> *{!b}}` are not 100% equivalent, because the former encompasses `a{> b}` and the latter does not, but internally the former is basically encoded as the latter plus a special "collapse" flag that there is no syntax for.
