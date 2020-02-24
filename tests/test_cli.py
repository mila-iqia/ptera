import pytest

from ptera import ConflictError, auto_cli, cat, default, ptera

from .common import one_test_per_assert


@ptera
def lager(x, y):
    z: cat.Argument
    return x + y + z


@ptera
def stout(v):
    w: cat.Argument = default(1)
    q: cat.Argument = 2
    a = lager(v, w)
    b = lager(v, q)
    return a, b


@one_test_per_assert
def test_cli():
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3".split()
    ) == (7, 8)
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3 --w=10".split()
    ) == (16, 8)


def test_unknown_argument():
    with pytest.raises(SystemExit):
        auto_cli(stout, (3,), category=cat.Argument, argv="--x=4".split())


def test_conflict():
    with pytest.raises(ConflictError):
        auto_cli(
            stout, (3,), category=cat.Argument, argv="--z=3 --q=10".split()
        )
