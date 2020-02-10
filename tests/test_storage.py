from ptera import Category, ptera
from ptera.storage import Storage, initializer, updater, valuer

from .common import Bouffe, Fruit, Legume


@ptera
def mul(x):
    factor1: Fruit
    factor2: Legume
    factor = factor1 + factor2
    return factor * x


@ptera
def grind(xs, start=0):
    acc = start
    for i, x in enumerate(xs):
        acc += mul[i](x)
    return acc


def test_storage_valuer_1():
    class UpdateStrategy(Storage):

        pattern = "mul{x, factor1, factor2}"
        default_target = "f"

        @valuer(target="factor1")
        def init_factor1(self):
            return 1

        @valuer(target="factor2")
        def init_factor2(self):
            return 2

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 90


def test_storage_valuer_2():
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


def test_storage_valuer_3():
    class UpdateStrategy(Storage):

        pattern = "$f:Bouffe"
        default_target = "f"

        @valuer(target_category=Fruit)
        def init_factor1(self):
            return 1

        @valuer(target_category=Legume)
        def init_factor2(self):
            return 2

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 90


def test_storage_valuer_4():
    class UpdateStrategy(Storage):

        pattern = "grind{start} >> $f:Bouffe"
        default_target = "f"

        @valuer
        def init_f(self, start):
            return start

    g = grind.using(UpdateStrategy())
    res = g([10, 20])
    assert res == 0

    res = g([10, 20], start=10)
    assert res == 610


def test_storage_updater_1():
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


def test_storage_updater_2():
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


def test_direct_storage():
    mymul = mul.new(factor1=3, factor2=4)
    assert mymul(10) == 70
