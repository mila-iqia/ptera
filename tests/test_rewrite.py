from ptera.rewrite import transform
from ptera.selector import ABSENT


class InteractLogger:
    def __init__(self):
        self.log = []

    def __call__(self, sym, key, category, value=ABSENT):
        self.log.append((sym, key, category, value))
        return value


def get_log(fn, *args):
    logger = InteractLogger()
    fn2 = transform(fn, interact=logger)
    result = fn2(*args)
    return [result, *logger.log]


def test_simple():
    def f(x, y):
        a = x + y
        return a

    assert get_log(f, 4, 5) == [
        9,
        ("x", None, None, 4),
        ("y", None, None, 5),
        ("a", None, None, 9),
        ("#value", None, None, 9),
    ]


def test_annotations():
    def f(x: float, y):
        a: int = x + y
        return a

    assert get_log(f, 4, 5) == [
        9,
        ("x", None, float, 4),
        ("y", None, None, 5),
        ("a", None, int, 9),
        ("#value", None, None, 9),
    ]


def test_declaration():
    def f(x: float, y):
        decl: int
        a: int = x + y
        return a

    assert get_log(f, 4, 5) == [
        9,
        ("x", None, float, 4),
        ("y", None, None, 5),
        ("decl", None, int, ABSENT),
        ("a", None, int, 9),
        ("#value", None, None, 9),
    ]


def test_indexing():
    def f(n):
        rec = {}
        rec[0] = 0
        for i in range(n):
            rec[i + 1] = rec[i] + i
        return rec[n]

    assert get_log(f, 5) == [
        10,
        ("n", None, None, 5),
        ("rec", None, None, {0: 0, 1: 0, 2: 1, 3: 3, 4: 6, 5: 10}),
        ("rec", 0, None, 0),
        ("rec", 1, None, 0),
        ("rec", 2, None, 1),
        ("rec", 3, None, 3),
        ("rec", 4, None, 6),
        ("rec", 5, None, 10),
        ("#value", None, None, 10),
    ]


def test_deconstruct():
    def f(x, y):
        a, (b, c) = y, (x, x)
        return a / b

    assert get_log(f, 5, 10) == [
        2,
        ("x", None, None, 5),
        ("y", None, None, 10),
        ("a", None, None, 10),
        ("b", None, None, 5),
        ("c", None, None, 5),
        ("#value", None, None, 2),
    ]
