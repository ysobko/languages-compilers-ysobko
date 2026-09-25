import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
TESTS = ROOT / "tests"
COMPILER = ROOT / "compiler.py"


def run_valid(source):
    expected_path = source.with_suffix(".expected")
    expected = expected_path.read_text().strip()

    with tempfile.NamedTemporaryFile(suffix=".ll") as output:
        compile_result = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(source),
                output.name,
            ],
            capture_output=True,
            text=True,
        )

        if compile_result.returncode != 0:
            return False, compile_result.stderr.strip()

        run_result = subprocess.run(
            ["lli", output.name],
            capture_output=True,
            text=True,
        )

        actual = run_result.stdout.strip()

        if actual != expected:
            return False, f"expected: {expected}\nactual:   {actual}"

    return True, ""


def run_invalid(source):
    expected_path = source.with_suffix(".expected")
    expected = expected_path.read_text().strip()

    with tempfile.NamedTemporaryFile(suffix=".ll") as output:
        result = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
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


def main():
    failures = 0

    valid_tests = sorted(TESTS.glob("valid*.txt"))
    invalid_tests = sorted(TESTS.glob("invalid*.txt"))

    for source in valid_tests:
        ok, message = run_valid(source)

        if ok:
            print(f"PASS {source.name}")
        else:
            failures += 1
            print(f"FAIL {source.name}")
            print(message)

        ast_ok, ast_message = run_ast(source)

        if source.with_suffix(".ast").exists():
            if ast_ok:
                print(f"PASS {source.stem}.ast")
            else:
                failures += 1
                print(f"FAIL {source.stem}.ast")
                print(ast_message)

    for source in invalid_tests:
        ok, message = run_invalid(source)

        if ok:
            print(f"PASS {source.name}")
        else:
            failures += 1
            print(f"FAIL {source.name}")
            print(message)

    total = len(valid_tests) + len(invalid_tests)

    print()
    print(f"{total} program tests, {failures} failures")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
