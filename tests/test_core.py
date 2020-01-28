import numpy

from ptera import Category, Policy, ptera, selector as sel
from ptera.storage import Storage, initializer, updater, valuer

Bouffe = Category("Bouffe")
Fruit = Category("Fruit", [Bouffe])
Legume = Category("Legume", [Bouffe])


@ptera
def pamplemousse(x, y):
    W: object
    xy = x * y
    return xy * W


@ptera
def plum(x, y):
    a = pamplemousse[1](x, x)
    b = pamplemousse[2](y, y)
    return a + b


@ptera
def hibou(x, y):
    a: Fruit = x * x
    b: Legume = 13
    c: Fruit = y * y
    return a + b + c


@ptera
def aigle(q, z):
    qq: Fruit = q + 1
    zz: Legume = z + 1
    return hibou(q, z) + hibou(qq, zz)


def test_call():
    policy = Policy({"pamplemousse >> W": {"value": lambda: 10}})
    with policy:
        assert plum(2, 3) == 130


def test_callkey():
    policy = Policy(
        {"pamplemousse[$i] >> W": {"value": lambda i: i.value * 10}}
    )
    with policy:
        assert plum(2, 3) == 220


def test_callcapture():
    policy = Policy({"pamplemousse{x} >> W": {"value": lambda x: x.value}})
    with policy:
        assert plum(2, 3) == 35


# def test_accumulate():
#     policy = Policy(
#         {"pamplemousse >> W": {"value": lambda: 10}, "xy": {"accumulate": True}}
#     )
#     with policy:
#         assert plum(2, 3) == 130
#         assert list(policy.values("xy").map("xy")) == [4, 9]


def test_tap():
    policy = Policy({"pamplemousse >> W": {"value": lambda: 10}})
    with policy:
        ret, xys = plum.tap("xy")(2, 3)
        assert ret == 130
        assert list(xys.map("xy")) == [4, 9]


def test_tap_map():
    policy = Policy({"pamplemousse >> W": {"value": lambda: 10}})
    with policy:
        ret, xys = plum.tap("pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys.map()) == [{"x": 2, "y": 2}, {"x": 3, "y": 3}]
        assert list(xys.map(lambda x, y: x + y)) == [4, 6]


def test_tap_map2():
    policy = Policy({"plum >> W": {"value": lambda: 10}})
    with policy:
        ret, xys = plum.tap("plum{a, plum} >> pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys.map()) == [
            {"a": 40, "plum": 130, "x": 2, "y": 2},
            {"a": 40, "plum": 130, "x": 3, "y": 3},
        ]


def test_category():
    with Policy({}):
        ret, ac = aigle.tap("$f:Fruit")(2, 3)
        assert ret == 64
        assert set(ac.map_full(lambda f: f.name)) == {"a", "c", "qq"}


@ptera
def mul(x):
    factor1: Fruit
    factor2: Legume
    factor = factor1 + factor2
    return factor * x


@ptera
def grind(xs):
    acc = 0
    for i, x in enumerate(xs):
        acc += mul[i](x)
    return acc


def test_storage_1():
    class UpdateStrategy(Storage):

        pattern = "$f:Bouffe"
        default_target = "f"

        @valuer(target_name="factor1")
        def init_factor1(self):
            return 1

        @valuer(target_name="factor2")
        def init_factor2(self):
            return 2

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 90


def test_storage_2():
    class UpdateStrategy(Storage):

        pattern = "$f:Bouffe"
        default_target = "f"

        @initializer(target_name="factor1")
        def init_factor1(self):
            return 1

        @initializer(target_name="factor2")
        def init_factor2(self):
            return 2

        @updater
        def update_factor(self, f):
            return f + 1

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 90

    res = g([10, 20])
    assert res == 150


def test_storage_3():
    class UpdateStrategy(Storage):

        pattern = "$f:Bouffe"
        default_target = "f"

        @initializer(target_category=Fruit)
        def init_factor1(self):
            return 1

        @initializer(target_category=Legume)
        def init_factor2(self):
            return 2

        @updater(target_category=Fruit)
        def update_factor(self, f):
            return f + 1

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 90

    res = g([10, 20])
    assert res == 120
