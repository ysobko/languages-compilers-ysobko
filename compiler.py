import os
import sys

from llvmlite import ir
import llvmlite.binding as llvm


I1 = ir.IntType(1)
I8 = ir.IntType(8)
I32 = ir.IntType(32)
I64 = ir.IntType(64)

I32_MAX = 2 ** 31 - 1
I64_MAX = 2 ** 63 - 1


class CompileError(Exception):
    pass


class ProgramNode:
    def __init__(
        self,
        structs,
        functions,
        statements,
        exit_node
    ):
        self.structs = structs
        self.functions = functions
        self.statements = statements
        self.exit = exit_node

    def accept(self, visitor):
        return visitor.visit_program(self)


class StmtNode:
    pass

class StructNode:
    def __init__(self, name, fields, line, column, methods=None):
        self.name = name
        self.fields = fields
        self.methods = methods if methods is not None else []
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_struct(self)


class FieldDeclNode:
    def __init__(
        self,
        name,
        type_name,
        mutable,
        line,
        column
    ):
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.line = line
        self.column = column
        self.index = None

    def accept(self, visitor):
        return visitor.visit_field_decl(self)


class ParameterNode:
    def __init__(self, name, type_name, line, column):
        self.name = name
        self.type_name = type_name
        self.line = line
        self.column = column
        self.mutable = False
        self.ir_ptr = None

    def accept(self, visitor):
        return visitor.visit_parameter(self)


class FunctionNode:
    def __init__(
        self,
        name,
        parameters,
        return_type,
        body,
        line,
        column
    ):
        self.name = name
        self.parameters = parameters
        self.return_type = return_type
        self.body = body
        self.line = line
        self.column = column
        self.ir_function = None

    def accept(self, visitor):
        return visitor.visit_function(self)


class MemberCallNode:
    def __init__(self, obj, name, arguments, line, column):
        self.obj = obj
        self.name = name
        self.arguments = arguments
        self.line = line
        self.column = column
        self.type = None

    def accept(self, visitor):
        if (
            hasattr(self, "callable_member")
            and not isinstance(visitor, SemanticChecker)
        ):
            return self.callable_member.accept(visitor)

        return visitor.visit_member_call(self)


class DeclNode(StmtNode):
    def __init__(self, name, type_name, mutable, init, line, column):
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init
        self.init_values = (
            init if isinstance(init, list) else [init]
        )
        self.line = line
        self.column = column
        self.ir_ptr = None

    def accept(self, visitor):
        return visitor.visit_decl(self)


class AssignNode(StmtNode):
    def __init__(
        self,
        name,
        value,
        line,
        column,
        fields=None
    ):
        self.name = name
        self.value = value
        self.line = line
        self.column = column
        self.fields = fields or []
        self.decl = None
        self.resolved_fields = []

    def accept(self, visitor):
        return visitor.visit_assign(self)


class IfNode(StmtNode):
    def __init__(
        self,
        condition,
        then_block,
        else_block,
        line,
        column
    ):
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_if(self)


class BlockNode:
    def __init__(self, statements, exit_node, line, column):
        self.statements = statements
        self.exit = exit_node
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_block(self)


class ExitNode:
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_exit(self)


class ExprNode:
    def __init__(self):
        self.type = None


class StructInitNode(ExprNode):
    def __init__(self, values, line, column):
        super().__init__()
        self.values = values
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_struct_init(self)


class BinOpNode(ExprNode):
    def __init__(self, op, left, right, line, column):
        super().__init__()
        self.op = op
        self.left = left
        self.right = right
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_binop(self)


class VarNode(ExprNode):
    def __init__(self, name, line, column):
        super().__init__()
        self.name = name
        self.line = line
        self.column = column
        self.decl = None

    def accept(self, visitor):
        return visitor.visit_var(self)


class FieldAccessNode(ExprNode):
    def __init__(self, name, fields, line, column):
        super().__init__()
        self.name = name
        self.fields = fields
        self.line = line
        self.column = column
        self.decl = None
        self.resolved_fields = []

    def accept(self, visitor):
        return visitor.visit_field_access(self)


class ResultFieldNode(ExprNode):
    def __init__(self, obj, field, line, column):
        super().__init__()
        self.obj = obj
        self.field = field
        self.line = line
        self.column = column
        self.resolved_field = None

    def accept(self, visitor):
        return visitor.visit_result_field(self)


class CallNode(ExprNode):
    def __init__(self, name, arguments, line, column):
        super().__init__()
        self.name = name
        self.arguments = arguments
        self.line = line
        self.column = column
        self.function = None

    def accept(self, visitor):
        if (
            hasattr(self, "callable_member")
            and not isinstance(visitor, SemanticChecker)
        ):
            return self.callable_member.accept(visitor)

        return visitor.visit_call(self)


class ConstNode(ExprNode):
    def __init__(self, value, line, column):
        super().__init__()
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_const(self)


class BoolNode(ExprNode):
    def __init__(self, value, line, column):
        super().__init__()
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_bool(self)


class NotNode(ExprNode):
    def __init__(self, value, line, column):
        super().__init__()
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_not(self)


class ReadNode(ExprNode):
    def __init__(self, line, column):
        super().__init__()
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_read(self)


class StringNode(ExprNode):
    def __init__(self, value, line, column):
        super().__init__()
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_string(self)


class PrintNode(StmtNode):
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_print(self)


class Token:
    def __init__(self, kind, text, line, column):
        self.kind = kind
        self.text = text
        self.line = line
        self.column = column

    def __repr__(self):
        return (
            f"Token({self.kind!r}, {self.text!r}, "
            f"{self.line}:{self.column})"
        )


KEYWORDS = {
    "i32": "keyword",
    "i64": "keyword",
    "bool": "keyword",
    "mut": "keyword",
    "exit": "keyword",
    "true": "keyword",
    "false": "keyword",
    "if": "keyword",
    "else": "keyword",
    "struct": "keyword",
    "fn": "keyword",
    "read": "keyword",
    "print": "keyword",
}


def is_alpha(b):
    return (
        ord("a") <= b <= ord("z")
        or ord("A") <= b <= ord("Z")
        or b == ord("_")
    )


def is_digit(b):
    return ord("0") <= b <= ord("9")


def lex(data: bytes):
    lines = []
    tokens = []

    state = "START"
    start = 0
    start_col = 1

    line = 1
    col = 1
    i = 0

    while i <= len(data):
        b = data[i] if i < len(data) else None

        if state == "START":
            if b is None:
                break

            if b in (32, 9):
                pass

            elif b == 10:
                tokens.append(
                    Token("endline", "\n", line, col)
                )

                lines.append(tokens)
                tokens = []

                line += 1
                col = 0

            elif b == ord('"'):
                start_col = col
                end = data.find(b'"', i + 1)

                if end == -1 or b"\n" in data[i + 1:end]:
                    raise CompileError(
                        f"line {line}:{col}: unterminated string literal"
                    )

                value = data[i + 1:end]

                if b"\\" in value:
                    raise CompileError(
                        f"line {line}:{col}: string escapes are not supported"
                    )

                try:
                    text = value.decode("utf-8")
                except UnicodeDecodeError:
                    raise CompileError(
                        f"line {line}:{col}: invalid UTF-8 string"
                    )

                tokens.append(Token("string", text, line, col))
                col += end - i
                i = end

            elif is_alpha(b):
                state = "IDENT"
                start = i
                start_col = col

            elif is_digit(b):
                state = "NUMBER"
                start = i
                start_col = col

            elif b == ord("{"):
                tokens.append(
                    Token("block", "{", line, col)
                )

            elif b == ord("}"):
                tokens.append(
                    Token("block", "}", line, col)
                )

            elif b == ord("+"):
                tokens.append(
                    Token("operator", "+", line, col)
                )

            elif b == ord("-"):
                if (
                    i + 1 < len(data)
                    and data[i + 1] == ord(">")
                ):
                    tokens.append(
                        Token("operator", "->", line, col)
                    )
                    i += 1
                    col += 1
                else:
                    tokens.append(
                        Token("operator", "-", line, col)
                    )

            elif b == ord("*"):
                tokens.append(
                    Token("operator", "*", line, col)
                )

            elif b == ord(","):
                tokens.append(
                    Token("punctuation", ",", line, col)
                )

            elif b == ord("."):
                tokens.append(
                    Token("punctuation", ".", line, col)
                )

            elif b == ord("("):
                tokens.append(
                    Token("punctuation", "(", line, col)
                )

            elif b == ord(")"):
                tokens.append(
                    Token("punctuation", ")", line, col)
                )

            elif b == ord(":"):
                state = "COLON"
                start_col = col

            elif b == ord("="):
                state = "EQUAL"
                start_col = col

            elif b == ord("!"):
                state = "BANG"
                start_col = col

            else:
                if 32 <= b <= 126:
                    char = chr(b)
                else:
                    char = f"0x{b:02x}"

                raise CompileError(
                    f"line {line}:{col}: "
                    f"unexpected byte '{char}'"
                )

        elif state == "IDENT":
            if (
                b is not None
                and (is_alpha(b) or is_digit(b))
            ):
                pass

            else:
                word = data[start:i].decode("ascii")

                kind = KEYWORDS.get(
                    word,
                    "identifier"
                )

                tokens.append(
                    Token(
                        kind,
                        word,
                        line,
                        start_col
                    )
                )

                state = "START"
                continue

        elif state == "NUMBER":
            if b is not None and is_digit(b):
                pass

            elif b is not None and is_alpha(b):
                raise CompileError(
                    f"line {line}:{start_col}: "
                    "letter inside number"
                )

            else:
                number = data[start:i].decode("ascii")

                tokens.append(
                    Token(
                        "number",
                        number,
                        line,
                        start_col
                    )
                )

                state = "START"
                continue

        elif state == "COLON":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        ":=",
                        line,
                        start_col
                    )
                )

                state = "START"

            else:
                raise CompileError(
                    f"line {line}:{start_col}: "
                    "':' must be followed by '='"
                )

        elif state == "EQUAL":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        "==",
                        line,
                        start_col
                    )
                )

                state = "START"

            else:
                raise CompileError(
                    f"line {line}:{start_col}: "
                    "expected '==' "
                    "(a single '=' is not an operator)"
                )

        elif state == "BANG":
            if b == ord("="):
                tokens.append(
                    Token(
                        "operator",
                        "!=",
                        line,
                        start_col
                    )
                )

                state = "START"

            else:
                tokens.append(
                    Token(
                        "operator",
                        "!",
                        line,
                        start_col
                    )
                )

                state = "START"
                continue

        i += 1
        col += 1

    if tokens:
        lines.append(tokens)

    return lines


def print_tokens(token_lines):
    for line in token_lines:
        for token in line:
            if token.kind == "endline":
                continue

            print(
                f"{token.text}\t"
                f"{token.kind}\t"
                f"{token.line}:{token.column}"
            )


def error_at(token, message):
    raise CompileError(
        f"line {token.line}:{token.column}: {message}"
    )


class Parser:
    def __init__(self, token_lines):
        self.token_lines = token_lines
        self.line_position = 0
        self.tokens = []
        self.position = 0

    def set_line(self, tokens):
        self.tokens = [
            token
            for token in tokens
            if token.kind != "endline"
        ]
        self.position = 0

    def peek_line(self):
        position = self.line_position

        while position < len(self.token_lines):
            tokens = [
                token
                for token in self.token_lines[position]
                if token.kind != "endline"
            ]

            if tokens:
                return tokens

            position += 1

        return None

    def next_line(self):
        while self.line_position < len(self.token_lines):
            raw_tokens = self.token_lines[self.line_position]
            self.line_position += 1
            self.set_line(raw_tokens)

            if self.tokens:
                return True

        self.tokens = []
        self.position = 0
        return False

    def peek(self):
        if self.position >= len(self.tokens):
            return None

        return self.tokens[self.position]

    def eat(self, text=None, kind=None):
        token = self.peek()

        if token is None:
            raise CompileError(
                "unexpected end of line"
            )

        if text is not None and token.text != text:
            error_at(
                token,
                f"expected '{text}'"
            )

        if kind is not None and token.kind != kind:
            error_at(
                token,
                f"expected {kind}"
            )

        self.position += 1
        return token

    def end_column(self):
        if not self.tokens:
            return 1

        last = self.tokens[-1]
        return last.column + len(last.text)

    def parse_factor(self):
        token = self.peek()

        if token is None:
            if self.tokens:
                raise CompileError(
                    f"line {self.tokens[-1].line}:"
                    f"{self.end_column()}: "
                    "expected constant or variable"
                )

            raise CompileError(
                "line 1:1: expected constant or variable"
            )

        if token.text == "!":
            operator = self.eat(text="!")
            value = self.parse_factor()

            return NotNode(
                value,
                operator.line,
                operator.column
            )

        if token.text == "read":
            self.eat(text="read")
            self.eat(text="(")

            if self.peek() is not None and self.peek().text != ")":
                error_at(self.peek(), "read() takes no arguments")

            self.eat(text=")")
            return ReadNode(token.line, token.column)

        if token.kind == "string":
            error_at(token, "string literal is only allowed in print()")

        if token.kind == "number":
            self.eat(kind="number")

            return ConstNode(
                int(token.text),
                token.line,
                token.column
            )

        if token.text in ("true", "false"):
            self.eat()

            return BoolNode(
                token.text == "true",
                token.line,
                token.column
            )

        if token.kind == "identifier":
            self.eat(kind="identifier")

            if (
                self.peek() is not None
                and self.peek().text == "("
            ):
                self.eat(text="(")
                arguments = []

                if (
                    self.peek() is not None
                    and self.peek().text != ")"
                ):
                    while True:
                        arguments.append(
                            self.parse_expr()
                        )

                        if (
                            self.peek() is not None
                            and self.peek().text == ","
                        ):
                            self.eat(text=",")
                            continue

                        break

                self.eat(text=")")

                return CallNode(
                    token.text,
                    arguments,
                    token.line,
                    token.column
                )

            if (
                self.peek() is not None
                and self.peek().text == "."
            ):
                fields = []

                while (
                    self.peek() is not None
                    and self.peek().text == "."
                ):
                    self.eat(text=".")
                    field = self.eat(kind="identifier")
                    fields.append(field.text)

                if (
                    self.peek() is not None
                    and self.peek().text == "("
                ):
                    self.eat(text="(")
                    arguments = []

                    if (
                        self.peek() is not None
                        and self.peek().text != ")"
                    ):
                        while True:
                            arguments.append(self.parse_expr())

                            if (
                                self.peek() is not None
                                and self.peek().text == ","
                            ):
                                self.eat(text=",")
                                continue

                            break

                    self.eat(text=")")

                    if len(fields) == 1:
                        obj = VarNode(
                            token.text,
                            token.line,
                            token.column
                        )
                    else:
                        obj = FieldAccessNode(
                            token.text,
                            fields[:-1],
                            token.line,
                            token.column
                        )

                    return MemberCallNode(
                        obj,
                        fields[-1],
                        arguments,
                        token.line,
                        token.column
                    )

                return FieldAccessNode(
                    token.text,
                    fields,
                    token.line,
                    token.column
                )

            return VarNode(
                token.text,
                token.line,
                token.column
            )

        error_at(
            token,
            "expected a constant or variable"
        )

    def parse_postfix(self, node):
        while self.peek() is not None and self.peek().text == ".":
            dot = self.eat(text=".")
            name = self.eat(kind="identifier")

            if self.peek() is not None and self.peek().text == "(":
                self.eat(text="(")
                arguments = []

                if self.peek() is not None and self.peek().text != ")":
                    while True:
                        arguments.append(self.parse_expr())

                        if self.peek() is not None and self.peek().text == ",":
                            self.eat(text=",")
                            continue

                        break

                self.eat(text=")")

                node = MemberCallNode(
                    node,
                    name.text,
                    arguments,
                    dot.line,
                    dot.column
                )
            else:
                node = ResultFieldNode(
                    node,
                    name.text,
                    dot.line,
                    dot.column
                )

        return node

    def parse_term(self):
        left = self.parse_postfix(self.parse_factor())

        while (
            self.peek() is not None
            and self.peek().text == "*"
        ):
            operator = self.eat()
            right = self.parse_factor()

            left = BinOpNode(
                operator.text,
                left,
                right,
                operator.line,
                operator.column
            )

        return left

    def parse_arith(self):
        left = self.parse_term()

        while (
            self.peek() is not None
            and self.peek().text in ("+", "-")
        ):
            operator = self.eat()
            right = self.parse_term()

            left = BinOpNode(
                operator.text,
                left,
                right,
                operator.line,
                operator.column
            )

        return left

    def parse_expr(self):
        left = self.parse_arith()

        if (
            self.peek() is not None
            and self.peek().text in ("==", "!=")
        ):
            operator = self.eat()
            right = self.parse_arith()

            left = BinOpNode(
                operator.text,
                left,
                right,
                operator.line,
                operator.column
            )

        return left

    def parse_initializer_value(self):
        token = self.peek()

        if token is None or token.text != "{":
            return self.parse_expr()

        open_brace = self.eat(text="{")
        values = []

        if self.peek() is not None and self.peek().text != "}":
            values.append(self.parse_initializer_value())

            while (
                self.peek() is not None
                and self.peek().text == ","
            ):
                self.eat(text=",")
                values.append(self.parse_initializer_value())

        token = self.peek()

        if token is None:
            raise CompileError(
                f"line {open_brace.line}:"
                f"{self.end_column()}: expected '}}', found end of line"
            )

        self.eat(text="}")

        return StructInitNode(
            values,
            open_brace.line,
            open_brace.column
        )

    def parse_decl(self):
        type_token = self.peek()

        if type_token is None:
            raise CompileError(
                "unexpected end of line"
            )

        if (
            type_token.text not in ("i32", "i64", "bool")
            and type_token.kind != "identifier"
        ):
            error_at(
                type_token,
                "expected type"
            )

        self.eat()

        mutable = False
        token = self.peek()

        if token is not None and token.text == "mut":
            self.eat(text="mut")
            mutable = True

        name_token = self.peek()

        if name_token is None:
            raise CompileError(
                f"line {type_token.line}:{self.end_column()}: "
                "expected variable name"
            )

        name_token = self.eat(kind="identifier")

        token = self.peek()

        if token is None:
            raise CompileError(
                f"line {name_token.line}:"
                f"{name_token.column + len(name_token.text)}: "
                f"variable '{name_token.text}' "
                "needs an initialiser in {}"
            )

        if token.text != "{":
            error_at(
                token,
                f"variable '{name_token.text}' "
                "needs an initialiser in {}"
            )

        self.eat(text="{")

        values = []

        if self.peek() is not None and self.peek().text != "}":
            values.append(self.parse_initializer_value())

            while (
                self.peek() is not None
                and self.peek().text == ","
            ):
                self.eat(text=",")
                values.append(self.parse_initializer_value())

        token = self.peek()

        if token is None:
            raise CompileError(
                f"line {type_token.line}:"
                f"{self.end_column()}: expected '}}', found end of line"
            )

        self.eat(text="}")

        init = values[0] if len(values) == 1 else values

        return DeclNode(
            name_token.text,
            type_token.text,
            mutable,
            init,
            name_token.line,
            name_token.column
        )

    def parse_assign(self):
        name_token = self.eat(kind="identifier")
        fields = []

        while (
            self.peek() is not None
            and self.peek().text == "."
        ):
            self.eat(text=".")
            field = self.eat(kind="identifier")
            fields.append(field.text)

        token = self.peek()

        if token is None:
            raise CompileError(
                f"line {name_token.line}:"
                f"{name_token.column + len(name_token.text)}: "
                "expected ':='"
            )

        if token.text != ":=":
            error_at(
                token,
                f"expected ':=' after '{name_token.text}'"
            )

        self.eat(text=":=")

        value = self.parse_expr()

        return AssignNode(
            name_token.text,
            value,
            name_token.line,
            name_token.column,
            fields
        )

    def parse_exit(self):
        start = self.eat(text="exit")
        value = self.parse_factor()

        return ExitNode(
            value,
            start.line,
            start.column
        )

    def parse_block(self):
        if not self.next_line():
            raise CompileError(
                "line 1:1: expected '{' after 'if'"
            )

        token = self.peek()

        if token.text != "{":
            error_at(
                token,
                f"expected '{{' on its own line after 'if', "
                f"got '{token.text}'"
            )

        block_start = self.eat(text="{")
        self.ensure_end()

        statements = []
        exit_node = None

        while True:
            if not self.next_line():
                raise CompileError(
                    f"line {block_start.line}:"
                    f"{block_start.column}: "
                    "'{' is never closed"
                )

            first = self.peek()

            if first.text == "}":
                self.eat(text="}")
                self.ensure_end()

                if not statements and exit_node is None:
                    raise CompileError(
                        f"line {block_start.line}:"
                        f"{block_start.column}: empty block"
                    )

                return BlockNode(
                    statements,
                    exit_node,
                    block_start.line,
                    block_start.column
                )

            if exit_node is not None:
                error_at(
                    first,
                    "statement after 'exit' in the same block"
                )

            if first.text == "exit":
                exit_node = self.parse_exit()
                self.ensure_end()
                continue

            if first.text == "else":
                error_at(
                    first,
                    "'else' without an 'if'"
                )

            statement = self.parse_statement()
            self.ensure_end()
            statements.append(statement)

    def parse_if(self):
        if_token = self.eat(text="if")

        if self.peek() is None:
            raise CompileError(
                f"line {if_token.line}:"
                f"{if_token.column + 2}: "
                "expected condition after 'if'"
            )

        condition = self.parse_expr()

        token = self.peek()

        if token is not None:
            if token.text == "{":
                error_at(
                    token,
                    "unexpected '{' after the statement"
                )

            error_at(
                token,
                "extra tokens after statement"
            )

        then_block = self.parse_block()
        else_block = None

        next_tokens = self.peek_line()

        if (
            next_tokens is not None
            and next_tokens[0].text == "else"
        ):
            self.next_line()
            else_token = self.eat(text="else")
            self.ensure_end()

            if self.peek_line() is None:
                raise CompileError(
                    f"line {else_token.line}:"
                    f"{else_token.column}: "
                    "expected '{' after 'else'"
                )

            else_block = self.parse_block()

        return IfNode(
            condition,
            then_block,
            else_block,
            if_token.line,
            if_token.column
        )

    def parse_struct(self):
        struct_token = self.eat(text="struct")

        name_token = self.peek()

        if name_token is None:
            raise CompileError(
                f"line {struct_token.line}:"
                f"{struct_token.column + len(struct_token.text)}: "
                "expected struct name"
            )

        name_token = self.eat(kind="identifier")
        self.ensure_end()

        if not self.next_line():
            raise CompileError(
                f"line {name_token.line}:"
                f"{name_token.column}: "
                "expected '{' after struct declaration"
            )

        token = self.peek()

        if token.text != "{":
            error_at(
                token,
                "expected '{' after struct declaration"
            )

        block_start = self.eat(text="{")
        self.ensure_end()

        fields = []
        methods = []

        while True:
            if not self.next_line():
                raise CompileError(
                    f"line {block_start.line}:"
                    f"{block_start.column}: "
                    "'{' is never closed"
                )

            first = self.peek()

            if first.text == "}":
                self.eat(text="}")
                self.ensure_end()

                if not fields:
                    raise CompileError(
                        f"line {block_start.line}:"
                        f"{block_start.column}: "
                        "struct must have at least one field"
                    )

                return StructNode(
                    name_token.text,
                    fields,
                    struct_token.line,
                    struct_token.column,
                    methods
                )

            if first.text == "fn":
                if not fields:
                    error_at(
                        first,
                        "member function requires at least one field"
                    )

                method = self.parse_function()

                if any(field.name == method.name for field in fields):
                    raise CompileError(
                        f"line {method.line}:{method.column}: "
                        f"member function '{method.name}' "
                        "has the same name as a field"
                    )

                if any(existing.name == method.name for existing in methods):
                    raise CompileError(
                        f"line {method.line}:{method.column}: "
                        f"duplicate member function '{method.name}'"
                    )

                methods.append(method)
                continue

            if methods:
                error_at(
                    first,
                    "field cannot appear after a member function"
                )

            type_token = self.eat()

            if (
                type_token.text not in ("i32", "i64", "bool")
                and type_token.kind != "identifier"
            ):
                error_at(
                    type_token,
                    "expected field type"
                )

            mutable = False

            if (
                self.peek() is not None
                and self.peek().text == "mut"
            ):
                self.eat(text="mut")
                mutable = True

            field_token = self.peek()

            if field_token is None:
                raise CompileError(
                    f"line {type_token.line}:"
                    f"{self.end_column()}: "
                    "expected field name"
                )

            field_token = self.eat(kind="identifier")
            self.ensure_end()

            fields.append(
                FieldDeclNode(
                    field_token.text,
                    type_token.text,
                    mutable,
                    field_token.line,
                    field_token.column
                )
            )

    def parse_function(self):
        fn_token = self.eat(text="fn")

        name_token = self.peek()

        if name_token is None:
            raise CompileError(
                f"line {fn_token.line}:"
                f"{fn_token.column + len(fn_token.text)}: "
                "expected function name"
            )

        name_token = self.eat(kind="identifier")
        self.eat(text=":=")
        self.eat(text="(")

        parameters = []

        if self.peek() is not None and self.peek().text != ")":
            while True:
                type_token = self.peek()

                if type_token is None:
                    raise CompileError(
                        f"line {name_token.line}:"
                        f"{self.end_column()}: "
                        "expected parameter type"
                    )

                if (
                    type_token.text not in ("i32", "i64", "bool")
                    and type_token.kind != "identifier"
                ):
                    error_at(
                        type_token,
                        "expected parameter type"
                    )

                self.eat()

                param_token = self.peek()

                if param_token is None:
                    raise CompileError(
                        f"line {type_token.line}:"
                        f"{self.end_column()}: "
                        "expected parameter name"
                    )

                param_token = self.eat(kind="identifier")

                parameters.append(
                    ParameterNode(
                        param_token.text,
                        type_token.text,
                        param_token.line,
                        param_token.column
                    )
                )

                if (
                    self.peek() is not None
                    and self.peek().text == ","
                ):
                    self.eat(text=",")
                    continue

                break

        self.eat(text=")")
        self.eat(text="->")

        return_type = self.peek()

        if return_type is None:
            raise CompileError(
                f"line {name_token.line}:"
                f"{self.end_column()}: "
                "expected return type"
            )

        if (
            return_type.text not in ("i32", "i64", "bool")
            and return_type.kind != "identifier"
        ):
            error_at(
                return_type,
                "expected return type"
            )

        self.eat()
        self.ensure_end()

        body = self.parse_block()

        return FunctionNode(
            name_token.text,
            parameters,
            return_type.text,
            body,
            fn_token.line,
            fn_token.column
        )

    def parse_print(self):
        token = self.eat(text="print")
        self.eat(text="(")

        if self.peek() is None or self.peek().text == ")":
            raise CompileError(
                f"line {token.line}:{token.column}: print() expects one argument"
            )

        if self.peek().kind == "string":
            string_token = self.eat(kind="string")
            value = StringNode(
                string_token.text,
                string_token.line,
                string_token.column
            )
        else:
            value = self.parse_expr()

        self.eat(text=")")
        return PrintNode(value, token.line, token.column)

    def parse_statement(self):
        token = self.peek()

        if token.text == "print":
            return self.parse_print()

        if token.text in ("i32", "i64", "bool"):
            return self.parse_decl()

        if token.kind == "identifier":
            position = self.position + 1

            while (
                position + 1 < len(self.tokens)
                and self.tokens[position].text == "."
                and self.tokens[position + 1].kind == "identifier"
            ):
                position += 2

            if (
                position < len(self.tokens)
                and self.tokens[position].text == ":="
            ):
                return self.parse_assign()

            return self.parse_decl()

        if token.text == "if":
            return self.parse_if()

        if token.text == "else":
            error_at(
                token,
                "'else' without an 'if'"
            )

        error_at(
            token,
            "invalid statement"
        )

    def ensure_end(self):
        token = self.peek()

        if token is not None:
            error_at(
                token,
                "extra tokens after statement"
            )

    def parse_program(self):
        structs = []
        functions = []
        statements = []
        exit_node = None
        phase = "struct"

        while self.next_line():
            first = self.peek()

            if exit_node is not None:
                error_at(
                    first,
                    "exit must be the last statement"
                )

            if first.text == "struct":
                if phase != "struct":
                    error_at(
                        first,
                        "struct declaration is not allowed here"
                    )

                struct_node = self.parse_struct()
                structs.append(struct_node)
                continue

            if first.text == "fn":
                if phase == "statement":
                    error_at(
                        first,
                        "function declaration is not allowed after statements"
                    )

                phase = "function"
                function_node = self.parse_function()
                functions.append(function_node)
                continue

            if first.text == "exit":
                exit_node = self.parse_exit()
                self.ensure_end()
                continue

            if first.text == "else":
                error_at(
                    first,
                    "'else' without an 'if'"
                )

            phase = "statement"
            node = self.parse_statement()
            self.ensure_end()
            statements.append(node)

        if exit_node is None:
            raise CompileError(
                "line 1:1: program has no exit statement"
            )

        return ProgramNode(
            structs,
            functions,
            statements,
            exit_node
        )



class SemanticChecker:
    def __init__(self):
        self.scopes = [{}]
        self.structs = {}
        self.functions = {}
        self.current_function = None
        self.current_struct = None

    def current_scope(self):
        return self.scopes[-1]

    def lookup(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]

        if self.current_struct is not None:
            for field in self.current_struct.fields:
                if field.name == name:
                    return field

        return None

    def visit_program(self, node):
        for struct in node.structs:
            struct.accept(self)

        for function in node.functions:
            if function.name in self.functions:
                raise CompileError(
                    f"line {function.line}:{function.column}: "
                    f"function '{function.name}' is already declared"
                )

            if (
                function.return_type not in ("i32", "i64", "bool")
                and function.return_type not in self.structs
            ):
                raise CompileError(
                    f"line {function.line}:{function.column}: "
                    f"unknown return type '{function.return_type}'"
                )

            self.functions[function.name] = function

        for function in node.functions:
            function.accept(self)

        for struct in node.structs:
            for method in struct.methods:
                self.check_member_function(struct, method)

        for statement in node.statements:
            statement.accept(self)

        node.exit.accept(self)

        self.analyze_member_mutability(node)

    def analyze_member_mutability(self, program):
        methods = []

        for struct in program.structs:
            for method in struct.methods:
                method.is_mutating = False
                methods.append(method)

        def expressions(node):
            if node is None:
                return

            if isinstance(node, AssignNode):
                yield from expressions(node.value)
                return

            if isinstance(node, PrintNode):
                yield from expressions(node.value)
                return

            if isinstance(node, DeclNode):
                for value in node.init_values:
                    yield from expressions(value)
                return

            if isinstance(node, BlockNode):
                for statement in node.statements:
                    yield from expressions(statement)
                yield from expressions(node.exit)
                return

            if isinstance(node, IfNode):
                yield from expressions(node.condition)
                yield from expressions(node.then_block)
                yield from expressions(node.else_block)
                return

            if isinstance(node, ExitNode):
                yield from expressions(node.value)
                return

            if isinstance(node, BinOpNode):
                yield from expressions(node.left)
                yield from expressions(node.right)
                return

            if isinstance(node, NotNode):
                yield from expressions(node.value)
                return

            if isinstance(node, StructInitNode):
                for value in node.values:
                    yield from expressions(value)
                return

            if isinstance(node, (CallNode, MemberCallNode)):
                resolved = getattr(node, "callable_member", node)
                yield resolved

                for argument in resolved.arguments:
                    yield from expressions(argument)
                return

        for struct in program.structs:
            for method in struct.methods:
                method.directly_mutating = False
                method.member_dependencies = []

                def scan(node):
                    if isinstance(node, AssignNode):
                        if isinstance(node.decl, FieldDeclNode):
                            method.directly_mutating = True

                        scan(node.value)
                        return

                    if isinstance(node, BlockNode):
                        for statement in node.statements:
                            scan(statement)
                        scan(node.exit)
                        return

                    if isinstance(node, IfNode):
                        scan(node.condition)
                        scan(node.then_block)
                        scan(node.else_block)
                        return

                    for call in expressions(node):
                        if isinstance(call, CallNode):
                            dependency = getattr(
                                call, "member_method", None
                            )
                            if dependency is not None:
                                method.member_dependencies.append(
                                    dependency
                                )

                        if isinstance(call, MemberCallNode):
                            receiver = call.obj

                            if isinstance(receiver.decl, FieldDeclNode):
                                method.member_dependencies.append(
                                    call.method
                                )

                scan(method.body)
                method.is_mutating = method.directly_mutating

        changed = True

        while changed:
            changed = False

            for method in methods:
                if method.is_mutating:
                    continue

                if any(
                    dependency.is_mutating
                    for dependency in method.member_dependencies
                ):
                    method.is_mutating = True
                    changed = True

        def check_calls(node):
            if node is None:
                return

            node = getattr(node, "callable_member", node)

            if isinstance(node, MemberCallNode):
                if node.method.is_mutating:
                    receiver = node.obj

                    current = receiver

                    while isinstance(current, ResultFieldNode):
                        if not current.resolved_field.mutable:
                            raise CompileError(
                                f"line {node.line}:{node.column}: "
                                "cannot call mutating member function "
                                f"'{node.name}' through const field"
                            )

                        current = current.obj

                    if isinstance(current, (VarNode, FieldAccessNode)):
                        if not current.decl.mutable:
                            raise CompileError(
                                f"line {node.line}:{node.column}: "
                                "cannot call mutating member function "
                                f"'{node.name}' on const object"
                            )

                        if isinstance(current, FieldAccessNode):
                            for field in current.resolved_fields:
                                if not field.mutable:
                                    raise CompileError(
                                        f"line {node.line}:{node.column}: "
                                        "cannot call mutating member function "
                                        f"'{node.name}' through const field"
                                    )

                    if isinstance(receiver, (VarNode, FieldAccessNode)):
                        if not receiver.decl.mutable:
                            raise CompileError(
                                f"line {node.line}:{node.column}: "
                                f"cannot call mutating member function "
                                f"'{node.name}' on const object"
                            )

                    if isinstance(receiver, FieldAccessNode):
                        for field in receiver.resolved_fields:
                            if not field.mutable:
                                raise CompileError(
                                    f"line {node.line}:{node.column}: "
                                    "cannot call mutating member function "
                                    f"'{node.name}' through const field"
                                )

            if isinstance(node, BlockNode):
                for statement in node.statements:
                    check_calls(statement)
                check_calls(node.exit)
                return

            if isinstance(node, IfNode):
                check_calls(node.condition)
                check_calls(node.then_block)
                check_calls(node.else_block)
                return

            if isinstance(node, PrintNode):
                check_calls(node.value)
                return

            if isinstance(node, DeclNode):
                for value in node.init_values:
                    check_calls(value)
                return

            if isinstance(node, AssignNode):
                check_calls(node.value)
                return

            if isinstance(node, ExitNode):
                check_calls(node.value)
                return

            if isinstance(node, BinOpNode):
                check_calls(node.left)
                check_calls(node.right)
                return

            if isinstance(node, NotNode):
                check_calls(node.value)
                return

            if isinstance(node, StructInitNode):
                for value in node.values:
                    check_calls(value)
                return

            if isinstance(node, (CallNode, MemberCallNode)):
                for argument in node.arguments:
                    check_calls(argument)

        for struct in program.structs:
            for method in struct.methods:
                check_calls(method.body)

        for function in program.functions:
            check_calls(function.body)

        for statement in program.statements:
            check_calls(statement)

        check_calls(program.exit)

    def visit_read(self, node):
        node.type = "i32"
        return node.type

    def visit_string(self, node):
        node.type = "string"
        return node.type

    def visit_print(self, node):
        node.value.accept(self)

        if node.value.type not in (
            "i32", "i64", "bool", "string"
        ) and node.value.type not in self.structs:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"cannot print type '{node.value.type}'"
            )

    def visit_struct(self, node):
        if node.name in self.structs:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"struct '{node.name}' is already declared"
            )

        fields = {}

        for index, field in enumerate(node.fields):
            if field.name in fields:
                raise CompileError(
                    f"line {field.line}:{field.column}: "
                    f"field '{field.name}' is already declared "
                    f"in struct '{node.name}'"
                )

            if field.type_name == node.name:
                raise CompileError(
                    f"line {field.line}:{field.column}: "
                    f"struct '{node.name}' cannot contain itself"
                )

            if (
                field.type_name not in ("i32", "i64", "bool")
                and field.type_name not in self.structs
            ):
                raise CompileError(
                    f"line {field.line}:{field.column}: "
                    f"unknown type '{field.type_name}'"
                )

            field.index = index
            fields[field.name] = field

        self.structs[node.name] = node

        method_names = set()

        for method in node.methods:
            if method.name in fields:
                raise CompileError(
                    f"line {method.line}:{method.column}: "
                    f"member function '{method.name}' "
                    "has the same name as a field"
                )

            if method.name in method_names:
                raise CompileError(
                    f"line {method.line}:{method.column}: "
                    f"duplicate member function '{method.name}'"
                )

            method_names.add(method.name)

            if (
                method.return_type not in ("i32", "i64", "bool")
                and method.return_type not in self.structs
            ):
                raise CompileError(
                    f"line {method.line}:{method.column}: "
                    f"unknown return type '{method.return_type}'"
                )

    def check_member_function(self, struct, method):
        previous_struct = self.current_struct

        self.current_struct = struct

        try:
            method.accept(self)
        finally:
            self.current_struct = previous_struct

    def visit_field_decl(self, node):
        pass

    def visit_block(self, node):
        self.scopes.append({})

        for statement in node.statements:
            statement.accept(self)

        if node.exit is not None:
            node.exit.accept(self)

        self.scopes.pop()

    def visit_if(self, node):
        condition_type = node.condition.accept(self)

        if condition_type != "bool":
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"the condition of 'if' must be bool, "
                f"got {condition_type}"
            )

        node.then_block.accept(self)

        if node.else_block is not None:
            node.else_block.accept(self)

    def visit_function(self, node):
        previous_scopes = self.scopes
        previous_function = self.current_function

        self.scopes = [{}]
        self.current_function = node

        for parameter in node.parameters:
            parameter.accept(self)

        node.body.accept(self)

        if node.body.exit is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"function '{node.name}' must end with exit"
            )

        self.current_function = previous_function
        self.scopes = previous_scopes

    def visit_parameter(self, node):
        scope = self.current_scope()

        if node.name in scope:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"parameter '{node.name}' is already declared"
            )

        if (
            node.type_name not in ("i32", "i64", "bool")
            and node.type_name not in self.structs
        ):
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"unknown type '{node.type_name}'"
            )

        scope[node.name] = node

    def check_initializer_value(
        self,
        value,
        target_type,
        what
    ):
        if isinstance(value, StructInitNode):
            struct = self.structs.get(target_type)

            if struct is None:
                raise CompileError(
                    f"line {value.line}:{value.column}: "
                    f"nested initialiser cannot initialise "
                    f"non-struct type '{target_type}'"
                )

            if len(value.values) != len(struct.fields):
                raise CompileError(
                    f"line {value.line}:{value.column}: "
                    f"struct '{target_type}' needs "
                    f"{len(struct.fields)} initialiser values, "
                    f"got {len(value.values)}"
                )

            for nested_value, field in zip(
                value.values,
                struct.fields
            ):
                self.check_initializer_value(
                    nested_value,
                    field.type_name,
                    f"initialise field '{field.name}'"
                )

            value.type = target_type
            return

        value.accept(self)

        if isinstance(value, ConstNode):
            self.check_constant_for_target(
                value,
                target_type
            )

        self.check_assignable(
            value,
            target_type,
            value.line,
            value.column,
            what
        )

    def visit_decl(self, node):
        scope = self.current_scope()

        if node.name in scope:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is already "
                "declared in this block"
            )

        if node.type_name in ("i32", "i64", "bool"):
            if len(node.init_values) != 1:
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"type {node.type_name} needs exactly one "
                    "initialiser value"
                )

            value = node.init_values[0]
            value.accept(self)

            if isinstance(value, ConstNode):
                self.check_constant_for_target(
                    value,
                    node.type_name
                )

            self.check_assignable(
                value,
                node.type_name,
                node.line,
                node.column,
                f"initialise '{node.name}'"
            )

            scope[node.name] = node
            return

        struct = self.structs.get(node.type_name)

        if struct is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"unknown type '{node.type_name}'"
            )

        values = node.init_values

        if (
            len(values) == 1
            and not isinstance(values[0], StructInitNode)
        ):
            value = values[0]
            value.accept(self)

            if value.type == node.type_name:
                scope[node.name] = node
                return

        if len(values) != len(struct.fields):
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"struct '{node.type_name}' needs "
                f"{len(struct.fields)} initialiser values, "
                f"got {len(values)}"
            )

        for value, field in zip(values, struct.fields):
            self.check_initializer_value(
                value,
                field.type_name,
                f"initialise field '{field.name}'"
            )

        scope[node.name] = node

    def struct_is_fully_mutable(self, type_name):
        struct = self.structs.get(type_name)

        if struct is None:
            return True

        for field in struct.fields:
            if not field.mutable:
                return False

            if (
                field.type_name in self.structs
                and not self.struct_is_fully_mutable(
                    field.type_name
                )
            ):
                return False

        return True

    def visit_assign(self, node):
        declaration = self.lookup(node.name)

        if declaration is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is "
                "used before its declaration"
            )

        if not declaration.mutable:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"cannot assign to '{node.name}': "
                "it is not mut"
            )

        node.decl = declaration

        if isinstance(declaration, FieldDeclNode):
            node.is_member_field = True
        else:
            node.is_member_field = False

        if node.fields:
            current_type = declaration.type_name
            node.resolved_fields = []

            for field_name in node.fields:
                struct = self.structs.get(current_type)

                if struct is None:
                    raise CompileError(
                        f"line {node.line}:{node.column}: "
                        f"type '{current_type}' has no fields"
                    )

                field = next(
                    (
                        field
                        for field in struct.fields
                        if field.name == field_name
                    ),
                    None
                )

                if field is None:
                    raise CompileError(
                        f"line {node.line}:{node.column}: "
                        f"struct '{current_type}' has no field "
                        f"'{field_name}'"
                    )

                if not field.mutable:
                    raise CompileError(
                        f"line {node.line}:{node.column}: "
                        f"cannot assign through field "
                        f"'{field_name}': it is not mut"
                    )

                node.resolved_fields.append(field)
                current_type = field.type_name

            target_type = current_type

        else:
            target_type = declaration.type_name

            if (
                target_type in self.structs
                and not self.struct_is_fully_mutable(
                    target_type
                )
            ):
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"cannot assign whole struct "
                    f"'{target_type}': "
                    "not all fields are mut"
                )

        node.value.accept(self)

        if isinstance(node.value, ConstNode):
            self.check_constant_for_target(
                node.value,
                target_type
            )

        self.check_assignable(
            node.value,
            target_type,
            node.line,
            node.column,
            f"assign to '{node.name}'"
        )

    def visit_exit(self, node):
        node.value.accept(self)

        if self.current_function is not None:
            self.check_assignable(
                node.value,
                self.current_function.return_type,
                node.line,
                node.column,
                f"return from function '{self.current_function.name}'"
            )
            return

        if node.value.type not in ("i32", "i64", "bool"):
            raise CompileError(
                f"line {node.line}:{node.column}: "
                "invalid exit value"
            )

    def visit_binop(self, node):
        left_type = node.left.accept(self)
        right_type = node.right.accept(self)

        if node.op in ("+", "-", "*"):
            if left_type == "bool":
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"cannot apply '{node.op}' to bool"
                )

            if right_type == "bool":
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"cannot apply '{node.op}' to bool"
                )

            if left_type == "i64" or right_type == "i64":
                node.type = "i64"
            else:
                node.type = "i32"

            return node.type

        if node.op in ("==", "!="):
            left_integer = left_type in ("i32", "i64")
            right_integer = right_type in ("i32", "i64")

            if left_integer and right_integer:
                node.type = "bool"
                return node.type

            if left_type == "bool" and right_type == "bool":
                node.type = "bool"
                return node.type

            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"cannot compare {left_type} with {right_type}"
            )

        raise CompileError(
            f"line {node.line}:{node.column}: "
            f"unknown operator '{node.op}'"
        )

    def visit_not(self, node):
        value_type = node.value.accept(self)

        if value_type != "bool":
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"cannot apply '!' to {value_type}"
            )

        node.type = "bool"
        return node.type

    def visit_result_field(self, node):
        object_type = node.obj.accept(self)

        struct = self.structs.get(object_type)

        if struct is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"type '{object_type}' has no fields"
            )

        field = next(
            (
                field
                for field in struct.fields
                if field.name == node.field
            ),
            None
        )

        if field is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"struct '{object_type}' has no field "
                f"'{node.field}'"
            )

        node.resolved_field = field
        node.type = field.type_name

        return node.type

    def visit_member_call(self, node):
        object_type = node.obj.accept(self)

        struct = self.structs.get(object_type)

        if struct is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"type '{object_type}' has no member functions"
            )

        method = next(
            (
                method
                for method in struct.methods
                if method.name == node.name
            ),
            None
        )

        if method is None:
            field = next(
                (
                    field
                    for field in struct.fields
                    if field.name == node.name
                ),
                None
            )

            if field is not None:
                receiver = ResultFieldNode(
                    node.obj,
                    node.name,
                    node.line,
                    node.column
                )

                callable_call = MemberCallNode(
                    receiver,
                    "call",
                    node.arguments,
                    node.line,
                    node.column
                )

                callable_call.accept(self)

                node.callable_member = callable_call
                node.type = callable_call.type
                return node.type

            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"struct '{object_type}' has no member function "
                f"'{node.name}'"
            )

        if len(node.arguments) != len(method.parameters):
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"member function '{node.name}' expects "
                f"{len(method.parameters)} arguments, "
                f"got {len(node.arguments)}"
            )

        for argument, parameter in zip(
            node.arguments,
            method.parameters
        ):
            argument.accept(self)

            if isinstance(argument, ConstNode):
                self.check_constant_for_target(
                    argument,
                    parameter.type_name
                )

            self.check_assignable(
                argument,
                parameter.type_name,
                argument.line,
                argument.column,
                f"pass argument to '{node.name}'"
            )

        node.method = method
        node.type = method.return_type

        return node.type

    def resolve_callable_object(self, node):
        declaration = self.lookup(node.name)

        if declaration is None:
            return None

        if node.name in self.functions:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"'{node.name}' is both a variable and a function: "
                "rename one of them"
            )

        object_type = declaration.type_name
        struct = self.structs.get(object_type)

        if struct is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"'{node.name}' is not callable: "
                f"it is {object_type}"
            )

        method = next(
            (
                method
                for method in struct.methods
                if method.name == "call"
            ),
            None
        )

        if method is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"'{node.name}' is not callable: "
                f"{object_type} has no member function 'call'"
            )

        receiver = VarNode(
            node.name,
            node.line,
            node.column
        )

        member_call = MemberCallNode(
            receiver,
            "call",
            node.arguments,
            node.line,
            node.column
        )

        try:
            member_call.accept(self)
        except CompileError as error:
            message = str(error)
            message = message.replace(
                "member function 'call'",
                f"callable object '{node.name}'"
            )
            message = message.replace(
                "pass argument to 'call'",
                f"pass argument to '{node.name}'"
            )
            raise CompileError(message) from None

        node.callable_member = member_call
        node.type = member_call.type

        return node.type

    def visit_call(self, node):
        callable_type = self.resolve_callable_object(node)

        if callable_type is not None:
            return callable_type

        if self.current_struct is not None:
            method = next(
                (
                    method
                    for method in self.current_struct.methods
                    if method.name == node.name
                ),
                None
            )

            if method is not None:
                receiver = VarNode(
                    node.name,
                    node.line,
                    node.column
                )
                member_call = MemberCallNode(
                    receiver,
                    node.name,
                    node.arguments,
                    node.line,
                    node.column
                )
                member_call.method = method
                node.member_method = method

                if len(node.arguments) != len(method.parameters):
                    raise CompileError(
                        f"line {node.line}:{node.column}: "
                        f"member function '{node.name}' expects "
                        f"{len(method.parameters)} arguments, "
                        f"got {len(node.arguments)}"
                    )

                for argument, parameter in zip(
                    node.arguments,
                    method.parameters
                ):
                    argument.accept(self)
                    self.check_assignable(
                        argument,
                        parameter.type_name,
                        argument.line,
                        argument.column,
                        f"pass argument to '{node.name}'"
                    )

                node.type = method.return_type
                return node.type

        function = self.functions.get(node.name)

        if function is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"unknown function '{node.name}'"
            )

        if len(node.arguments) != len(function.parameters):
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"function '{node.name}' expects "
                f"{len(function.parameters)} arguments, "
                f"got {len(node.arguments)}"
            )

        for argument, parameter in zip(
            node.arguments,
            function.parameters
        ):
            argument.accept(self)

            if isinstance(argument, ConstNode):
                self.check_constant_for_target(
                    argument,
                    parameter.type_name
                )

            self.check_assignable(
                argument,
                parameter.type_name,
                argument.line,
                argument.column,
                f"pass argument to '{node.name}'"
            )

        node.function = function
        node.type = function.return_type
        return node.type

    def visit_var(self, node):
        declaration = self.lookup(node.name)

        if declaration is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is "
                "used before its declaration"
            )

        node.decl = declaration
        node.type = declaration.type_name

        return node.type

    def visit_field_access(self, node):
        declaration = self.lookup(node.name)

        if declaration is None:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is "
                "used before its declaration"
            )

        node.decl = declaration
        current_type = declaration.type_name
        node.resolved_fields = []

        for field_name in node.fields:
            struct = self.structs.get(current_type)

            if struct is None:
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"type '{current_type}' has no fields"
                )

            field = next(
                (
                    field
                    for field in struct.fields
                    if field.name == field_name
                ),
                None
            )

            if field is None:
                raise CompileError(
                    f"line {node.line}:{node.column}: "
                    f"struct '{current_type}' has no field "
                    f"'{field_name}'"
                )

            node.resolved_fields.append(field)
            current_type = field.type_name

        node.type = current_type
        return node.type

    def visit_const(self, node):
        if node.value <= I32_MAX:
            node.type = "i32"
            return node.type

        if node.value <= I64_MAX:
            node.type = "i64"
            return node.type

        raise CompileError(
            f"line {node.line}:{node.column}: "
            f"constant {node.value} does not fit in i64"
        )

    def visit_bool(self, node):
        node.type = "bool"
        return node.type

    def check_constant_for_target(self, node, target_type):
        if target_type == "i32" and node.value > I32_MAX:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"constant {node.value} does not fit in i32"
            )

        if target_type == "i64" and node.value > I64_MAX:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"constant {node.value} does not fit in i64"
            )

    def check_assignable(
        self,
        expr,
        want,
        line,
        column,
        what
    ):
        have = expr.type

        if have == want:
            return

        if have == "i32" and want == "i64":
            return

        raise CompileError(
            f"line {line}:{column}: "
            f"cannot {what} of type {want} "
            f"with a value of type {have}"
        )

class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="practice6")
        self.module.triple = llvm.get_default_triple()
        self.struct_types = {}

        main_type = ir.FunctionType(I32, [])

        self.main_function = ir.Function(
            self.module,
            main_type,
            name="main"
        )

        entry = self.main_function.append_basic_block(
            "entry"
        )

        self.builder = ir.IRBuilder(entry)

        printf_type = ir.FunctionType(
            I32,
            [ir.PointerType(I8)],
            var_arg=True
        )

        self.printf = ir.Function(
            self.module,
            printf_type,
            name="printf"
        )

        self.int_fmt = self.make_string(
            "int_fmt",
            b"Program exit with result %lld\n\0"
        )

        self.bool_fmt = self.make_string(
            "bool_fmt",
            b"Program exit with result %s\n\0"
        )

        scanf_type = ir.FunctionType(
            I32, [ir.PointerType(I8)], var_arg=True
        )
        self.scanf = ir.Function(
            self.module, scanf_type, name="scanf"
        )

        self.read_fmt = self.make_string(
            "read_fmt", b"%d\0"
        )
        self.print_int_fmt = self.make_string(
            "print_int_fmt", b"%lld\0"
        )
        self.print_text_fmt = self.make_string(
            "print_text_fmt", b"%s\0"
        )
        self.print_newline = self.make_string(
            "print_newline", b"\n\0"
        )

        self.string_counter = 0

        self.true_string = self.make_string(
            "true_string",
            b"true\0"
        )

        self.false_string = self.make_string(
            "false_string",
            b"false\0"
        )

    def make_string(self, name, data):
        string_type = ir.ArrayType(I8, len(data))

        global_string = ir.GlobalVariable(
            self.module,
            string_type,
            name=name
        )

        global_string.linkage = "private"
        global_string.global_constant = True
        global_string.initializer = ir.Constant(
            string_type,
            bytearray(data)
        )

        return global_string

    def llvm_type(self, type_name):
        if type_name == "i32":
            return I32

        if type_name == "i64":
            return I64

        if type_name == "bool":
            return I1

        if type_name in self.struct_types:
            return self.struct_types[type_name]

        raise RuntimeError(
            f"unknown type {type_name}"
        )

    def create_struct_types(self, node):
        for struct in node.structs:
            struct_type = (
                self.module.context
                .get_identified_type(struct.name)
            )

            self.struct_types[struct.name] = struct_type

            field_types = [
                self.llvm_type(field.type_name)
                for field in struct.fields
            ]

            struct_type.set_body(*field_types)

    def create_function_declarations(self, node):
        for function in node.functions:
            parameter_types = [
                self.llvm_type(parameter.type_name)
                for parameter in function.parameters
            ]

            function_type = ir.FunctionType(
                self.llvm_type(function.return_type),
                parameter_types
            )

            function.ir_function = ir.Function(
                self.module,
                function_type,
                name=f"user_{function.name}"
            )

    def create_member_function_declarations(self, node):
        for struct in node.structs:
            struct_type = self.llvm_type(struct.name)

            for method in struct.methods:
                parameter_types = [
                    struct_type.as_pointer()
                ]

                parameter_types.extend(
                    self.llvm_type(parameter.type_name)
                    for parameter in method.parameters
                )

                function_type = ir.FunctionType(
                    self.llvm_type(method.return_type),
                    parameter_types
                )

                method.ir_function = ir.Function(
                    self.module,
                    function_type,
                    name=f"{struct.name}_{method.name}"
                )

                method.owner_struct = struct

    def string_pointer(self, global_string):
        zero = ir.Constant(I32, 0)

        return self.builder.gep(
            global_string,
            [zero, zero],
            inbounds=True
        )

    def coerce(self, value, have, want):
        if have == want:
            return value

        if have == "i32" and want == "i64":
            return self.builder.sext(
                value,
                I64,
                name="sexttmp"
            )

        raise RuntimeError(
            f"cannot coerce {have} to {want}"
        )

    def wider_integer_type(
        self,
        left_type,
        right_type
    ):
        if (
            left_type == "i64"
            or right_type == "i64"
        ):
            return "i64"

        return "i32"

    def allocate_declarations(self, node):
        if isinstance(node, ProgramNode):
            for statement in node.statements:
                self.allocate_declarations(statement)

            return

        if isinstance(node, DeclNode):
            node.ir_ptr = self.builder.alloca(
                self.llvm_type(node.type_name),
                name=node.name
            )

            return

        if isinstance(node, IfNode):
            self.allocate_declarations(
                node.then_block
            )

            if node.else_block is not None:
                self.allocate_declarations(
                    node.else_block
                )

            return

        if isinstance(node, BlockNode):
            for statement in node.statements:
                self.allocate_declarations(statement)

    def visit_program(self, node):
        self.current_program = node
        self.struct_nodes = {
            struct.name: struct for struct in node.structs
        }
        self.create_struct_types(node)
        self.create_function_declarations(node)
        self.create_member_function_declarations(node)

        for function in node.functions:
            function.accept(self)

        for struct in node.structs:
            for method in struct.methods:
                self.visit_member_function(struct, method)

        self.allocate_declarations(node)

        for statement in node.statements:
            statement.accept(self)

        if not self.builder.block.is_terminated:
            node.exit.accept(self)

        return str(self.module)

    def visit_member_function(self, struct, method):
        previous_builder = self.builder
        previous_function = getattr(
            self,
            "current_function",
            None
        )
        previous_struct = getattr(
            self,
            "current_struct",
            None
        )
        previous_this = getattr(
            self,
            "this_ptr",
            None
        )

        self.current_function = method
        self.current_struct = struct

        entry = method.ir_function.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry)

        self.this_ptr = method.ir_function.args[0]
        self.this_ptr.name = "this"

        for parameter, argument in zip(
            method.parameters,
            method.ir_function.args[1:]
        ):
            argument.name = parameter.name

            parameter.ir_ptr = self.builder.alloca(
                self.llvm_type(parameter.type_name),
                name=f"{parameter.name}_slot"
            )

            self.builder.store(
                argument,
                parameter.ir_ptr
            )

        self.allocate_declarations(method.body)
        method.body.accept(self)

        self.this_ptr = previous_this
        self.current_struct = previous_struct
        self.current_function = previous_function
        self.builder = previous_builder

    def visit_function(self, node):
        previous_builder = self.builder
        previous_function = getattr(
            self,
            "current_function",
            None
        )

        self.current_function = node

        entry = node.ir_function.append_basic_block(
            "entry"
        )
        self.builder = ir.IRBuilder(entry)

        for parameter, argument in zip(
            node.parameters,
            node.ir_function.args
        ):
            argument.name = parameter.name

            parameter.ir_ptr = self.builder.alloca(
                self.llvm_type(parameter.type_name),
                name=f"{parameter.name}_slot"
            )

            self.builder.store(
                argument,
                parameter.ir_ptr
            )

        self.allocate_declarations(node.body)
        node.body.accept(self)

        self.current_function = previous_function
        self.builder = previous_builder

    def visit_block(self, node):
        for statement in node.statements:
            if self.builder.block.is_terminated:
                break

            statement.accept(self)

        if (
            node.exit is not None
            and not self.builder.block.is_terminated
        ):
            node.exit.accept(self)

    def visit_if(self, node):
        condition = node.condition.accept(self)

        current_ir_function = self.builder.block.function

        then_bb = current_ir_function.append_basic_block(
            "then"
        )

        if node.else_block is not None:
            else_bb = current_ir_function.append_basic_block(
                "else"
            )
        else:
            else_bb = None

        merge_bb = current_ir_function.append_basic_block(
            "merge"
        )

        self.builder.cbranch(
            condition,
            then_bb,
            (
                else_bb
                if else_bb is not None
                else merge_bb
            )
        )

        self.builder.position_at_end(then_bb)

        node.then_block.accept(self)

        if not self.builder.block.is_terminated:
            self.builder.branch(merge_bb)

        if else_bb is not None:
            self.builder.position_at_end(else_bb)

            node.else_block.accept(self)

            if not self.builder.block.is_terminated:
                self.builder.branch(merge_bb)

        self.builder.position_at_end(merge_bb)

    def emit_initializer_value(
        self,
        value_node,
        target_type
    ):
        if isinstance(value_node, StructInitNode):
            struct = None

            for candidate in self.current_program.structs:
                if candidate.name == target_type:
                    struct = candidate
                    break

            aggregate = ir.Constant(
                self.llvm_type(target_type),
                None
            )

            for index, (nested_value, field) in enumerate(
                zip(value_node.values, struct.fields)
            ):
                value = self.emit_initializer_value(
                    nested_value,
                    field.type_name
                )

                aggregate = self.builder.insert_value(
                    aggregate,
                    value,
                    index,
                    name=f"{target_type.lower()}_init"
                )

            return aggregate

        value = value_node.accept(self)

        return self.coerce(
            value,
            value_node.type,
            target_type
        )

    def visit_decl(self, node):
        if node.type_name in ("i32", "i64", "bool"):
            value = node.init_values[0].accept(self)

            value = self.coerce(
                value,
                node.init_values[0].type,
                node.type_name
            )

            self.builder.store(
                value,
                node.ir_ptr
            )

            return

        if len(node.init_values) == 1:
            value_node = node.init_values[0]

            if value_node.type == node.type_name:
                value = value_node.accept(self)

                self.builder.store(
                    value,
                    node.ir_ptr
                )

                return

        zero = ir.Constant(I32, 0)

        for index, value_node in enumerate(
            node.init_values
        ):
            struct = None

            for candidate in self.current_program.structs:
                if candidate.name == node.type_name:
                    struct = candidate
                    break

            field = struct.fields[index]

            value = self.emit_initializer_value(
                value_node,
                field.type_name
            )

            field_index = ir.Constant(
                I32,
                field.index
            )

            field_ptr = self.builder.gep(
                node.ir_ptr,
                [zero, field_index],
                inbounds=True,
                name=f"{node.name}_{field.name}_ptr"
            )

            self.builder.store(
                value,
                field_ptr
            )

    def visit_assign(self, node):
        value = node.value.accept(self)

        if node.fields:
            target_type = node.resolved_fields[-1].type_name
        else:
            target_type = node.decl.type_name

        value = self.coerce(
            value,
            node.value.type,
            target_type
        )

        if isinstance(node.decl, FieldDeclNode):
            pointer = self.builder.gep(
                self.this_ptr,
                [
                    ir.Constant(I32, 0),
                    ir.Constant(I32, node.decl.index)
                ],
                inbounds=True,
                name=f"this_{node.name}_ptr"
            )
        else:
            pointer = node.decl.ir_ptr

        if node.fields:
            for field in node.resolved_fields:
                pointer = self.builder.gep(
                    pointer,
                    [
                        ir.Constant(I32, 0),
                        ir.Constant(I32, field.index)
                    ],
                    inbounds=True,
                    name=f"assign_{field.name}"
                )

        self.builder.store(
            value,
            pointer
        )

    def visit_read(self, node):
        pointer = self.builder.alloca(I32, name="read_value")
        self.builder.call(
            self.scanf,
            [self.string_pointer(self.read_fmt), pointer]
        )
        return self.builder.load(pointer, name="read_result")

    def visit_string(self, node):
        self.string_counter += 1
        global_string = self.make_string(
            f"user_string_{self.string_counter}",
            node.value.encode("utf-8") + b"\0"
        )
        return self.string_pointer(global_string)

    def print_text(self, text):
        self.builder.call(
            self.printf,
            [self.string_pointer(self.print_text_fmt), text]
        )

    def print_literal(self, text):
        self.string_counter += 1
        global_string = self.make_string(
            f"print_literal_{self.string_counter}",
            text.encode("utf-8") + b"\0"
        )
        self.print_text(self.string_pointer(global_string))

    def print_value(self, value, type_name):
        if type_name in ("i32", "i64"):
            value = self.coerce(value, type_name, "i64")
            self.builder.call(
                self.printf,
                [self.string_pointer(self.print_int_fmt), value]
            )
            return

        if type_name == "bool":
            text = self.builder.select(
                value,
                self.string_pointer(self.true_string),
                self.string_pointer(self.false_string)
            )
            self.print_text(text)
            return

        if type_name == "string":
            self.print_text(value)
            return

        struct = self.struct_nodes[type_name]
        self.print_literal(f"{type_name}{{")

        for index, field in enumerate(struct.fields):
            if index:
                self.print_literal(", ")

            self.print_literal(f"{field.name}: ")

            field_value = self.builder.extract_value(
                value, index
            )
            self.print_value(field_value, field.type_name)

        self.print_literal("}")

    def visit_print(self, node):
        value = node.value.accept(self)
        self.print_value(value, node.value.type)
        self.print_text(self.string_pointer(self.print_newline))

    def visit_exit(self, node):
        value = node.value.accept(self)
        value_type = node.value.type

        current_function = getattr(
            self,
            "current_function",
            None
        )

        if current_function is not None:
            value = self.coerce(
                value,
                value_type,
                current_function.return_type
            )

            self.builder.ret(value)
            return

        if value_type in ("i32", "i64"):
            value = self.coerce(
                value,
                value_type,
                "i64"
            )

            self.builder.call(
                self.printf,
                [
                    self.string_pointer(
                        self.int_fmt
                    ),
                    value
                ]
            )

        else:
            text = self.builder.select(
                value,
                self.string_pointer(
                    self.true_string
                ),
                self.string_pointer(
                    self.false_string
                ),
                name="bool_text"
            )

            self.builder.call(
                self.printf,
                [
                    self.string_pointer(
                        self.bool_fmt
                    ),
                    text
                ]
            )

        self.builder.ret(
            ir.Constant(I32, 0)
        )

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)

        left_type = node.left.type
        right_type = node.right.type

        if node.op in ("+", "-", "*"):
            result_type = node.type

            left = self.coerce(
                left,
                left_type,
                result_type
            )

            right = self.coerce(
                right,
                right_type,
                result_type
            )

            if node.op == "+":
                return self.builder.add(
                    left,
                    right,
                    name="addtmp"
                )

            if node.op == "-":
                return self.builder.sub(
                    left,
                    right,
                    name="subtmp"
                )

            return self.builder.mul(
                left,
                right,
                name="multmp"
            )

        if node.op in ("==", "!="):
            if (
                left_type in ("i32", "i64")
                and right_type in ("i32", "i64")
            ):
                compare_type = (
                    self.wider_integer_type(
                        left_type,
                        right_type
                    )
                )

                left = self.coerce(
                    left,
                    left_type,
                    compare_type
                )

                right = self.coerce(
                    right,
                    right_type,
                    compare_type
                )

            predicate = (
                "=="
                if node.op == "=="
                else "!="
            )

            return self.builder.icmp_signed(
                predicate,
                left,
                right,
                name="cmptmp"
            )

        raise RuntimeError(
            f"unknown operator {node.op}"
        )

    def visit_not(self, node):
        value = node.value.accept(self)

        return self.builder.xor(
            value,
            ir.Constant(I1, 1),
            name="nottmp"
        )

    def visit_result_field(self, node):
        value = node.obj.accept(self)

        return self.builder.extract_value(
            value,
            node.resolved_field.index,
            name=f"result_{node.field}"
        )

    def visit_member_call(self, node):
        obj = node.obj

        if isinstance(obj, VarNode):
            if isinstance(obj.decl, FieldDeclNode):
                pointer = self.builder.gep(
                    self.this_ptr,
                    [
                        ir.Constant(I32, 0),
                        ir.Constant(I32, obj.decl.index)
                    ],
                    inbounds=True
                )
            else:
                pointer = obj.decl.ir_ptr

        elif isinstance(obj, FieldAccessNode):
            if isinstance(obj.decl, FieldDeclNode):
                pointer = self.builder.gep(
                    self.this_ptr,
                    [
                        ir.Constant(I32, 0),
                        ir.Constant(I32, obj.decl.index)
                    ],
                    inbounds=True
                )
            else:
                pointer = obj.decl.ir_ptr

            for field in obj.resolved_fields:
                pointer = self.builder.gep(
                    pointer,
                    [
                        ir.Constant(I32, 0),
                        ir.Constant(I32, field.index)
                    ],
                    inbounds=True
                )

        else:
            value = obj.accept(self)

            pointer = self.builder.alloca(
                self.llvm_type(obj.type),
                name="temporary_receiver"
            )

            self.builder.store(value, pointer)

        arguments = [pointer]

        for argument, parameter in zip(
            node.arguments,
            node.method.parameters
        ):
            value = argument.accept(self)

            value = self.coerce(
                value,
                argument.type,
                parameter.type_name
            )

            arguments.append(value)

        return self.builder.call(
            node.method.ir_function,
            arguments,
            name=f"call_{node.name}"
        )

    def visit_call(self, node):
        if hasattr(node, "member_method"):
            arguments = [self.this_ptr]

            for argument, parameter in zip(
                node.arguments,
                node.member_method.parameters
            ):
                value = argument.accept(self)
                value = self.coerce(
                    value,
                    argument.type,
                    parameter.type_name
                )
                arguments.append(value)

            return self.builder.call(
                node.member_method.ir_function,
                arguments,
                name=f"call_{node.name}"
            )

        arguments = []

        for argument, parameter in zip(
            node.arguments,
            node.function.parameters
        ):
            value = argument.accept(self)

            value = self.coerce(
                value,
                argument.type,
                parameter.type_name
            )

            arguments.append(value)

        return self.builder.call(
            node.function.ir_function,
            arguments,
            name=f"call_{node.name}"
        )

    def visit_var(self, node):
        if isinstance(node.decl, FieldDeclNode):
            pointer = self.builder.gep(
                self.this_ptr,
                [
                    ir.Constant(I32, 0),
                    ir.Constant(I32, node.decl.index)
                ],
                inbounds=True
            )

            return self.builder.load(
                pointer,
                name=f"load_{node.name}"
            )

        return self.builder.load(
            node.decl.ir_ptr,
            name=f"load_{node.name}"
        )

    def visit_field_access(self, node):
        if isinstance(node.decl, FieldDeclNode):
            pointer = self.builder.gep(
                self.this_ptr,
                [
                    ir.Constant(I32, 0),
                    ir.Constant(I32, node.decl.index)
                ],
                inbounds=True
            )
        else:
            pointer = node.decl.ir_ptr

        for field in node.resolved_fields:
            pointer = self.builder.gep(
                pointer,
                [
                    ir.Constant(I32, 0),
                    ir.Constant(I32, field.index)
                ],
                inbounds=True,
                name=f"field_{field.name}"
            )

        return self.builder.load(
            pointer,
            name=f"load_{node.fields[-1]}"
        )

    def visit_const(self, node):
        return ir.Constant(
            self.llvm_type(node.type),
            node.value
        )

    def visit_bool(self, node):
        return ir.Constant(
            I1,
            1 if node.value else 0
        )

class AstPrinter:
    def __init__(self):
        self.indent = 0

    def write(self, text):
        print(
            f"{' ' * self.indent}{text}"
        )

    def visit_program(self, node):
        self.write("Program")
        self.indent += 2

        for struct in node.structs:
            struct.accept(self)

        for function in node.functions:
            function.accept(self)

        for statement in node.statements:
            statement.accept(self)

        node.exit.accept(self)
        self.indent -= 2

    def visit_struct(self, node):
        self.write(f"Struct {node.name}")
        self.indent += 2

        for field in node.fields:
            field.accept(self)

        for method in node.methods:
            self.write(
                f"MemberFn {method.name} -> {method.return_type}"
            )
            self.indent += 2

            for parameter in method.parameters:
                parameter.accept(self)

            method.body.accept(self)
            self.indent -= 2

        self.indent -= 2

    def visit_field_decl(self, node):
        kind = "mut" if node.mutable else "const"
        self.write(
            f"Field {node.name} {node.type_name} {kind}"
        )

    def visit_function(self, node):
        self.write(
            f"Function {node.name} -> {node.return_type}"
        )
        self.indent += 2

        for parameter in node.parameters:
            parameter.accept(self)

        node.body.accept(self)
        self.indent -= 2

    def visit_parameter(self, node):
        self.write(
            f"Parameter {node.name} {node.type_name}"
        )

    def visit_decl(self, node):
        kind = "mut" if node.mutable else "const"

        self.write(
            f"Decl {node.name} {node.type_name} {kind}"
        )

        self.indent += 2

        for value in node.init_values:
            value.accept(self)

        self.indent -= 2

    def visit_assign(self, node):
        self.write(
            f"Assign {node.name}"
        )

        self.indent += 2
        node.value.accept(self)
        self.indent -= 2

    def visit_if(self, node):
        self.write("If")
        self.indent += 2

        node.condition.accept(self)
        node.then_block.accept(self)

        if node.else_block is not None:
            node.else_block.accept(self)

        self.indent -= 2

    def visit_block(self, node):
        self.write("Block")
        self.indent += 2

        for statement in node.statements:
            statement.accept(self)

        if node.exit is not None:
            node.exit.accept(self)

        self.indent -= 2

    def visit_exit(self, node):
        self.write("Exit")

        self.indent += 2
        node.value.accept(self)
        self.indent -= 2

    def visit_struct_init(self, node):
        self.write("StructInit")
        self.indent += 2

        for value in node.values:
            value.accept(self)

        self.indent -= 2

    def visit_binop(self, node):
        self.write(
            f"BinOp {node.op}"
        )

        self.indent += 2
        node.left.accept(self)
        node.right.accept(self)
        self.indent -= 2

    def visit_read(self, node):
        self.write("Read")

    def visit_string(self, node):
        self.write(f"String {node.value!r}")

    def visit_print(self, node):
        self.write("Print")
        self.indent += 2
        node.value.accept(self)
        self.indent -= 2

    def visit_call(self, node):
        self.write(f"Call {node.name}")
        self.indent += 2

        for argument in node.arguments:
            argument.accept(self)

        self.indent -= 2

    def visit_member_call(self, node):
        self.write(f"MemberCall {node.name}")
        self.indent += 2

        node.obj.accept(self)

        for argument in node.arguments:
            argument.accept(self)

        self.indent -= 2

    def visit_var(self, node):
        self.write(
            f"Var {node.name}"
        )

    def visit_field_access(self, node):
        self.write(
            f"FieldAccess {node.name}."
            + ".".join(node.fields)
        )

    def visit_result_field(self, node):
        self.write(f"ResultField {node.field}")
        self.indent += 2
        node.obj.accept(self)
        self.indent -= 2

    def visit_const(self, node):
        self.write(
            f"Const {node.value}"
        )

    def visit_bool(self, node):
        self.write(
            f"Bool {'true' if node.value else 'false'}"
        )

    def visit_not(self, node):
        self.write("Not")
        self.indent += 2
        node.value.accept(self)
        self.indent -= 2


def print_ast(program):
    printer = AstPrinter()
    program.accept(printer)


def parse_program(data):
    token_lines = lex(data)
    parser = Parser(token_lines)
    return parser.parse_program()


def check_program(program):
    checker = SemanticChecker()
    program.accept(checker)


def compile_program(data):
    program = parse_program(data)

    check_program(program)

    codegen = CodeGen()
    return program.accept(codegen)


def main():
    tokens_mode = (
        len(sys.argv) == 3
        and sys.argv[1] == "--tokens"
    )

    ast_mode = (
        len(sys.argv) == 3
        and sys.argv[1] == "--ast"
    )

    if tokens_mode:
        input_path = sys.argv[2]

        try:
            with open(input_path, "rb") as source:
                data = source.read()

            token_lines = lex(data)
            print_tokens(token_lines)

        except CompileError as error:
            print(
                f"compilation error: {error}",
                file=sys.stderr
            )
            sys.exit(1)

        except FileNotFoundError:
            print(
                "compilation error: input file not found",
                file=sys.stderr
            )
            sys.exit(1)

        return

    if ast_mode:
        input_path = sys.argv[2]

        try:
            with open(input_path, "rb") as source:
                data = source.read()

            program = parse_program(data)
            print_ast(program)

        except CompileError as error:
            print(
                f"compilation error: {error}",
                file=sys.stderr
            )
            sys.exit(1)

        except FileNotFoundError:
            print(
                "compilation error: input file not found",
                file=sys.stderr
            )
            sys.exit(1)

        return

    if len(sys.argv) != 3:
        print(
            "usage: python3 compiler.py input.txt output.ll",
            file=sys.stderr
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        with open(input_path, "rb") as source:
            data = source.read()

        llvm_ir = compile_program(data)

        with open(output_path, "w") as output:
            output.write(llvm_ir)

    except CompileError as error:
        if os.path.exists(output_path):
            os.remove(output_path)

        print(
            f"compilation error: {error}",
            file=sys.stderr
        )
        sys.exit(1)

    except FileNotFoundError:
        if os.path.exists(output_path):
            os.remove(output_path)

        print(
            "compilation error: input file not found",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
