from ptera import Overlay, tooled


def __ptera_resolver__(x):
    env = globals()
    start, *parts = [f"X{part}" for part in x.split(".")]
    if start in env:
        curr = env[start]
    else:
        raise Exception(f"Could not resolve '{start}'.")

    for part in parts:
        curr = getattr(curr, part)

    return curr


@tooled
def Xcrouton(x, y):
    return x + y + z


class X:
    pass


Xpain = X()
Xpain.Xmie = Xcrouton


def test_custom():
    with Overlay.tweaking({"crouton > z": 3}):
        assert Xcrouton(3, 4) == 10

    with Overlay.tweaking({"pain.mie > z": 23}):
        assert Xpain.Xmie(3, 4) == 30
