from dataclasses import dataclass

category_registry = {}


class Category:
    def __init__(self, name, parents=()):
        self.name = name
        self.parents = frozenset(parents)
        if self.name in category_registry:
            assert category_registry[self.name] == self
        else:
            category_registry[self.name] = self

    def matches(self, category):
        return category is self or any(
            parent.matches(category) for parent in self.parents
        )

    def __eq__(self, other):
        return (
            isinstance(other, Category)
            and other.name == self.name
            and other.parents == self.parents
        )

    def __repr__(self):
        return self.name

    __str__ = __repr__
