import sys


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

            elif b in (32, 9):
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


def main():
    data = sys.stdin.buffer.read()

    try:
        token_lines = lex(data)

        for tokens in token_lines:
            print(tokens)

    except CompileError as error:
        print(
            f"compilation error: {error}",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
