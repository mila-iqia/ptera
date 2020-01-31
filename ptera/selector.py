"""Specifications for call paths."""


from dataclasses import dataclass, replace as dc_replace

from . import opparse
from .categories import Category, category_registry
from .utils import ABSENT, Named


@dataclass(frozen=True)
class Element:
    name: object
    value: object = ABSENT
    category: Category = None
    capture: object = None
    focus: bool = False
    key_field: str = None

    def all_captures(self):
        if self.capture:
            return {self.capture}
        else:
            return set()

    def valid(self):
        if self.name is None:
            return self.focus
        else:
            return True

    def rewrite(self, required, focus=None):
        if focus is not None and focus == self.capture:
            return dc_replace(self, focus=True)
        elif focus is None and self.focus:
            return self
        elif self.capture not in required:
            if self.value is ABSENT:
                return None
            else:
                return dc_replace(self, capture=None, focus=False)
        elif focus is not None:
            return dc_replace(self, focus=False)
        else:
            return self

    # def filter(self, info):
    #     if not isinstance(info, ElementInfo):
    #         return None, False
    #     if self.name is not None and self.name != info.name:
    #         return None, False
    #     if self.category and not self.category.contains(info.category):
    #         return None, False

    #     if self.key is None:
    #         key_cap = []
    #     else:
    #         success, key_cap = self.key.filter(info.key)
    #         if not success:
    #             return None, False

    #     if self.capture is None:
    #         return True, key_cap
    #     else:
    #         cap = ElementInfo(
    #             name=info.name,
    #             category=self.category,
    #             value=info.value,
    #             capture=self.capture,
    #         )
    #         return True, [*key_cap, cap]

    # def key_captures(self):
    #     if self.key_field is not None:
    #         return {(self.capture, self.key_field)}
    #     else:
    #         return set()

    # def specialize(self, specializations):
    #     spc = specializations.get(self.capture, None)
    #     if spc is not None:
    #         rval = dc_replace(
    #             self,
    #             name=spc.name or self.name,
    #             category=spc.category or self.category,
    #             value=spc.value if self.value is ABSENT else self.value,
    #         )
    #         if rval.key_field == 'name' and rval.name is not None:
    #             rval = dc_replace(rval, key_field=None)
    #         if rval.key_field == 'value' and rval.value is not ABSENT:
    #             rval = dc_replace(rval, key_field=None)
    #         return rval
    #     else:
    #         return self

    def encode(self):
        if self.name is None and self.capture is not None:
            name = f"${self.capture}"
            cap = ""
        else:
            name = "*" if self.name is None else self.name
            cap = (
                ""
                if self.capture is None or self.capture == self.name
                else f" as {self.capture}"
            )
        cat = "" if self.category is None else f":{self.category}"
        focus = "!" if self.focus else ""
        val = f"={self.value}" if self.value is not ABSENT else ""
        return f"{focus}{name}{cap}{cat}{val}"


@dataclass(frozen=True)
class Call:
    element: object
    children: tuple = ()
    captures: tuple = ()
    immediate: bool = False

    @property
    def focus(self):
        return any(x.focus for x in self.captures + self.children)

    def all_captures(self):
        rval = set()
        for x in self.captures + self.children:
            rval.update(x.all_captures())
        return rval

    def valid(self):
        return (
            all(x.valid() for x in self.captures + self.children)
            and sum(x.focus for x in self.captures + self.children) <= 1
        )

    def rewrite(self, required, focus=None):
        captures = [x.rewrite(required, focus) for x in self.captures]
        captures = [x for x in captures if x is not None]

        children = [x.rewrite(required, focus) for x in self.children]
        children = [x for x in children if x is not None]

        if not captures and not children:
            return None

        return dc_replace(
            self, captures=tuple(captures), children=tuple(children)
        )

    # def filter(self, info):
    #     if not isinstance(info, CallInfo):
    #         return None, False
    #     success, elem_cap = self.element.filter(info.element)
    #     if not success:
    #         return None, False
    #     this_cap = [
    #         ElementInfo(
    #             name=cap.name,
    #             category=cap.category,
    #             capture=cap.capture,
    #             value=ABSENT,
    #         )
    #         for cap in self.captures
    #     ]
    #     return True, elem_cap + this_cap

    # def key_captures(self):
    #     rval = self.element.key_captures()
    #     for child in self.children:
    #         rval.update(child.key_captures())
    #     for cap in self.captures:
    #         rval.update(cap.key_captures())
    #     return rval

    # def specialize(self, specializations):
    #     return Call(
    #         element=self.element and self.element.specialize(specializations),
    #         child=self.child and self.child.specialize(specializations),
    #         captures=tuple(cap.specialize(specializations)
    #                        for cap in self.captures),
    #     )

    def encode(self):
        name = self.element.encode()
        caps = []
        for cap in self.captures:
            caps.append(cap.encode())
        for child in self.children:
            enc = child.encode()
            enc = f"> {enc}" if child.immediate else enc
            caps.append(enc)
        caps = "" if not caps else "{" + ", ".join(caps) + "}"
        return f"{name}{caps}"


parse = opparse.Parser(
    lexer=opparse.Lexer(
        {
            r"\s*(?:\bas\b|>>|[(){}\[\]>.:,$!=])?\s*": "OPERATOR",
            r"[a-zA-Z_0-9#*]+": "WORD",
        }
    ),
    order=opparse.OperatorPrecedenceTower(
        {
            ",": opparse.rassoc(10),
            ("", ">", ">>"): opparse.rassoc(100),
            "=": opparse.lassoc(120),
            "!": opparse.lassoc(150),
            ":": opparse.lassoc(200),
            "as": opparse.rassoc(250),
            "$": opparse.lassoc(300),
            ("(", "[", "{"): opparse.obrack(500),
            (")", "]", "}"): opparse.cbrack(500),
            ": WORD": opparse.lassoc(1000),
        }
    ),
)


def _guarantee_call(parent):
    if isinstance(parent, Element):
        parent = dc_replace(parent, capture=None)
        parent = Call(element=parent, captures=())
    assert isinstance(parent, Call)
    return parent


@parse.register_action("_ ( X ) _")
def make_group(node, _1, element, _2):
    return element


@parse.register_action("X > X")
def make_nested_imm(node, parent, child):
    parent = _guarantee_call(parent)
    if isinstance(child, Element):
        child = dc_replace(child, focus=True)
        return dc_replace(parent, captures=parent.captures + (child,))
    else:
        return dc_replace(
            parent,
            children=parent.children + (dc_replace(child, immediate=True),),
        )


@parse.register_action("X >> X")
def make_nested(node, parent, child):
    parent = _guarantee_call(parent)
    if isinstance(child, Element):
        child = dc_replace(child, focus=True)
        child = Call(
            element=Element(name=None), captures=(child,), immediate=False
        )
    return dc_replace(parent, children=parent.children + (child,))


@parse.register_action("_ > X")
def make_nested_imm_pfx(node, _, child):
    child = _guarantee_call(child)
    return dc_replace(child, immediate=True)


@parse.register_action("_ >> X")
def make_nested_pfx(node, _, child):
    child = _guarantee_call(child)
    return dc_replace(child, immediate=False)


@parse.register_action("X : X")
def make_class(node, element, klass):
    assert isinstance(klass, Element)
    assert not element.category
    return dc_replace(element, category=category_registry[klass.name])


@parse.register_action("_ : X")
def make_class(node, _, klass):
    return Element(
        name=None, category=category_registry[klass.name], capture=None
    )


@parse.register_action("_ ! X")
def make_class(node, _, element):
    assert isinstance(element, Element)
    return dc_replace(element, focus=True)


@parse.register_action("_ $ X")
def make_class(node, _, name):
    return Element(
        name=None, category=None, capture=name.name, key_field="name"
    )


@parse.register_action("X [ X ] _")
def make_instance(node, element, key, _):
    assert isinstance(element, Element)
    assert isinstance(key, Element)
    element = _guarantee_call(element)
    key = Element(
        name="#key",
        value=key.name if key.name is not None else ABSENT,
        category=key.category,
        capture=key.capture if key.name != key.capture else None,
        key_field="value" if key.name is None else None,
    )
    return dc_replace(element, captures=element.captures + (key,))


@parse.register_action("X { X } _")
def make_call_capture(node, fn, names, _2):
    names = names if isinstance(names, list) else [names]
    fn = _guarantee_call(fn)
    caps = tuple(name for name in names if isinstance(name, Element))
    children = tuple(name for name in names if isinstance(name, Call))
    return dc_replace(
        fn, captures=fn.captures + caps, children=fn.children + children
    )


@parse.register_action("X , X")
def make_sequence(node, a, b):
    if not isinstance(b, list):
        b = [b]
    return [a, *b]


@parse.register_action("X as X")
def make_as(node, element, name):
    return dc_replace(
        element,
        capture=name.name,
        key_field="name" if element.name is None else None,
    )


@parse.register_action("X = X")
def make_equals(node, element, value):
    assert isinstance(value, Element)
    return dc_replace(element, value=value.name, capture=None)


@parse.register_action("SYMBOL")
def make_symbol(node):
    if node.value == "*":
        return Element(name=None)
    else:
        value = node.value
        cap = node.value
        try:
            value = int(value)
            cap = None
        except ValueError:
            pass
        return Element(name=value, capture=cap)
