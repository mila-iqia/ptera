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
    value: object = ABSENT
    category: Category = None


@dataclass
class CallInfo:
    element: ElementInfo
    key: ElementInfo


@dataclass(frozen=True)
class Element:
    name: object
    category: Category = None
    capture: object = None

    def filter(self, info):
        if not isinstance(info, ElementInfo):
            return None, False
        if self.name is not None and self.name != info.name:
            return None, False
        if self.category and not self.category.matches(info.category):
            return None, False

        if self.capture is None:
            return True, []
        else:
            return True, [(info.name, self.capture, info.value)]


@dataclass(frozen=True)
class Call:
    element: object
    key: object = None
    captures: tuple = ()

    def filter(self, info):
        if not isinstance(info, CallInfo):
            return None, False
        success, elem_cap = self.element.filter(info.element)
        if not success:
            return None, False
        if self.key is None:
            key_cap = []
        else:
            success, key_cap = self.key.filter(info.key)
            if not success:
                return None, False
        this_cap = [(name, key, ABSENT) for name, key in self.captures]
        return True, elem_cap + key_cap + this_cap


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


parse = opparse.Parser(
    lexer=opparse.Lexer(
        {
            r" *(?:\bas\b|>>|[(){}\[\]>.:,$])? *": "OPERATOR",
            r"[a-zA-Z_0-9*]+": "WORD",
        }
    ),
    order=opparse.OperatorPrecedenceTower(
        {
            ",": opparse.rassoc(10),
            "as": opparse.rassoc(50),
            ("", ">", ">>", "~"): opparse.rassoc(100),
            ":": opparse.lassoc(200),
            "$": opparse.lassoc(300),
            ("(", "[", "{"): opparse.obrack(500),
            (")", "]", "}"): opparse.cbrack(500),
            ": WORD": opparse.lassoc(1000),
        }
    ),
)


def _guarantee_call(parent):
    if isinstance(parent, Element):
        parent = Call(element=parent, key=None, captures=(),)
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
        name=element.name, category=category_registry[klass.name], capture=None
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
    captures = ()
    return Call(element=element, key=key, captures=captures)


@parse.register_action("X { X } _")
def make_call_capture(node, call, names, _2):
    call = _guarantee_call(call)
    names = names if isinstance(names, list) else [names]
    return Call(
        element=call.element,
        key=call.key,
        captures=call.captures
        + tuple((name.name, name.capture or name.name) for name in names),
    )


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
