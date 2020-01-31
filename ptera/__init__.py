from .categories import Category
from .core import (
    PatternCollection,
    PteraFunction,
    interact,
    overlay,
    to_pattern,
)
from .recur import Recurrence
from .rewrite import transform

# from .storage import Storage, initializer, updater, valuer


def ptera(fn):
    fn = transform(fn, interact=interact)
    return PteraFunction(fn)
