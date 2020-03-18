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


class PteraDecorator:
    def __init__(self, kwargs):
        self.kwargs = kwargs

    def defaults(self, **defaults):
        return PteraDecorator({**self.kwargs, "defaults": defaults})

    def __call__(self, fn):
        new_fn, state = transform(fn, interact=interact)
        fn = PteraFunction(new_fn, state)
        if "defaults" in self.kwargs:
            fn = fn.new(
                **{
                    k: override(v, -0.5)
                    for k, v in self.kwargs["defaults"].items()
                }
            )
        return fn


tooled = PteraDecorator({})
