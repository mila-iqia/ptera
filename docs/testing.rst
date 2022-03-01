
Testing with Ptera
==================

Ptera's capabilities can be quite useful for testing, especially for complex tests or integration tests.

There is a plugin for pytest with a lot of interesting capabilities: `pytest-ptera <https://github.com/breuleux/pytest-ptera>`_. This being said, plain Ptera can be leveraged to write tests.

Many of the tests below could also be done with clever monkey patching, but they are a lot simpler with Ptera.


Test information flow
---------------------

There are many situations where you provide an argument to a top level function and you expect its value to bubble down to subroutines. This can be a source of subtle bugs, especially if these subroutines have default parameters that you forget to pass them along (silent bugs 😱). Oftentimes this could be checked by verifying the program's expected output, but that can be tricky for very complex programs and it makes the test sensitive to many other bugs.

Ptera can help you verify that the information flow is as you expect it:

.. code-block:: python

    def g(x, opt=0):
        return x * opt

    def f(x, opt=0):
        return g(x + 1)  # BUG: should be g(x + 1, opt=opt)

    def test_flow():
        with probing("f(opt as fopt) > g(!opt as gopt)") as prb:
            prb.fail_if_empty()
            prb.kfilter(lambda fopt, gopt: fopt != gopt).fail()

            f(10, opt=11)  # Fails!

**The probe**: ``f(opt as fopt) > g(!opt as gopt)`` is triggered when ``g`` is called within ``f``, and the ``opt`` variable or parameter in ``g`` is set.

* The ``!`` denotes the *focus variable*. When that variable is set, the pipeline is activated.
* Two variables are collected: ``opt`` in ``f`` which we rename ``fopt``, and ``opt`` in ``g`` which we rename ``gopt``.

**The pipeline**:

* :meth:`~ptera.probe.Probe.fail_if_empty` ensures that the selector is triggered at least once. This is a recommended sanity check to make sure that the test is doing something!
* The :func:`~giving.operators.kfilter` method will be fed both of our variables as keyword arguments. This means that the parameter names of the lambda must be the same as the variable names.
* ``kfilter`` will only produce the elements where ``fopt`` and ``gopt`` are not the same (where the lambda returns True).
* :meth:`~ptera.probe.Probe.fail` will raise an exception whenever it receives anything. Because of the ``kfilter``, ``fail`` will only get data if ``fopt`` and ``gopt`` differ (which is the precise error we want the test to catch).


Test for infinite loops
-----------------------

The following test will check that the function ``f`` is called no more than a thousand times during the test:

.. code-block:: python

    def loopy(i):
        while i != 0:
            f()
            i = i - 1

    def test_loopy():
        with probing("f > #enter") as prb:
            prb.skip(1000).fail()

            loopy(-1)  # Fails

**The probe**: ``f > #enter`` uses the special variable ``#enter`` that is triggered immediately at the start of ``f``. Every time ``f`` is called, this pipeline is triggered.

.. note::
    In this example, you could also set a probe on ``loopy > i``. It is up to you to choose what makes the most sense.

**The pipeline**:

* :func:`~giving.operators.skip` will throw away the first thousand entries in the pipeline, corresponding to the first 1000 calls to ``f``.
* :meth:`~ptera.probe.Probe.fail` will fail whenever it sees anything. If ``f`` is called less than 1000 times, all calls are skipped and there will be no failure. Otherwise, the 1001st call will trigger a failure.

Of course, this test can be adapted to check that a function is called once or more (use ``fail_if_empty()``), or a specific number of times (``count().filter(lambda x: x != expected_count).fail()``).


Test trends
-----------

Another great use for Ptera is to check for trends in the values of certain variables in the program as it progresses. Perhaps they must be monotonically increasing or decreasing, perhaps they should be convergent, and so on.

For example, let's say you want to verify that a variable in a loop always goes down:

.. code-block:: python

    def loopy(i, step):
        while i != 0:
            f()
            i = i - step

    def test_loopy():
        with probing("loopy > i") as prb:
            prb["i"] \
                .pairwise() \
                .starmap(lambda i1, i2: i2 - i1) \
                .filter(lambda x: x >= 0) \
                .fail()

            loopy(10, 0)  # Fails

**The probe**: ``loopy > i`` is triggered when ``i`` is set in ``loopy``. Being passed as an argument counts as being set.

**The pipeline**:

* ``prb["i"]`` extracts the field named ``"i"``.
* :func:`~giving.operators.pairwise` pairs consecutive elements. It will transform the sequence ``(x, y, z, ...)`` into ``((x, y), (y, z), ...)``. Therefore, after this operator, we have pairs of successive values taken by ``i``.
* :func:`~giving.operators.starmap` applies a function on each tuple as a list of arguments, so the pairs we just created are passed as two separate argument. We compute the difference between them.
* :func:`~giving.operators.filter` applies on the differences we just created. Unlike ``kfilter`` it does not take the arguments as keyword arguments, just the raw values we have so far.
* :meth:`~ptera.probe.Probe.fail` will fail as soon as we detect a non-negative difference.


Test caching
------------

In this example, we test that a function is never called twice with the same argument. For example, maybe it computes something expensive, so we want to cache the results, and we want to make sure the cache is properly used.


.. code-block:: python

    cache = {}

    def _expensive(x):
        return x * x  # oof! so expensive

    def expensive(x):
        if x in cache:
            return cache[x]
        else:
            # We forget to populate the cache
            return _expensive(x)

    def test_expensive():
        with probing("_expensive > x") as prb:
            xs = prb["x"].accum()

            expensive(12)
            expensive(12)  # again

        assert len(set(xs)) == len(xs) > 0  # fails


This example could also be written with the ``distinct`` method, but since the number of available methods can be overwhelming I'm showing a more polyvalent way to do things.

**The probe:** ``_expensive > x`` instruments the argument ``x`` of ``_expensive``. It is important to probe the function that unconditionally does the computation in this case.

**The pipeline:**

* ``prb["x"]`` extracts the field named ``"x"``.
* :meth:`~ptera.probe.Probe.accum` creates a (currently empty) list and returns it. Every time the probe is activated, the current value is appended to the list.
* After calling ``expensive`` twice, we can look at what's in the list. Here we could simply check that it only contains one element, but more generally we can check that its distinct elements (``set(xs)``) are exactly as numerous as the complete list, from which we can conclude that there are no duplicates.
* The ``> 0`` is added for good measure, to make sure we are not testing a dud that never calls ``_expensive`` at all.

You can of course do whatever you want with the list returned by ``accum``, which is what makes it very polyvalent. You only have to make sure not to use it until *after* the ``probing`` block concludes, especially if you accumulate the result of a reduction operator like ``min`` or ``average``.
