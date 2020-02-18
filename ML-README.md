
# Ptera and machine learning

* **Debugging**: Grab the value of some variable deep into your model and plot it or properties of it such as its mean absolute value.

* **Configure**: Add and configure new parameters with a minimum of code. Any function is, or can become a configurable object.

* **Cross-function features**: You want to grab all activations in your model and regularize over some function of them? You can easily do that.

* **Inspect gradients**: Take the gradient of anything with respect to anything else. The variables don't even need to be in the same scope.


# Using Ptera with PyTorch

This is very early and very experimental (like all of Ptera at the moment), but it works well enough to play with. Here is how to define a simple MLP and train it with SGD:

```python
import torch

from ptera import Recurrence
from ptera.torch import (
    ActivationFunction, BiasVector, Grad, Learnable, WeightMatrix
)


@ptera
def layer(inp):
    W: WeightMatrix
    b: BiasVector
    actfn: ActivationFunction

    act = inp @ W + b
    return actfn(act)


@ptera
def sequential(inp):
    layers: list

    h = Recurrence()
    h[0] = inp
    for i, layer in enumerate(layers):
        h[i + 1] = layer(h[i])
    return h[len(layers)]


@ptera
def step(inp, target):
    model: object
    lossfn: object

    output = model(inp)
    loss = lossfn(output, target)
    return loss


def make_network(*layer_sizes):
    layers = [
        layer.new(
            W=torch.nn.Parameter(
                (torch.rand(nin, nout) * 2 - 1) / (nin ** 0.5)
            ),
            b=torch.nn.Parameter(
                (torch.rand(1, nout) * 2 - 1) / (nin ** 0.5)
            ),
            actfn=torch.relu
        )
        for nin, nout in zip(layer_sizes[:-1], layer_sizes[1:])
    ]
    layers[-1].state.actfn = torch.nn.LogSoftmax(dim=1)
    network = step.new(
        lossfn=torch.nn.NLLLoss(),
        model=sequential.new(layers=layers)
    )
    return network


def train(dataset):

    model = make_network(784, 1000, 10).clone(return_object=True)

    @model.on(Grad("step{!!loss} >> layer > $param:Learnable"))
    def update(param):
        param_value, param_grad = param
        param_value.data.add_(-0.01 * param_grad)

    for inputs, targets in dataset:
        results = model(inputs, targets)
        print(f"Loss: {results.value:.5f}")
```

The one new thing in this example that hasn't been covered yet is the `Grad` plugin, which we use to implement the `update` function. `Grad` takes a query describing the gradients we want to calculate. In that query, we want to take the derivative of the secondary focus (tagged with `!!`) with respect to the primary focus (tagged with `!`, or implicitly defined on the right hand side of `>`).

Essentially, if `y = f(x)` and we wish to compute `dy/dx`, we can express this as `Grad("f{!x, !!y}")`. The primary and secondary focus do not need to be in the same scope (in the MLP example provided above, they are not in the same scope).


## Looking at intermediate gradients

Let's say you want to know what the gradient is with respect to the first layer. You can do it like this:


```python
...
@model.on(Grad("step{!!loss} >> h[1] as h"))
def check_h(h):
    h_value, h_grad = h
    # You can print it
    print(h_grad)
    # You can also return some arbitrary data
    return h_grad.abs().mean()
...
results = model(inputs, targets)
# This is a list of all the values returned by check_h
print(results.check_h)
```

## Adding regularization terms

Let's say you want to penalize the magnitude of the weights in your model. Even within a ptera function, you can write a query to get all weights from the model, and then simply sum them all up and add that to the loss. Try rewriting the step function as follows:

```python
@ptera
def step(inp, target):
    model: object
    lossfn: object

    output = model.using(weights="$param:WeightMatrix")(inp)
    reg = sum(output.weights.map(lambda param: param.abs().mean()))
    loss = lossfn(output.value, target) + reg
    return loss
```

Of course, this is not limited to fetching the weights. You can also fetch intermediate variables like activations. Anything you need.


## Adding new parameters

One neat feature of Ptera is that it is easy to add parameters anywhere in the program and play with their values without needing to change much anything else. For example, you might want to add some notion of temperature in layers:

```python
@ptera
def layer(inp):
    W: WeightMatrix
    b: BiasVector
    T: float  # Declare the new parameter here
    actfn: ActivationFunction

    act = inp @ W + b
    return actfn(act / T)  # Use it here
```

Then, you can set this parameter and play with it:

```python
# You can initially set it with new
layer1 = layer.new(W=..., b=..., actfn=..., T=1)

# Tweak the temperature to 1
model.tweak({"layer > T": 1})(inp)

# Tweak the temperature to 2
model.tweak({"layer > T": 2})(inp)

# Tweak the temperature to 10 but ONLY for layer 1
model.tweak({"layer[1] > T": 10})(inp)
```

You can also easily make it a parameter of the model and update it with gradient descent.

The beauty of this is that each tweak to the model uses the exact same parameters, the exact same state, *except* for the tweak. This makes it very easy to experiment: for example, you might add various flags in your program that control things like dropout, batch normalization, and so on. Using Ptera, you can turn them on and off at the drop of a hat.

This is hard/annoying to do using conventional frameworks: if you set the flag in the constructor for a layer in your model, how do you change it? How do you change it for all layers at once? If you add the flag as a parameter to the call to the step function, how do you propagate the flag down the call stack?

This is a software engineering problem and no one has time for this kind of nonsense. With Ptera, you simply define the flag where you will need it, with a sensible default, and you can just write a simple query to override it where necessary.
