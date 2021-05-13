import pytest
import rx
from rx import operators as op

from ptera.probe import Probe, probing


class Accumulator:
    def __init__(self, fn=None):
        self.fn = fn
        self.results = []

    def clear(self):
        self.results.clear()

    def check(self, expected):
        if isinstance(expected, set):
            assert set(self.results) == expected
        else:
            assert self.results == list(expected)

    def on_next(self, data):
        if self.fn:
            data = self.fn(data)
        self.results.append(data)

    def on_error(self, err):
        raise err

    def on_completed(self):
        pass


def f(x):
    a: "@flag" = x * x  # type: ignore
    return a + 1


def g(x):
    a = -x
    return a + 1


class Elephant:
    def __init__(self, secret):
        self.secret = secret

    def sing(self, x):
        wow = x + self.secret
        return wow


def loopy():
    el = Elephant(10)
    acc = 0
    for i in range(100):
        acc += f(i)
        acc += g(i)
        acc += el.sing(i)
    return acc


def test_probe():
    results = Accumulator(lambda data: data["a"].value)
    probe = Probe("f > a")

    probe.subscribe(results)

    loopy()
    results.check(x * x for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_probe_method():
    results = Accumulator(lambda data: data["wow"].value)
    probe = Probe("Elephant.sing > wow")

    probe.subscribe(results)

    loopy()
    results.check(x + 10 for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_probe_tag():
    results = Accumulator(lambda data: data["x"].value)
    probe = Probe("f > $x:@flag")

    probe.subscribe(results)

    loopy()
    results.check(x * x for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_pipe():
    results = Accumulator()
    probe = Probe("f > a")

    neg = probe.pipe(op.map(lambda data: -data["a"].value))

    neg.subscribe(results)

    loopy()
    results.check(-x * x for x in range(100))

    probe.deactivate()


def test_merge():
    results = Accumulator()
    probe = Probe("f > a")

    arr = rx.of(-1, -2, -3)
    vals = probe.pipe(op.map(lambda data: data["a"].value))
    merged = arr.pipe(op.merge(vals))

    merged.subscribe(results)

    loopy()
    results.check({x * x for x in range(100)} | {-1, -2, -3})

    probe.deactivate()


def test_two_probes():
    results1 = Accumulator(lambda data: data["a"].value)
    results2 = Accumulator(lambda data: data["a"].value)

    probe1 = Probe("f > a")
    probe2 = Probe("g > a")

    probe1.subscribe(results1)
    probe2.subscribe(results2)

    probe2.deactivate()
    loopy()
    results1.check([x * x for x in range(100)])
    results2.check([])

    probe2.activate()
    loopy()
    results1.check([x * x for x in range(100)] * 2)
    results2.check([-x for x in range(100)])

    probe1.deactivate()
    loopy()
    results1.check([x * x for x in range(100)] * 2)
    results2.check([-x for x in range(100)] * 2)


def test_probe_same_var_twice():
    results1 = Accumulator(lambda data: data["a"].value)
    results2 = Accumulator(lambda data: data["a"].value)

    probe1 = Probe("f > a")
    probe2 = Probe("f > a")  # Different probe for same var

    probe1.subscribe(results1)
    probe2.subscribe(results2)

    probe2.deactivate()
    loopy()
    results1.check([x * x for x in range(100)])
    results2.check([])

    probe2.activate()
    loopy()
    results1.check([x * x for x in range(100)] * 2)
    results2.check([x * x for x in range(100)])

    probe1.deactivate()
    loopy()
    results1.check([x * x for x in range(100)] * 2)
    results2.check([x * x for x in range(100)] * 2)


def test_bad_probe():
    with pytest.raises(NameError):
        Probe("unknown > a")


def test_probing():
    results = Accumulator()
    with probing("f > a") as probe:
        probe.pipe(
            op.map(lambda data: data["a"].value),
            op.max(),
        ).subscribe(results)
        loopy()
    results.check([99 ** 2])
