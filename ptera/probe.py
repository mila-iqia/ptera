import inspect
from contextlib import contextmanager

import rx

from .core import dict_to_pattern_list, global_patterns
from .deco import tooled
from .selector import select
from .tags import tag


def make_resolver(*namespaces):
    """Hook into ptera's selector resolution.

    * Resolve functions in the given namespaces. They will automatically be
      instrumented with ptera.tooled.
    * When a tag is found, instrument all functions in all modules that might
      use that tag (with ptera.tooled).

    Arguments:
        namespaces: A list of globals dicts to find functions and variables in.
    """

    def __ptera_resolver__(x):
        if x.startswith("/"):
            import codefind

            _, module, *parts = x.split("/")
            co = codefind.find_code(*parts, module=module)
            funcs = [
                fn
                for fn in codefind.get_functions(co)
                if inspect.isfunction(fn)
                and not fn.__name__.endswith("__ptera_redirect")
            ]
            (curr,) = funcs

        else:
            varname, *rest = x.split(".")

            if varname.startswith("@"):
                curr = getattr(tag, varname[1:])

            else:
                for ns in namespaces:
                    if varname in ns:
                        curr = ns[varname]
                        seq = [(ns, varname, dict.__setitem__)]
                        break
                else:
                    raise NameError(f"Could not resolve '{varname}'.")

                for part in rest:
                    seq.append((curr, part, setattr))
                    curr = getattr(curr, part)

        if inspect.isfunction(curr):
            # Instrument the function directly
            tooled.inplace(curr)

        # elif isinstance(curr, Tag):
        #     # Instrument existing modules and update substitutions
        #     instrument_for_tag(curr)

        return getattr(curr, "__ptera__", curr)

    return __ptera_resolver__


class Probe(rx.Observable):
    def __init__(self, selector, auto_activate=True, raw=False):
        self.selector = select(selector, env_wrapper=make_resolver)
        self.patterns = dict_to_pattern_list(
            {self.selector: {"immediate": self.emit}}
        )
        self.raw = raw
        self.listeners = []
        self.clisteners = []
        if auto_activate:
            self.activate()

    @property  # pragma: no cover
    @contextmanager
    def lock(self):
        # This is called by throttle_first when on a different thread, I think
        yield None

    def activate(self):
        global_patterns.extend(self.patterns)

    def deactivate(self):
        global_patterns.remove_all(self.patterns)

    def subscribe_(
        self, on_next=None, on_error=None, on_completed=None, scheduler=None
    ):
        if on_next is not None:
            self.listeners.append(on_next)
        if on_completed is not None:
            self.clisteners.append(on_completed)

    def emit(self, **data):
        if not self.raw:
            data = {name: cap.value for name, cap in data.items()}
        for fn in self.listeners:
            fn(data)

    def complete(self):
        for fn in self.clisteners:
            fn()


@contextmanager
def probing(selector, raw=False):
    probe = Probe(selector, raw=raw)
    try:
        yield probe
    finally:
        probe.deactivate()
        probe.complete()
