import inspect
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from itertools import chain, count

from .selector import Call, Element, to_pattern
from .utils import ABSENT, ACTIVE, COMPLETE, FAILED, call_with_captures, setvar

_cnt = count()


class Frame:

    top = ContextVar("Frame.top", default=None)

    def __init__(self, fname):
        self.function_name = fname
        self.listeners = defaultdict(list)
        self.exit_listeners = []

    def listen(self, varname, listener):
        self.listeners[varname].append(listener)

    def set(self, varname, key, category, value):
        for listener in chain(self.listeners[varname], self.listeners[None]):
            listener(varname, category, value)

    def get(self, varname, key, category):
        for listener in chain(self.listeners[varname], self.listeners[None]):
            return listener(varname, category, ABSENT)

    def on_exit(self, fn):
        self.exit_listeners.append(fn)

    def exit(self):
        for fn in self.exit_listeners:
            fn()


class Capture:
    def __init__(self, element):
        self.element = element
        self.capture = element.capture
        self.names = []
        self.values = []

    @property
    def name(self):
        if len(self.names) > 1:
            raise ValueError("Multiple values stored for this capture.")
        return self.names[0]

    @property
    def value(self):
        if len(self.values) > 1:
            raise ValueError("Multiple values stored for this capture.")
        return self.values[0]

    def nomatch(self):
        return None if self.element.name is None else False

    def acquire(self, varname, category, value):
        el = self.element
        assert el.name is None or varname == el.name
        if el.category and not el.category.contains(category):
            return self.nomatch()
        if el.value is not ABSENT and el.value != value:
            return self.nomatch()
        self.names.append(varname)
        self.values.append(value)
        return True


class Accumulator:
    def __init__(self, names, parent=None, rules=None, focus=False):
        self.id = next(_cnt)
        self.names = set(names)
        self.parent = parent
        self.rules = rules or defaultdict(list)
        self.captures = {}
        self.status = ACTIVE
        self.subtasks = []

    def attach(self, frame, element):
        def listener(varname, category, value):
            acc = self
            if value is not ABSENT:
                if element.focus:
                    acc = self.fork()
                if element.capture not in acc.captures:
                    cap = Capture(element)
                    acc.captures[element.capture] = cap
                cap = acc.captures[element.capture]
                status = cap.acquire(varname, category, value)
                if status is False:
                    acc.status = FAILED
                if element.focus:
                    acc.close()
            else:
                return self.run("value", may_fail=False)

        frame.listen(element.name, listener)

    def build(self):
        rval = {}
        curr = self
        while curr:
            rval.update(
                {
                    name: cap
                    for name, cap in curr.captures.items()
                    if cap.values and name is not None
                }
            )
            curr = curr.parent
        return rval

    def run(self, rulename, may_fail):
        rval = None
        for fn in self.rules[rulename]:
            args = self.build()
            if may_fail and set(args) != self.names:
                return None
            else:
                rval = fn(**args)
        return rval

    def close(self):
        if self.status is ACTIVE:
            self.subtasks.append(
                lambda: self.run("listeners", may_fail=True)
            )
            if self.parent is None:
                for task in self.subtasks:
                    task()
            else:
                self.parent.subtasks.extend(self.subtasks)
            self.status = COMPLETE

    def fork(self):
        return Accumulator(self.names, self, rules=self.rules)

    def __str__(self):
        rval = str(self.id)
        curr = self.parent
        while curr:
            rval = f"{curr.id} > {rval}"
            curr = curr.parent
        return rval


def get_names(fn):
    if hasattr(fn, "_ptera_argspec"):
        return fn._ptera_argspec
    else:
        spec = inspect.getfullargspec(fn)
        return None, spec.args


class PatternCollection:
    current = ContextVar("PatternCollection.current", default=None)

    def __init__(self, patterns=None):
        self.patterns = patterns or []

    def update(self, patterns):
        tmp = {}
        for pattern, triggers in patterns.items():
            pattern = to_pattern(pattern)
            for name, entries in triggers.items():
                if not isinstance(entries, (tuple, list)):
                    entries = [entries]
                for entry in entries:
                    focus, names = get_names(entry)
                    this_pattern = pattern.rewrite(names, focus=focus)
                    if this_pattern not in tmp:
                        tmp[this_pattern] = Accumulator(names)
                    acc = tmp[this_pattern]
                    acc.rules[name].append(entry)
        self.patterns.extend(tmp.items())

    def proceed(self, fname, frame):
        next_patterns = []
        for pattern, acc in self.patterns:
            ename = pattern.element.name
            if not pattern.immediate:
                next_patterns.append((pattern, acc))
            if ename is None or ename == fname:
                if pattern.focus:
                    acc = acc.fork()
                for cap in pattern.captures:
                    acc.attach(frame, cap)
                for child in pattern.children:
                    next_patterns.append((child, acc))
                if pattern.focus:
                    frame.on_exit(acc.close)
        rval = PatternCollection(next_patterns)
        return rval

    def show(self):
        for pattern, acc in self.patterns:
            print(pattern.encode(), "\t", acc)


@contextmanager
def newframe():
    frame = Frame(None)
    try:
        with setvar(Frame.top, frame):
            yield frame
    finally:
        frame.exit()


@contextmanager
def proceed(fname):
    curr = PatternCollection.current.get()
    frame = Frame.top.get()
    if curr is None:
        yield None
    else:
        new = curr.proceed(fname, frame)
        with setvar(PatternCollection.current, new):
            yield new


@contextmanager
def overlay(rules):
    if rules is None:
        yield None

    else:
        collection = PatternCollection()
        collection.update(rules)
        new_patterns = collection.patterns

        curr = PatternCollection.current.get()
        if curr is not None:
            collection.patterns = curr.patterns + collection.patterns

        with setvar(PatternCollection.current, collection):
            yield collection
            for pattern, acc in new_patterns:
                acc.close()


def interact(sym, key, category, value=ABSENT):
    fr = Frame.top.get()
    if value is ABSENT:
        value = fr.get(sym, key, category)
    fr.set(sym, key, category, value)
    return value


class Collector:
    def __init__(self, pattern):
        self.data = []
        pattern = to_pattern(pattern)

        def listener(**kwargs):
            self.data.append(kwargs)

        listener._ptera_argspec = None, set(pattern.all_captures())
        self._listener = listener

    def __iter__(self):
        return iter(self.data)

    def map(self, fn=None):
        if isinstance(fn, str):
            return [entry[fn].value for entry in self]
        else:
            vals = [
                {key: cap.value for key, cap in entry.items()} for entry in self
            ]
            if fn is None:
                return vals
            else:
                return [call_with_captures(fn, entry) for entry in vals]

    def map_full(self, fn=None):
        if isinstance(fn, str):
            return [entry[fn] for entry in self]
        else:
            if fn is None:
                return list(self)
            else:
                return [call_with_captures(fn, entry) for entry in self]


class PteraFunction:
    def __init__(self, fn, callkey=None, taps=None):
        self.fn = fn
        self.callkey = callkey
        self.taps = taps

    def tap(self, *taps):
        return PteraFunction(self.fn, self.callkey, (self.taps or ()) + taps)

    def make_rules(self):
        if self.taps is None:
            return None, None
        collectors = {pattern: Collector(pattern) for pattern in self.taps}
        rules = {
            pattern: {"listeners": [collector._listener]}
            for pattern, collector in collectors.items()
        }
        return collectors, rules

    def __getitem__(self, callkey):
        assert self.callkey is None
        return PteraFunction(self.fn, callkey)

    def __call__(self, *args, **kwargs):
        collectors, rules = self.make_rules()
        with newframe() as frame:
            with overlay(rules):
                with proceed(self.fn.__name__):
                    if self.callkey is not None:
                        interact("#key", None, None, self.callkey)
                    rval = self.fn(*args, **kwargs)
        if self.taps is not None:
            return (rval, *[collectors[tap] for tap in self.taps])
        return rval
