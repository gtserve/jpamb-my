# Understanding the DTU Semantics Exercises Involving JPAMB

The [DTU semantics page](https://courses.compute.dtu.dk/02242/topics/semantics.html) uses JPAMB to turn the theory of operational semantics into two practical activities:

1. Build an analyzer that predicts possible program outcomes.
2. Build an interpreter that executes JVM bytecode one instruction at a time.

For the current repository, the analyzer activity is the main path. The interpreter exercises are still valuable because they teach the execution model that a more advanced static analyzer will eventually approximate.

## The overall purpose

The theoretical progression on the DTU semantics page is:

```text
Java syntax
    -> JVM bytecode
    -> machine state
    -> single-instruction transitions
    -> complete execution traces
    -> properties of all possible executions
```

The exercises make each arrow concrete.

| Activity | What you construct | What it is intended to teach |
|---|---|---|
| Inspect bytecode | Different views of a compiled Java method | How Java constructs are represented by JVM instructions |
| Bytecode syntactic analysis | Rules that recognize instruction patterns | What can and cannot be inferred without simulating execution |
| Write the `dup` rule | A formal state-transition rule | How an instruction receives precise mathematical meaning |
| Implement `dup` | A Python `step` case | How semantic rules become executable code |
| Build an interpreter | A sequence of concrete JVM states | Small-step operational semantics |
| Build a JPAMB analyzer | Predictions across all possible inputs | Static approximation, reachability, uncertainty, and calibration |

This is why the page first discusses axiomatic, denotational, and operational semantics. The practical work concentrates on small-step operational semantics because a rule of the form

```text
bc |- state -> next_state
```

can be translated almost directly into an interpreter branch.

## What JPAMB is asking

JPAMB contains small Java methods exhibiting six observable outcomes:

- `ok`: normal completion
- `divide by zero`
- `assertion error`
- `out of bounds`
- `null pointer`
- `*`: nontermination

The crucial point is that the analysis questions are existential. For every method `m` and outcome `q`, JPAMB asks:

```text
Does there exist an input x such that executing m(x) produces q?
```

It does not ask for the most common outcome, nor for the outcome of one supplied input.

Consequently, several answers can be true for the same method. For example, a method that asserts a Boolean parameter can have both `ok` and `assertion error` as possible outcomes. This contract is documented in [README.md](README.md) and [docs/rules.md](docs/rules.md).

### Analyzer versus interpreter

These are related but different JPAMB modes:

| | Analyzer | Interpreter |
|---|---|---|
| Input | Method identifier only | Method, concrete input, maximum steps |
| Question | What can happen for some input? | What happens for this input? |
| Output | Six predictions | Initial state and consecutive transitions |
| Main challenge | Approximation and path feasibility | Faithfully implementing JVM operations |
| JPAMB command | `jpamb analyse` | `jpamb interpret` |

An analyzer might receive:

```text
jpamb.cases.Simple.assertBoolean:(Z)V
```

It must produce six lines such as:

```text
ok;100%
divide by zero;0%
assertion error;100%
out of bounds;0%
null pointer;0%
*;0%
```

Those values would only be justified if the implementation had actually proved every claim.

An interpreter instead receives something like:

```text
jpamb.cases.Simple.assertBoolean:(Z)V
(false)
100
```

It must report the initial state, every transition, and eventually `"assertion error"`.

## Purpose of each JPAMB exercise

### 1. Inspect the class file

The first exercise asks you to run `javap`:

```bash
javap -cp target/classes -c jpamb.cases.Simple
```

Its purpose is to break the assumption that Java source statements correspond one-to-one with runtime operations.

For example, `assert condition;` becomes a sequence involving:

- the synthetic `$assertionsDisabled` field,
- conditional branches,
- allocation of `AssertionError`,
- `dup`,
- constructor invocation,
- `throw`,
- and a normal return branch.

That matters because a bytecode analyzer cannot simply search for a source-level `assert` node.

### 2. Inspect JPAMB's simplified bytecode

JPAMB provides decompiled JSON under:

```text
target/decompiled/jpamb/cases/
```

It also provides an inspection command:

```bash
jpamb inspect 'jpamb.cases.Simple.assertBoolean:(Z)V'
jpamb inspect --format=repr 'jpamb.cases.Simple.assertBoolean:(Z)V'
jpamb inspect --format=real 'jpamb.cases.Simple.assertBoolean:(Z)V'
jpamb inspect --format=json 'jpamb.cases.Simple.assertBoolean:(Z)V'
```

The purpose is to compare four representations:

- JPAMB's readable instruction format
- Python opcode objects
- real JVM mnemonics
- raw decompiled JSON

The simplified representation reduces the large JVM instruction set to a smaller set suitable for coursework.

### 3. Extend the bytecode syntactic analyzer

The starting example is [solutions/syntactic/src/syntactic_bytecode.py](solutions/syntactic/src/syntactic_bytecode.py). It only checks whether bytecode contains construction of an `AssertionError`.

This is deliberately imprecise. Its purpose is to expose the difference between:

```text
"The method contains instructions related to an assertion"
```

and:

```text
"There is a feasible input and execution path that reaches a failed assertion"
```

The first is syntactic pattern matching. The second requires semantic reasoning about branch conditions and reachability.

For example, the presence of division bytecode does not prove that divide-by-zero is possible. Earlier guards may imply that the divisor is nonzero. Similarly, an `assert false` following an infinite loop is present syntactically but unreachable.

### 4. Define and implement `dup`

The page asks you to write the small-step rule for `dup` before writing its Python implementation.

Conceptually, for the one-word case:

```text
Before stack: sigma, v
After stack:  sigma, v, v
PC:           pc -> pc + 1
Heap:         unchanged
Locals:       unchanged
```

A compact transition rule is:

```text
bc[pc] = dup 1
--------------------------------
<locals, sigma v, pc>
    ->
<locals, sigma v v, pc + 1>
```

For a reference, this duplicates the reference value. It does not clone the object in the heap.

The pedagogical purpose is important: consult the instruction specification, write down exactly what changes, and only then implement it. This prevents the interpreter from becoming a collection of guesses.

### 5. Build the interpreter

The interpreter maintains a state containing:

- a program counter,
- local variables,
- an operand stack,
- later, a stack of method frames,
- later, a heap.

Its `step` function performs exactly one transition. JPAMB then checks that consecutive states agree: the `after` state of one step must be the `before` state of the next. See [docs/interpret.md](docs/interpret.md).

The partial local implementation is [solutions/dynamic/src/dynamic.py](solutions/dynamic/src/dynamic.py). It already illustrates `push`, integer division, return, `$assertionsDisabled`, and assertion construction.

The intended development order is incremental:

1. Stack and local operations
2. Straight-line arithmetic
3. Return
4. Conditional branches
5. Assertion-related instructions
6. Calls and multiple frames
7. Objects, arrays, and heap operations
8. Loops and maximum-step handling

## Recommended starting path in this repository

The main project is currently the Tree-sitter analyzer [syntactic_new.py](syntactic_new.py), not the bytecode interpreter. Use the interpreter exercises to understand semantics while concentrating implementation work on the analyzer.

### Step 1: Activate and repair the Python environment

From the repository root:

```bash
cd /Users/gtserve/Code/jpamb-my
source .jpamb-eval/bin/activate
python --version
```

Python must be 3.13 or later.

The current environment imports JPAMB, but `tree_sitter` does not import. Install the local projects and Tree-sitter dependencies:

```bash
uv pip install --python .jpamb-eval/bin/python --editable .
uv pip install --python .jpamb-eval/bin/python --editable solutions/syntactic
```

Then verify:

```bash
python -c 'import tree_sitter, tree_sitter_java; print("Tree-sitter OK")'
./syntactic_new.py info
```

You can also run:

```bash
jpamb checkhealth
```

In the workspace's current state, most checks pass, but the final opcode check reports `what is 0`. That is separate from the missing Tree-sitter dependency and should not prevent source-level analyzer work, although it may affect some bytecode/interpreter experiments.

### Step 2: Understand one method in all representations

Start with:

```text
jpamb.cases.Simple.assertBoolean:(Z)V
```

Inspect:

```bash
sed -n '1,130p' cases/jpamb/cases/Simple.java
javap -cp target/classes -c jpamb.cases.Simple
jpamb inspect 'jpamb.cases.Simple.assertBoolean:(Z)V'
jpamb inspect --format=json 'jpamb.cases.Simple.assertBoolean:(Z)V'
```

When looking at Java source for analyzer development, inspect the method implementation but do not use `@Case` annotations to make predictions. They are benchmark ground truth, not analyzer input.

For each instruction, manually record:

```text
instruction
values consumed from stack
values produced on stack
locals changed
heap changed
next program counter
possible terminal outcome
```

### Step 3: Verify the analyzer protocol directly

Run:

```bash
./syntactic_new.py info
./syntactic_new.py 'jpamb.cases.Simple.assertFalse:()V'
```

The first command must print exactly five metadata lines. The second must print exactly one prediction for each of the six outcomes.

Debug output belongs on stderr because JPAMB parses stdout as the protocol.

### Step 4: Run a small focused evaluation

Use one iteration during development:

```bash
jpamb analyse \
  -N 1 \
  --filter 'Simple\.(assertFalse|assertTrue|doNothing)' \
  ./syntactic_new.py
```

Then broaden to the whole `Simple` class:

```bash
jpamb analyse -N 1 --filter 'jpamb\.cases\.Simple\.' ./syntactic_new.py
```

Focused evaluation gives faster feedback and makes regressions easier to identify.

### Step 5: Implement rules in increasing semantic difficulty

1. **Literal assertions**

   Handle `assert false` and `assert true`.

2. **Normal completion**

   Prove `ok` for empty bodies, safe fall-through, `return;`, and returns of safe literals.

   Do not conclude that every `return expression;` is safe: evaluating the expression could fail.

3. **Boolean and integer parameters**

   Treat parameters as unknown values that may satisfy multiple possibilities. A Boolean parameter may be true or false; an integer may be zero or nonzero.

4. **Branch reachability**

   Analyze `if` branches independently, refining facts such as `n == 0` and `n != 0` on their respective paths.

5. **Division**

   Report divide-by-zero if a reachable path permits a zero divisor. Report continuation if another reachable path permits a nonzero divisor.

6. **Arrays and nullness**

   Track whether references may be null, array lengths, and possible index ranges.

7. **Calls**

   Summarize called methods or analyze them recursively. Include recursion protection.

8. **Loops**

   Distinguish definitely infinite loops, definitely terminating loops, and unknown loops. Also account for unreachable code after a nonterminating loop.

The existing analyzer already has a useful three-valued structure—`IMPOSSIBLE`, `UNKNOWN`, and `POSSIBLE`—in [syntactic_new.py](syntactic_new.py). Alternative paths use existential joining, while requirements on one path must all hold.

### Step 6: Analyze the selected method body only

This is an especially important Tree-sitter detail.

The supplied example accidentally obtains `body` from the class node in [solutions/syntactic/src/syntactic_treesitter.py](solutions/syntactic/src/syntactic_treesitter.py). That can make one method inherit syntax from unrelated methods in the same class.

The current implementation correctly captures the selected method's block as `@method-body` in [syntactic_new.py](syntactic_new.py). Preserve that behavior as you add rules.

### Step 7: Use uncertainty honestly

Only emit `0%` when you have proved an outcome impossible, and `100%` when you have proved it possible.

Unsupported syntax should normally remain `50%` or be assigned an appropriate calibration category. A false certainty can cost much more than an honest neutral prediction.

This is particularly important for:

- calls whose bodies have not been analyzed,
- compound expressions,
- arrays with unknown lengths,
- aliasing,
- loops,
- and statements after possibly nonterminating code.

### Step 8: Regenerate and validate the submission report

During development, use filters and one iteration. For the final report, run the complete benchmark with the default three iterations:

```bash
jpamb analyse --report report.sexp ./syntactic_new.py
jpamb validate report.sexp
```

Do not combine `--report` with `--filter`; the current CLI explicitly rejects that combination.

The course page shows an older `--format=json` form. This repository's current `jpamb analyse` command does not provide that option; `--report report.sexp` is the correct submission path here. Likewise, the page's old `-W` interpreter flag has become `--step-wise`.

## If you also want to do the interpreter activity

Install the partial dynamic solution:

```bash
uv pip install --python .jpamb-eval/bin/python --editable solutions/dynamic
```

Then begin with one small group of methods:

```bash
jpamb interpret \
  --filter 'jpamb\.cases\.Simple\.' \
  --max-steps 100 \
  dynamic-interpreter
```

Use `--step-wise` to resume around a failure:

```bash
jpamb interpret \
  --step-wise \
  --filter 'jpamb\.cases\.Simple\.' \
  dynamic-interpreter
```

Implement one opcode at a time. For each opcode:

1. Inspect its JPAMB object with `jpamb inspect --format=repr`.
2. Write its stack/state transition on paper.
3. Add one `match` case to `step`.
4. Print diagnostics to stderr.
5. Test the smallest method that uses it.
6. Confirm the reported `before`, `pc`, and `after` states form a continuous trace.

Be careful with Java-specific behavior. For example, Java integer division truncates toward zero, whereas Python's `//` floors negative results. A faithful interpreter must reproduce Java's behavior.

## The main lesson

The exercises are designed to move you through three levels:

```text
Pattern recognition:
    "This instruction exists."

Reachability reasoning:
    "A feasible path can reach this instruction."

Semantic reasoning:
    "There exists an input whose complete execution produces this outcome."
```

JPAMB measures the last statement, but the earlier exercises give you the representations and execution rules needed to reach it. For this project, the most effective immediate route is to continue the Tree-sitter analyzer, add normal-completion and guarded-division rules first, test on small filtered groups, and regenerate `report.sexp` after every meaningful improvement.
