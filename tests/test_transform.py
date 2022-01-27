import functools
import sys
from types import SimpleNamespace

import pytest

from ptera.transform import Key, name_error, transform
from ptera.utils import ABSENT, keyword_decorator

from .common import one_test_per_assert


def _format_sym(entry):
    rval, key, typ, _ = entry
    if key is not None:
        if key.type == "attr":
            rval += f".{key.value}"
        elif key.type == "index":
            rval += f"[{key.value}]"
    return rval


class Interactions(list):
    def has(self, sublist):
        i = 0
        for entry in self:
            if entry == sublist[i]:
                i += 1
                if i == len(sublist):
                    return True
        return False

    def syms(self):
        return type(self)(_format_sym(x) for x in self)

    def vals_for(self, sym):
        return type(self)(x[-1] for x in self if x[0] == sym)

    @property
    def ret(self):
        assert self[-1][0] == "#value"
        return self[-1][-1]


def test_Interactions():
    xs = Interactions([1, 2, 3, 7, 2, 9])
    assert xs.has(xs)
    assert xs.has([2, 3, 7])
    assert xs.has([1, 3, 9])
    assert not xs.has([3, 2, 3, 7])
    assert not xs.has([1, 1])

    xs = Interactions(
        [
            ("a", None, None, 6),
            ("b", None, None, 48),
            ("b", Key("attr", "wow"), None, 8),
            ("a", None, None, 9),
            ("c", None, None, -1),
        ]
    )
    assert xs.syms() == ["a", "b", "b.wow", "a", "c"]
    assert xs.vals_for("a") == [6, 9]
    assert xs.vals_for("b") == [48, 8]
    assert xs.vals_for("c") == [-1]


@keyword_decorator
def wrap(fn, all=False):
    results = Interactions()
    overrides = {}

    def interact(sym, key, category, value):
        results.append((sym, key, category, value))
        rval = overrides.get(sym, value)
        if rval is ABSENT:
            raise name_error(sym, wrapped)
        return rval

    new_fn, info = transform(fn, interact)

    @functools.wraps(fn)
    def wrapped(*args, **ovrd):
        results.clear()
        overrides.clear()
        overrides.update(ovrd)
        rval = new_fn(*args)
        if all:
            return results
        else:
            return rval

    wrapped.info = info
    return wrapped


@wrap(all=True)
def iceberg(
    # The parameter x
    x: float,
    # The parameter y
    y,
):
    # The great
    # zee
    z: int
    return sum([x, y, z])


_iceberg_line = 97


@wrap
def chocolat(x, y):
    z = x + y
    rval = z * z
    if add1:
        rval = rval + 1
    return rval


@wrap
def puerh(x=2, y=3):
    return x + y


@wrap
def helicopter(x, y):
    return min(x, y)


@wrap
def wishful_thinking():
    return unicorn


#################
# General tests #
#################


def test_interact():
    data = iceberg(7, 3, z=5)
    assert data.ret == 15
    assert data == [
        ("x", None, float, 7),
        ("y", None, None, 3),
        ("int", None, None, int),
        ("sum", None, None, sum),
        ("z", None, int, ABSENT),
        ("#value", None, None, 15),
    ]


@one_test_per_assert
def test_misc():
    assert iceberg(2, 3, z=5).ret == 10

    assert chocolat(2, 3, add1=False) == 25
    assert chocolat(2, 3, add1=True) == 26

    assert puerh() == 5
    assert puerh(x=7) == 10
    assert puerh(y=10) == 12
    assert puerh(4, 5) == 9

    assert helicopter(2, 10) == 2
    assert helicopter(2, 10, min=max) == 10


def test_name_error():
    with pytest.raises(NameError):
        iceberg(2, 3)
    with pytest.raises(NameError):
        chocolat(2, 3)
    with pytest.raises(NameError):
        wishful_thinking()


def test_missing_argument():
    with pytest.raises(TypeError):
        chocolat()


##############################
# Test information gathering #
##############################


def test_info():
    info = iceberg.info["z"]
    filename, fn, lineno = info.pop("location")
    assert fn.__name__ == "iceberg"
    assert lineno == _iceberg_line + 9
    assert info == {
        "name": "z",
        "annotation": int,
        "provenance": "body",
        "doc": "The great\nzee",
    }


def test_info_parameter():
    info = iceberg.info["x"]
    filename, fn, lineno = info.pop("location")
    assert fn.__name__ == "iceberg"
    assert lineno == _iceberg_line + 3
    assert info == {
        "name": "x",
        "annotation": float,
        "provenance": "argument",
        "doc": "The parameter x",
    }


def test_info_external():
    info = iceberg.info["sum"]
    filename, fn, lineno = info.pop("location")
    assert fn.__name__ == "iceberg"
    assert lineno is None
    assert info == {
        "name": "sum",
        "annotation": ABSENT,
        "provenance": "external",
        "doc": None,
    }


def test_docstring_preserved():
    @wrap
    def docteur(n):
        """Docstrings should be preserved."""
        diet = n * "pomme"
        return diet

    assert docteur.__doc__ == """Docstrings should be preserved."""


#################################
# Test language feature support #
#################################


@wrap
def spatula(x):
    a, b = x
    return a + b


def test_tuple_assignment():
    assert spatula((4, 5)) == 9
    assert spatula((4, 5), a=70) == 75
    assert spatula((4, 5), b=70) == 74


def test_nested_function():
    @wrap
    def kangaroo(x):
        def child(y):
            return y * y

        a = child(x)
        b = child(x + 1)
        return a + b

    assert kangaroo(3) == 25


def test_attribute_assignment():
    class X:
        pass

    @wrap(all=True)
    def obelisk(x):
        x.y = 2
        return x.y

    data = obelisk(X())
    assert data.ret == 2
    assert "x.y" in data.syms()


def test_index_assignment():
    @wrap(all=True)
    def limbo(x):
        x[0] = 2
        return x

    data = limbo([0, 1])
    assert data.ret == [2, 1]
    assert "x[0]" in data.syms()


def test_nested_no_crash():
    @wrap(all=True)
    def limbo(x):
        x[0][1] = 2
        return x

    data = limbo([[0, 1], 2])
    assert data.ret == [[0, 2], 2]
    assert data.syms() == ["x", "#value"]


def test_empty_return():
    @wrap
    def foo():
        return

    assert foo() is None


def test_for_loop():
    @wrap
    def brooms(xs):
        rval = 0
        for i, x in enumerate(xs):
            rval = rval + (i + 1) * x
        return rval

    assert brooms([1, 2, 3]) == 14
    assert brooms([1, 2, 3], i=0) == 6


def test_while_loop():
    @wrap
    def broomy(n):
        rval = 0
        while n > 0:
            x = n * n
            rval = rval + x
            n -= 1
        return rval

    assert broomy(3) == 14
    assert broomy(3, x=2) == 6


def test_generator():
    @wrap
    def oxygen():
        j = 0
        for i in range(10):
            j = j + 1
            yield j
        return j

    results = list(oxygen())
    assert results == list(range(1, 11))

    results = list(oxygen(j=0))
    assert results == [0] * 10


def test_exception():
    @wrap
    def excite():
        try:
            1 / 0
        except ZeroDivisionError as exc:
            return exc
        except TypeError:
            return None

    assert isinstance(excite(), ZeroDivisionError)
    assert excite(exc="nope") == "nope"


def test_import_inside():
    from ptera import tools as T_orig

    @wrap
    def imp(x):
        import ptera.tools  # noqa
        import ptera.tools as T

        return T.gt(3)(x)

    assert imp(7)
    assert not imp(7, T=SimpleNamespace(gt=T_orig.lt))


def test_import_from_inside():
    from ptera.tools import lt as lt_orig

    @wrap
    def imp(x):
        from ptera.tools import gt

        return gt(3)(x)

    assert imp(7)
    assert not imp(7, gt=lt_orig)


if sys.version_info >= (3, 8, 0):

    def test_named_expression():
        from .walrus import ratatouille

        ratatouille = wrap(ratatouille)

        assert ratatouille(5) == 36
        assert ratatouille(5, y=3) == 9