
What is Ptera?
==============

Ptera is a way to instrument code from the outside. More precisely, it allows you to specify a set of variables to watch in an arbitrary Python call graph and manipulate a stream of their values.

For example, the following code will print ``a = 12 and b = 34``, at the moment that the variable ``a`` is set.

.. code-block:: python

    from ptera import probing

    def f():
        a = 12

    def g():
        b = 34
        f()

    # "g(b) > f > a" is a *selector* that selects the variable b in the function g
    # and the variable a in the function f, with a focus on variable a
    with probing("g(b) > f > a") as prb:
        # The following line declares a processing pipeline. It must be declared
        # before the main functionality is called.
        prb.print("a = {a} and b = {b}")

        # When the watched variables are set, the values will go through the pipeline
        # declared previously
        g()

See :ref:`Probing` for more information on the probing syntax.

You can use Ptera to:

* :ref:`Instrument code that you do not control.<Instrumenting external code>`
* :ref:`Collect data across function scopes.<Probe across scopes>`
* Perform :ref:`complex filters<Filtering>` and :ref:`reductions<Reduction>` on the stream of values.
* :ref:`Test<Testing with Ptera>` complex conditions on a program's internal state.


Getting started
===============

Install
-------

.. code-block:: bash

    pip install ptera

Usage
-----

The main API for Ptera is :func:`~ptera.probe.probing`, which is used as a context manager.

Here's an example involving `a fun function <https://en.wikipedia.org/wiki/Collatz_conjecture>`_. Even though the function returns nothing, we can use Ptera to extract all sorts of interesting things:

.. code-block:: python

    from ptera import probing

    def collatz(n):
        while n != 1:
            n = (3 * n + 1) if n % 2 else (n // 2)

    # `collatz > n` means: probe variable `n` in function `collatz`
    # Every time `n` is set (including when it is given as a parameter)
    # an event is sent through `prb`
    with probing("collatz > n") as prb:
        # Declare one or more pipelines on the data.
        prb["n"].print("n = {}")
        prb["n"].max().print("max(n) = {}")
        prb["n"].count().print("number of steps: {}")

        # We can also ask for all values to be accumulated into a list
        values = prb["n"].accum()

        # Call the function once all the pipelines are set up.
        collatz(2021)

        # Print the values
        print("values =", values)

    # Output:
    # n = 2021
    # ...
    # n = 1
    # values = [2021, ..., 1]
    # max(n) = 6064
    # number of steps: 63

Note that in the example above the max/count are printed after the with block ends (they are triggered when there is no more data, and the stream is ended when the with block ends), which is why ``print(values)`` is not the last thing that's printed.
