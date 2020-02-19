import pytest

from ptera import selector as sel

from .common import one_test_per_assert


def lex(code):
    return [(token.value, token.type) for token in sel.parser.lexer(code)]


@one_test_per_assert
def test_lexer():

    assert lex("apple > banana") == [
        ("apple", "WORD"),
        (">", "OPERATOR"),
        ("banana", "WORD"),
    ]
    assert lex("apple banana cherry") == [
        ("apple", "WORD"),
        ("", "OPERATOR"),
        ("banana", "WORD"),
        ("", "OPERATOR"),
        ("cherry", "WORD"),
    ]
    assert lex("apple:Fruit asparagus") == [
        ("apple", "WORD"),
        (":", "OPERATOR"),
        ("Fruit", "WORD"),
        ("", "OPERATOR"),
        ("asparagus", "WORD"),
    ]
    assert lex("radish > :cake") == [
        ("radish", "WORD"),
        (">", "OPERATOR"),
        (":", "OPERATOR"),
        ("cake", "WORD"),
    ]
    assert lex("radish as cake") == [
        ("radish", "WORD"),
        ("as", "OPERATOR"),
        ("cake", "WORD"),
    ]


@one_test_per_assert
def test_parser_equivalencies():
    assert sel.parse("apple") == sel.parse("(apple)")
    assert sel.parse("a > b > c") == sel.parse("a > (b > c)")
    assert sel.parse("a > b >> c > d") == sel.parse("a > (b >> (c > d))")
    assert sel.parse("* as x") == sel.parse("$x")
    assert sel.parse("a > b > c") == sel.parse("a\n> b\n> c")
    assert sel.parse("a > b > c") == sel.parse("\n  a > b > c\n")

    assert sel.parse("a > b") == sel.parse("a{!b}")
    assert sel.parse("a > b > c") == sel.parse("a > b{!c}")
    assert sel.parse("a > b > c") == sel.parse("a{} > b{!c}")
    assert sel.parse("a >> b") == sel.parse("a{>> !b}")

    assert sel.parse("a > b{c}") == sel.parse("a{b{c}}")
    assert sel.parse("a >> b{c}") == sel.parse("a{>> b{c}}")

    assert sel.parse("a[b]") == sel.parse("a{#key=b}")
    assert sel.parse("a[b] as c") == sel.parse("a{#key=b, !#value as c}")
    assert sel.parse("a{} as b") == sel.parse("a{!#value as b}")


@one_test_per_assert
def test_parser():
    assert sel.parse("apple") == sel.Element(
        name="apple", capture="apple", tags=frozenset({1})
    )

    assert sel.parse("apple > banana") == sel.Call(
        sel.Element("apple"),
        captures=(
            sel.Element("banana", capture="banana", tags=frozenset({1})),
        ),
        immediate=False,
    )

    assert sel.parse("apple >> banana") == sel.Call(
        element=sel.Element("apple"),
        captures=(),
        children=(
            sel.Call(
                element=sel.Element(None),
                captures=(
                    sel.Element(
                        "banana", capture="banana", tags=frozenset({1})
                    ),
                ),
                immediate=False,
                collapse=True,
            ),
        ),
        immediate=False,
    )

    assert sel.parse("apple > banana > cherry") == sel.Call(
        element=sel.Element("apple"),
        children=(
            sel.Call(
                element=sel.Element("banana"),
                captures=(
                    sel.Element(
                        "cherry", capture="cherry", tags=frozenset({1})
                    ),
                ),
                immediate=True,
            ),
        ),
        immediate=False,
    )

    assert sel.parse("*:Fruit") == sel.Element(
        name=None, category="Fruit", capture=None,
    )

    assert sel.parse("apple > :Fruit") == sel.Call(
        element=sel.Element("apple"),
        captures=(
            sel.Element(
                name=None, category="Fruit", capture=None, tags=frozenset({1})
            ),
        ),
        immediate=False,
    )

    assert sel.parse("apple{a}") == sel.Call(
        element=sel.Element("apple"),
        captures=(sel.Element(name="a", capture="a"),),
    )

    assert sel.parse("apple{!a}") == sel.Call(
        element=sel.Element("apple"),
        captures=(sel.Element(name="a", capture="a", tags=frozenset({1})),),
    )

    assert sel.parse("apple{a, b, c, d as e}") == sel.Call(
        element=sel.Element("apple"),
        captures=(
            sel.Element(name="a", capture="a"),
            sel.Element(name="b", capture="b"),
            sel.Element(name="c", capture="c"),
            sel.Element(name="d", capture="e"),
        ),
    )

    assert sel.parse("apple[pie]") == sel.Call(
        element=sel.Element("apple"),
        captures=(sel.Element("#key", value="pie"),),
    )

    assert sel.parse("apple[0]") == sel.Call(
        element=sel.Element("apple"), captures=(sel.Element("#key", value=0),)
    )

    assert sel.parse("apple[* as filling]") == sel.Call(
        element=sel.Element("apple"),
        captures=(sel.Element("#key", capture="filling", key_field="value"),),
    )

    assert sel.parse("axe > bow:Weapon > crowbar[* as length]") == sel.Call(
        element=sel.Element("axe"),
        children=(
            sel.Call(
                element=sel.Element("bow", category="Weapon"),
                children=(
                    sel.Call(
                        element=sel.Element("crowbar"),
                        captures=(
                            sel.Element(
                                name="#key", capture="length", key_field="value"
                            ),
                        ),
                        immediate=True,
                    ),
                ),
                immediate=True,
            ),
        ),
        immediate=False,
    )

    assert sel.parse("$f:Fruit") == sel.Element(
        name=None, category="Fruit", capture="f", key_field="name"
    )

    assert sel.parse("!!x") == sel.Element(
        name="x", category=None, capture="x", tags=frozenset({1, 2})
    )


@one_test_per_assert
def test_to_pattern():
    assert sel.to_pattern("apple") == sel.to_pattern(">> *{!apple}")
    assert sel.to_pattern("pie:Fruit") == sel.to_pattern(">> *{!pie:Fruit}")


@one_test_per_assert
def test_validity():
    assert not sel.parse("a{$b}").valid()
    assert sel.parse("a >> $b").valid()
    assert sel.parse("a{!$b}").valid()
    assert not sel.parse("a{!$b, !$c}").valid()
    assert sel.parse("a{b, c}").valid()
    assert sel.parse("a{!b, c}").valid()
    assert not sel.parse("a{!b, !c}").valid()


def _rewrite(before, after, required, focus=None):
    bef = sel.parse(before)
    transformed = bef.rewrite(required, focus)
    aft = sel.parse(after)
    return transformed == aft


@one_test_per_assert
def test_rewrite():

    assert _rewrite(
        before="bug{world} >> spider{w, e, b}",
        after="bug{world}",
        required=("world",),
    )

    assert _rewrite(
        before="bug{world} > spider{!w, e, b}",
        after="bug > spider{w, !b}",
        required=("w",),
        focus="b",
    )

    assert _rewrite(
        before="bug{world} > spider{!w, e, b}",
        after="bug > spider{!w, b}",
        required=("w", "b",),
    )

    assert _rewrite(
        before="a{b{c}, d{e, f{g}}, h{!i}, j}",
        after="a{d{f{g}}, h{!i}, j}",
        required=("g", "j",),
    )

    assert _rewrite(
        before="a{!b, !c, !d}", after="a{b, !d}", required=("b",), focus="d"
    )

    assert _rewrite(
        before="a[0]{x}", after="a[0]{x}", required=("x",), focus=None,
    )

    assert _rewrite(before="a{!b}", after="a{!b}", required=(), focus="b")

    assert _rewrite(before="a{!b}", after="a{!b}", required=())


@one_test_per_assert
def test_key_captures():
    assert sel.parse("bleu > blanc > rouge").key_captures() == set()
    assert sel.parse("bleu > blanc[$b] > rouge").key_captures() == {
        ("b", "value")
    }
    assert sel.parse("bleu > blanc[$b] > $rouge").key_captures() == {
        ("b", "value"),
        ("rouge", "name"),
    }


@one_test_per_assert
def test_specialize():
    assert sel.parse("co >> co[$n] >> nut").specialize(
        {"n": sel.Element(name=None, value="x")}
    ) == sel.parse("co >> co[x as n] >> nut")

    assert sel.parse("co >> co >> $nut").specialize(
        {"nut": sel.Element(name=None, category="Fruit")}
    ) == sel.parse("co >> co >> $nut:Fruit")

    assert sel.parse("co >> co >> $nut").specialize(
        {"nut": sel.Element(name="coconut", category="Fruit")}
    ) == sel.parse("co >> co >> (coconut as nut):Fruit")
