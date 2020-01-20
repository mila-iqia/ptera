
from ptera import ptera, Policy, selector as sel


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
def gourgane(z, q):
    return plum(z, q)


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
        "pamplemousse[* as i] >> W": {
            "value": lambda i: i * 10
        }
    })
    with policy:
        assert plum(2, 3) == 220


def test_callcapture():
    policy = Policy({
        "pamplemousse{x} >> W": {
            "value": lambda x: x
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
        assert list(policy.values('xy')) == [4, 9]


def test_tap():
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = plum.tap("xy")(2, 3)
        assert ret == 130
        assert list(xys) == [4, 9]


def test_tap_map():
    policy = Policy({
        "pamplemousse >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = plum.tap("pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys) == [{'x': 2, 'y': 2}, {'x': 3, 'y': 3}]


def test_tap_map2():
    policy = Policy({
        "plum >> W": {
            "value": lambda: 10
        }
    })
    with policy:
        ret, xys = gourgane.tap("plum{a, plum} >> pamplemousse{x, y}")(2, 3)
        assert ret == 130
        assert list(xys) == [{'a': 40, 'plum': 130, 'x': 2, 'y': 2},
                             {'a': 40, 'plum': 130, 'x': 3, 'y': 3}]
