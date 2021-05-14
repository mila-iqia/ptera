
# Ptera

**Note**: This is super alpha. A lot of the features are implemented very inefficiently and the error reporting is not very good. That will be fixed in due time, and then this note will disappear into the mists of git history.


## What is Ptera?

Ptera is a set of powerful tools to query or tweak the values of variables from a program.

* **Keep your program clean**: Queries can be defined outside of your main function, so there is no need to pollute your code with logging or debug code.
* **Debug and analyze across scopes**: Easily write queries that collect variables at various points in the call stack, or even across different calls. Then, you can analyze them all together.
* **Tag variables and functions**: Categorize parts of your program to make more general queries.


## Example 1

Take the following function, which estimates whether a point `c` in the complex pane belongs to the Mandelbrot set or not (repeat this for a range of real/imag values to draw a pretty monochrome fractal).

```python
from ptera import tooled

MAX_ITER = 100

@tooled
def mandelbrot(real, imag):
    c = real + imag * 1j
    z = 0
    for i in range(MAX_ITER):
        z = z * z + c
        if abs(z) > 2:
            return False
    return True
```

Ptera allows you, among other things, to look at the values taken by the variable `z` through the course of the function. This can be very interesting!

```python
mandelbrot_zs = mandelbrot.using(zs="mandelbrot > z")

print(mandelbrot_zs(0.25, 0).zs.map("z"))
# -> Converges to 0.5

print(mandelbrot_zs(-1, 0).zs.map("z"))
# -> Oscillates between 0 and -1

print(mandelbrot_zs(-0.125, 0.75).zs.map("z"))
# -> 3-way oscillation between 0.01-0.006j, -0.125+0.75j and -0.67+0.56j
```

(Depending on which bulb of the fractal you are looking at, the iteration will converge on a cycle with a finite period, which can be arbitrarily large, which you can sort of visualize [like this](https://en.wikipedia.org/wiki/Mandelbrot_set#/media/File:Logistic_Map_Bifurcations_Underneath_Mandelbrot_Set.gif). But enough about that.)

All the values are collected together and can be mapped in any way you'd like. You can also capture multiple variables together, for instance:

```python
mandelbrot_zis = mandelbrot.using(zis="mandelbrot(i) > z")

print(mandelbrot_zis(0.25, 0).zis.map(lambda z, i=None: (i, z)))
# [(None, 0), (0, 0.25), (1, 0.3125), ..., (999, 0.499)]
```

**Tweaking variables**

You can also "tweak" variables. For example, you can change the value of `MAX_ITER` within the call:

```python
mandelbrot_short = mandelbrot.tweaking({"MAX_ITER": 10})
mandelbrot_long = mandelbrot.tweaking({"MAX_ITER": 1000})

print(mandelbrot_short(0.2501, 0))  # True
print(mandelbrot_long(0.2501, 0))   # False
```

As you can see, both versions of the function use their own version of `MAX_ITER`, without interference.

Note however that Ptera will add significant overhead to a function like `mandelbrot` because all of its operations are cheap compared to the cost of tracking everything with Ptera. Only the body of functions decorated with `@tooled` will be slower, however, and if the bulk of the time of the program is spent in non-decorated functions, the overhead should be acceptable.


## Example 2

Suppose you have a simple PyTorch model with a few layers and a `tanh` activation function:

```python
class MLP(torch.nn.Module):
    def __init__(self):
        super(MLP, self).__init__()
        self.linear1 = torch.nn.Linear(784, 250)
        self.linear2 = torch.nn.Linear(250, 100)
        self.linear3 = torch.nn.Linear(100, 10)

    def forward(self, inputs):
        h1 = torch.tanh(self.linear1(inputs))
        h2 = torch.tanh(self.linear2(h1))
        h3 = self.linear3(h2)
        return torch.log_softmax(h3, dim=1)

def step(model, optimizer, inputs, targets):
    optimizer.zero_grad()
    output = model(Variable(inputs).float())
    loss = torch.nn.CrossEntropyLoss()(output, Variable(targets))
    loss.backward()
    optimizer.step()

def fit(model, data, epochs):
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    for epoch in range(epochs):
        for batch_idx, (inputs, targets) in enumerate(data):
            step(model, optimizer, inputs, targets)

if __name__ == "__main__":
    ...
    fit(model, data, epochs)
```

You want to know whether the activations on the layer `h2` tend to saturate, meaning that they are very close to -1 or 1. Therefore, you would like to log the percentage of the values in the `h2` matrix that have an absolute value greater than 0.99. You would only like to check every 100 iterations or so, though.

Here is how to do this with ptera. Comments indicate all the changes you need to make:

```python
from ptera import tooled, Overlay
from ptera.tools import every

class MLP(torch.nn.Module):
    def __init__(self):
        super(MLP, self).__init__()
        self.linear1 = torch.nn.Linear(784, 250)
        self.linear2 = torch.nn.Linear(250, 100)
        self.linear3 = torch.nn.Linear(100, 10)

    # Decorate this function
    @tooled
    def forward(self, inputs):
        h1 = torch.tanh(self.linear1(inputs))
        h2 = torch.tanh(self.linear2(h1))
        h3 = self.linear3(h2)
        return torch.log_softmax(h3, dim=1)

# Decorate this function too
@tooled
def step(model, optimizer, inputs, targets):
    optimizer.zero_grad()
    output = model(Variable(inputs).float())
    loss = torch.nn.CrossEntropyLoss()(output, Variable(targets))
    loss.backward()
    optimizer.step()

def fit(model, data, epochs):
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    for epoch in range(epochs):
        for batch_idx, (inputs, targets) in enumerate(data):
            step(model, optimizer, inputs, targets)

if __name__ == "__main__":
    ...

    # Create an overlay
    overlay = Overlay()

    # Set up a listener for the variable of MLP.forward named h2, but only
    # within a call to step where the batch_idx variable is a multiple of 100.
    # * The notation `x ~ f` means that we only trigger when f(x) == True.
    # * The >> operator means arbitrary nesting.
    # * The > operator means direct nesting
    @overlay.on("step(batch_idx ~ every(100)) >> MLP.forward > h2")
    def check_saturation(batch_idx, h2):
        sat = float((h2.abs() > 0.99).float().mean())
        print(sat)
        return sat

    # Call fit within a with block
    with overlay as results:
        fit(model, data, epochs)

    # results.check_saturation contains a list of all the return values of the
    # listener
    print(results.check_saturation)
```

The interface is a bit different from the Mandelbrot example, because in this example the function we are calling, `fit`, is not decorated with `@tooled`. This is fine, however, because the overlay (which also has methods like `use`, `tweak`, etc.) will apply to everything that's going on inside the `with` block, and the data accumulated by the various listeners and plugins will be put in the `results` data structure.


## Overlays

An *overlay* is a collection of plugins that operate over the variables of ptera-decorated functions. It is used roughly like this:

```python
overlay = Overlay()

# Use plugins. A plugin can be a simple query string, which by default
# creates a Tap plugin.
overlay.use(p1=plugin1, p2=plugin2, ...)

# Call a function every time the query is triggered
@overlay.on(query)
def p3(var1, var2, ...):
    do_something(var1, var2, ...)

# Change the value of a variable
overlay.tweak({query: value, ...})

# Change the value of a variable, but using a function which can depend on
# other collected variables.
overlay.rewrite({query: rewriter, ...})

# Call the function while the overlay is active
with overlay as results:
    func()

# Do something with the results
do_something(results.p1)  # Set by plugin1
do_something(results.p2)  # Set by plugin2
do_something(results.p3)  # List of the return values of on(...)
...

# The "Tap" plugin, which is the default when giving a query string to use,
# puts a Collector instance in its field in results. The main method you will
# use is map:
results.p1.map()                    # List of dictionaries with all captures
results.p1.map("x")                 # List for variable "x"
results.p1.map("x", "y")            # List of tuples of values for x and y
results.p1.map(lambda x, y: x + y)  # Call the function on captured variables

# map_all:
# Each capture is a list of values. For example, the query `f(!x) > g(y)` will
# trigger for every value of "x" because of the "!", but if g is called
# multiple times, Ptera may list all of the values for "y". If that is the case,
# `map` will error out and you must use `map_all`.
results.p1.map_all()

# map_full:
# Each capture is a Capture object. This can be useful with a query
# such as `$v:SomeTag` which captures any variable annotated with SomeTag, but
# regardless of the variable's actual name. The value will be provided under
# the name "v", but the actual name will be in the capture.name field.
# results.p1.map("x") <=> results.p1.map_full(lambda x: x.value)
# results.p1.map_all("x") <=> results.p1.map_full(lambda x: x.values)
results.p1.map_full()
```


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
def cap(d: Thing & int):     # cap > d ; $x:Thing ; $x:int ; cap > $x
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
