import atexit

from giving import SourceProxy

from .interpret import Immediate, Total
from .overlay import BaseOverlay, autotool
from .selector import select
from .utils import ABSENT

global_probes = set()


def _identity(x):
    return x


class Probe(SourceProxy):
    """Observable which generates a stream of values from program variables.

    Probes should be created with
    :func:`~ptera.probe.probing` or :func:`~ptera.probe.global_probe`.

    .. note::
        In the documentation for some methods you may see calls to ``give()``
        or ``given()``, but that's because they come from the documentation
        for the ``giving`` package (on top of which Probe is built).

        ``give()`` is equivalent to what Ptera does when a
        variable of interest is set, ``given()`` yields an object that has
        the same interface as ``Probe`` (the superclass to ``Probe``, in
        fact). Take variables named ``gv`` to be probes.

    Arguments:
        selectors: The selector strings describing the variables to probe (at least one).
        raw: Defaults to False. If True, produce a stream of :class:`~ptera.interpret.Capture` objects that
            contain extra information about the capture. Mostly relevant for
            advanced selectors such as ``f > $x:@Parameter`` which captures the value
            of any variable with the Parameter tag under the generic name "x".
            When raw is True, the actual name of the variable is preserved in a
            Capture object associated to x.
        probe_type: Either "immediate", "total", or None (the default).

            * If "immediate", use :class:`~ptera.interpret.Immediate`.
            * If "total", use :class:`~ptera.interpret.Total`.
            * If None, determine what to use based on whether the selector has
              a focus or not.
        env: A dictionary that will be used to resolve symbols in the selector.
            If it is not provided, ptera will seek the locals and globals
            dictionaries of the scope where this function is called.
    """

    def __init__(
        self,
        *selectors,
        raw=False,
        probe_type=None,
        env=None,
        _obs=None,
        _root=None,
    ):
        # Note: the private _obs and _root parameters are used to "fork"
        # the probe when using operators on it while keeping a reference
        # to the root or master probe.

        if not selectors and _obs is None:
            raise TypeError("Probe() takes at least one selector argument.")

        super().__init__(_obs=_obs, _root=_root)

        if selectors:
            if probe_type not in ("immediate", "total", None):
                raise TypeError(
                    "probe_type must be 'immediate', 'total' or None"
                )
            self._selectors = [select(s, env=env) for s in selectors]
            rules = [
                self._make_rule(sel, probe_type) for sel in self._selectors
            ]
            self._ol = BaseOverlay(*rules)
            self._raw = raw
            self._activated = False

    def _make_emitter(self, sel):
        tags = set(sel.all_tags)
        if not tags or tags == {1}:
            return self._emit
        elif tags == {1, 2}:
            return self._emit2
        else:
            raise ValueError(f"Unsupported focus pattern: {tags}")

    def _make_rule(self, sel, probe_type):
        if probe_type != "total" and (sel.focus or probe_type == "immediate"):
            return Immediate(
                sel, trigger=self._make_emitter(sel), pass_info=True
            )
        else:
            return Total(sel, close=self._make_emitter(sel))

    def _install_tooling(self):
        for selector in self._selectors:
            autotool(selector)

    def _uninstall_tooling(self):
        for selector in self._selectors:
            autotool(selector, undo=True)

    ######################
    # Changed from Given #
    ######################

    def breakpoint(self, *args, skip=[], **kwargs):  # pragma: no cover
        skip = ["ptera.*", *skip]
        return super().breakpoint(*args, skip=skip, **kwargs)

    def breakword(self, *args, skip=[], **kwargs):  # pragma: no cover
        skip = ["ptera.*", *skip]
        return super().breakword(*args, skip=skip, **kwargs)

    def fail(self, *args, skip=[], **kwargs):  # pragma: no cover
        skip = ["ptera.*", "reactivex.*", "giving.*", *skip]
        return super().fail(*args, skip=skip, **kwargs)

    def fail_if_false(self, *args, skip=[], **kwargs):  # pragma: no cover
        skip = ["ptera.*", "reactivex.*", "giving.*", *skip]
        return super().fail_if_false(*args, skip=skip, **kwargs)

    ###################
    # Context manager #
    ###################

    def _emit(self, data, acc=None, element=None):
        """Emit data on the stream.

        This is used internally.
        """
        if not self._raw:
            data = {name: cap.value for name, cap in data.items()}
        self._push(data)
        return ABSENT

    def _emit2(self, data, acc=None, element=None):
        """Emit data on the stream.

        Used for selectors with two focuses
        """
        if not self._raw:
            data = {name: cap.value for name, cap in data.items()}

        data["$wrap"] = {
            "id": id(acc),
            "name": acc.selector.main.capture,
            "step": "begin" if element.focus else "end",
        }

        self._push(data)
        return ABSENT

    def _enter(self):
        # This is called on the root probe by the __enter__ method of a child.
        # So e.g. `with probing("f > x").min(): ...` will call __enter__ on the
        # object returned by min, but _enter is called on the main probe
        # returned by probing (stored in self._root)
        if self._activated:
            raise Exception("An instance of Probe can only be entered once")

        self._install_tooling()
        self._activated = True
        global_probes.add(self)
        self._ol.__enter__()
        return self

    def _exit(self):
        # This is called on the root probe by the __exit__ method of a child.
        self._ol.__exit__(None, None, None)
        global_probes.remove(self)
        self._uninstall_tooling()

    def activate(self):
        """Activate this probe."""
        self.__enter__()

    def deactivate(self):
        """Deactivate this probe."""
        self.__exit__(None, None, None)


class OverridableProbe(Probe):
    """Probe that allows overriding the values of variables.

    OverridableProbe works essentially like :class:`~ptera.probe.Probe`, but it also
    has the :meth:`~ptera.probe.OverridableProbe.override` and
    :meth:`~ptera.probe.OverridableProbe.koverride` methods, which can be used to
    inject different values in the probed variables.

    OverridableProbe is triggered before Probe, so a Probe will see the changes of
    an OverridableProbe. However, if there are multiple operations on an OverridableProbe,
    these operations will proceed using the old, non-overriden values.
    """

    def _make_rule(self, sel, probe_type):
        if probe_type != "total" and (sel.focus or probe_type == "immediate"):
            return Immediate(
                sel, intercept=self._make_emitter(sel), pass_info=True
            )
        else:
            raise Exception(
                "OverridableProbe must use the 'immediate' probe type"
            )

    def override(self, setter=_identity):
        """Override the value of the focus variable using a setter function.

        .. code-block:: python

            # Increment a whenever it is set (will not apply recursively)
            OverridableProbe("f > a")["a"].override(lambda value: value + 1)

        .. note::
            **Important:** override() only overrides the **focus variable**. The focus
            variable is the one to the right of ``>``, or the one prefixed with ``!``.

            This is because a Ptera selector is triggered when the focus variable is set,
            so realistically it is the only one that it makes sense to override.

            Be careful, because it is easy to write misleading code:

            .. code-block:: python

                # THIS WILL SET y = x + 1, NOT x
                OverridableProbe("f(x) > y")["x"].override(lambda x: x + 1)

        .. note::
            ``override`` will only work at the end of a synchronous pipe (map/filter are OK,
            but not e.g. sample)

        Arguments:
            setter:

                A function that takes a value from the pipeline and produces the value
                to set the focus variable to.

                * If not provided, the value from the stream is used as-is.
                * If not callable, set the variable to the value of setter
        """
        if not callable(setter):
            value = setter

            def setter(_):
                return value

        def _override(data):
            self._root._value = setter(data)

        return self.subscribe(_override)

    def koverride(self, setter):
        """Override the value of the focus variable using a setter function with kwargs.

        .. code-block:: python

            def f(x):
                ...
                y = 123
                ...

            # This will basically override y = 123 to become y = x + 123
            OverridableProbe("f(x) > y").koverride(lambda x, y: x + y)

        .. note::

            **Important:** override() only overrides the **focus variable**. The focus
            variable is the one to the right of ``>``, or the one prefixed with ``!``.

            See :meth:`~ptera.probe.OverridableProbe.override`.

        Arguments:
            setter: A function that takes a value from the pipeline as keyword arguments
                and produces the value to set the focus variable to.
        """

        def _override(data):
            self._root._value = setter(**data)

        return self.subscribe(_override)

    ###################
    # Context manager #
    ###################

    def _emit(self, data, acc=None, element=None):
        """Emit data on the stream.

        This is used internally.
        """
        self._value = ABSENT
        super()._emit(data, acc=acc, element=element)
        # self._value is set by override(), but this will only work if the pipeline
        # is synchronous
        return self._value


def probing(
    *selectors, raw=False, probe_type=None, env=None, overridable=False
):
    """Probe that can be used as a context manager.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> with probing("f > a").print():
    ...     f(4)  # Prints {"a": 16}

    Arguments:
        selectors: The selector strings describing the variables to probe (at least one).
        raw: Defaults to False. If True, produce a stream of :class:`~ptera.interpret.Capture` objects that
            contain extra information about the capture.
        probe_type: Either "immediate", "total", or None (the default).

            * If "immediate", use :class:`~ptera.interpret.Immediate`.
            * If "total", use :class:`~ptera.interpret.Total`.
            * If None, determine what to use based on whether the selector has
              a focus or not.
        env: A dictionary that will be used to resolve symbols in the selector.
            If it is not provided, ptera will seek the locals and globals
            dictionaries of the scope where this function is called.
        overridable: Whether to include the override/koverride methods.
    """
    probe_class = OverridableProbe if overridable else Probe
    return probe_class(*selectors, raw=raw, probe_type=probe_type, env=env)


def global_probe(*selectors, raw=False, probe_type=None, env=None):
    """Set a probe globally.

    Example:

    >>> def f(x):
    ...     a = x * x
    ...     return a

    >>> probe = global_probe("f > a")
    >>> probe["a"].print()
    >>> f(4)  # Prints 16

    Arguments:
        selectors: The selector strings describing the variables to probe (at least one).
        raw: Defaults to False. If True, produce a stream of :class:`~ptera.interpret.Capture` objects that
            contain extra information about the capture.
        probe_type: Either "immediate", "total", or None (the default).

            * If "immediate", use :class:`~ptera.interpret.Immediate`.
            * If "total", use :class:`~ptera.interpret.Total`.
            * If None, determine what to use based on whether the selector has
              a focus or not.
        env: A dictionary that will be used to resolve symbols in the selector.
            If it is not provided, ptera will seek the locals and globals
            dictionaries of the scope where this function is called.
    """
    prb = Probe(*selectors, raw=raw, probe_type=probe_type, env=env)
    prb.activate()
    return prb


@atexit.register
def _terminate_global_probes():  # pragma: no cover
    # This closes active probes at program exit. This is important for global
    # probes if reduction operations like min() are requested, because it tells
    # them that there is no more data and that they can proceed.
    for probe in list(global_probes):
        probe.deactivate()
