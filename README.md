
# Ptera


## What is Ptera?

Ptera is a bit like a tracer, a bit like aspect-oriented programming, a bit like a new way to program. It chiefly aims to facilitate algorithm research, especially machine learning.

Within Ptera,

* **"Selfless objects"** are objects that are defined as functions. The fields of these objects are simply the variables used in the function.
* **Execution trace queries** lets you address any variable anywhere in functions decorated with `@ptera`, at arbitrary depths in the call tree, and either collect the values of these variables, or set these values.

Although they can be used independently, selfless objects and trace queries interact together in Ptera in order to form a new programming paradigm.

* Define parameterized functions with basically no boilerplate.
* Interfere with carefully selected parts of your program to test edge cases or variants.
* Plot the values of some variable deep in the execution of a program.

Ptera can also be combined with other libraries to make certain tasks very easy:

* Using Ptera with PyTorch, it is easy to get the gradient of any quantity with respect to any other quantity. These quantities can be *anywhere* in the program! They don't need to be in the same scope!


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
