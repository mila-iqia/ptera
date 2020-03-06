import json

import pytest

from ptera import (
    ArgsExpander,
    ConflictError,
    auto_cli,
    cat,
    catalogue,
    default,
    ptera,
)
from ptera.core import ABSENT

from .common import one_test_per_assert


@ptera
def lager(x, y):
    z: cat.Argument & cat.Bargument & int
    return x + y + z


@ptera
def stout(v):
    # Double you,
    # Double me
    w: cat.Argument & int = default(1)
    # This is your cue
    q: cat.Argument & int = 2
    a = lager(v, w)
    b = lager(v, q)
    return a, b


@ptera
def thing():
    arg: cat.Argument & str
    return arg


@ptera
def thingy():
    arg: cat.Argument
    return arg


def test_catalogue():
    assert catalogue(lager) == {
        lager: {
            "cat": {"annotation": ABSENT, "doc": None},
            "int": {"annotation": ABSENT, "doc": None},
            "x": {"annotation": ABSENT, "doc": None},
            "y": {"annotation": ABSENT, "doc": None},
            "z": {
                "annotation": cat.Argument & cat.Bargument & int,
                "doc": None,
            },
        },
    }

    assert catalogue(stout) == {
        **catalogue(lager),
        stout: {
            "cat": {"annotation": ABSENT, "doc": None},
            "int": {"annotation": ABSENT, "doc": None},
            "w": {
                "annotation": cat.Argument & int,
                "doc": "Double you,\nDouble me",
            },
            "q": {"annotation": cat.Argument & int, "doc": "This is your cue"},
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
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3".split()
    ) == (7, 8)
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv="--z=3 --w=10".split()
    ) == (16, 8)
    assert auto_cli(
        stout, (3,), category=cat.Bargument, argv="--z=3".split()
    ) == (7, 8)

    assert (
        auto_cli(thingy, (), category=cat.Argument, argv=["--arg", "1"]) == "1"
    )
    assert (
        auto_cli(thingy, (), category=cat.Argument, argv=["--arg", "xyz"])
        == "xyz"
    )
    assert (
        auto_cli(
            thingy,
            (),
            category=cat.Argument,
            eval_env={"foo": "bar"},
            argv=["--arg", ":foo"],
        )
        == "bar"
    )
    assert auto_cli(
        thingy,
        (),
        category=cat.Argument,
        eval_env={"foo": [1, 2, 3]},
        argv=["--arg", ":foo"],
    ) == [1, 2, 3]

    assert (
        auto_cli(
            thing,
            (),
            category=cat.Argument,
            eval_env={"foo": [1, 2, 3]},
            argv=["--arg", ":foo"],
        )
        == ":foo"
    )


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
        stout,
        (3,),
        category=cat.Argument,
        argv=[],
        expand=ArgsExpander("@", default_file=cfg1),
    ) == (16, 8)

    assert auto_cli(
        stout,
        (3,),
        category=cat.Argument,
        argv=[f"@{cfg1.strpath}"],
        expand="@",
    ) == (16, 8)

    assert auto_cli(
        stout,
        (3,),
        category=cat.Argument,
        argv=[f"&{cfg1.strpath}"],
        expand="@&",
    ) == (16, 8)

    cfg2 = tmpdir.join("config2.json")
    with pytest.raises(SystemExit) as exc:
        auto_cli(
            stout,
            (3,),
            category=cat.Argument,
            argv=f"@{cfg2.strpath}".split(),
            expand="@",
        )
    assert exc.value.code == 2

    cfg3 = tmpdir.join("config3.json")
    cfg3.write(json.dumps({"#include": cfg1.strpath, "w": 10}))
    assert auto_cli(
        stout,
        (3,),
        category=cat.Argument,
        argv=[],
        expand=ArgsExpander("@", default_file=cfg3),
    ) == (16, 8)

    assert auto_cli(
        stout, (3,), category=cat.Argument, argv=[{"#include": cfg1.strpath}],
    ) == (16, 8)


def test_config_dict():
    assert auto_cli(
        stout, (3,), category=cat.Argument, argv=[{"z": 3, "w": 10}],
    ) == (16, 8)

    assert (
        auto_cli(
            patriotism,
            (),
            category=cat.Argument,
            argv=[{"flag": True, "times": 2}],
        )
        == "wavewave"
    )

    assert (
        auto_cli(patriotism, (), category=cat.Argument, argv=[{"flag": False}],)
        == "don't wave"
    )


def test_subcommands():
    assert (
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv="thingy --arg xyz".split(),
        )
        == "xyz"
    )

    assert (
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv="patriotism --flag".split(),
        )
        == "wave"
    )

    with pytest.raises(SystemExit) as exc:
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv="thingy --flag".split(),
        )
    assert exc.value.code == 2

    assert (
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv=["patriotism", {"flag": True}],
        )
        == "wave"
    )


def test_config_subcommands(tmpdir):
    cfg1 = tmpdir.join("config1.json")
    cfg1.write(json.dumps({"flag": True}))

    assert (
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv=f"patriotism @{cfg1.strpath}".split(),
            expand="@",
        )
        == "wave"
    )

    cfg2 = tmpdir.join("config2.json")
    with pytest.raises(SystemExit) as exc:
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv=f"patriotism @{cfg2.strpath}".split(),
            expand="@",
        )
    assert exc.value.code == 2

    cfg3 = tmpdir.join("config1.json")
    cfg3.write(json.dumps({"#command": "patriotism", "flag": True}))
    assert (
        auto_cli(
            {"thingy": thingy, "patriotism": patriotism},
            (),
            category=cat.Argument,
            argv=f"@{cfg3.strpath}".split(),
            expand="@",
        )
        == "wave"
    )
