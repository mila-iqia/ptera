"""Parser for the selector syntax."""

import math
import re


class Location:
    """Location in source code that corresponds to a node.

    Attributes:
        source: String that contains the source code.
        filename: Name of the file the source code came from.
        start: Offset of the first character.
        end: Offset of the last character plus one.
    """

    def __init__(self, source, filename, start, end):
        self.source = source
        self.filename = filename
        self.start = start
        self.end = end

    def syntax_error(self, msg="Invalid syntax"):
        """Raise a syntax error at this location."""
        err = SyntaxError(msg)
        err.lineno = 1
        err.offset = self.start + 1
        err.filename = self.filename
        err.text = self.source
        return err


class Token:
    """Token produced by the lexer.

    Attributes:
        value: Textual value of the token.
        type: Type of the token.
        location: Location of the token.
    """

    def __init__(self, value, type, source, start, end):
        """Initialize a Token.

        Arguments:
            value: Textual value of the token.
            type: Type of the token.
            source: Complete source code the token is from.
            start: Offset of the first character.
            end: Offset of the last character plus one.
        """
        self.value = value.strip()
        self.type = type
        self.location = Location(
            source=source, filename="<string>", start=start, end=end
        )


class ASTNode:
    """Node that results from parsing.

    Attributes:
        args: List of arguments.
        ops: List of operators. Generally one less than the number of
            arguments.
        key: String key that represents the kind of operation we are
            dealing with: which arguments are non-null and what the ops
            are. If args == [a, b, None] and ops == [+, -] then
            key == "X + X - _".
        location: Location of the node in the source code. It encompasses
            the locations of all args and ops.
    """

    def __init__(self, parts):
        """Initialize an ASTNode from a list of parts.

        The parts are arguments interleaved with ops in a pattern like
        [arg1, op1, arg2, op2, ..., argn]. Some arguments may be None,
        which means there was nothing at that position.
        """
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
    """The Lexer splits source code into Tokens."""

    def __init__(self, definitions):
        """Initialize a Lexer.

        Arguments:
            definitions: A dictionary mapping regular expressions
                to token types.
        """
        self.definitions = definitions
        self.token_types = [None, *definitions.values()]

    def __call__(self, code):
        """Lex the given code.

        We match each regexp in the definitions list in order and produce
        a list of tokens with the corresponding types.
        """
        code = code.strip()
        tokens = []
        current = 0
        while code:
            for rx, typ in self.definitions.items():
                m = re.match(rx, code)
                if m:
                    tokens.append(
                        Token(
                            value=code[: m.end()],
                            type=typ,
                            source=code,
                            start=current,
                            end=current + m.end(),
                        )
                    )
                    current += m.end()
                    code = code[m.end() :]
                    break
            else:
                tokens.append(
                    Token(
                        value=code[:1],
                        type=None,
                        source=code,
                        start=current,
                        end=current + 1,
                    )
                )
                code = code[1:]
                current += 1
        return tokens


class OperatorPrecedenceTower:
    """Compare operators using a simple operator tower."""

    def __init__(self, operators):
        """Initialize an OperatorPrecedenceTower.

        Arguments:
            operators: A dict from an operator name or a tuple of operator
                names to a priority tuple (right_prio, left_prio) used to
                compare priority when the operator is on the right or left
                of another, respectively.

                An operator is left-associative if the left_prio (the second
                element of the tuple) is greater and its right_prio.

                An operator of the form ": TOKEN_TYPE" will match all tokens
                with that type.
        """
        self.operators = {}
        for keys, prio in operators.items():
            if not isinstance(keys, tuple):
                keys = (keys,)
            for key in keys:
                self.operators[key] = prio

    def resolve(self, op):
        """Resolve the priority tuple for a given op."""
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
        """Compare op1 to op2.

        We assume that op1 is on the left of some argument and op2 is on
        the right, like this:

        ... op1 ARG op2 ...

        * If the left_prio of op1 is greater than the right_prio of op2, then
          we will parenthesize the expression like `(... op1 ARG) op2 ...`.
        * If the left_prio of op1 is less than the right_prio of op2, then
          we will parenthesize the expression like `... op1 (ARG op2 ...)`.
        * If the left_prio of op1 is equal to the right_prio of op2, then
          both ops are part of the same operator. This may happen if e.g.
          we have a ternary operator, or if we are comparing an opening bracket
          to a closing bracket.
        """
        if op1 is None and op2 is None:
            return "done"
        _, lprio = self.resolve(op1)
        rprio, _ = self.resolve(op2)
        return rprio - lprio


class Parser:
    """Operator precedence parser."""

    def __init__(self, lexer, order):
        """Initialize the Parser.

        Arguments:
            lexer: The lexer to use for tokenization.
            order: A function to use to determine which operations have
                priority over which other operations.
        """
        self.lexer = lexer
        self.order = order

    def __call__(self, code):
        """Parse the given code."""
        tokens = self.lexer(code)
        return self.process(tokens)

    def process(self, tokens):
        """Process a list of tokens."""

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
        """Clean up a list of parts that form a completed ASTNode.

        * If the parts are [None, op, None], this is just the op.
        * If the parts are [arg1, op1, arg2, op2, ... argn] then we
          create an ASTNode with the given args and ops.
        """
        if len(parts) == 3 and parts[0] is None and parts[2] is None:
            return parts[1]
        return ASTNode(parts)


def lassoc(prio):
    """Create a priority tuple for a left-associative operator."""
    return (prio, prio + 1)


def rassoc(prio):
    """Create a priority tuple for a right-associative operator."""
    return (prio, prio - 1)


def obrack(prio):
    """Create a priority tuple for an opening bracket."""
    return (prio, 0)


def cbrack(prio):
    """Create a priority tuple for a closing bracket."""
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
