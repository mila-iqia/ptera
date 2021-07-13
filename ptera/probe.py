import inspect
from contextlib import contextmanager

import rx

from . import operators as op
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
    """Observable which generates a stream of values from program variables.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> probe = Probe("f > a").pipe(op.getitem("a"))
    >>> probe.subscribe(print)
    >>> f(4)  # Prints 16

    Arguments:
        selector: A selector string describing the variables to probe.
        auto_activate: Whether to activate this probe on creation (default: True)
        raw: Defaults to False. If True, produce a stream of Capture objects that
            contain extra information about the capture. Mostly relevant for
            advanced selectors such as "f > $x:#Parameter" which captures the value
            of any variable with the Parameter tag under the generic name "x".
            When raw is True, the actual name of the variable is preserved in a
            Capture object associated to x.
    """

    def __init__(self, selector, auto_activate=True, raw=False):
        self.selector = select(selector, env_wrapper=make_resolver)
        self.patterns = dict_to_pattern_list(
            {self.selector: {"immediate": self._emit}}
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
        """Activate this Probe."""
        global_patterns.extend(self.patterns)

    def deactivate(self):
        """Deactivate this Probe."""
        global_patterns.remove_all(self.patterns)

    def subscribe_(
        self, on_next=None, on_error=None, on_completed=None, scheduler=None
    ):
        """Subscribe a function to this Probe.

        The function is executed each time the selector's focus variable is
        set.
        """
        if on_next is not None:
            self.listeners.append(on_next)
        if on_completed is not None:
            self.clisteners.append(on_completed)

    def _emit(self, **data):
        """Emit data on the stream.

        This is used internally.
        """
        if not self.raw:
            data = {name: cap.value for name, cap in data.items()}
        for fn in self.listeners:
            fn(data)

    def complete(self):
        """Mark the probe as complete.

        This is necessary in order to trigger operators such as sum or max
        which can only yield a result once the stream is complete.
        """
        for fn in self.clisteners:
            fn()


class LocalProbe:
    """Probe that can be used as a context manager.

    A LocalProbe has ``pipe`` and ``subscribe`` methods like a normal Probe
    or Observable, but must be used as a context manager in order to
    instantiate a real Probe (which is only valid within the context
    manager). The Probe is deactivated and marked as complete at the end of
    the block in order to trigger reduction operators.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> with LocalProbe("f > a").pipe(op.getitem("a")) as probe:
    ...     probe.subscribe(print)
    ...     f(4)  # Prints 16

    Arguments:
        selector: The selector string describing the variables to probe.
        pipes: A list of operators to pipe the stream into.
        subscribes: A list of functions to subscribe to the probe once
            it is created.
        raw: Defaults to False. If True, produce a stream of Capture objects that
            contain extra information about the capture.
    """

    def __init__(self, selector, pipes=[], subscribes=[], raw=False):
        self.probe = None
        self.obs = None
        self.selector = selector
        self.pipes = pipes
        self.subscribes = subscribes
        self.raw = raw

    def pipe(self, *ops):
        """Pipe the stream into the provided operators.

        Arguments:
            ops: A list of operators (ptera.op.getitem, ptera.op.map, etc.)

        Returns:
            A new LocalProbe.
        """
        return LocalProbe(
            self.selector, pipes=[*self.pipes, *ops], subscribes=self.subscribes
        )

    def subscribe(self, *args):
        """Subscribe a function to the stream.

        Arguments:
            args: The same arguments as would be given to rx.Observable.pipe.

        Returns:
            None
        """
        self.subscribes.append(args)

    def __enter__(self):
        assert self.probe is None
        self.probe = Probe(self.selector, raw=self.raw)
        self.obs = self.probe.pipe(*self.pipes)
        for sub in self.subscribes:
            self.obs.subscribe(*sub)
        self.obs._local_probe = self
        return self.obs

    def __exit__(self, exc_type, exc, tb):
        self.probe.deactivate()
        self.probe.complete()
        self.probe = None
        self.obs = None
        return None


def as_local_probe(lprobe, raw=False):
    if isinstance(lprobe, LocalProbe):
        return lprobe
    else:
        return LocalProbe(lprobe, raw=raw)


def probing(selector, *, do=None, format=None, raw=False):
    """Probe that can be used as a context manager.

    ``probing`` is a thin wrapper around ``LocalProbe``.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> with probing("f > a", do=print).pipe(op.getitem("a")):
    ...     f(4)  # Prints 16

    Arguments:
        selector: The selector string describing the variables to probe.
        do: A function to execute on each data point.
        format: A format string (implies do=print)
        raw: Defaults to False. If True, produce a stream of Capture objects that
            contain extra information about the capture.
    """

    lprobe = as_local_probe(selector, raw=raw).pipe()

    if format is not None:
        lprobe = lprobe.pipe(op.format(format))
        if do is None:
            do = print

    if do is not None:
        lprobe.subscribe(do)

    return lprobe


@contextmanager
def accumulate(lprobe):
    """Accumulate variables from a probe into a list.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> with accumulate("f > a") as results:
    ...     f(4)
    ...     f(5)
    ...     assert results == [{"a": 16}, {"a": 25}]

    Arguments:
        lprobe: Either a selector string or a LocalProbe.
    """
    lprobe = as_local_probe(lprobe)
    results = []
    with lprobe as probe:
        probe.subscribe(results.append)
        yield results
