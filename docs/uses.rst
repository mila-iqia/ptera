
Use cases
=========

Instrumenting external code
---------------------------

There can be situations where you are interested in something an external library or program is computing, but is not easily available from its interface.

For example, if you are using someone else's code to train a neural network and are interested in how the training loss evolves, but that information is tucked inside a while loop, that can be a bit annoying to work with.

Instead of modifying the code to log the information you need, you can use Ptera to extract it.

For example, here is an example script to train a model on MNIST with Pytorch that you can download from Pytorch's main repository:

.. code-block:: bash

    wget https://raw.githubusercontent.com/pytorch/examples/main/mnist/main.py

`If you look at the code <https://github.com/pytorch/examples/blob/main/mnist/main.py#L43>`_ you can see that a loss variable is set in the train function. Let's do something with it.

Try running the following script instead of ``main.py`` (put that script in the same directory as ``main.py``):

.. code-block:: python

    from main import main, train
    from ptera import probing

    if __name__ == "__main__":
        with probing("train > loss") as prb:
            (
                prb["loss"]          # Extract the loss variable
                .average(scan=100)   # Running average of last 100
                .throttle(1)         # Produce at most once per second
                .print("Loss = {}")
            )

            # Run the original script within context of the probe
            main()

In addition to the original script's output, you will now get new output that corresponds to the running average of the last 100 training losses, reported at most once per second.

.. tip::
    If you like the idea of using this for logging data in your own scripts because of how powerful the probe interface is, you certainly can! But you can have the same interface in a more explicit way with the giving_ library, using ``give/given`` instead of ``probing``.

.. _giving: https://giving.readthedocs.io


Advanced logging
----------------

Since probes are defined outside of the code they instrument, they can be used to log certain metrics without littering the main program. These logs can be easily augmented with information from outer scopes, limited using throttling, reduced in order to compute an average/min/max, and so on.


Advanced debugging
------------------

Probes have a :meth:`~ptera.probe.Probe.breakpoint` method. Coupled with operators such as :func:`~giving.operators.filter`, it is easy to define reusable conditional breakpoints. For example:

.. code-block:: python

    from ptera import probing

    def f(x):
        y = x * x
        return y

    with probing("f > x") as prb:
        prb["x"].filter(lambda x: x == 2).breakpoint()

        f(1)
        f(2)  # <- will set a breakpoint at the start
        f(3)

Such breakpoints should work regardless of the IDE you use, and they should be robust to most code changes, short of changing variable and function names.

Using operators like :func:`~giving.operators.pairwise`, you can also set breakpoints that activate if a variable increases or decreases in value.


Testing
-------

Ptera's ability to extract arbitrary variables from multiple scopes can be very useful for writing tests that verify conditions about a program or library's internal state.

See :ref:`Testing with Ptera` for detailed examples.
