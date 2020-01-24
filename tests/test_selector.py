import pytest

from ptera import Category, selector as sel

# Categories must be declared to be used
Bouffe = Category("Bouffe")
Fruit = Category("Fruit", [Bouffe])
Weapon = Category("Weapon", [Bouffe])


def test_lexer():
    def lex(code):
        return [(token.value, token.type) for token in sel.parse.lexer(code)]

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


def test_parser_equivalencies():
    assert sel.parse("apple") == sel.parse("(apple)")
    assert sel.parse("a > b > c") == sel.parse("a > (b > c)")
    assert sel.parse("a > b >> c > d") == sel.parse("a > (b >> (c > d))")
    assert sel.parse("* as x") == sel.parse("$x")
    assert sel.parse("a > b > c") == sel.parse("a\n> b\n> c")
    assert sel.parse("a > b > c") == sel.parse("\n  a > b > c\n")


def test_parser():
    assert sel.parse("apple") == sel.Element("apple")

    assert sel.parse("apple > banana") == sel.Nested(
        sel.Call(sel.Element("apple")), sel.Element("banana"), immediate=True,
    )

    assert sel.parse("apple >> banana") == sel.Nested(
        sel.Call(sel.Element("apple")), sel.Element("banana"), immediate=False,
    )

    assert sel.parse("apple > banana > cherry") == sel.Nested(
        sel.Call(sel.Element("apple")),
        sel.Nested(
            sel.Call(sel.Element("banana")),
            sel.Element("cherry"),
            immediate=True,
        ),
        immediate=True,
    )

    assert sel.parse("*:Fruit") == sel.Element(
        name=None, category=Fruit, capture=None,
    )

    assert sel.parse("apple > :Fruit") == sel.Nested(
        sel.Call(sel.Element("apple")),
        sel.Element(name=None, category=Fruit, capture=None,),
        immediate=True,
    )

    assert sel.parse("apple{a}") == sel.Call(
        element=sel.Element("apple"), captures=(("a", "a"),)
    )

    assert sel.parse("apple{a, b, c, d as e}") == sel.Call(
        element=sel.Element("apple"),
        captures=(("a", "a"), ("b", "b"), ("c", "c"), ("d", "e")),
    )

    assert sel.parse("apple[pie]") == sel.Call(
        element=sel.Element("apple"), key=sel.Element("pie")
    )

    assert sel.parse("apple[* as filling]") == sel.Call(
        element=sel.Element("apple"),
        key=sel.Element(name=None, capture="filling"),
    )

    assert sel.parse("axe > bow:Weapon > crowbar[* as length]") == sel.Nested(
        sel.Call(sel.Element("axe")),
        sel.Nested(
            sel.Call(sel.Element("bow", category=Weapon),),
            sel.Call(
                sel.Element("crowbar"),
                key=sel.Element(name=None, capture="length"),
            ),
            immediate=True,
        ),
        immediate=True,
    )

    assert sel.parse("$f:Fruit") == sel.Element(
        name=None, category=Fruit, capture="f",
    )


def test_key_captures():
    assert sel.parse("bleu > blanc > rouge").key_captures() == set()
    assert sel.parse("bleu > blanc[$b] > rouge").key_captures() == {
        ("b", "value")
    }
    assert sel.parse("bleu > blanc[$b] > $rouge").key_captures() == {
        ("b", "value"),
        ("rouge", "name"),
    }


def test_retarget():
    def _test(before, target, after):
        assert sel.parse(before).retarget(target) == sel.parse(after)

    _test("spider{w, e, b}", "b", "spider{w, e} > b")
    _test("spider{w as v, e, b}", "v", "spider{e, b} > w as v")

    _test("bleu{b} > rouge{r} > vert{v}", "b", "bleu > b")
    _test("bleu{b} > rouge{r} > vert{v}", "r", "bleu{b} > rouge > r")


def test_specialize():
    assert sel.parse("co >> co[$n] >> nut").specialize(
        {"n": sel.ElementInfo(name="x")}
    ) == sel.parse("co >> co[x] >> nut")

    assert sel.parse("co >> co >> $nut").specialize(
        {"nut": sel.ElementInfo(name=None, category=Fruit)}
    ) == sel.parse("co >> co >> $nut:Fruit")

    assert sel.parse("co >> co >> $nut").specialize(
        {"nut": sel.ElementInfo(name="coconut", category=Fruit)}
    ) == sel.parse("co >> co >> coconut:Fruit")
