1. Describe the features or idioms covered by the course that you think to be the most useful.

For me the most useful part was learning how source code becomes LLVM IR. In `compile_program` compiler parses code, checks it, optionally optimizes it and then generates IR. This helped me to understand what each stage does. Expression parsing was also very useful. In parser function `parse_term` handles multiplication and `parse_arith` handles addition and subtraction. This means that multiplication is first. I also found optimization useful because it showed how compiler can remove unnecessary code and keep the program’s behaviour correct.

2. Which features were not covered properly?

Personally i would like to have more simple examples of LLVM code generation. In `CodeGen.visit_while` compiler creates like separate blocks for condition, loop body and end. It took me some time to understand how these blocks connect. also about optimization i would like to have mire expamples with explanations. In `UseCounter.visit_decl` unused declaration can be kept if its initializer has effects. I would've liked to compare more cases where for example removing declaration is safe and where it would change what the program does.

3. Provide at least 3 examples related to languages and compilers that surprised you most.

First, i was surprised that unused variable can't always be removed. For example its initializer may call `read()`. In `UseCounter.visit_decl` this effect is checked because if we remove declaration it would also remove input operation.

Second, i was surprised that one optimization pass may not be enough. In `optimize_program` unused declarations and functions are removed repeatedly until their counts stop changing.Ans if we remove one declaration than it can make another one unused.

Third, i was surprised that LLVM doesn't need special instruction for `while` loop. In `CodeGen.visit_while` compiler builds loop using blocks and jumps between them. Loop repeats because execution jumps back to condition. This helped me understand what happens behind this feature.

4. Which concepts (idioms) or approaches are still not clear enough?

I still need more practice with deciding whether code is safe to remove. `EffectAnalyzer` checks effects inside functions and through calls to other functions. I understand why this matters, but following several calls or recursive calls is still difficult for me. I also want to understand LLVM memory operations better. For example `CodeGen.visit_field_access` uses `getelementptr` to find struct fields. I can follow code but i would need more practice to better understand.

5. Other ideas and suggestions related to the course content.

I would suggest to add more small examples with results before and after optimization. The existing `--ast-checked` and `--remove-unused --ast-checked` modes could show exactly which declarations disappear. It would be useful to include both unused variables that can be removed and one containing `read()` that must stay. I would also like to follow one short program through tokens, AST, semantic checks, optimization and LLVM IR. Seeing the same example at every stage would help me connect all course topics.
