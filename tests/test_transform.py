import functools
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

from ptera.selector import Element, SelectorError, select
from ptera.tags import enter_tag, exit_tag
from ptera.transform import (
    Key,
    StackedTransforms,
    SyncedStackedTransforms,
    TransformSet,
    name_error,
    transform,
)
from ptera.utils import ABSENT, keyword_decorator

from .common import one_test_per_assert


def _format_sym(entry):
    rval, key, typ, _, ovr = entry
    if key is not None:
        if key.type == "attr":
            rval += f".{key.value}"
        elif key.type == "index":
            rval += f"[{key.value}]"
    return rval


_current_layer = ContextVar("_current_layer", default=None)


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
        return type(self)(x[-2] for x in self if x[0] == sym)

    @property
    def ret(self):
        assert self[-2][0] == "#value"
        return self[-2][-2]


def test_Interactions():
    xs = Interactions([1, 2, 3, 7, 2, 9])
    assert xs.has(xs)
    assert xs.has([2, 3, 7])
    assert xs.has([1, 3, 9])
    assert not xs.has([3, 2, 3, 7])
    assert not xs.has([1, 1])

    xs = Interactions(
        [
            ("a", None, None, 6, True),
            ("b", None, None, 48, True),
            ("b", Key("attr", "wow"), None, 8, True),
            ("a", None, None, 9, True),
            ("c", None, None, -1, True),
        ]
    )
    assert xs.syms() == ["a", "b", "b.wow", "a", "c"]
    assert xs.vals_for("a") == [6, 9]
    assert xs.vals_for("b") == [48, 8]
    assert xs.vals_for("c") == [-1]


class SimpleInteractor:
    def __init__(self, fn):
        self.fn = fn
        self.results, self.overrides = _current_layer.get()

    def interact(self, sym, key, category, value, overridable):
        self.results.append((sym, key, category, value, overridable))
        rval = self.overrides.get(sym, value)
        if rval is ABSENT:
            raise name_error(sym, self.fn)
        return rval

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


@keyword_decorator
def wrap(
    fn, all=False, names=True, noreset=False, allow_errors=False, results=None
):
    new_fn = transform(
        fn,
        proceed=SimpleInteractor,
        to_instrument=True
        if names is True
        else [Element(name=name) for name in names],
    )

    @functools.wraps(fn)
    def wrapped(*args, **overrides):
        nonlocal results
        kw = overrides.pop("KW", {})
        if results is None:
            results = Interactions()
        reset = _current_layer.set((results, overrides))
        try:
            rval = new_fn(*args, **kw)
        except:  # noqa: E722
            if allow_errors:
                rval = None
            else:
                raise
        if not noreset:
            _current_layer.reset(reset)
        results.actual_ret = rval
        if all:
            return results
        else:
            return rval

    wrapped.__ptera_info__ = wrapped.info = new_fn.__ptera_info__
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


_iceberg_line = iceberg.__wrapped__.__code__.co_firstlineno


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


@wrap(all=True, names=["b", "d"])
def only_some(a):
    b = a + 1
    c = b + 1
    d = c + 1
    e = d + 1
    return e + 1


#################
# General tests #
#################


def test_interact():
    data = iceberg(7, 3, z=5)
    assert data.ret == 15
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("int", None, None, int, True),
        ("sum", None, None, sum, True),
        ("x", None, float, 7, True),
        ("y", None, None, 3, True),
        ("z", None, int, ABSENT, True),
        ("#value", None, None, 15, True),
        ("#exit", None, exit_tag, True, False),
    ]


def test_interact_only_some():
    data = only_some(10)
    assert data.actual_ret == 15
    assert data == [
        ("b", None, None, 11, True),
        ("d", None, None, 13, True),
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


def _has_problem(selector, problem):
    with pytest.raises(SelectorError) as exc:
        select(selector, strict=True)
    exc_string = str(exc.value)
    assert problem in exc_string
    return True


@one_test_per_assert
def test_resolvability():
    assert _has_problem("a", "Wildcard")
    assert _has_problem("apple > banana", "Could not resolve 'apple'")
    assert _has_problem("chocolat > no", "Cannot find a variable named `no`")
    assert _has_problem(
        "iceberg > chocolat > no", "Cannot find a variable named `no`"
    )
    assert _has_problem("chocolat > x:@xyz", "does not have the category")
    assert _has_problem("chocolat > *:@xyz", "has the category")
    assert _has_problem("_has_problem > selector", "is not properly tooled")
    assert _has_problem("chocolat > #what", "#what is not a valid hashvar")

    assert select("chocolat > x", strict=True)
    assert select("chocolat > *", strict=True)
    assert select("chocolat > #enter", strict=True)
    assert select("iceberg > chocolat > x", strict=True)


@one_test_per_assert
def test_Key():
    assert str(Key("attr", "wow")) == "<Key attr='wow'>"
    assert Key("attr", "wow").affix_to("thing") == "thing.wow"
    assert Key("index", "wow").affix_to("thing") == "thing['wow']"


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


@wrap
def pincettes(x):
    a = b = x + 1
    return a + b


def test_multiple_assignment():
    assert pincettes(10) == 22
    assert pincettes(10, a=100) == 111


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
    assert data.syms() == ["#enter", "x", "#value", "#exit"]


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
    @wrap(noreset=True)
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


def test_bare_except():
    @wrap
    def excite():
        x = 1
        try:
            x / 0
        except:  # noqa: E722
            return x

    assert excite() == 1
    assert excite(x=3) == 3


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


def test_closure():
    x = 3
    y = 7

    @wrap(all=True)
    def inside_scoop():
        return x + y

    data = inside_scoop()
    assert data.ret == 10
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("x", None, None, 3, False),
        ("y", None, None, 7, False),
        ("#value", None, None, 10, True),
        ("#exit", None, exit_tag, True, False),
    ]


class Animal:
    def __init__(self, cry):
        self._cry = cry

    @wrap(all=True)
    def cry(self):
        intensity = 2
        return self._cry * intensity


def test_transform_method():
    cow = Animal("moo")
    data = cow.cry()
    assert data.ret == "moomoo"
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("self", None, None, cow, True),
        ("intensity", None, None, 2, True),
        ("#value", None, None, "moomoo", True),
        ("#exit", None, exit_tag, True, False),
    ]


def test_transform_type_error():
    with pytest.raises(TypeError, match="only works on functions"):
        transform(Animal("meow").cry, lambda *args: args)


def test_varargs():
    @wrap(all=True)
    def nightmare(x, y, *z, **k):
        return x + y + sum(z) + sum(k.values())

    # Keyword arguments in wrap() override variables, to pass
    # keyword arguments to nightmare we need to pass a special
    # KW key.
    data = nightmare(1, 2, 3, 4, KW=dict(a=5, b=6))
    assert data.ret == 21
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("sum", None, None, sum, True),
        ("x", None, None, 1, True),
        ("y", None, None, 2, True),
        ("z", None, None, (3, 4), True),
        ("k", None, None, {"a": 5, "b": 6}, True),
        ("#value", None, None, 21, True),
        ("#exit", None, exit_tag, True, False),
    ]


def test_kwonly():
    @wrap(all=True)
    def waycool(x, *, y):
        return x + y

    data = waycool(21, KW=dict(y=32))
    assert data.ret == 53
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("x", None, None, 21, True),
        ("y", None, None, 32, True),
        ("#value", None, None, 53, True),
        ("#exit", None, exit_tag, True, False),
    ]


def test_error_in_execution():
    verr = ValueError(999)

    @wrap(all=True, allow_errors=True)
    def cheapo(x):
        if x > 0:
            raise verr

    data = cheapo(21)
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("verr", None, None, verr, False),
        ("x", None, None, 21, True),
        ("#error", None, None, verr, False),
        ("#exit", None, exit_tag, True, False),
    ]


def test_generator_interactions():
    data = Interactions()

    @wrap(noreset=True, results=data)
    def genny(x):
        for i in range(x):
            yield i * i
        return -1

    g = genny(3)
    g.send(None)
    g.send(111)
    g.send(222)
    with pytest.raises(StopIteration):
        g.send(333)

    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("range", None, None, range, True),
        ("x", None, None, 3, True),
        ("#loop_i", None, None, True, False),
        ("i", None, None, 0, True),
        ("#yield", None, exit_tag, 0, True),
        ("#receive", None, enter_tag, 111, True),
        ("#endloop_i", None, None, True, False),
        ("#loop_i", None, None, True, False),
        ("i", None, None, 1, True),
        ("#yield", None, exit_tag, 1, True),
        ("#receive", None, enter_tag, 222, True),
        ("#endloop_i", None, None, True, False),
        ("#loop_i", None, None, True, False),
        ("i", None, None, 2, True),
        ("#yield", None, exit_tag, 4, True),
        ("#receive", None, enter_tag, 333, True),
        ("#endloop_i", None, None, True, False),
        ("#value", None, None, -1, True),
        ("#exit", None, exit_tag, True, False),
    ]


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_named_expression():
    from .feat38 import ratatouille

    ratatouille = wrap(ratatouille)

    assert ratatouille(5) == 36
    assert ratatouille(5, y=3) == 9


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_positional():
    from .feat38 import gnarly

    gnarly = wrap(all=True)(gnarly)

    data = gnarly(21, 32)
    assert data.ret == 53
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("x", None, None, 21, True),
        ("y", None, None, 32, True),
        ("#value", None, None, 53, True),
        ("#exit", None, exit_tag, True, False),
    ]


def f(x, y):
    x += 1
    x += 2
    return x + y


def test_augassign():
    f2 = wrap(all=True)(f)
    data = f2(2, 10)
    assert data.ret == 15
    assert data == [
        ("#enter", None, enter_tag, True, False),
        ("x", None, None, 2, True),
        ("y", None, None, 10, True),
        ("x", None, None, 3, True),
        ("x", None, None, 5, True),
        ("#value", None, None, 15, True),
        ("#exit", None, exit_tag, True, False),
    ]


def test_augassign_ignore():
    # Covers the else clause in the augassign transform
    f3 = wrap(all=True, names=["y"])(f)
    data = f3(2, 10)
    assert data == [("y", None, None, 10, True)]


def test_stacked_transforms():
    @contextmanager
    def with_syms(caps=None):
        results = Interactions()
        reset = _current_layer.set((results, {}))
        if caps:
            st.push(caps)
        yield results
        if caps:
            st.pop(caps)
        _current_layer.reset(reset)

    def call(arg):
        fn, *_ = st.get()
        return fn(arg)

    def comb(x):
        y = x + 1
        z = y + 1
        q = z + 1
        return q

    st = StackedTransforms(TransformSet(comb, proceed=SimpleInteractor))

    with with_syms() as results:
        assert st.get()[0] is comb
        call(50)
    assert results == []

    with with_syms(select("comb > x").captures) as results:
        assert st.get()[0] is not comb
        call(50)
    assert st.get()[0] is comb
    assert results.syms() == ["x"]

    with with_syms(select("comb(x) > y").captures) as results:
        call(50)
    assert results.syms() == ["x", "y"]

    with with_syms(select("comb > $x").captures) as results:
        call(50)
    assert results.syms() == ["#enter", "x", "y", "z", "q", "#value", "#exit"]

    with with_syms(select("comb() as fabulous").captures) as results:
        call(50)
    assert results.syms() == ["#value"]

    with with_syms(select("comb > x").captures) as results_outer:
        with with_syms(select("comb > y").captures) as results_inner:
            call(50)
        call(50)
    assert results_outer.syms() == ["x"]
    assert results_inner.syms() == ["x", "y"]

    with with_syms(select("comb > x").captures) as results_outer:
        with with_syms(select("comb > y").captures) as results_inner1:
            with with_syms(select("comb(x) > y").captures) as results_inner2:
                call(50)
            call(50)
        call(50)
    assert results_outer.syms() == ["x"]
    assert results_inner1.syms() == ["x", "y"]
    assert results_inner2.syms() == ["x", "y"]

    with with_syms() as results:
        call(50)
    assert results == []


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="requires python3.8 or higher"
)
def test_stacked_transforms_conform():
    from codefind import conform

    @contextmanager
    def with_syms(caps=None):
        results = Interactions()
        reset = _current_layer.set((results, {}))
        if caps:
            st.push(caps)
        yield results
        if caps:
            st.pop(caps)
        _current_layer.reset(reset)

    def first(x):
        y = 10
        return x + y

    def second(x):
        y = 20
        return x + y

    def third(x):
        y = 30
        return x + y

    orig_code = first.__code__

    st = SyncedStackedTransforms(first, proceed=SimpleInteractor)

    with with_syms(select("first > y").captures) as results:
        assert first(2) == 12
        conform(orig_code, second)
        assert first(2) == 22

    assert first(2) == 22

    assert results == [
        ("y", None, None, 10, True),
        ("y", None, None, 20, True),
    ]

    conform(second.__code__, third)

    with with_syms(select("first > y").captures) as results:
        assert first(2) == 32

    assert results == [
        ("y", None, None, 30, True),
    ]
