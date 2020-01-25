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
        ("f", None, None, 9),
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
        ("f", None, None, 9),
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
        ("f", None, None, 9),
    ]
