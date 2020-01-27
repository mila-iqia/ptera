"""Specifications for call paths."""


from dataclasses import dataclass

from . import opparse
from .categories import Category, category_registry


class Named:
    """A named object.

    This class can be used to construct objects with a name that will be used
    for the string representation.

    """

    def __init__(self, name):
        """Construct a named object.

        Arguments:
            name: The name of this object.
        """
        self.name = name

    def __repr__(self):
        """Return the object's name."""
        return self.name


ABSENT = Named("ABSENT")


@dataclass
class ElementInfo:
    name: str
    key: "ElementInfo" = None
    value: object = ABSENT
    category: Category = None


@dataclass
class CallInfo:
    element: ElementInfo


@dataclass(frozen=True)
class Element:
    name: object
    key: object = None
    category: Category = None
    capture: object = None

    def filter(self, info):
        if not isinstance(info, ElementInfo):
            return None, False
        if self.name is not None and self.name != info.name:
            return None, False
        if self.category and not self.category.contains(info.category):
            return None, False

        if self.key is None:
            key_cap = []
        else:
            success, key_cap = self.key.filter(info.key)
            if not success:
                return None, False

        if self.capture is None:
            return True, key_cap
        else:
            return True, [*key_cap, (info.name, self.capture, info.value)]

    def key_captures(self, key_field="name"):
        results = (
            self.key.key_captures(key_field="value")
            if self.key is not None
            else set()
        )
        if self.name is None and self.capture is not None:
            results.add((self.capture, key_field))
        return results

    def retarget(self, target):
        if self.capture and self.capture == target:
            return self
        else:
            return None

    def specialize(self, specializations):
        spc = specializations.get(self.capture, None)
        newkey = self.key and self.key.specialize(specializations)
        if spc is not None:
            newname = spc.name or self.name
            return Element(
                name=newname,
                key=newkey,
                category=spc.category or self.category,
                capture=self.capture if newname is None else None,
            )
        elif newkey is not self.key:
            return Element(
                name=self.name,
                key=newkey,
                category=self.category,
                capture=self.capture,
            )
        else:
            return self

    def encode(self):
        key = "" if self.key is None else f"[{self.key.encode()}]"
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
        return f"{name}{key}{cap}{cat}"


@dataclass(frozen=True)
class Call:
    element: object
    captures: tuple = ()

    def filter(self, info):
        if not isinstance(info, CallInfo):
            return None, False
        success, elem_cap = self.element.filter(info.element)
        if not success:
            return None, False
        this_cap = [
            (cap.name, cap.capture or cap.name, ABSENT) for cap in self.captures
        ]
        return True, elem_cap + this_cap

    def key_captures(self, key_field="name"):
        return self.element.key_captures()

    def retarget(self, target):
        for cap in self.captures:
            name = cap.name
            key = cap.capture or cap.name
            if key == target:
                child = Element(
                    name=name,
                    category=None,
                    capture=None if key == name else key,
                )
                return Nested(
                    parent=Call(
                        element=self.element,
                        captures=tuple(
                            _cap
                            for _cap in self.captures
                            if (_cap.capture or _cap.name) != target
                        ),
                    ),
                    child=child,
                    immediate=True,
                )
        return None

    def specialize(self, specializations):
        return Call(
            element=self.element and self.element.specialize(specializations),
            captures=self.captures,
        )

    def encode(self):
        name = self.element.encode()
        cap = []
        for capname, capkey in self.captures:
            if capname == capkey:
                cap.append(capname)
            else:
                cap.append(f"{capname} as {capkey}")
        cap = "" if not cap else "{" + ", ".join(cap) + "}"
        return f"{name}{cap}"


@dataclass(frozen=True)
class Nested:
    """Represents nesting of elements.

    Syntax:
        parent child    # immediate = False
        parent > child  # immediate = True

    Attributes:
        parent: The parent element.
        child: The child element.
        immediate: Whether the child is expected to be the direct descendent
            of the parent, or any descendent (direct or indirect).
    """

    parent: object
    child: object
    immediate: bool = False

    def filter(self, info):
        success, captures = self.parent.filter(info)
        if success:
            return self.child, captures
        elif self.immediate:
            return None, False
        else:
            return self, []

    def key_captures(self, key_field="name"):
        return self.parent.key_captures() | self.child.key_captures()

    def retarget(self, target):
        ret = self.parent.retarget(target)
        if ret is not None:
            return ret
        else:
            return Nested(
                parent=self.parent,
                child=self.child.retarget(target),
                immediate=self.immediate,
            )

    def specialize(self, specializations):
        return Nested(
            self.parent.specialize(specializations),
            self.child.specialize(specializations),
            immediate=self.immediate,
        )

    def encode(self):
        op = ">" if self.immediate else ">>"
        return f"{self.parent.encode()} {op} {self.child.encode()}"


parse = opparse.Parser(
    lexer=opparse.Lexer(
        {
            r"\s*(?:\bas\b|>>|[(){}\[\]>.:,$])?\s*": "OPERATOR",
            r"[a-zA-Z_0-9*]+": "WORD",
        }
    ),
    order=opparse.OperatorPrecedenceTower(
        {
            ",": opparse.rassoc(10),
            ("", ">", ">>", "~"): opparse.rassoc(100),
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
        parent = Call(element=parent, captures=())
    assert isinstance(parent, Call)
    return parent


@parse.register_action("_ ( X ) _")
def make_group(node, _1, element, _2):
    return element


@parse.register_action("X > X")
def make_nested_imm(node, parent, child):
    return Nested(_guarantee_call(parent), child, immediate=True)


@parse.register_action("X >> X")
def make_nested(node, parent, child):
    return Nested(_guarantee_call(parent), child, immediate=False)


@parse.register_action("X : X")
def make_class(node, element, klass):
    assert isinstance(klass, Element)
    assert not element.category
    return Element(
        name=element.name,
        category=category_registry[klass.name],
        capture=element.capture,
    )


@parse.register_action("_ : X")
def make_class(node, _, klass):
    return Element(
        name=None, category=category_registry[klass.name], capture=None
    )


@parse.register_action("_ $ X")
def make_class(node, _, name):
    return Element(name=None, category=None, capture=name.name)


@parse.register_action("_ { X } _")
def make_capture(node, _1, name, _2):
    return Element(name=None, category=None, capture=name)


@parse.register_action("X [ X ] _")
def make_instance(node, element, key, _):
    assert isinstance(element, Element)
    assert isinstance(key, Element)
    assert element.key is None
    captures = ()
    # return Call(element=element, key=key, captures=captures)
    return Element(
        name=element.name,
        key=key,
        category=element.category,
        capture=element.capture,
    )


@parse.register_action("X { X } _")
def make_call_capture(node, fn, names, _2):
    names = names if isinstance(names, list) else [names]
    return Call(element=fn, captures=tuple(names))


@parse.register_action("X , X")
def make_sequence(node, a, b):
    if not isinstance(b, list):
        b = [b]
    return [a, *b]


@parse.register_action("X as X")
def make_as(node, element, name):
    return Element(name=element.name, category=None, capture=name.name)


@parse.register_action("SYMBOL")
def make_symbol(node):
    if node.value == "*":
        return Element(None)
    else:
        return Element(node.value)
