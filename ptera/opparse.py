import math
import re
from dataclasses import dataclass


@dataclass
class Location:
    source: str
    filename: str
    start: int
    end: int

    def syntax_error(self, msg="Invalid syntax"):
        err = SyntaxError(msg)
        err.lineno = 1
        err.offset = self.start + 1
        err.filename = self.filename
        err.text = self.source
        return err


class Token:
    def __init__(self, value, type, source, start, end):
        self.value = value.strip()
        self.type = type
        self.location = Location(
            source=source, filename="<string>", start=start, end=end,
        )


class ASTNode:
    def __init__(self, parts):
        self.args = [p for i, p in enumerate(parts) if i % 2 == 0]
        self.ops = [p for i, p in enumerate(parts) if i % 2 == 1]
        self.key = " ".join(
            ("_" if p is None else "X") if i % 2 == 0 else p.value
            for i, p in enumerate(parts)
        )
        nonnulls = [p for p in parts if p is not None]
        assert nonnulls
        self.location = Location(
            source=nonnulls[0].location.source,
            filename=nonnulls[0].location.filename,
            start=nonnulls[0].location.start,
            end=nonnulls[-1].location.end,
        )


class Lexer:
    def __init__(self, definitions):
        self.regexp = re.compile(f'({")|(".join(definitions)})')
        self.token_types = [None, *definitions.values()]

    def __call__(self, code):
        code = code.strip()
        tokens = []
        current = 0
        for i, entry in enumerate(self.regexp.split(code)):
            if entry:
                tokens.append(
                    Token(
                        value=entry,
                        type=self.token_types[i % len(self.token_types)],
                        source=code,
                        start=current,
                        end=current + len(entry),
                    )
                )
                current += len(entry)
        return tokens


class OperatorPrecedenceTower:
    def __init__(self, operators):
        self.operators = {}
        for keys, prio in operators.items():
            if not isinstance(keys, tuple):
                keys = (keys,)
            for key in keys:
                self.operators[key] = prio

    def resolve(self, op):
        if op is None:
            return (-math.inf, -math.inf)
        elif op.value in self.operators:
            return self.operators[op.value]
        elif f": {op.type}" in self.operators:
            return self.operators[f": {op.type}"]
        else:
            raise op.location.syntax_error(
                f"Invalid token: {op.value} :: {op.type}"
            )

    def __call__(self, op1, op2):
        if op1 is None and op2 is None:
            return "done"
        _, lprio = self.resolve(op1)
        rprio, _ = self.resolve(op2)
        return rprio - lprio


class Parser:
    def __init__(self, lexer, order, actions=None):
        self.lexer = lexer
        self.order = order

    def __call__(self, code):
        tokens = self.lexer(code)
        return self.process(tokens)

    def process(self, tokens):
        def _next():
            return tokens.pop() if tokens else None

        tokens = list(reversed(tokens))
        stack = []
        # middle points to the handle between the two operators we are
        # currently comparing (None if the two tokens are consecutive)
        middle = None
        left = None
        right = _next()
        current = [None, left]
        while True:
            order = self.order(left, right)
            if order == "done":
                # Returned when left and right are both None (out of bounds)
                return middle
            elif order > 0:
                # Open new handle; it's like inserting "(" between left and
                # middle
                stack.append(current)
                current = [middle, right]
                middle = None
                left = right
                right = _next()
            elif order < 0:
                # Close current handle; it's like inserting ")" between middle
                # and right and then the newly closed block becomes the new
                # middle
                current.append(middle)
                middle = self.finalize(current)
                current = stack.pop()
                left = current[-1]
            elif order == 0:
                # Merge to current handle and keep going
                current += [middle, right]
                middle = None
                left = right
                right = _next()
            else:
                raise AssertionError(
                    "Invalid operator ordering"
                )  # pragma: no cover

    def finalize(self, parts):
        if len(parts) == 3 and parts[0] is None and parts[2] is None:
            return parts[1]
        return ASTNode(parts)


def lassoc(prio):
    return (prio, prio + 1)


def rassoc(prio):
    return (prio, prio - 1)


def obrack(prio):
    return (prio, 0)


def cbrack(prio):
    return (0, prio + 1)


__all__ = [
    "ASTNode",
    "Lexer",
    "OperatorPrecedenceTower",
    "Parser",
    "Token",
    "cbrack",
    "lassoc",
    "obrack",
    "rassoc",
]
