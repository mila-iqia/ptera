from ptera.tags import match_tag as mt, tag

from .common import one_test_per_assert


@one_test_per_assert
def test_category():
    assert tag.Fruit == tag.Fruit
    assert tag.Fruit is tag.Fruit


@one_test_per_assert
def test_category_set():
    assert (tag.Foo & tag.Baz & tag.Bar & tag.Baz).members == {
        tag.Foo,
        tag.Bar,
        tag.Baz,
    }
    assert (tag.Foo & int).members == {tag.Foo, int}
    assert (int & tag.Foo).members == {tag.Foo, int}


@one_test_per_assert
def test_category_repr():
    assert str(tag.Fruit) == "ptera.tag.Fruit"
    assert repr(tag.Fruit) == "ptera.tag.Fruit"
    assert str(tag.Foo & tag.Bar) == "ptera.tag.Bar & ptera.tag.Foo"
    assert (
        str(tag.Foo & tag.Bar & tag.Baz)
        == "ptera.tag.Bar & ptera.tag.Baz & ptera.tag.Foo"
    )


@one_test_per_assert
def test_match_tag():
    assert mt(tag.Fruit, tag.Fruit)
    assert mt(tag.Fruit, tag.Fruit & tag.Legume)
    assert not mt(tag.Fruit, tag.Legume)
    assert mt(tag.Fruit, tag.Fruit & int)
