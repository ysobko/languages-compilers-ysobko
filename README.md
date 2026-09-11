The compiler has a lexer written as a state machine. 
It reads the source byte by byte and creates tokens with type, text, line and column.

The language supports:

- `i32` variables
- `mut` variables
- `+`, `-`, `*`
- assignment with `:=`
- `exit`

LLVM IR is generated with `llvmlite.ir`.

## Run

```bash
python3 compiler.py input.txt output.ll
lli output.ll


Or compile to a program:
llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program
./program

Tests are in the tests/ folder.
There are valid and invalid test programs with expected results.

Run a valid test:

```bash
python3 compiler.py tests/valid1.txt output.ll
lli output.ll

Run an invalid test:

```bash
python3 compiler.py tests/invalid1.txt output.ll
