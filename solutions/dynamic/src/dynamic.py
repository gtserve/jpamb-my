import random
import sys

import jpamb
import jvm
import jvm.state as jvmc


def binary(op, v1: int, v2: int) -> int | str:
    match op:
        case jvm.BinaryOpr.Add:
            return v1 + v2
        case jvm.BinaryOpr.Sub:
            return v1 - v2
        case jvm.BinaryOpr.Mul:
            return v1 * v2
        case jvm.BinaryOpr.Div:
            try:
                return v1 // v2
            except ZeroDivisionError:
                return "divide by zero"
        case jvm.BinaryOpr.Rem:
            try:
                return v1 - (v1 / v2) * v2
            except ZeroDivisionError:
                return "division by zero"
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


def step(bc: jpamb.Bytecode, state: jvmc.State) -> tuple[jvmc.PC, jvmc.State | str]:
    assert isinstance(state, jvmc.State), f"expected state but got {state}"
    frame = state.frames.peek()
    pc = frame.pc
    opr = bc[pc]
    output = state
    print(f"Stepping {pc}:\n > {opr}", file=sys.stderr)
    match opr:
        case jvm.Push(type=value_type, value=value):
            # iconst_i
            if isinstance(value_type, jvm.jvm_type.Int):
                frame.stack.push(jvmc.StackInt(value))
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

            if isinstance(value_type, jvm.jvm_type.Int):
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
            if isinstance(value_type, jvm.jvm_type.Int):
                # ireturn
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
                    raise NotImplementedError("RETURN: Method caller not implemented!")
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

        case jvm.New(classname=jvm.ClassName("java.lang.AssertionError")):
            # Hack -- if we create an assertion error, we probably also throw it.
            output = "assertion error"

        case jvm.Ifz(condition=op, target=target):
            value = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt), f"expected int, but got {value}"

            if compare(op, value.value, 0):
                frame.pc %= target
            else:
                frame.pc += 1

        case jvm.If(condition=op, target=target):
            v2 = frame.stack.pop()
            v1 = frame.stack.pop()

            # if_icmp<cond>
            if isinstance(v1, jvmc.StackInt) and isinstance(v2, jvmc.StackInt):
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
            # i2s
            value = frame.stack.pop()
            frame.stack.push(jvmc.StackInt(value.value))
            frame.pc += 1
            # assert isinstance(source, jvm.jvm_type.Int), \
            #     f"CAST: Only Int -> Short supported! Got from: {source}, to: {target}!"
            # value = frame.stack.pop()
            # assert isinstance(value, jvmc.StackInt), f"CAST: Expected int value but got {value}!"
            # new_value = jvmc.StackInt(value.value)
            # frame.stack.push(new_value)

        # case jvm.NewArray(type=t, dim=size):
        #     # newarray
        #     count = frame.stack.pop()
        #     assert isinstance(count, jvmc.StackInt), f"NEW-ARRAY: Expected count of type Int, but got {type(count)}!"
        #     stack_ref = state.heap.new(jvmc.HeapArray(
        #         contains=t,
        #         values=[]
        #     ))

        case jvm.Incr(index=index, amount=amount):
            # iinc
            value = frame.locals[index]
            assert isinstance(value, jvmc.StackInt)
            value.value += amount
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
        pc, state = step(bc, state)
        last = jpamb.emit_step(last, pc, state)

        if isinstance(state, str):
            break


def fuzz_input(rand: random.Random, methodid: jvm.AbsMethodID) -> jpamb.case.Input:
    input = []
    # 1. come up with possible inputs
    for p in methodid.extension.params:
        match p:
            case jvm.Int():
                input.append(jpamb.case.Int(rand.randint(-(1 << 31), 1 << 31)))
            case jvm.Boolean():
                input.append(jpamb.case.Boolean(1 == rand.randint(0, 1)))
            case a:
                raise NotImplementedError(
                    f"Don't know how to create random values for {input}"
                )

    return jpamb.case.Input(input)


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

    max_steps = 200

    import random

    # Make the randomness deterministic
    rand = random.Random(0)

    # Try 10 random inputs
    behaviors = set()
    for i in range(10):
        input = fuzz_input(rand, methodid)
        state = initial(bc, methodid, input)

        for x in range(max_steps):
            _, state = step(bc, state)
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
