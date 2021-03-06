import pytest

from ptera import BaseOverlay, Overlay, Recurrence, select, tag, tooled
from ptera.core import Capture, Tap
from ptera.selector import Element, parse
from ptera.selfless import default
from ptera.tools import every

from .common import one_test_per_assert


@tooled
def brie(x, y) -> tag.Fromage:
    """Brie is a sort of cheese."""
    a: tag.Bouffe = x * x
    b: "@Bouffe & @Agrement" = y * y
    return a + b


@tooled
def extra(cheese):
    return cheese + 1


@tooled
@tooled
@tooled
def double_brie(x1, y1):
    a = brie[[1]](x1, x1 + 1)
    b = brie[[2]](y1, y1 + 1)
    aa = extra[[1]](a)
    bb = extra[[2]](b)
    return aa + bb


@one_test_per_assert
def test_normal_call():
    assert brie(3, 4) == 25
    assert double_brie(3, 4) == 68


class GrabAll:
    def __init__(self, pattern):
        self.results = []
        pattern = select(pattern)

        def listener(**kwargs):
            self.results.append(
                {name: cap.values for name, cap in kwargs.items()}
            )

        self.rules = {pattern: {"listeners": listener}}


def _test(f, args, pattern):
    store = GrabAll(pattern)
    with BaseOverlay(store.rules):
        f(*args)
    return store.results


def _dbrie(pattern):
    return _test(double_brie, (2, 10), pattern)


@one_test_per_assert
def test_patterns():
    # Simple, test focus
    assert _dbrie("*(x)") == [{"x": [2]}, {"x": [10]}]
    assert _dbrie("*(!x)") == [{"x": [2]}, {"x": [10]}]
    assert _dbrie("*(!x, y)") == [{"x": [2], "y": [3]}, {"x": [10], "y": [11]}]
    assert _dbrie("*(x, y)") == [{"x": [2], "y": [3]}, {"x": [10], "y": [11]}]

    # Simple
    assert _dbrie("*(!a)") == [{"a": [4]}, {"a": [100]}, {"a": [13]}]
    assert _dbrie("brie(!a)") == [{"a": [4]}, {"a": [100]}]

    # Indirect
    assert _dbrie("a") == [{"a": [4]}, {"a": [100]}, {"a": [13]}]
    assert _dbrie("double_brie >> a") == [{"a": [13]}, {"a": [4]}, {"a": [100]}]
    assert _dbrie("double_brie >> x") == [{"x": [2]}, {"x": [10]}]

    # Multi-level
    assert _dbrie("double_brie(a) > brie(x)") == [{"a": [13], "x": [2, 10]}]
    assert _dbrie("double_brie(a) > brie(!x)") == [
        {"a": [13], "x": [2]},
        {"a": [13], "x": [10]},
    ]

    # Accumulate values across calls
    assert _dbrie("double_brie(extra(cheese), brie(x))") == [
        {"cheese": [13, 221], "x": [2, 10]}
    ]
    assert _dbrie("double_brie(extra(!cheese), brie(x))") == [
        {"cheese": [13], "x": [2, 10]},
        {"cheese": [221], "x": [2, 10]},
    ]

    # Indexing
    assert _dbrie("brie[[$i]](!a)") == [
        {"a": [4], "i": [1]},
        {"a": [100], "i": [2]},
    ]
    assert _dbrie("brie[[1]](!a)") == [{"a": [4]}]
    assert _dbrie("brie[[1.0]](!a)") == [{"a": [4]}]
    assert _dbrie("brie[[2]](!a)") == [{"a": [100]}]

    # Parameter
    assert _dbrie("brie($v:tag.Bouffe)") == [{"v": [4, 9]}, {"v": [100, 121]}]
    assert _dbrie("brie($v:@Bouffe)") == [{"v": [4, 9]}, {"v": [100, 121]}]
    assert _dbrie("brie(!$v:tag.Bouffe)") == [
        {"v": [4]},
        {"v": [9]},
        {"v": [100]},
        {"v": [121]},
    ]
    assert _dbrie("*(a) >> brie(!$v:tag.Bouffe)") == [
        {"a": [13], "v": [4]},
        {"a": [13], "v": [9]},
        {"a": [13], "v": [100]},
        {"a": [13], "v": [121]},
    ]

    # Function category
    assert _dbrie("*:tag.Fromage(a)") == [{"a": [4]}, {"a": [100]}]

    # Inexistent category
    assert _dbrie("brie > $x:tag.Xylophone") == []

    # Filter on value
    assert _dbrie("brie(!x, y, a=4)") == [{"x": [2], "y": [3]}]
    assert _dbrie("double_brie(x1=2) > brie > x") == [{"x": [2]}, {"x": [10]}]
    assert _dbrie("double_brie(#value=1234) > brie > x") == []


@tooled
def snapple(x):
    a = cabanana(x + 1)
    b = cabanana(x + 2)
    return a + b


@tooled
def cabanana(y):
    return peacherry(y + 1)


@tooled
def peacherry(z):
    return z + 1


def test_deep():
    assert _test(snapple, [5], "snapple > cabanana(y) > peacherry > z") == [
        {"y": [6], "z": [7]},
        {"y": [7], "z": [8]},
    ]


@tooled
def fib(n):
    f = Recurrence(2)
    f[0] = 1
    f[1] = 1
    for i in range(2, n + 1):
        f[i] = f[i - 1] + f[i - 2]
    return f[n]


even = every(2)


def test_match():
    res, fs = fib.using("f[~even] as x")(5)
    assert fs.map("x") == [1, 2, 5]

    res, fs = fib.using("f[$i ~ every(2)] as x")(5)
    assert fs.map("x") == [1, 2, 5]

    res, fs = fib.using("f[$i ~ every(2, start=1)] as x")(5)
    assert fs.map("x") == [1, 3, 8]

    res, fs = fib.using("f[$i ~ even] as x")(5)
    assert fs.map("i", "x") == [(0, 1), (2, 2), (4, 5)]


def test_indexing():
    assert fib(5) == 8

    res, fs = fib.using("f[0] as x")(5)
    assert fs.map("x") == [1]

    res, fs = fib.using("'f'(#key=0) as x")(5)
    assert fs.map("x") == [1]

    res, fs = fib.using("f[$i] as x")(5)
    intermediates = [1, 1, 2, 3, 5, 8]
    indices = list(range(6))
    assert fs.map("x") == intermediates
    assert fs.map("i") == indices
    assert fs.map("i", "x") == list(zip(indices, intermediates))


def test_indexing_2():
    res, fs = fib.full_tapping("fib(!n, f[3] as x)")(5)
    assert res == 8
    assert fs.map("n") == [5]
    assert fs.map("x") == [3]


def test_attach():
    _brie = brie.attach(hello=12).using("brie > #hello")
    res, hello = _brie(5, 6)
    assert hello.map("hello") == [12]


@tooled
def superbrie(n):
    result = 0
    k = 0
    for i in range(n):
        for j in range(n):
            result += brie[[i, j]](k, 2)
            k = k + 1
    return result


def test_function_indexing():
    assert superbrie(10) == 328750

    _, x = superbrie.using("brie[[1, $j]] > x")(10)
    assert x.map("j") == list(range(10))
    assert x.map("x") == list(range(10, 20))

    _, x = superbrie.using("brie[[1, $j ~ every(3)]] > x")(10)
    assert x.map("x") == list(range(10, 20, 3))


def test_immediate_evaluation():
    # This uses a GetterAccumulator
    ss = superbrie.rewriting({"superbrie(k=7) > brie > x": (lambda: 0)})
    assert ss(10) == 328701

    # This uses a GetterAccumulator
    ss = superbrie.rewriting({"superbrie(i=9) > brie > x": (lambda: 0)})
    assert ss(10) == 239365

    # By default this uses a TotalAccumulator, which requires every
    # value of i to be 1 and every j to be a multiple of 3
    _, x = superbrie.full_tapping("superbrie(i=1, j~every(3)) > brie > x")(10)
    assert x.map("x") == []

    # Creates a SetterAccumulator which only takes into account the values
    # of i and j at the moment the focus variable x is triggered
    _, x = superbrie.using(
        Tap("superbrie(i=1, j~every(3)) > brie > x", immediate=True)
    )(10)
    assert x.map("x") == list(range(10, 20, 3))


def test_nested_overlay():
    expectedx = [{"x": [2]}, {"x": [10]}]
    expectedy = [{"y": [3]}, {"y": [11]}]

    storex = GrabAll("brie > x")
    storey = GrabAll("brie > y")
    with BaseOverlay({**storex.rules, **storey.rules}):
        assert double_brie(2, 10) == 236
    assert storex.results == expectedx
    assert storey.results == expectedy

    storex = GrabAll("brie > x")
    storey = GrabAll("brie > y")
    with BaseOverlay(storex.rules):
        with BaseOverlay(storey.rules):
            assert double_brie(2, 10) == 236
    assert storex.results == expectedx
    assert storey.results == expectedy


@tooled
def mystery(hat):
    surprise: tag.MyStErY
    return surprise * hat


def test_provide_var():
    with BaseOverlay({"mystery(!surprise)": {"value": lambda surprise: 4}}):
        assert mystery(10) == 40

    with BaseOverlay(
        {"mystery(hat, !surprise)": {"value": lambda hat, surprise: hat.value}}
    ):
        assert mystery(8) == 64


def test_missing_var():
    try:
        mystery(3)
    except NameError as err:
        assert err.varname == "surprise"
        assert err.function == mystery
        info = err.info()
        assert info["annotation"] == tag.MyStErY

    with pytest.raises(NameError):
        mystery.tweaking({"mystery(hat=10) > surprise": 0})(3)


def test_tap_map():
    rval, acoll = double_brie.full_tapping("brie(!a, b)")(2, 10)
    assert acoll.map("a") == [4, 100]
    assert acoll.map("b") == [9, 121]
    assert acoll.map(lambda a, b: a + b) == [13, 221]
    assert acoll.map() == [{"a": 4, "b": 9}, {"a": 100, "b": 121}]
    assert acoll.map(lambda **kwargs: kwargs["a"] + kwargs["b"]) == [13, 221]


def test_tap_map_all():
    rval, acoll = double_brie.full_tapping("double_brie(!x1) >> brie(x)")(2, 10)
    with pytest.raises(ValueError):
        acoll.map("x1", "x")
    assert acoll.map_all("x1", "x") == [([2], [2, 10])]
    assert acoll.map_all() == [{"x1": [2], "x": [2, 10]}]


def test_tap_map_named():
    rval = double_brie.using(data="brie(!a, b)")(2, 10)
    assert rval.value == 236
    assert rval.data.map("a") == [4, 100]


def test_tap_map_full():
    rval, acoll = double_brie.using("brie > $param:tag.Bouffe")(2, 10)
    assert acoll.map_full(lambda param: param.value) == [4, 9, 100, 121]
    assert acoll.map_full(lambda param: param.name) == ["a", "b", "a", "b"]


def test_on():
    dbrie = double_brie.clone(return_object=True)

    @dbrie.on("brie > x")
    def minx(x):
        return -x

    @dbrie.on("brie > x", all=True)
    def minx_all(x):
        return [-v for v in x]

    @dbrie.on("brie > x", full=True)
    def minx_full(x):
        assert x.name == "x"
        return -x.value

    results = dbrie(2, 10)
    assert results.minx == [-2, -10]
    assert results.minx_all == [[-2], [-10]]
    assert results.minx_full == [-2, -10]


def test_use():
    dbrie = double_brie.clone(return_object=True)
    dbrie.use(data="brie(!a, b)")
    rval = dbrie(2, 10)
    assert rval.value == 236
    assert rval.data.map() == [{"a": 4}, {"a": 100}]


def test_full_tap():
    dbrie = double_brie.clone(return_object=True)
    dbrie.full_tap(data="brie(!a, b)")
    rval = dbrie(2, 10)
    assert rval.value == 236
    assert rval.data.map("a") == [4, 100]
    assert rval.data.map("b") == [9, 121]


def test_tweak():
    dbrie = double_brie.clone()
    dbrie.tweak({"brie > x": 10})
    assert dbrie(2, 10) == 332


def test_rewrite():
    dbrie = double_brie.clone()
    dbrie.rewrite({"brie(x, !y)": lambda x: x})
    assert dbrie(2, 10) == 210


def test_collect():
    dbrie = double_brie.clone(return_object=True)

    @dbrie.collect("brie > x")
    def sumx(xs):
        return sum(xs.map("x"))

    results = dbrie(2, 10)
    assert results.sumx == 12


@tooled
def square(x):
    rval = x * x
    return rval


@tooled
def sumsquares(x, y):
    xx = square(x)
    yy = square(y)
    rval = xx + yy
    return rval


def test_readme():
    results = sumsquares.using(q="x")(3, 4)
    assert results.q.map("x") == [3, 3, 4]

    results = sumsquares.using(q="square > x")(3, 4)
    assert results.q.map("x") == [3, 4]

    results = sumsquares.full_tapping(q="square(rval) > x")(3, 4)
    assert results.q.map("x", "rval") == [(3, 9), (4, 16)]

    results = sumsquares.full_tapping(
        q="sumsquares(x as ssx, y as ssy) > square(rval) > x"
    )(3, 4)
    assert results.q.map("ssx", "ssy", "x", "rval") == [
        (3, 4, 3, 9),
        (3, 4, 4, 16),
    ]

    results = sumsquares.full_tapping(
        q="sumsquares(!x as ssx, y as ssy) > square(rval, x)"
    )(3, 4)
    assert results.q.map_all("ssx", "ssy", "x", "rval") == [
        ([3], [4], [3, 4], [9, 16])
    ]

    result = sumsquares.tweaking({"square > rval": 0})(3, 4)
    assert result == 0

    result = sumsquares.rewriting({"square(x) > rval": lambda x: x + 1})(3, 4)
    assert result == 9


@tooled.defaults(x=10, y=20)
def vanilla(x, y):
    return x * y


def test_ptera_defaults():
    assert vanilla() == 200
    assert vanilla(4, 5) == 20


def test_capture():
    cap = Capture(parse("x"))
    assert cap.name == "x"
    with pytest.raises(ValueError):
        cap.value
    cap.accum("x", 1)
    assert cap.name == "x"
    assert cap.value == 1
    cap.accum("x", 2)
    with pytest.raises(ValueError):
        cap.value

    assert str(cap) == "Capture(sel(\"!x\"), ['x', 'x'], [1, 2])"

    cap = Capture(Element(name=None))
    with pytest.raises(ValueError):
        cap.name
    cap.accum("y", 7)
    assert cap.name == "y"
    assert cap.value == 7
    cap.accum("z", 31)
    with pytest.raises(ValueError):
        cap.name
    with pytest.raises(ValueError):
        cap.value


@tooled
def cake():
    flavour: tag.Flavour
    return f"This is a {flavour} cake"


@tooled
def fruitcake():
    my_cake = cake.new(flavour="fruit").clone(return_object=True)

    @my_cake.on("flavour")
    def yum(flavour):
        return flavour * 2

    return my_cake()


def test_listener_within_ptera():
    res = fruitcake()
    assert res.value == "This is a fruit cake"
    assert res.yum == ["fruitfruit"]


def test_doc():
    assert brie.__doc__ == """Brie is a sort of cheese."""


class Matou:
    def __init__(self, species):
        self.species = species

    @tooled
    def meow(self, repeat=1):
        ms = "m"
        es = "e"
        os = "o" * repeat
        ws = "w" * len(self.species)
        cry = ms + es + os + ws
        meows = [cry] * repeat
        return " ".join(meows)


def test_method():
    siamese = Matou("siamese")
    assert siamese.meow() == "meowwwwwww"

    assert siamese.meow.tweaking({"Matou.meow > es": "eee"})() == "meeeowwwwwww"

    with Overlay.tweaking({"Matou.meow > es": "eee"}):
        assert siamese.meow() == "meeeowwwwwww"

    with Overlay.tweaking({"Matou.meow > repeat": 2}):
        assert siamese.meow() == "meoowwwwwww meoowwwwwww"

    store = GrabAll("Matou.meow(repeat) > os")
    with BaseOverlay(store.rules):
        for i in range(3):
            siamese.meow(i)
    assert store.results == [
        {"os": [""], "repeat": [0]},
        {"os": ["o"], "repeat": [1]},
        {"os": ["oo"], "repeat": [2]},
    ]


def test_overlay():
    def twice_mystery(x):
        return mystery(x), mystery(x + 1)

    ov = Overlay()
    ov.tweak({"surprise": 2})

    @ov.on("mystery > hat")
    def hats(hat):
        return hat * hat

    @ov.on("mystery(hat) > surprise")
    def shats(surprise, hat):
        return (surprise, hat)

    with ov as results:
        assert twice_mystery(10) == (20, 22)

    assert results.hats == [100, 121]
    assert results.shats == [(2, 10), (2, 11)]


@tooled
def brooms(xs):
    rval = 0
    for i, x in enumerate(xs):
        rval = rval + (i + 1) * x
    return rval


def test_for_loop():
    assert brooms([1, 2, 3]) == 14
    assert brooms.tweaking({"i": 0})([1, 2, 3]) == 6


@tooled
def multitag():
    y: tag.Bouffe = default(10)
    y = y * y
    return y


def test_samevar_multitag():
    assert multitag() == 100
    with Overlay.tweaking({"y:tag.Bouffe": 5}):
        assert multitag() == 25
    with Overlay.tweaking({"y:tag.Irrelevant": 5}):
        assert multitag() == 100


def test_redirect():
    def funkykong(x):
        surf: tag.Surfboard = True
        return x * x if surf else x

    orig_funky = funkykong
    new_funky = tooled.inplace(funkykong)

    assert funkykong is orig_funky
    assert funkykong is new_funky

    assert funkykong(10) == 100
    with Overlay.tweaking({"surf:tag.Surfboard": False}):
        assert funkykong(10) == 10
    assert funkykong(10) == 100


def test_redirect_noclobber():
    def one():
        x = 1
        return x

    def two():
        x = 1
        return x * 2

    tooled.inplace(one)
    tooled.inplace(two)

    assert one() == 1
    assert two() == 2

    with Overlay.tweaking({"x": 7}):
        assert one() == 7
        assert two() == 14


def exposure(n):
    x = 2
    return n ** x


def test_redirect_global():
    old_exposure = exposure

    tooled.inplace(exposure)
    assert exposure(8) == 64

    with Overlay.tweaking({"x": 3}):
        assert exposure(8) == 512

    assert old_exposure is exposure
