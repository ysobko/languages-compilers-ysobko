# Language Compiler

This project is a compiler written in Python.

The compiler uses a handwritten lexer and parser, checks the program for semantic errors, and generates LLVM IR using `llvmlite`.

## Language Features

The language supports:

- `i32`, `i64`, and `bool` types
- Mutable and immutable variables
- Arithmetic operations: `+`, `-`, `*`
- Comparisons: `==`, `!=`
- Assignment with `:=`
- `if` and `else`
- `while` loops
- Functions with parameters and return values
- Structures with fields and member functions
- Function and member function calls
- Callable objects and callable fields
- Lambda functions with captures
- `print()` and `read()`
- `exit`

## Callable Objects

A structure can define a member function named `call`.

Such objects can be called directly or through `.call()`.

Example:

```text
struct Counter
{
    i32 mut n

    fn call := () -> i32
    {
        n := n + 1
        exit n
    }
}

Counter mut c{0}

print(c())
print(c.call())

exit 0
```

Both calls use the same member function.

A callable object stored in a field can also be called through that field.

## Lambda Functions

A lambda is declared using `fn`, a capture list, parameters, and a return type.

Example:

```text
i32 mut k{10}

fn add_k := [k](i32 x) -> i32
{
    i32 result{x + k}
    exit result
}

k := 20

print(add_k(5))

exit 0
```

The lambda captures the value of `k` when it is declared.

Therefore, the output is `15`, even though `k` is changed later.

Capture rules:

- `[]` means no captured variables.
- `[x]` captures the current value of `x` as immutable.
- `[mut x]` captures the current value of `x` as mutable.
- Mutable captures preserve their modified values between calls.
- Changing a captured variable does not change the original variable.
- Mixed captures such as `[x, mut y]` are supported.
- A lambda with mutable captures is stored as a mutable object.
- Local variables must be explicitly captured to be used inside the lambda.
- Global functions can be called without capturing them.
- A lambda can capture another lambda.
- Lambdas can be declared inside functions and loops.
- Recursive lambda calls are not supported.
- Lambdas cannot be passed as function arguments or returned through `exit`.

### Mutable Captures (Bonus)

A lambda can modify a captured variable by using `mut` in its capture list.

Example:

```text
i32 mut x{10}

fn counter := [mut x]() -> i32
{
    x := x + 1
    exit x
}

print(counter())
print(counter())
print(x)

exit 0
```

Output:

```text
11
12
10
Program exit with result 0
```

The lambda keeps its own copy of `x`. Its value changes between calls, but the original `x` remains `10`.

## While Loops

A `while` loop repeats its body while its condition is `true`.

The condition must have type `bool`.

Example:

```text
i32 mut i{0}

while i != 3
{
    print(i)
    i := i + 1
}

exit 0
```

## Build and Run

Activate the Python virtual environment and install the required dependencies.

Compile a source program:

```bash
python3 compiler.py input.txt output.ll
```

Run the generated LLVM IR:

```bash
lli output.ll
```

Alternatively, compile it into an executable:

```bash
llc -filetype=obj -relocation-model=pic output.ll -o output.o
clang -fPIE output.o -o program
./program
```

## Tests

Valid programs are stored in `tests/ok`.

Invalid programs are stored in `tests/err`.

Expected results are stored in `.expected` files.

Input files, when needed, use the `.in` extension.

Run all tests:

```bash
python3 run_tests.py
```

The test script compiles each program, executes valid programs using `lli`, compares their complete output, and checks expected compilation errors.

## Optimizations

The compiler supports the `--remove-unused` flag. Optimization runs after semantic checking and before LLVM code generation.

- **Unused variable elimination:** Removes declarations and assignments whose values are never read. The pass repeats until no more variables can be removed. Initializers with side effects are preserved.
- **Unused global function elimination:** Removes unused global functions, including functions that become unused after other functions or declarations are removed. Struct methods and lambdas are not directly eliminated by this pass.
- **Calls without effects (additional task):** Analyzes functions and methods to identify calls that can be safely removed when their results are unused. Functions containing `print`, `read`, `while`, or field mutations are treated as effectful. Effects propagate through function calls. Recursive functions are conservatively treated as effectful. Pure calls can be removed, but calls with effectful arguments are preserved. The optimization repeats until no further declarations or global functions can be removed.

To inspect the optimized AST, run:

    python3 compiler.py --remove-unused --ast-checked input.txt

To run all tests with optimization, run:

    python3 run_tests.py --remove-unused

**Known limitations:** A self-feeding assignment such as `k := k + 1` counts as a read, so an otherwise unused variable may be retained. Unreachable cycles of mutually calling functions may also remain.

### Memory management

The compiler is implemented in Python. CPython uses reference counting and a cyclic garbage collector. When the optimizer removes an AST subtree and no strong references remain, Python automatically reclaims its memory.

AST nodes do not store explicit parent pointers. If they did, bidirectional parent-child references could create cycles that reference counting alone could not reclaim. Python's cyclic garbage collector can handle unreachable cycles.

We verified memory reclamation using `weakref.ref(node)` on an unused declaration. The experiment produced:

    Before optimization: True
    After optimization: None

After running the optimization and `gc.collect()`, the weak reference returned `None`, confirming that the removed node was reclaimed.

This concerns the compiler's AST memory, not the compiled program's memory. The compiled language does not support heap allocation yet.
