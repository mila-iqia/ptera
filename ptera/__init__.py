from .categories import Category
from .core import (
    PatternCollection,
    PteraFunction,
    interact,
    overlay,
    to_pattern,
)
from .recur import Recurrence
from .selfless import Override, override, transform
from .storage import Storage, initializer, updater, valuer


def ptera(fn):
    new_fn, state = transform(fn, interact=interact)
    return PteraFunction(new_fn, state)
