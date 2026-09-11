import os
import sys

from llvmlite import ir
import llvmlite.binding as llvm


I32 = ir.IntType(32)
I8 = ir.IntType(8)


class CompileError(Exception):
    pass


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
    "mut": "keyword",
    "exit": "keyword",
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

        i += 1
        col += 1

    if tokens:
        lines.append(tokens)

    return lines


def error_at(token, message):
    raise CompileError(
        f"line {token.line}:{token.column}: {message}"
    )


def compile_program(data):
    token_lines = lex(data)

    module = ir.Module(name="practice2")
    module.triple = llvm.get_default_triple()

    main_type = ir.FunctionType(I32, [])

    main_function = ir.Function(
        module,
        main_type,
        name="main"
    )

    entry = main_function.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    printf_type = ir.FunctionType(
        I32,
        [ir.PointerType(I8)],
        var_arg=True
    )

    printf = ir.Function(
        module,
        printf_type,
        name="printf"
    )

    message = b"Program exit with result %d\n\0"
    message_type = ir.ArrayType(I8, len(message))

    fmt = ir.GlobalVariable(
        module,
        message_type,
        name="fmt"
    )

    fmt.linkage = "private"
    fmt.global_constant = True

    fmt.initializer = ir.Constant(
        message_type,
        bytearray(message)
    )

    symbols = {}
    mutable = set()
    exit_seen = False

    def read_value(token):
        if token.kind == "number":
            return ir.Constant(
                I32,
                int(token.text)
            )

        if token.kind == "identifier":
            if token.text not in symbols:
                error_at(
                    token,
                    f"variable '{token.text}' is "
                    "used before its declaration"
                )

            return builder.load(
                symbols[token.text],
                name=f"load_{token.text}"
            )

        error_at(
            token,
            "expected a number or variable"
        )

    def read_expression(tokens):
        if len(tokens) == 1:
            return read_value(tokens[0])

        if len(tokens) != 3:
            error_at(
                tokens[0],
                "invalid expression"
            )

        left_token = tokens[0]
        operator_token = tokens[1]
        right_token = tokens[2]

        if (
            operator_token.kind != "operator"
            or operator_token.text not in ("+", "-", "*")
        ):
            error_at(
                operator_token,
                "expected +, - or *"
            )

        left = read_value(left_token)
        right = read_value(right_token)

        if operator_token.text == "+":
            return builder.add(
                left,
                right,
                name="addtmp"
            )

        if operator_token.text == "-":
            return builder.sub(
                left,
                right,
                name="subtmp"
            )

        return builder.mul(
            left,
            right,
            name="multmp"
        )

    for raw_tokens in token_lines:
        tokens = [
            token
            for token in raw_tokens
            if token.kind != "endline"
        ]

        if not tokens:
            continue

        if exit_seen:
            error_at(
                tokens[0],
                "exit must be the last statement"
            )

        if tokens[0].text == "i32":
            position = 1
            is_mutable = False

            if (
                position < len(tokens)
                and tokens[position].text == "mut"
            ):
                is_mutable = True
                position += 1

            if position >= len(tokens):
                error_at(
                    tokens[0],
                    "expected variable name"
                )

            name_token = tokens[position]

            if name_token.kind != "identifier":
                error_at(
                    name_token,
                    "expected variable name"
                )

            name = name_token.text

            if name in symbols:
                error_at(
                    name_token,
                    f"variable '{name}' is already declared"
                )

            position += 1

            if (
                position >= len(tokens)
                or tokens[position].text != "{"
            ):
                error_at(
                    name_token,
                    f"variable '{name}' needs an initialiser in {{}}"
                )

            position += 1
            expression_start = position

            while (
                position < len(tokens)
                and tokens[position].text != "}"
            ):
                position += 1

            if position >= len(tokens):
                error_at(
                    tokens[expression_start - 1],
                    "'{' is not closed"
                )

            expression_tokens = tokens[
                expression_start:position
            ]

            if not expression_tokens:
                error_at(
                    tokens[position],
                    "initializer cannot be empty"
                )

            value = read_expression(
                expression_tokens
            )

            position += 1

            if position != len(tokens):
                error_at(
                    tokens[position],
                    "extra tokens after declaration"
                )

            pointer = builder.alloca(
                I32,
                name=name
            )

            builder.store(
                value,
                pointer
            )

            symbols[name] = pointer

            if is_mutable:
                mutable.add(name)

            continue

        if tokens[0].text == "exit":
            if len(tokens) != 2:
                error_at(
                    tokens[0],
                    "exit expects one value"
                )

            value = read_value(tokens[1])

            zero = ir.Constant(I32, 0)

            fmt_pointer = builder.gep(
                fmt,
                [zero, zero],
                inbounds=True
            )

            builder.call(
                printf,
                [fmt_pointer, value]
            )

            builder.ret(value)

            exit_seen = True
            continue

        if tokens[0].kind == "identifier":
            name_token = tokens[0]
            name = name_token.text

            if name not in symbols:
                error_at(
                    name_token,
                    f"variable '{name}' is "
                    "used before its declaration"
                )

            if (
                len(tokens) < 2
                or tokens[1].text != ":="
            ):
                error_at(
                    name_token,
                    "invalid statement"
                )

            if name not in mutable:
                error_at(
                    name_token,
                    f"cannot assign to '{name}': "
                    "it is not mut"
                )

            expression_tokens = tokens[2:]

            if not expression_tokens:
                error_at(
                    tokens[1],
                    "assignment needs a value"
                )

            value = read_expression(
                expression_tokens
            )

            builder.store(
                value,
                symbols[name]
            )

            continue

        error_at(
            tokens[0],
            "invalid statement"
        )

    if not exit_seen:
        raise CompileError(
            "line 1:1: program has no exit statement"
        )

    return str(module)


def main():
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
