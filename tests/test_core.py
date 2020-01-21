
from ptera import Category, Policy, ptera, selector as sel

Fruit = Category('Fruit')
Legume = Category('Legume')


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
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        assert plum(2, 3) == 130


def test_callkey():
    policy = Policy({
        "pamplemousse[$i] >> W": {
            "value": lambda i: i * 10
        }
    })
    with policy:
        assert plum(2, 3) == 220


def test_callcapture():
    policy = Policy({
        "pamplemousse{x} >> W": {
            "value": lambda x: x.value
        }
    })
    with policy:
        assert plum(2, 3) == 35


def test_accumulate():
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        },
        "xy": {
            "accumulate": True
        }
    })
    with policy:
        assert plum(2, 3) == 130
        assert list(policy.values('xy').map('xy')) == [4, 9]


def test_tap():
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = plum.tap("xy")(2, 3)
        assert ret == 130
        assert list(xys.map('xy')) == [4, 9]


def test_tap_map():
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = plum.tap("pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys.map()) == [{'x': 2, 'y': 2}, {'x': 3, 'y': 3}]
        assert list(xys.map(lambda x, y: x + y)) == [4, 6]


def test_tap_map2():
    policy = Policy({
        "plum >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = plum.tap("plum{a, plum} >> pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys.map()) == [{'a': 40, 'plum': 130, 'x': 2, 'y': 2},
                                   {'a': 40, 'plum': 130, 'x': 3, 'y': 3}]


def test_category():
    with Policy({}):
        ret, ac = aigle.tap("$f:Fruit")(2, 3)
        assert ret == 64
        assert set(ac.map_full(lambda f: f.name)) == {'a', 'c', 'qq'}
