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
        self.accumulators = defaultdict(list)
        self.to_close = []

    def register(self, acc, captures, close_at_exit):
        for cap in captures:
            self.accumulators[cap.name].append((cap, acc))
        if close_at_exit:
            self.to_close.append(acc)

    def get_accumulators(self, varname):
        return chain(self.accumulators[varname], self.accumulators[None])

    def run(self, method, varname, category, value=ABSENT):
        rval = ABSENT
        for element, acc in self.get_accumulators(varname):
            acc = acc.match(element, varname, category, value)
            if acc:
                tmp = getattr(acc, method)(element, varname, category, value)
                if tmp is not ABSENT:
                    rval = tmp
        return rval

    def set(self, varname, key, category, value):
        self.run("varset", varname, category, value)

    def get(self, varname, key, category):
        rval = self.run("varget", varname, category)
        if rval is ABSENT:
            raise NameError(f"Cannot get value for variable `{varname}`")
        return rval

    def exit(self):
        for acc in self.to_close:
            acc.close()


class Capture:
    def __init__(self, element):
        self.element = element
        self.capture = element.capture
        self.names = []
        self.values = []

    @property
    def name(self):
        if self.element.name is not None:
            return self.element.name
        if len(self.names) == 0:
            raise ValueError(f"No name for capture `{self.capture}`")
        if len(self.names) > 1:
            raise ValueError(
                f"Multiple names stored for capture `{self.capture}`"
            )
        return self.names[0]

    @property
    def value(self):
        if len(self.values) == 0:
            raise ValueError(f"No value for capture `{self.capture}`")
        if len(self.values) > 1:
            raise ValueError(
                f"Multiple values stored for capture `{self.capture}`"
            )
        return self.values[0]

    def nomatch(self):
        return None if self.element.name is None else False

    def check(self, varname, category, value):
        el = self.element
        assert el.name is None or varname == el.name
        if el.category and not el.category.contains(category):
            return self.nomatch()
        elif el.value is not ABSENT and el.value != value:
            return self.nomatch()
        else:
            return True

    def acquire(self, varname, value):
        assert varname is not None
        self.names.append(varname)
        self.values.append(value)

    def __str__(self):
        return f"Capture({self.element}, {self.names}, {self.values})"

    __repr__ = __str__


class Accumulator:
    def __init__(
        self, names, parent=None, rules=None, template=True, pattern=None
    ):
        self.id = next(_cnt)
        self.names = set(names)
        self.pattern = pattern
        self.parent = parent
        self.children = []
        self.rules = rules or defaultdict(list)
        self.captures = {}
        self.status = ACTIVE
        self.template = template
        if self.parent is not None:
            self.parent.children.append(self)

    def getcap(self, element):
        if element.capture not in self.captures:
            cap = Capture(element)
            self.captures[element.capture] = cap
        return self.captures[element.capture]

    def fail(self):
        self.status = FAILED
        for leaf in self.leaves():
            leaf.status = FAILED

    def match(self, element, varname, category, value):
        if self.status is FAILED:
            return None
        if element.focus:
            acc = self.fork()
        else:
            acc = self
        cap = acc.getcap(element)
        status = cap.check(varname, category, value)
        if status is True:
            return acc
        elif status is False:
            self.fail()
            return None
        else:
            return None

    def varset(self, element, varname, category, value):
        if self.status is FAILED:
            return
        cap = self.getcap(element)
        cap.acquire(varname, value)

    def varget(self, element, varname, category, _):
        if not element.focus or self.status is FAILED:
            return ABSENT
        cap = self.getcap(element)
        cap.names.append(varname)
        rval = self.run("value", may_fail=False)
        if rval is ABSENT:
            cap.names.pop()
        else:
            cap.values.append(rval)
        return rval

    def build(self):
        rval = {}
        curr = self
        while curr:
            rval.update(
                {
                    name: cap
                    for name, cap in curr.captures.items()
                    if (cap.values or cap.names) and name is not None
                }
            )
            curr = curr.parent
        return rval

    def run(self, rulename, may_fail):
        if self.status is FAILED:
            return FAILED
        rval = ABSENT
        for fn in self.rules[rulename]:
            args = self.build()
            _, names = get_names(fn)
            if may_fail and set(args) != set(names):
                return ABSENT
            else:
                rval = fn(**args)
        return rval

    def leaves(self):
        if not self.children:
            return [self]
        else:
            rval = []
            for child in self.children:
                rval += child.leaves()
            return rval

    def close(self):
        if self.status is ACTIVE:
            if self.parent is None:
                for leaf in self.leaves():
                    leaf.run("listeners", may_fail=True)
            self.status = COMPLETE

    def fork(self):
        parent = None if self.template else self
        return Accumulator(
            self.names,
            parent,
            rules=self.rules,
            template=False,
            pattern=self.pattern,
        )

    def __str__(self):
        rval = str(self.id)
        curr = self.parent
        while curr:
            rval = f"{curr.id} > {rval}"
            curr = curr.parent
        return f"Accumulator({self.pattern}, {rval})"


def get_names(fn):
    if hasattr(fn, "_ptera_argspec"):
        return fn._ptera_argspec
    else:
        spec = inspect.getfullargspec(fn)
        if spec.args and spec.args[0] == "self":
            return None, spec.args[1:]
        else:
            return None, spec.args


def dict_to_collection(*rulesets):
    tmp = {}
    for rules in rulesets:
        for pattern, triggers in rules.items():
            pattern = to_pattern(pattern)
            for name, entries in triggers.items():
                if not isinstance(entries, (tuple, list)):
                    entries = [entries]
                for entry in entries:
                    focus, names = get_names(entry)
                    this_pattern = pattern.rewrite(names, focus=focus)
                    if this_pattern not in tmp:
                        tmp[this_pattern] = Accumulator(
                            names, pattern=this_pattern
                        )
                    acc = tmp[this_pattern]
                    acc.rules[name].append(entry)
    return PatternCollection(list(tmp.items()))


class PatternCollection:
    current = ContextVar("PatternCollection.current", default=None)

    def __init__(self, patterns=None):
        self.patterns = patterns or []

    def proceed(self, fname, frame):
        next_patterns = []
        to_process = list(self.patterns)
        while to_process:
            pattern, acc = to_process.pop()
            ename = pattern.element.name
            if not pattern.immediate:
                next_patterns.append((pattern, acc))
            if ename is None or ename == fname:
                is_template = acc.template
                if pattern.focus or is_template:
                    acc = acc.fork()
                frame.register(acc, pattern.captures, close_at_exit=is_template)
                for child in pattern.children:
                    if child.collapse:
                        to_process.append((child, acc))
                    else:
                        next_patterns.append((child, acc))
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
def overlay(*rulesets):
    rulesets = [rules for rules in rulesets if rules]

    if not rulesets:
        yield None

    else:
        collection = dict_to_collection(*rulesets)
        curr = PatternCollection.current.get()
        if curr is not None:
            collection.patterns = curr.patterns + collection.patterns
        with setvar(PatternCollection.current, collection):
            yield collection


def interact(sym, key, category, value=ABSENT):
    if key is None:
        fr = Frame.top.get()
        if value is ABSENT:
            value = fr.get(sym, key, category)
        fr.set(sym, key, category, value)
        return value

    else:
        assert value is not ABSENT
        with newframe() as frame:
            with proceed(sym):
                interact("#key", None, None, key)
                return interact("#value", None, category, value)


class Collector:
    def __init__(self, pattern):
        self.data = []
        self.pattern = to_pattern(pattern)

        def listener(**kwargs):
            self.data.append(kwargs)

        listener._ptera_argspec = None, set(self.pattern.all_captures())
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

    def rules(self):
        return {self.pattern: {"listeners": [self._listener]}}

    def finalize(self):
        return self


class Tap:
    hasoutput = True

    def __init__(self, selector):
        self.selector = selector

    def instantiate(self):
        return Collector(self.selector)


class CallResults:
    def __init__(self, value):
        self.value = value
        setattr(self, "0", self.value)

    def __getitem__(self, item):
        if isinstance(item, int):
            item = str(item)
        try:
            return getattr(self, item)
        except AttributeError:
            raise IndexError(item)


class State:
    hasoutput = False

    def __init__(self, values):
        self._rules = {
            patt: {"value": lambda __v=value, **_: __v}
            for patt, value in values.items()
        }

    def rules(self):
        return self._rules

    def instantiate(self):
        return self

    def finalize(self):
        return self


class PteraFunction:
    def __init__(self, fn, callkey=None, plugins=None, return_object=False):
        self.fn = fn
        self.callkey = callkey
        self.plugins = plugins or {}
        self.return_object = return_object

    def __getitem__(self, callkey):
        assert self.callkey is None
        return PteraFunction(
            fn=self.fn,
            callkey=callkey,
            plugins=self.plugins,
            return_object=self.return_object,
        )

    def new(self, **values):
        values = {f"> * > {name}": value for name, value in values.items()}
        return self.using(_state=State(values))

    def using(self, *plugins, **kwplugins):
        plugins = {str(i + 1): p for i, p in enumerate(plugins)}
        plugins.update(kwplugins)
        plugins = {
            name: Tap(p) if isinstance(p, str) else p
            for name, p in plugins.items()
        }
        return PteraFunction(
            fn=self.fn,
            callkey=self.callkey,
            plugins={**self.plugins, **plugins},
            return_object=any(p.hasoutput for name, p in plugins.items()),
        )

    def __call__(self, *args, **kwargs):
        rulesets = []
        with newframe() as frame:
            plugins = {
                name: p.instantiate() for name, p in self.plugins.items()
            }
            for plugin in plugins.values():
                rulesets.append(plugin.rules())
            with overlay(*rulesets):
                with proceed(self.fn.__name__):
                    if self.callkey is not None:
                        interact("#key", None, None, self.callkey)
                    rval = self.fn(*args, **kwargs)

        callres = CallResults(rval)
        for name, plugin in plugins.items():
            setattr(callres, name, plugin.finalize())

        if self.return_object:
            return callres
        else:
            return rval
