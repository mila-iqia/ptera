from dataclasses import dataclass

from .utils import ABSENT

category_registry = {
    "int": int,
    "float": float,
    "str": str,
    "dict": dict,
    "list": list,
    "tuple": tuple,
}


def register_category(name, obj):
    if name in category_registry:
        assert category_registry[name] == obj
    else:
        category_registry[name] = obj


class Category:
    def __init__(self, name):
        self.name = name
        register_category(self.name, self)

    def __eq__(self, other):
        return isinstance(other, Category) and other.name == self.name

    def __and__(self, other):
        if isinstance(other, CategorySet):
            return CategorySet(other.members | {self})
        else:
            return CategorySet({self, other})

    __rand__ = __and__

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return self.name

    __str__ = __repr__


class CategorySet:
    def __init__(self, members):
        self.members = set(members)

    def __and__(self, other):
        if isinstance(other, CategorySet):
            return CategorySet(self.members | other.members)
        else:
            return CategorySet(self.members | {other})

    __rand__ = __and__

    def __repr__(self):
        return "&".join(map(str, self.members))

    __str__ = __repr__


class _CategoryFactory:
    def __getattr__(self, name):
        return Category(name)


def match_category(to_match, category, value=ABSENT):
    if isinstance(to_match, str):
        to_match = category_registry[to_match]

    if category is None:
        cats = set()
    elif isinstance(category, CategorySet):
        cats = category.members
    else:
        cats = {category}

    rval = False
    if to_match is None:
        rval = True
    elif isinstance(to_match, type) and isinstance(value, to_match):
        rval = True

    for cat in cats:
        if isinstance(cat, type):
            if value is ABSENT:
                if isinstance(to_match, type) and issubclass(cat, to_match):
                    rval = True
            else:
                assert isinstance(value, cat)
        elif (
            isinstance(cat, Category)
            and isinstance(to_match, Category)
            and cat == to_match
        ):
            rval = True

    return rval


cat = _CategoryFactory()
