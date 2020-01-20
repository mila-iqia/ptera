from contextvars import ContextVar
from dataclasses import dataclass

from .selector import ABSENT, CallInfo, ElementInfo, Nested, parse

_current_policy = ContextVar("current_policy")
_current_policy.set(None)


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
            pattern=parse(pattern),
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
                key: value
                for name, key, value in captures
                if value is not ABSENT
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
        new_patterns = []
        for pattern in self.patterns:
            new_pattern = pattern.proceed(info)
            if new_pattern is not None:
                new_patterns.append(new_pattern)
            elif not pattern.immediate and pattern.pattern is not True:
                new_patterns.append(pattern)
        new_patterns += [p for p in self.patterns if p.fresh]
        if taps:
            accumulators = dict(self.accumulators)
            for tap in taps:
                new_patterns.append(
                    ActivePattern.from_rules(tap, {"accumulate": True})
                )
                # TODO: accumulate in both the old and the new tap
                accumulators[tap] = []
        else:
            accumulators = self.accumulators
        return Policy(new_patterns, accumulators, extend_current=False)

    def values(self, pattern):
        return self.accumulators[pattern]

    def __enter__(self):
        self._reset_token = _current_policy.set(self)
        return self

    def __exit__(self, exc, exctype, tb):
        _current_policy.reset(self._reset_token)


def interact(sym, class_, value=ABSENT):
    if value is ABSENT:
        return _fetch(sym)
    else:
        return _store(sym, value)


def _fetch(sym):
    init = None
    info = ElementInfo(name=sym, classes=())
    new_policy = _current_policy.get().proceed(info)
    for pattern in new_policy.patterns:
        if pattern.pattern is True:
            captures = pattern.get_captures()
            init = pattern.rules["value"]
    if init is None:
        raise Exception(f"Cannot fetch symbol: {sym}")
    val = init(**captures)
    return _store(sym, val)


def _store(name, value):
    for pattern in _current_policy.get().patterns:
        if name in pattern.to_capture:
            pattern.captures[name] = value
    info = ElementInfo(name=name, classes=())
    new_policy = _current_policy.get().proceed(info)
    for pattern in new_policy.patterns:
        if pattern.pattern is True:
            if pattern.rules.get("accumulate", False):
                lst = new_policy.accumulators.setdefault(
                    pattern.original_pattern, []
                )
                lst.append(value)
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
            element=ElementInfo(name=self.fn.__name__, classes=(),),
            key=ElementInfo(name=self.calltag, value=self.calltag,),
        )
        with _current_policy.get().proceed(info, taps=self.taps) as pol:
            rval = self.fn(*args, **kwargs)
            for patt in pol.patterns:
                if patt.pattern is True:
                    if patt.rules.get("accumulate", False):
                        pol.accumulators[patt.original_pattern].append(patt)
            if self.taps:
                taps = [pol.accumulators[tap] for tap in self.taps]
                taps = [
                    [
                        x.get_captures() if isinstance(x, ActivePattern) else x
                        for x in res
                    ]
                    for res in taps
                ]
                rval = rval, *taps
        return rval
