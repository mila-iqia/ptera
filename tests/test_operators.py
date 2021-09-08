from giving import operators as op

from ptera.probe import probing

TOLERANCE = 1e-6


def fib(n):
    a = 0
    b = 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b


def test_getitem():
    with probing("fib > b") as probe:
        results = []
        probe["b"].subscribe(results.append)
        fib(5)
        assert results == [1, 1, 2, 3, 5]


def test_getitem2():
    with probing("fib(a) > b") as probe:
        results = []
        probe["a", "b"].subscribe(results.append)
        fib(5)
        assert results == [(0, 1), (1, 1), (1, 2), (2, 3), (3, 5)]


def test_format():
    with probing("fib > b") as probe:
        results = []
        probe.format("b={b}").subscribe(results.append)
        fib(5)
        assert results == ["b=1", "b=1", "b=2", "b=3", "b=5"]


def test_format3():
    with probing("fib(a) > b") as probe:
        results = []
        probe["a", "b"].format("a={},b={}").subscribe(results.append)
        fib(5)
        assert results == [
            "a=0,b=1",
            "a=1,b=1",
            "a=1,b=2",
            "a=2,b=3",
            "a=3,b=5",
        ]


def test_keymap():
    with probing("fib > b") as probe:
        results = []
        probe.keymap(lambda b: -b).subscribe(results.append)
        fib(5)
        assert results == [-1, -1, -2, -3, -5]


def test_roll():
    with probing("fib > b") as probe:
        results = []
        probe["b"].roll(3).map(list).subscribe(results.append)
        fib(5)
        assert results == [[1], [1, 1], [1, 1, 2], [1, 2, 3], [2, 3, 5]]


def test_rolling_average_and_variance():
    with probing("fib > b") as probe:
        results1 = []
        results2 = []
        bs = probe.pipe(op.getitem("b"))

        bs.average_and_variance(scan=7).skip(1) >> results1

        def meanvar(xs):
            n = len(xs)
            if len(xs) >= 2:
                mean = sum(xs) / n
                var = sum((x - mean) ** 2 for x in xs) / (n - 1)
                return (mean, var)
            else:
                return (None, None)

        bs.roll(7).map(meanvar).skip(1) >> results2

        fib(25)
        assert all(
            abs(m1 - m2) < TOLERANCE and abs(v1 - v2) < TOLERANCE
            for (m1, v1), (m2, v2) in zip(results1, results2)
        )
