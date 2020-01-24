from ptera.rewrite import transform
from ptera.selector import ABSENT


class InteractLogger:
    def __init__(self):
        self.log = []

    def __call__(self, sym, category, value=ABSENT):
        self.log.append((sym, category, value))
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
        ("x", None, 4),
        ("y", None, 5),
        ("a", None, 9),
        ("f", None, 9),
    ]


def test_annotations():
    def f(x: float, y):
        a: int = x + y
        return a

    assert get_log(f, 4, 5) == [
        9,
        ("x", float, 4),
        ("y", None, 5),
        ("a", int, 9),
        ("f", None, 9),
    ]


def test_declaration():
    def f(x: float, y):
        decl: int
        a: int = x + y
        return a

    assert get_log(f, 4, 5) == [
        9,
        ("x", float, 4),
        ("y", None, 5),
        ("decl", int, ABSENT),
        ("a", int, 9),
        ("f", None, 9),
    ]
