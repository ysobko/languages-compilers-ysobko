import os
import sys

from llvmlite import ir
import llvmlite.binding as llvm


I32 = ir.IntType(32)
I8 = ir.IntType(8)


class CompileError(Exception):
    pass


class ProgramNode:
    def __init__(self, statements, exit_node):
        self.statements = statements
        self.exit = exit_node

    def accept(self, visitor):
        return visitor.visit_program(self)


class StmtNode:
    pass


class DeclNode(StmtNode):
    def __init__(self, name, type_name, mutable, init, line, column):
        self.name = name
        self.type_name = type_name
        self.mutable = mutable
        self.init = init
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_decl(self)


class AssignNode(StmtNode):
    def __init__(self, name, value, line, column):
        self.name = name
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_assign(self)


class ExitNode:
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_exit(self)


class ExprNode:
    pass


class BinOpNode(ExprNode):
    def __init__(self, op, left, right, line, column):
        self.op = op
        self.left = left
        self.right = right
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_binop(self)


class VarNode(ExprNode):
    def __init__(self, name, line, column):
        self.name = name
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_var(self)


class ConstNode(ExprNode):
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_const(self)


class BoolNode(ExprNode):
    def __init__(self, value, line, column):
        self.value = value
        self.line = line
        self.column = column

    def accept(self, visitor):
        return visitor.visit_bool(self)


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

    brace_columns = []

    while i <= len(data):
        b = data[i] if i < len(data) else None

        if state == "START":
            if b is None:
                if brace_columns:
                    raise CompileError(
                        f"line {line}:{brace_columns[0]}: "
                        "'{' is not closed before the end of the line"
                    )
                break

            if b in (32, 9):
                pass

            elif b == 10:
                if brace_columns:
                    raise CompileError(
                        f"line {line}:{brace_columns[0]}: "
                        "'{' is not closed before the end of the line"
                    )

                tokens.append(
                    Token("endline", "\n", line, col)
                )

                lines.append(tokens)
                tokens = []

                line += 1
                col = 0
                brace_columns = []

            elif is_alpha(b):
                state = "IDENT"
                start = i
                start_col = col

            elif is_digit(b):
                state = "NUMBER"
                start = i
                start_col = col

            elif b == ord("{"):
                brace_columns.append(col)
                tokens.append(
                    Token("block", "{", line, col)
                )

            elif b == ord("}"):
                if brace_columns:
                    brace_columns.pop()

                tokens.append(
                    Token("block", "}", line, col)
                )

            elif b == ord("+"):
                tokens.append(
                    Token("operator", "+", line, col)
                )

            elif b == ord("-"):
                tokens.append(
                    Token("operator", "-", line, col)
                )

            elif b == ord("*"):
                tokens.append(
                    Token("operator", "*", line, col)
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
                if b > 127:
                    char = f"0x{b:02x}"
                else:
                    char = chr(b)

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
                raise CompileError(
                    f"line {line}:{start_col}: "
                    "expected '!=' "
                    "(a single '!' is not an operator)"
                )

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
        self.tokens = []
        self.position = 0

    def set_line(self, tokens):
        self.tokens = [
            token
            for token in tokens
            if token.kind != "endline"
        ]
        self.position = 0

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
            raise CompileError(
                f"line {self.tokens[-1].line}:"
                f"{self.end_column()}: "
                "expected constant or variable"
            )

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

            return VarNode(
                token.text,
                token.line,
                token.column
            )

        error_at(
            token,
            "expected a constant or variable"
        )

    def parse_term(self):
        left = self.parse_factor()

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

    def parse_decl(self):
        type_token = self.peek()

        if (
            type_token is None
            or type_token.text not in ("i32", "i64", "bool")
        ):
            if type_token is None:
                raise CompileError(
                    "unexpected end of line"
                )

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

        value = self.parse_expr()

        token = self.peek()

        if token is None:
            raise CompileError(
                f"line {type_token.line}:"
                f"{self.end_column()}: expected '}}'"
            )

        self.eat(text="}")

        return DeclNode(
            name_token.text,
            type_token.text,
            mutable,
            value,
            name_token.line,
            name_token.column
        )

    def parse_assign(self):
        name_token = self.eat(kind="identifier")

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
            name_token.column
        )

    def parse_exit(self):
        start = self.eat(text="exit")
        value = self.parse_factor()

        return ExitNode(
            value,
            start.line,
            start.column
        )

    def parse_statement(self):
        token = self.peek()

        if token.text in ("i32", "i64", "bool"):
            return self.parse_decl()

        if token.kind == "identifier":
            return self.parse_assign()

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
        statements = []
        exit_node = None

        for raw_tokens in self.token_lines:
            self.set_line(raw_tokens)

            if not self.tokens:
                continue

            first = self.peek()

            if exit_node is not None:
                error_at(
                    first,
                    "exit must be the last statement"
                )

            if first.text == "exit":
                exit_node = self.parse_exit()
                self.ensure_end()
                continue

            node = self.parse_statement()
            self.ensure_end()
            statements.append(node)

        if exit_node is None:
            raise CompileError(
                "line 1:1: program has no exit statement"
            )

        return ProgramNode(
            statements,
            exit_node
        )


class CodeGen:
    def __init__(self):
        self.module = ir.Module(name="practice4")
        self.module.triple = llvm.get_default_triple()

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

        message = b"Program exit with result %d\n\0"
        message_type = ir.ArrayType(
            I8,
            len(message)
        )

        self.fmt = ir.GlobalVariable(
            self.module,
            message_type,
            name="fmt"
        )

        self.fmt.linkage = "private"
        self.fmt.global_constant = True
        self.fmt.initializer = ir.Constant(
            message_type,
            bytearray(message)
        )

        self.symbols = {}
        self.mutable = set()

    def visit_program(self, node):
        for statement in node.statements:
            statement.accept(self)

        node.exit.accept(self)

        return str(self.module)

    def visit_decl(self, node):
        if node.name in self.symbols:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is already declared"
            )

        value = node.init.accept(self)

        pointer = self.builder.alloca(
            I32,
            name=node.name
        )

        self.builder.store(
            value,
            pointer
        )

        self.symbols[node.name] = pointer

        if node.mutable:
            self.mutable.add(node.name)

    def visit_assign(self, node):
        if node.name not in self.symbols:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is "
                "used before its declaration"
            )

        if node.name not in self.mutable:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"cannot assign to '{node.name}': "
                "it is not mut"
            )

        value = node.value.accept(self)

        self.builder.store(
            value,
            self.symbols[node.name]
        )

    def visit_exit(self, node):
        value = node.value.accept(self)

        zero = ir.Constant(I32, 0)

        fmt_pointer = self.builder.gep(
            self.fmt,
            [zero, zero],
            inbounds=True
        )

        self.builder.call(
            self.printf,
            [fmt_pointer, value]
        )

        self.builder.ret(value)

    def visit_binop(self, node):
        left = node.left.accept(self)
        right = node.right.accept(self)

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

        if node.op == "*":
            return self.builder.mul(
                left,
                right,
                name="multmp"
            )

        raise CompileError(
            f"line {node.line}:{node.column}: "
            f"operator '{node.op}' is not "
            "implemented in code generation yet"
        )

    def visit_var(self, node):
        if node.name not in self.symbols:
            raise CompileError(
                f"line {node.line}:{node.column}: "
                f"variable '{node.name}' is "
                "used before its declaration"
            )

        return self.builder.load(
            self.symbols[node.name],
            name=f"load_{node.name}"
        )

    def visit_const(self, node):
        return ir.Constant(
            I32,
            node.value
        )

    def visit_bool(self, node):
        return ir.Constant(
            I32,
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

        for statement in node.statements:
            statement.accept(self)

        node.exit.accept(self)
        self.indent -= 2

    def visit_decl(self, node):
        kind = "mut" if node.mutable else "const"

        self.write(
            f"Decl {node.name} {node.type_name} {kind}"
        )

        self.indent += 2
        node.init.accept(self)
        self.indent -= 2

    def visit_assign(self, node):
        self.write(
            f"Assign {node.name}"
        )

        self.indent += 2
        node.value.accept(self)
        self.indent -= 2

    def visit_exit(self, node):
        self.write("Exit")

        self.indent += 2
        node.value.accept(self)
        self.indent -= 2

    def visit_binop(self, node):
        self.write(
            f"BinOp {node.op}"
        )

        self.indent += 2
        node.left.accept(self)
        node.right.accept(self)
        self.indent -= 2

    def visit_var(self, node):
        self.write(
            f"Var {node.name}"
        )

    def visit_const(self, node):
        self.write(
            f"Const {node.value}"
        )

    def visit_bool(self, node):
        self.write(
            f"Bool {'true' if node.value else 'false'}"
        )


def print_ast(program):
    printer = AstPrinter()
    program.accept(printer)


def parse_program(data):
    token_lines = lex(data)
    parser = Parser(token_lines)
    return parser.parse_program()


def compile_program(data):
    program = parse_program(data)
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
