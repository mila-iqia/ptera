from dataclasses import dataclass

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

    def __add__(self, other):
        if isinstance(other, CategorySet):
            return CategorySet(other.members | {self})
        else:
            return CategorySet({self, other})

    __radd__ = __add__

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return self.name

    __str__ = __repr__


class CategorySet:
    def __init__(self, members):
        self.members = set(members)

    def __add__(self, other):
        if isinstance(other, CategorySet):
            return CategorySet(self.members | other.members)
        else:
            return CategorySet(self.members | {other})

    __radd__ = __add__

    def __repr__(self):
        return "+".join(map(str, self.members))

    __str__ = __repr__


class _CategoryFactory:
    def __getattr__(self, name):
        return Category(name)


cat = _CategoryFactory()
