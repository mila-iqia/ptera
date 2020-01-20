from .core import Policy, PteraFunction, interact
from .rewrite import transform


def ptera(fn):
    fn = transform(fn)
    return PteraFunction(fn)
