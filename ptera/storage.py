import functools
from collections import defaultdict
from dataclasses import dataclass
from functools import partial

from .categories import Category
from .selector import Call, Element, ElementInfo, Nested, parse
from .utils import call_with_captures, keyword_decorator


class Store:
    def __init__(self, fill):
        self.data = {}
        self.fill = fill

    def key(self, kwargs):
        return tuple(sorted(kwargs.items()))

    def get(self, **kwargs):
        key = self.key(kwargs)
        if key not in self.data:
            self.data[key] = self.fill(**kwargs)
        return self.data[key]

    def set(self, value, **kwargs):
        key = self.key(kwargs)
        self.data[key] = value


@dataclass
class Role:
    role: str
    target: object
    target_name: str
    target_category: Category
    full: bool

    def make_capture(self):
        sel = {}
        if self.target_name or self.target_category:
            return {
                self.target: ElementInfo(
                    name=self.target_name, category=self.target_category
                )
            }
        else:
            return {}


def role_wrapper(role):
    @keyword_decorator
    def wrap(
        fn, target=None, target_name=None, target_category=None, full=False
    ):
        fn._ptera_role = Role(
            role=role,
            target=target,
            target_name=target_name,
            target_category=target_category,
            full=full,
        )
        return fn

    return wrap


initializer = role_wrapper("initializer")
updater = role_wrapper("updater")
valuer = role_wrapper("valuer")


class Storage:

    pattern = None
    default_target = None

    def __init__(self, select):
        self._prepare(select=select)
        self.store = {}

    def _init_wrap(self, initfn):
        @functools.wraps(initfn)
        def wrapped(**cap):
            cap = {**initfn._ptera_role.make_capture(), **cap}
            key = tuple(
                getattr(cap[k], field) for k, field in self._key_captures
            )
            if key not in self.store:
                self.store[key] = call_with_captures(initfn, cap)
            return self.store[key]

        return wrapped

    def _update_wrap(self, updatefn):
        @functools.wraps(updatefn)
        def wrapped(**cap):
            cap = {**updatefn._ptera_role.make_capture(), **cap}
            key = tuple(
                getattr(cap[k], field) for k, field in self._key_captures
            )
            assert key in self.store
            self.store[key] = call_with_captures(updatefn, cap)

        return wrapped

    def _value_wrap(self, valuefn):
        @functools.wraps(valuefn)
        def wrapped(**cap):
            cap = {**valuefn._ptera_role.make_capture(), **cap}
            return call_with_captures(valuefn, cap)

        return wrapped

    def _prepare(self, select):
        assert self.pattern
        pattern = parse(self.pattern)

        self._key_captures = pattern.specialize(select).key_captures()

        update_taps = []
        policy_dict = defaultdict(dict)

        for method in dir(self):
            fn = getattr(self, method)
            role = getattr(fn, "_ptera_role", None)
            if role is None:
                continue

            if role.target is None:
                role.target = self.default_target

            sel = dict(select)
            sel.update(role.make_capture())
            patt = pattern.retarget(role.target).specialize(sel)

            if role.role == "initializer":
                policy_dict[patt.encode()]["value"] = self._init_wrap(fn)

            elif role.role == "valuer":
                policy_dict[patt.encode()]["value"] = self._value_wrap(fn)

            elif role.role == "updater":
                update_taps.append((patt.encode(), self._update_wrap(fn)))

            else:
                raise AssertionError(f"Unknown role: {role.role}")

        self.policy_dict = policy_dict
        self.update_taps = update_taps

    def policy(self):
        return self.policy_dict

    def taps(self):
        return [pattern for pattern, _ in self.update_taps]

    def process_taps(self, tap_results):
        for tap_result, (_, ufn) in zip(tap_results, self.update_taps):
            for entry in tap_result:
                ufn(**entry)
