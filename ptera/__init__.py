from .categories import Category
from .core import Policy, PteraFunction, interact
from .recur import Recurrence
from .rewrite import transform
from .storage import Storage, initializer, updater, valuer


def ptera(fn):
    fn = transform(fn)
    return PteraFunction(fn)
