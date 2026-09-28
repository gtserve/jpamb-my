import random
import sys
from itertools import product

import jpamb
import jvm
import jvm.state as jvmc


def int32(value: int) -> int:
    """Apply the wrapping used by JVM integer operations."""
    value &= 0xFFFFFFFF
    return value if value < 0x80000000 else value - 0x100000000


def binary(op, v1: int, v2: int) -> int | str:
    match op:
        case jvm.BinaryOpr.Add:
            return int32(v1 + v2)
        case jvm.BinaryOpr.Sub:
            return int32(v1 - v2)
        case jvm.BinaryOpr.Mul:
            return int32(v1 * v2)
        case jvm.BinaryOpr.Div:
            if v2 == 0:
                return "divide by zero"
            sign = -1 if (v1 < 0) != (v2 < 0) else 1
            return int32(abs(v1) // abs(v2) * sign)
        case jvm.BinaryOpr.Rem:
            if v2 == 0:
                return "divide by zero"
            sign = -1 if (v1 < 0) != (v2 < 0) else 1
            quotient = abs(v1) // abs(v2) * sign
            return int32(v1 - quotient * v2)
        case _:
            raise NotImplementedError(f"Unhandled binary {op!r}")


def compare(op, v1: int, v2: int) -> bool:
    match op:
        case jvm.CmpOpr.Eq:
            return v1 == v2
        case jvm.CmpOpr.Ne:
            return v1 != v2
        case jvm.CmpOpr.Le:
            return v1 <= v2
        case jvm.CmpOpr.Lt:
            return v1 < v2
        case jvm.CmpOpr.Gt:
            return v1 > v2
        case jvm.CmpOpr.Ge:
            return v1 >= v2
        case _:
            raise NotImplementedError(f"COMPARE: Unhandled comparison {op!r}!")


def step(
    bc: jpamb.Bytecode, state: jvmc.State, *, debug: bool = False
) -> tuple[jvmc.PC, jvmc.State | str]:
    assert isinstance(state, jvmc.State), f"expected state but got {state}"
    frame = state.frames.peek()
    pc = frame.pc
    opr = bc[pc]
    output = state
    if debug:
        print(f"Stepping {pc}:\n > {opr}", file=sys.stderr)
    match opr:
        case jvm.Push(type=value_type, value=value):
            # iconst_i
            if isinstance(value_type, jvm.jvm_type.Int):
                frame.stack.push(jvmc.StackInt(value))
                frame.pc += 1
            elif isinstance(value_type, jvm.jvm_type.Reference):
                frame.stack.push(jvmc.StackReference(value))
                frame.pc += 1
            elif isinstance(value_type, jvm.Object) and isinstance(value, str):
                frame.stack.push(state.heap.new(jvmc.HeapString(value)))
                frame.pc += 1
            else:
                raise NotImplementedError(f"PUSH: Type {value_type} not implemented!")

        case jvm.Load(type=value_type, index=index):
            local = frame.locals[index]

            if isinstance(value_type, jvm.jvm_type.Int):
                # iload_n
                frame.stack.push(local)
                frame.pc += 1
            elif isinstance(value_type, jvm.jvm_type.Reference):
                # aload_<n>
                frame.stack.push(local)
                frame.pc += 1
            else:
                raise NotImplementedError(f"LOAD: Type {value_type} not implemented!")

        case jvm.Store(type=value_type, index=index):
            assert index <= len(frame.locals.locals) - 1, (
                f"STORE: Index {index} out of range!"
            )
            value = frame.stack.pop()

            if isinstance(value_type, (jvm.jvm_type.Int, jvm.jvm_type.Reference)):
                # istore_<n>
                frame.locals[index] = value
                frame.pc += 1
            else:
                raise NotImplementedError(f"STORE: Type {value_type} not implemented!")

        case jvm.Binary(type=jvm.Int(), operant=op):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert isinstance(v1, jvmc.StackInt), f"expected int, but got {v1}"
            assert isinstance(v2, jvmc.StackInt), f"expected int, but got {v2}"

            value = binary(op, v1.value, v2.value)

            if isinstance(value, str):
                output = value
            else:
                frame.stack.push(jvmc.StackInt(value))
                frame.pc += 1

        case jvm.Return(type=value_type):
            if value_type is not None:
                value = frame.stack.pop()
                state.frames.pop()
                if state.frames:
                    frame = state.frames.peek()
                    frame.stack.push(value)
                    frame.pc += 1
                else:
                    output = "ok"

            elif value_type is None:
                state.frames.pop()
                if state.frames:
                    state.frames.peek().pc += 1
                else:
                    output = "ok"

            else:
                raise NotImplementedError(f"RETURN: Type {value_type} not Implemented!")

        case jvm.Get(static=True, field=field):
            # Hack - Only handle the assertion case
            assert field.extension.name == "$assertionsDisabled"

            # Hack - Assuming assertions are never disabled
            frame.stack.push(jvmc.StackInt(0))
            frame.pc += 1

        case jvm.New(classname=classname):
            frame.stack.push(state.heap.new(jvmc.HeapObject(classname, {})))
            frame.pc += 1

        case jvm.Dup(words=1):
            value = frame.stack.pop()
            frame.stack.push(value)
            frame.stack.push(value)
            frame.pc += 1

        case jvm.NewArray(type=value_type, dim=1):
            count = frame.stack.pop()
            assert isinstance(count, jvmc.StackInt)
            if count.value < 0:
                output = "out of bounds"
            else:
                ref = state.heap.new(jvmc.HeapArray(value_type, [0] * count.value))
                frame.stack.push(ref)
                frame.pc += 1

        case jvm.ArrayStore():
            value = frame.stack.pop()
            index = frame.stack.pop()
            reference = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt)
            assert isinstance(index, jvmc.StackInt)
            assert isinstance(reference, jvmc.StackReference)
            if reference.value == 0:
                output = "null pointer"
            else:
                array = state.heap[reference]
                assert isinstance(array, jvmc.HeapArray)
                if index.value < 0 or index.value >= len(array.values):
                    output = "out of bounds"
                else:
                    array.values[index.value] = value.value
                    frame.pc += 1

        case jvm.ArrayLoad():
            index = frame.stack.pop()
            reference = frame.stack.pop()
            assert isinstance(index, jvmc.StackInt)
            assert isinstance(reference, jvmc.StackReference)
            if reference.value == 0:
                output = "null pointer"
            else:
                array = state.heap[reference]
                assert isinstance(array, jvmc.HeapArray)
                if index.value < 0 or index.value >= len(array.values):
                    output = "out of bounds"
                else:
                    frame.stack.push(jvmc.StackInt(array.values[index.value]))
                    frame.pc += 1

        case jvm.ArrayLength():
            reference = frame.stack.pop()
            assert isinstance(reference, jvmc.StackReference)
            if reference.value == 0:
                output = "null pointer"
            else:
                array = state.heap[reference]
                assert isinstance(array, jvmc.HeapArray)
                frame.stack.push(jvmc.StackInt(len(array.values)))
                frame.pc += 1

        case jvm.InvokeStatic(method=methodid):
            called = bc.getmethod(methodid)
            called_frame = jvmc.Frame.from_method(called)
            arguments = [frame.stack.pop() for _ in methodid.extension.params]
            for index, value in enumerate(reversed(arguments)):
                called_frame.locals[index] = value
            state.frames.push(called_frame)

        case jvm.InvokeVirtual(method=methodid):
            arguments = [frame.stack.pop() for _ in methodid.extension.params]
            receiver = frame.stack.pop()
            assert isinstance(receiver, jvmc.StackReference)
            if receiver.value == 0:
                output = "null pointer"
            elif methodid.extension.name == "equals" and len(arguments) == 1:
                argument = arguments[0]
                left = state.heap[receiver]
                right = (
                    state.heap[argument]
                    if isinstance(argument, jvmc.StackReference) and argument.value
                    else None
                )
                equal = (
                    isinstance(left, jvmc.HeapString)
                    and isinstance(right, jvmc.HeapString)
                    and left.content == right.content
                )
                frame.stack.push(jvmc.StackInt(1 if equal else 0))
                frame.pc += 1
            else:
                raise NotImplementedError(f"INVOKE VIRTUAL: {methodid}")

        case jvm.InvokeSpecial(method=methodid):
            for _ in methodid.extension.params:
                frame.stack.pop()
            frame.stack.pop()
            frame.pc += 1

        case jvm.Throw():
            reference = frame.stack.pop()
            assert isinstance(reference, jvmc.StackReference)
            if reference.value == 0:
                output = "null pointer"
            else:
                thrown = state.heap[reference]
                if isinstance(
                    thrown, jvmc.HeapObject
                ) and thrown.classname == jvm.ClassName("java.lang.AssertionError"):
                    output = "assertion error"
                else:
                    raise NotImplementedError(f"THROW: {thrown}")

        case jvm.Ifz(condition=op, target=target):
            value = frame.stack.pop()
            assert isinstance(value, (jvmc.StackInt, jvmc.StackReference)), (
                f"expected int or reference, but got {value}"
            )

            if compare(op, value.value, 0):
                frame.pc %= target
            else:
                frame.pc += 1

        case jvm.If(condition=op, target=target):
            v2 = frame.stack.pop()
            v1 = frame.stack.pop()

            # if_icmp<cond>
            if isinstance(v1, type(v2)) and isinstance(
                v1, (jvmc.StackInt, jvmc.StackReference)
            ):
                if compare(op, v1.value, v2.value):
                    frame.pc %= target
                else:
                    frame.pc += 1
            else:
                raise NotImplementedError("IF: Either types of v1, v2 not implemented!")

        case jvm.Goto(target=target):
            # goto
            frame.pc %= target

        case jvm.Cast(from_=source, to_=target):
            value = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt)
            if isinstance(source, jvm.Int) and isinstance(target, jvm.Short):
                short = value.value & 0xFFFF
                signed = short if short < 0x8000 else short - 0x10000
                frame.stack.push(jvmc.StackInt(signed))
            else:
                raise NotImplementedError(f"CAST: {source} -> {target}")
            frame.pc += 1

        case jvm.Negate(type=jvm.Int()):
            value = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt)
            frame.stack.push(jvmc.StackInt(int32(-value.value)))
            frame.pc += 1

        case jvm.Incr(index=index, amount=amount):
            # iinc
            value = frame.locals[index]
            assert isinstance(value, jvmc.StackInt)
            frame.locals[index] = jvmc.StackInt(int32(value.value + amount))
            frame.pc += 1

        case a:
            raise NotImplementedError(a.help())

    assert isinstance(output, (jvmc.State, str))

    return pc, output


def initial(bc: jpamb.Bytecode, methodid: jvm.AbsMethodID, input: jpamb.Input):
    frame = jvmc.Frame.from_method(bc.getmethod(methodid))
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack.from_frames([frame]))
    for i, v in enumerate(input.values):
        # Convert arbitrary values into local values
        match v:
            case jpamb.case.Boolean(value):
                frame.locals[i] = jvmc.StackInt(1 if value else 0)
            case jpamb.case.Int(value):
                frame.locals[i] = jvmc.StackInt(value)
            case jpamb.case.Array(contains=type, values=values):
                match type:
                    case jvm.Char():
                        ref = state.heap.new(
                            jvmc.HeapArray(type, [ord(a) for a in values])
                        )
                    case jvm.Int():
                        ref = state.heap.new(jvmc.HeapArray(type, [a for a in values]))
                frame.locals[i] = ref
            case jpamb.case.String(value=value):
                ref = state.heap.new(jvmc.HeapString(value))
                frame.locals[i] = ref
            case a:
                raise NotImplementedError(
                    f"Do not know how to convert values of type {a!r} to a local value"
                )

    return state


def interpret():
    """The entry point for the interpreter"""

    methodid, input, max_steps = jpamb.getcase(
        "My Dynamic Analyzer",
        "1.0",
        "YTS Group Ltd.",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    state = initial(bc, methodid, input)

    last = jpamb.emit_init(state)

    for x in range(max_steps):
        pc, state = step(bc, state, debug=True)
        last = jpamb.emit_step(last, pc, state)

        if isinstance(state, str):
            break


def fuzz_inputs(
    rand: random.Random, bc: jpamb.Bytecode, methodid: jvm.AbsMethodID
) -> list[jpamb.case.Input]:
    constants = {
        op.value
        for op in bc.getmethod(methodid).opcodes
        if isinstance(op, jvm.Push) and isinstance(op.value, int)
    }
    integers = set(range(-16, 17))
    integers.update((32, 100, 1_024))
    for value in constants:
        integers.update((int32(value - 1), int32(value), int32(value + 1)))
    integers.update(rand.randint(-100, 100) for _ in range(8))

    choices = []
    for parameter in methodid.extension.params:
        match parameter:
            case jvm.Int():
                choices.append([jpamb.case.Int(value) for value in sorted(integers)])
            case jvm.Boolean():
                choices.append([jpamb.case.Boolean(False), jpamb.case.Boolean(True)])
            case jvm.Array(contains=jvm.Int()):
                choices.append(
                    [
                        jpamb.case.Array(jvm.Int(), values)
                        for values in (
                            (),
                            (0,),
                            (1,),
                            (-1,),
                            (100, 101, 102),
                            (2, 3, 4, 10, 40),
                        )
                    ]
                )
            case jvm.Array(contains=jvm.Char()):
                choices.append(
                    [
                        jpamb.case.Array(jvm.Char(), tuple(value))
                        for value in ("", "a", "hello", "world")
                    ]
                )
            case jvm.Object(name=jvm.ClassName("java.lang.String")):
                choices.append(
                    [jpamb.case.String(value) for value in ("", "hello", "world")]
                )
            case unsupported:
                raise NotImplementedError(f"Cannot fuzz parameter {unsupported}")

    if not choices:
        return [jpamb.case.Input([])]

    combinations = list(product(*choices))
    rand.shuffle(combinations)

    # Always include simple aligned inputs before sampling the Cartesian product.
    # This preserves useful pairs such as (0, 0) even when there are many choices.
    seeds = []
    for index in range(min(len(values) for values in choices)):
        seeds.append(tuple(values[index] for values in choices))

    candidates = []
    seen = set()
    for values in seeds + combinations:
        input = jpamb.case.Input(list(values))
        key = input.encode()
        if key not in seen:
            seen.add(key)
            candidates.append(input)
        if len(candidates) == 100:
            break
    return candidates


def analyse():
    """The dynamic analysis, e.g. in this case a (dumb) fuzzer."""

    methodid = jpamb.getmethodid(
        "My Dynamic Analyzer",
        "1.0",
        "YTS Group Ltd.",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    max_steps = 2_000

    # Make the randomness deterministic
    rand = random.Random(0)

    behaviors = set()
    for input in fuzz_inputs(rand, bc, methodid):
        state = initial(bc, methodid, input)
        seen = set()

        for _ in range(max_steps):
            signature = repr(state)
            if signature in seen:
                behaviors.add("*")
                break
            seen.add(signature)

            try:
                _, state = step(bc, state)
            except (AssertionError, IndexError, NotImplementedError):
                break
            if isinstance(state, str):
                behaviors.add(state)
                break

    for query in jpamb.QUERIES:
        if query in behaviors:
            if query == "*":
                print(f"{query};timeout")
            else:
                print(f"{query};found")
        else:
            print(f"{query};not-found")
