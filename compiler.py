import sys
import re

from llvmlite import ir
import llvmlite.binding as llvm


I32 = ir.IntType(32)
I8 = ir.IntType(8)

IDENT_RE = r"[A-Za-z_][A-Za-z0-9_]*"
RESERVED = {"int", "exit"}


def fail(line_no, message):
    print(f"compilation error: line {line_no}: {message}", file=sys.stderr)
    sys.exit(1)


def is_int(text):
    return re.fullmatch(r"-?\d+", text) is not None


def build_compiler(source_path, output_path):
    with open(source_path, "r") as f:
        lines = f.readlines()

    module = ir.Module(name="practice1")
    module.triple = llvm.get_default_triple()

    main_fn = ir.Function(
        module,
        ir.FunctionType(I32, []),
        name="main"
    )

    entry = main_fn.append_basic_block("entry")
    builder = ir.IRBuilder(entry)

    printf = ir.Function(
        module,
        ir.FunctionType(
            I32,
            [ir.PointerType(I8)],
            var_arg=True
        ),
        name="printf"
    )

    text = b"Program exit with result %d\n\0"

    fmt = ir.GlobalVariable(
        module,
        ir.ArrayType(I8, len(text)),
        name="fmt"
    )

    fmt.linkage = "private"
    fmt.global_constant = True

    fmt.initializer = ir.Constant(
        ir.ArrayType(I8, len(text)),
        bytearray(text)
    )

    symbols = {}
    exit_seen = False

    def value_of(token, line_no):
        if is_int(token):
            return ir.Constant(I32, int(token))

        if re.fullmatch(IDENT_RE, token):
            if token not in symbols:
                fail(line_no, f"variable '{token}' is not declared")
            return builder.load(symbols[token], name=f"load_{token}")

        fail(line_no, f"invalid operand '{token}'")

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        if not line:
            continue

        if exit_seen:
            fail(line_no, "exit must be the last statement")

        declaration = re.fullmatch(
            rf"int\s+({IDENT_RE})",
            line
        )

        if declaration:
            name = declaration.group(1)

            if name in RESERVED:
                fail(line_no, f"'{name}' is a reserved word")

            if name in symbols:
                fail(line_no, f"variable '{name}' already declared")

            symbols[name] = builder.alloca(I32, name=name)
            continue

        if line.startswith("int"):
            fail(line_no, "invalid declaration")

        exit_match = re.fullmatch(
            rf"exit\s+({IDENT_RE})",
            line
        )

        if exit_match:
            name = exit_match.group(1)

            if name not in symbols:
                fail(line_no, f"variable '{name}' is not declared")

            value = builder.load(
                symbols[name],
                name=f"exit_{name}"
            )

            fmt_ptr = builder.bitcast(
                fmt,
                ir.PointerType(I8)
            )

            builder.call(
                printf,
                [fmt_ptr, value]
            )

            builder.ret(ir.Constant(I32, 0))
            exit_seen = True
            continue

        if line.startswith("exit"):
            fail(line_no, "invalid exit statement")

        assign_match = re.fullmatch(
            rf"({IDENT_RE})\s*:=\s*(.+)",
            line
        )

        if assign_match:
            target = assign_match.group(1)
            expression = assign_match.group(2).strip()

            if target not in symbols:
                fail(
                    line_no,
                    f"variable '{target}' is not declared"
                )

            binary_match = re.fullmatch(
                rf"({IDENT_RE}|-?\d+)\s*([+\-*])\s*({IDENT_RE}|-?\d+)",
                expression
            )

            if binary_match:
                left_token = binary_match.group(1)
                operator = binary_match.group(2)
                right_token = binary_match.group(3)

                left = value_of(left_token, line_no)
                right = value_of(right_token, line_no)

                if operator == "+":
                    result = builder.add(
                        left,
                        right,
                        name="addtmp"
                    )
                elif operator == "-":
                    result = builder.sub(
                        left,
                        right,
                        name="subtmp"
                    )
                else:
                    result = builder.mul(
                        left,
                        right,
                        name="multmp"
                    )

                builder.store(result, symbols[target])
                continue

            simple_match = re.fullmatch(
                rf"({IDENT_RE}|-?\d+)",
                expression
            )

            if simple_match:
                value = value_of(
                    simple_match.group(1),
                    line_no
                )

                builder.store(
                    value,
                    symbols[target]
                )
                continue

            fail(line_no, "invalid assignment expression")

        fail(line_no, "unparsable statement")

    if not exit_seen:
        fail(len(lines) if lines else 1, "no exit statement")

    with open(output_path, "w") as f:
        f.write(str(module))


def main():
    if len(sys.argv) != 3:
        print(
            "usage: python3 compiler.py <source> <output.ll>",
            file=sys.stderr
        )
        sys.exit(1)

    source_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        build_compiler(source_path, output_path)
    except FileNotFoundError:
        print(
            f"compilation error: source file '{source_path}' not found",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
