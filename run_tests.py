import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
TESTS = ROOT / "tests"
OK_TESTS = TESTS / "ok"
ERR_TESTS = TESTS / "err"
OPT_TESTS = TESTS / "opt"
COMPILER = ROOT / "compiler.py"


def run_valid(source, optimize=False):
    expected_path = source.with_suffix(".expected")
    expected = expected_path.read_text().rstrip("\n")

    with tempfile.NamedTemporaryFile(suffix=".ll") as output:
        compile_result = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                *(["--remove-unused"] if optimize else []),
                str(source),
                output.name,
            ],
            capture_output=True,
            text=True,
        )

        if compile_result.returncode != 0:
            return False, compile_result.stderr.strip()

        input_path = source.with_suffix(".in")

        if not input_path.exists():
            input_path = source.with_suffix(".input")

        input_data = input_path.read_text() if input_path.exists() else ""

        run_result = subprocess.run(
            ["lli", output.name],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=10,
        )

        actual = run_result.stdout.rstrip("\n")

        if actual != expected:
            return False, f"expected: {expected}\nactual:   {actual}"

    return True, ""


def run_invalid(source, optimize=False):
    expected_path = source.with_suffix(".expected")
    expected = expected_path.read_text().strip()

    with tempfile.NamedTemporaryFile(suffix=".ll") as output:
        result = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                *(["--remove-unused"] if optimize else []),
                str(source),
                output.name,
            ],
            capture_output=True,
            text=True,
        )

        actual = result.stderr.strip()

        if result.returncode == 0:
            return False, "compiler succeeded but failure was expected"

        if actual != expected:
            return False, f"expected: {expected}\nactual:   {actual}"

    return True, ""


def run_ast(source):
    ast_path = source.with_suffix(".ast")

    if not ast_path.exists():
        return True, ""

    expected = ast_path.read_text().strip()

    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            "--ast",
            str(source),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, result.stderr.strip()

    actual = result.stdout.strip()

    if actual != expected:
        return False, f"expected AST:\n{expected}\n\nactual AST:\n{actual}"

    return True, ""


def run_checked_ast(source):
    ast_path = source.with_suffix(".checked.ast")

    if not ast_path.exists():
        return True, ""

    expected = ast_path.read_text().strip()

    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            "--ast-checked",
            str(source),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, result.stderr.strip()

    actual = result.stdout.strip()

    if actual != expected:
        return False, f"expected checked AST:\n{expected}\n\nactual checked AST:\n{actual}"

    return True, ""



def run_optimized_ast(source):
    expected = source.with_suffix(".astc").read_text().strip()

    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            "--remove-unused",
            "--ast-checked",
            str(source),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, result.stderr.strip()

    actual = result.stdout.strip()

    if actual != expected:
        return False, f"expected AST:\\n{expected}\\n\\nactual AST:\\n{actual}"

    return True, ""



def run_io(source, session, optimize=False):
    input_path = source.parent / f"{source.stem}.{session}.in"
    expected_path = source.parent / f"{source.stem}.{session}.expected"
    expected = expected_path.read_text()

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        ir_path = directory / "program.ll"
        obj_path = directory / "program.o"
        exe_path = directory / "program"

        commands = [
            [
                sys.executable,
                str(COMPILER),
                *(["--remove-unused"] if optimize else []),
                str(source),
                str(ir_path),
            ],
            [
                "llc",
                "-filetype=obj",
                "-relocation-model=pic",
                str(ir_path),
                "-o",
                str(obj_path),
            ],
            ["clang", "-fPIE", str(obj_path), "-o", str(exe_path)],
        ]

        for command in commands:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return False, result.stderr.strip()

        result = subprocess.run(
            [str(exe_path)],
            input=input_path.read_text(),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.stdout != expected:
            return False, (
                f"expected:\n{expected}\nactual:\n{result.stdout}"
            )

        return True, ""



def run_ffi(source, session, optimize=False):
    input_path = source.parent / f"{source.stem}.{session}.in"
    expected_path = source.parent / f"{source.stem}.{session}.expected"
    c_path = source.with_suffix(".c")
    expected = expected_path.read_text()

    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        ir_path = directory / "program.ll"
        obj_path = directory / "program.o"
        c_obj_path = directory / "helper.o"
        exe_path = directory / "program"

        commands = [
            [
                sys.executable,
                str(COMPILER),
                *(["--remove-unused"] if optimize else []),
                str(source),
                str(ir_path),
            ],
            [
                "llc", "-filetype=obj", "-relocation-model=pic",
                str(ir_path), "-o", str(obj_path),
            ],
            ["clang", "-c", str(c_path), "-o", str(c_obj_path)],
            ["clang", str(obj_path), str(c_obj_path), "-o", str(exe_path)],
        ]

        for command in commands:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return False, result.stderr.strip()

        result = subprocess.run(
            [str(exe_path)],
            input=input_path.read_text(),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.stdout != expected:
            return False, (
                f"expected:\n{expected}\nactual:\n{result.stdout}"
            )

        return True, ""


def main():
    optimize = "--remove-unused" in sys.argv[1:]
    failures = 0

    valid_tests = sorted(TESTS.glob("valid*.txt"))
    invalid_tests = sorted(TESTS.glob("invalid*.txt"))

    if OK_TESTS.exists():
        valid_tests += sorted(OK_TESTS.glob("*.txt"))

    if ERR_TESTS.exists():
        invalid_tests += sorted(ERR_TESTS.glob("*.txt"))

    for source in valid_tests:
        ok, message = run_valid(source, optimize)

        if ok:
            print(f"PASS {source.relative_to(TESTS)}")
        else:
            failures += 1
            print(f"FAIL {source.relative_to(TESTS)}")
            print(message)

        ast_ok, ast_message = run_ast(source)

        if source.with_suffix(".ast").exists():
            if ast_ok:
                print(
                    f"PASS "
                    f"{source.with_suffix('.ast').relative_to(TESTS)}"
                )
            else:
                failures += 1
                print(
                    f"FAIL "
                    f"{source.with_suffix('.ast').relative_to(TESTS)}"
                )
                print(ast_message)

        checked_ast_path = source.with_suffix(".checked.ast")

        if checked_ast_path.exists():
            ast_ok, ast_message = run_checked_ast(source)

            if ast_ok:
                print(
                    f"PASS {checked_ast_path.relative_to(TESTS)}"
                )
            else:
                failures += 1
                print(
                    f"FAIL {checked_ast_path.relative_to(TESTS)}"
                )
                print(ast_message)

    for source in invalid_tests:
        ok, message = run_invalid(source, optimize)

        if ok:
            print(f"PASS {source.relative_to(TESTS)}")
        else:
            failures += 1
            print(f"FAIL {source.relative_to(TESTS)}")
            print(message)

    opt_tests = sorted(OPT_TESTS.glob("*.txt"))

    for source in opt_tests:
        for optimize in (False, True):
            ok, message = run_valid(source, optimize)
            mode = "optimized" if optimize else "normal"

            if ok:
                print(f"PASS opt/{source.name} ({mode})")
            else:
                failures += 1
                print(f"FAIL opt/{source.name} ({mode})")
                print(message)

        ast_ok, ast_message = run_optimized_ast(source)

        if ast_ok:
            print(f"PASS opt/{source.stem}.astc")
        else:
            failures += 1
            print(f"FAIL opt/{source.stem}.astc")
            print(ast_message)


    io_tests = sorted((TESTS / "io").glob("*.txt"))

    for source in io_tests:
        for input_path in sorted(source.parent.glob(f"{source.stem}.*.in")):
            session = input_path.name[len(source.stem) + 1:-3]

            for io_optimize in (False, True):
                mode = "optimized" if io_optimize else "normal"
                ok, message = run_io(source, session, io_optimize)

                if ok:
                    print(f"PASS io/{source.stem}.{session} ({mode})")
                else:
                    failures += 1
                    print(f"FAIL io/{source.stem}.{session} ({mode})")
                    print(message)


    ffi_tests = sorted((TESTS / "ffi").glob("*.txt"))
    for source in ffi_tests:
        for input_path in sorted(source.parent.glob(f"{source.stem}.*.in")):
            session = input_path.name[len(source.stem) + 1:-3]
            for ffi_optimize in (False, True):
                mode = "optimized" if ffi_optimize else "normal"
                ok, message = run_ffi(source, session, ffi_optimize)
                if ok:
                    print(f"PASS ffi/{source.stem}.{session} ({mode})")
                else:
                    failures += 1
                    print(f"FAIL ffi/{source.stem}.{session} ({mode})")
                    print(message)

    total = len(valid_tests) + len(invalid_tests) + len(opt_tests) + len(io_tests) + len(ffi_tests)

    print()
    print(f"{total} program tests, {failures} failures")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
