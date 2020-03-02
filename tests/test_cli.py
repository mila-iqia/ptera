import json

import pytest

from ptera import ConflictError, auto_cli, cat, catalogue, default, ptera
from ptera.core import ABSENT

from .common import one_test_per_assert


@ptera
def lager(x, y):
    z: cat.Argument & cat.Bargument
    return x + y + z


@ptera
def stout(v):
    # Double you,
    # Double me
    w: cat.Argument = default(1)
    # This is your cue
    q: cat.Argument = 2
    a = lager(v, w)
    b = lager(v, q)
    return a, b


def test_catalogue():
    assert catalogue(lager) == {
        lager: {
            "cat": {"annotation": ABSENT, "doc": None},
            "x": {"annotation": ABSENT, "doc": None},
            "y": {"annotation": ABSENT, "doc": None},
            "z": {"annotation": cat.Argument & cat.Bargument, "doc": None},
        },
    }

    assert catalogue(stout) == {
        **catalogue(lager),
        stout: {
            "cat": {"annotation": ABSENT, "doc": None},
            "w": {"annotation": cat.Argument, "doc": "Double you,\nDouble me"},
            "q": {"annotation": cat.Argument, "doc": "This is your cue"},
            "a": {"annotation": ABSENT, "doc": None},
            "b": {"annotation": ABSENT, "doc": None},
            "default": {"annotation": ABSENT, "doc": None},
            "lager": {"annotation": ABSENT, "doc": None},
            "v": {"annotation": ABSENT, "doc": None},
        },
    }

    assert catalogue([lager, stout]) == catalogue(stout)


@one_test_per_assert
def test_cli():
    assert (
        auto_cli(lager, ("a", "b"), category=cat.Argument, argv="--z=c".split())
        == "abc"
    )
    assert (
        auto_cli(
            lager,
            ("a", "b"),
            category=cat.Argument,
            argv="--z=:foo".split(),
            eval_env={"foo": "c"},
        )
        == "abc"
    )
    assert (
        auto_cli(
            lager,
            (3, 2),
            category=cat.Argument,
            argv="--z=:math:cos(0)".split(),
        )
        == 6
    )
    assert (
        auto_cli(lager, (3, 2), category=cat.Argument, argv="--z=True".split(),)
        == 6
    )
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3".split()
    ) == (7, 8)
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3 --w=10".split()
    ) == (16, 8)
    assert auto_cli(
        stout, (3,), category=cat.Bargument, argv="--z=3".split()
    ) == (7, 8)


def test_no_env():
    with pytest.raises(Exception):
        auto_cli(
            lager, ("a", "b"), category=cat.Argument, argv="--z=:foo".split(),
        )


def test_unknown_argument():
    with pytest.raises(SystemExit) as exc:
        auto_cli(stout, (3,), category=cat.Argument, argv="--x=4".split())
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        auto_cli(
            stout, (3,), category=cat.Bargument, argv="--z=3 --w=10".split()
        )
    assert exc.value.code == 2


def test_conflict():
    with pytest.raises(ConflictError):
        auto_cli(
            stout, (3,), category=cat.Argument, argv="--z=3 --q=10".split()
        )


@ptera
def patriotism():
    flag: cat.Argument & bool = default(True)
    times: cat.Argument & int = default(1)
    if flag:
        return "wave" * times
    else:
        return "don't wave"


def test_types():
    assert auto_cli(patriotism, (), category=cat.Argument, argv=[]) == "wave"
    assert (
        auto_cli(patriotism, (), category=cat.Argument, argv="--flag".split())
        == "wave"
    )
    assert (
        auto_cli(
            patriotism, (), category=cat.Argument, argv="--no-flag".split()
        )
        == "don't wave"
    )
    assert (
        auto_cli(
            patriotism,
            (),
            category=cat.Argument,
            argv="--flag --times=3".split(),
        )
        == "wavewavewave"
    )
    with pytest.raises(SystemExit) as exc:
        auto_cli(patriotism, (), category=cat.Argument, argv="--flag=1".split())
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        auto_cli(
            patriotism, (), category=cat.Argument, argv="--times=ohno".split()
        )
    assert exc.value.code == 2


def test_config_file(tmpdir):
    cfg1 = tmpdir.join("config1.json")
    cfg1.write(json.dumps({"z": 3, "w": 10}))

    assert auto_cli(
        stout, (3,), category=cat.Argument, argv=[], default_config_file=cfg1
    ) == (16, 8)

    assert auto_cli(
        stout,
        (3,),
        category=cat.Argument,
        argv=["--config", cfg1.strpath],
        config_option=True,
    ) == (16, 8)

    assert auto_cli(
        stout,
        (3,),
        category=cat.Argument,
        argv=["--xxxx", cfg1.strpath],
        config_option="xxxx",
    ) == (16, 8)

    cfg2 = tmpdir.join("config2.json")
    with pytest.raises(SystemExit) as exc:
        auto_cli(
            stout,
            (3,),
            category=cat.Argument,
            argv=f"--z=4 --w=11 --save-config {cfg2.strpath}".split(),
            config_option=True,
        )
    assert exc.value.code == 0

    assert json.loads(cfg2.read()) == {"z": "4", "w": "11"}

    cfg3 = tmpdir.join("config3.json")
    with pytest.raises(SystemExit) as exc:
        auto_cli(
            stout,
            (3,),
            category=cat.Argument,
            argv=f"--xxxx {cfg1.strpath} --save-xxxx {cfg3.strpath}".split(),
            config_option="xxxx",
        )
    assert exc.value.code == 0

    assert json.loads(cfg1.read()) == json.loads(cfg3.read())

    cfg4 = tmpdir.join("config4.json")
    with pytest.raises(SystemExit) as exc:
        auto_cli(
            stout,
            (3,),
            category=cat.Argument,
            argv=f"--config {cfg4.strpath}".split(),
            config_option=True,
        )
    assert exc.value.code == 1
