import sys
from operator import itemgetter

import pytest
import rx

from ptera import op
from ptera.probe import LocalProbe, Probe, accumulate, probing

from .milk import cheese as ch, gouda


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


def test_probe_raw():
    results = Accumulator(lambda data: data["a"].value)
    probe = Probe("f > a", raw=True)

    probe.subscribe(results)

    loopy()
    results.check(x * x for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_probe():
    results = Accumulator(itemgetter("a"))
    probe = Probe("f > a")

    probe.subscribe(results)

    loopy()
    results.check(x * x for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_probe_method():
    results = Accumulator(itemgetter("wow"))
    probe = Probe("Elephant.sing > wow")

    probe.subscribe(results)

    loopy()
    results.check(x + 10 for x in range(100))

    results.clear()
    probe.deactivate()
    loopy()
    results.check([])


def test_probe_tag():
    results = Accumulator(itemgetter("x"))
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

    neg = probe.pipe(op.map(lambda data: -data["a"]))

    neg.subscribe(results)

    loopy()
    results.check(-x * x for x in range(100))

    probe.deactivate()


def test_merge():
    results = Accumulator()
    probe = Probe("f > a")

    arr = rx.of(-1, -2, -3)
    vals = probe.pipe(op.map(itemgetter("a")))
    merged = arr.pipe(op.merge(vals))

    merged.subscribe(results)

    loopy()
    results.check({x * x for x in range(100)} | {-1, -2, -3})

    probe.deactivate()


def test_two_probes():
    results1 = Accumulator(itemgetter("a"))
    results2 = Accumulator(itemgetter("a"))

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
    results1 = Accumulator(itemgetter("a"))
    results2 = Accumulator(itemgetter("a"))

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


def test_local_probe():
    results = Accumulator()
    lp = LocalProbe("f > a").pipe(op.map(itemgetter("a")), op.max())
    lp.subscribe(results)
    with lp as probe:
        assert probe._local_probe is lp
        loopy()
    results.check([99 ** 2])

    results.clear()
    loopy()  # Should not accumulate

    with lp:
        # lp should be reusable
        loopy()
    results.check([99 ** 2])


def test_probing():
    results = Accumulator()
    with probing("f > a") as probe:
        probe.pipe(op.map(itemgetter("a")), op.max()).subscribe(results)
        loopy()
    results.check([99 ** 2])


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_slash_probe():
    results = Accumulator()
    with probing("/tests.milk/cheese > a") as probe:
        probe.pipe(op.map(itemgetter("a"))).subscribe(results)
        assert ch(4) == 16 + 4
        assert ch(5) == 25 + 4
    results.check([16, 25])


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_slash_probe_multi():
    # Probing a function rewrites it and gives it a new code object, so
    # we need to check if we can find multiple times reliably

    results = Accumulator()
    with probing("/tests.milk/gouda > a") as probe:
        probe.pipe(op.map(itemgetter("a"))).subscribe(results)
        assert gouda(4) == 64
    results.check([8])

    results = Accumulator()
    with probing("/tests.milk/gouda > b") as probe:
        probe.pipe(op.map(itemgetter("b"))).subscribe(results)
        assert gouda(4) == 64
    results.check([64])

    results = Accumulator()
    with probing("/tests.milk/gouda() as ret") as probe:
        probe.pipe(op.map(itemgetter("ret"))).subscribe(results)
        assert gouda(4) == 64
    results.check([64])


def test_accumulate():
    with accumulate("f > a") as results:
        f(4)
        f(5)

    assert results == [{"a": 16}, {"a": 25}]


def test_accumulate2():
    lp = LocalProbe("f > a").pipe(op.getitem("a"))

    with accumulate(lp) as results:
        f(4)
        f(5)

    assert results == [16, 25]
