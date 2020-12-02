from itertools import count

from .core import (
    BaseOverlay,
    Overlay,
    PatternCollection,
    PteraFunction,
    interact,
)
from .recur import Recurrence
from .selector import select
from .selfless import ConflictError, Override, default, override, transform
from .tags import Tag, TagSet, match_tag, tag
from .utils import ABSENT

_c = count()


_redirector = """
def {}(*args, **kwargs):
    return {}(*args, **kwargs)
"""


def redirect(fn, new_fn):
    """Redirect fn to new_fn.

    After this, calling fn(...) will be equivalent to calling new_fn(...).
    """
    # We must create a unique global variable to avoid clobbering the same
    # reference with multiple invocations of redirect in the same global
    # scope.
    uniq = f"____ptera_redirect_{next(_c)}"
    fname = f"{fn.__name__}__ptera_redirect"
    glb = {}
    exec(_redirector.format(fname, uniq), glb)
    # The new code will still use the same globals, so we need to inject
    # the new function in there. This is why we generated a unique name.
    fn.__globals__[uniq] = new_fn
    # We replace the code pointer
    fn.__code__ = glb[fname].__code__


class PteraDecorator:
    def __init__(self, defaults={}, inplace=False):
        self._defaults = defaults
        self._inplace = inplace
        if inplace:
            self.inplace = self
        else:
            self.inplace = PteraDecorator(defaults=self._defaults, inplace=True)

    def defaults(self, **defaults):
        return PteraDecorator(defaults={**self._defaults, **defaults})

    def __call__(self, fn):
        if isinstance(fn, PteraFunction):
            return fn
        new_fn, state = transform(fn, interact=interact)
        new_fn = PteraFunction(new_fn, state)
        if self._defaults:
            new_fn = new_fn.new(
                **{k: override(v, -0.5) for k, v in self._defaults.items()}
            )

        if self._inplace:
            redirect(fn, new_fn)
            return fn
        else:
            return new_fn


tooled = PteraDecorator(defaults={})
