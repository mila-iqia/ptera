from contextvars import ContextVar
from dataclasses import dataclass

from .categories import Category
from .selector import ABSENT, CallInfo, Element, ElementInfo, Nested, parse

_current_policy = ContextVar("current_policy")
_current_policy.set(None)


@dataclass
class CapturedValue:
    name: str
    category: Category
    value: object


class Collection:
    def __init__(self):
        self.data = []
        self.done = False

    def add(self, pattern):
        assert not self.done
        self.data.append(pattern)

    def finish(self):
        if not self.done:
            self.done = True
            self.data = [pattern.get_captures() for pattern in self.data]
        return self

    def __iter__(self):
        self.finish()
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
                return [fn(**entry) for entry in vals]

    def map_full(self, fn=None):
        if isinstance(fn, str):
            return [entry[fn] for entry in self]
        else:
            if fn is None:
                return list(self)
            else:
                return [fn(**entry) for entry in self]


@dataclass
class ActivePattern:
    parent: object
    pattern: object
    original_pattern: str
    rules: object
    captures: dict
    to_capture: dict
    fresh: bool
    immediate: bool

    @classmethod
    def from_rules(cls, pattern, rules):
        return cls(
            parent=None,
            pattern=parse(pattern) if isinstance(pattern, str) else pattern,
            original_pattern=pattern,
            rules=rules,
            captures={},
            to_capture={},
            fresh=True,
            immediate=True,
        )

    def proceed(self, info):
        if self.pattern is True:
            return None
        new_pattern, captures = self.pattern.filter(info)
        if new_pattern is None:
            return None
        else:
            new_captures = {
                key: CapturedValue(name=name, category=None, value=value)
                for name, key, value in captures
            }
            to_capture = {
                name: key for name, key, value in captures if value is ABSENT
            }
            return ActivePattern(
                parent=self,
                pattern=new_pattern,
                original_pattern=self.original_pattern,
                rules=self.rules,
                captures=new_captures,
                to_capture=to_capture,
                fresh=False,
                immediate=(
                    isinstance(self.pattern, Nested) and self.pattern.immediate
                ),
            )

    def get_captures(self):
        current = self
        rval = {}
        while current is not None:
            rval.update(current.captures)
            current = current.parent
        return rval


class Policy:
    def __init__(self, patterns, accumulators=None, extend_current=True):
        if isinstance(patterns, dict):
            patterns = [
                ActivePattern.from_rules(pattern, rules)
                for pattern, rules in patterns.items()
            ]
        self.patterns = patterns
        self.accumulators = {} if accumulators is None else accumulators
        if extend_current:
            curr = _current_policy.get()
            if curr:
                self.patterns += curr.patterns
                self.accumulators.update(curr.accumulators)

    def proceed(self, info, taps=None):
        if taps:
            patterns = list(self.patterns)
            accumulators = dict(self.accumulators)
            for tap in taps:
                patterns.append(
                    ActivePattern.from_rules(tap, {"accumulate": True})
                )
                # TODO: accumulate in both the old and the new tap
                accumulators[tap] = Collection()
        else:
            patterns = self.patterns
            accumulators = self.accumulators

        new_patterns = []
        for pattern in patterns:
            new_pattern = pattern.proceed(info)
            if new_pattern is not None:
                new_patterns.append(new_pattern)
            elif not pattern.immediate and pattern.pattern is not True:
                new_patterns.append(pattern)
        new_patterns += [p for p in patterns if p.fresh]
        return Policy(new_patterns, accumulators, extend_current=False)

    def values(self, pattern):
        return self.accumulators[pattern]

    def __enter__(self):
        self._reset_token = _current_policy.set(self)
        return self

    def __exit__(self, exc, exctype, tb):
        _current_policy.reset(self._reset_token)


def interact(sym, category, value=ABSENT):
    if value is ABSENT:
        return _fetch(sym, category)
    else:
        return _store(sym, category, value)


def _fetch(sym, category):
    init = None
    info = ElementInfo(name=sym, category=category)
    new_policy = _current_policy.get().proceed(info)
    for pattern in new_policy.patterns:
        if pattern.pattern is True:
            captures = pattern.get_captures()
            if "value" not in pattern.rules:
                continue
            init = pattern.rules["value"]
    if init is None:
        raise Exception(f"Cannot fetch symbol: {sym}")
    val = init(**captures)
    return _store(sym, category, val)


def _store(name, category, value):
    for pattern in _current_policy.get().patterns:
        if name in pattern.to_capture:
            key = pattern.to_capture[name]
            pattern.captures[key] = CapturedValue(
                name=name, category=category, value=value,
            )
    info = ElementInfo(name=name, category=category)
    new_policy = _current_policy.get().proceed(info)
    for pattern in new_policy.patterns:
        if pattern.pattern is True:
            if pattern.rules.get("accumulate", False):
                parent = pattern.parent
                assert isinstance(parent.pattern, Element)
                lst = new_policy.accumulators.setdefault(
                    pattern.original_pattern, Collection()
                )
                pattern.captures[
                    parent.pattern.capture or name
                ] = CapturedValue(name=name, category=category, value=value,)
                lst.add(pattern)
    return value


class PteraFunction:
    def __init__(self, fn, calltag=None, taps=()):
        self.fn = fn
        self.calltag = calltag
        self.taps = taps

    def __getitem__(self, calltag):
        assert self.calltag is None
        return PteraFunction(self.fn, calltag)

    def tap(self, *selectors):
        return PteraFunction(self.fn, self.calltag, taps=self.taps + selectors)

    def __call__(self, *args, **kwargs):
        info = CallInfo(
            element=ElementInfo(name=self.fn.__name__, category=None),
            key=ElementInfo(name=self.calltag, value=self.calltag),
        )
        with _current_policy.get().proceed(info, taps=self.taps) as pol:
            rval = self.fn(*args, **kwargs)
            # TODO: move this behavior into Policy
            for patt in pol.patterns:
                if patt.pattern is True:
                    if patt.rules.get("accumulate", False):
                        pol.accumulators[patt.original_pattern].add(patt)
            if self.taps:
                taps = [pol.accumulators[tap] for tap in self.taps]
                rval = rval, *taps
        return rval
