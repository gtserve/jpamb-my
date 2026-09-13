#!/usr/bin/env python3

import argparse
import re
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

import tree_sitter
import tree_sitter_java

PROG_NAME = "Syntactic Analyzer"
VERSION = "1.0"
GROUP_NAME = "Group 5"
TAGS = "syntactic,python"
INFO = "macos"

OUTCOMES = (
    "ok",
    "divide by zero",
    "assertion error",
    "out of bounds",
    "null pointer",
    "*",
)

TS_JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
RUNTIME_OUTCOMES = OUTCOMES[1:]


@dataclass(frozen=True)
class MethodContext:
    return_type: str
    name: str
    body: tree_sitter.Node
    parameters: dict[str, str]


class Possibility(IntEnum):
    """Evidence that an existential outcome can happen."""

    IMPOSSIBLE = 0
    UNKNOWN = 1
    POSSIBLE = 2


def either(*values: Possibility) -> Possibility:
    """Join alternative paths: one possible path is enough."""
    return max(values, default=Possibility.IMPOSSIBLE)


def both(*values: Possibility) -> Possibility:
    """Combine requirements on one path: every part must be possible."""
    return min(values, default=Possibility.POSSIBLE)


def no_outcomes() -> dict[str, Possibility]:
    return dict.fromkeys(RUNTIME_OUTCOMES, Possibility.IMPOSSIBLE)


def unknown_outcomes() -> dict[str, Possibility]:
    return dict.fromkeys(RUNTIME_OUTCOMES, Possibility.UNKNOWN)


UNKNOWN_VALUE = object()


@dataclass
class ExpressionResult:
    completes: Possibility = Possibility.POSSIBLE
    outcomes: dict[str, Possibility] = field(default_factory=no_outcomes)
    can_be_true: Possibility = Possibility.UNKNOWN
    can_be_false: Possibility = Possibility.UNKNOWN
    can_be_zero: Possibility = Possibility.UNKNOWN
    can_be_nonzero: Possibility = Possibility.UNKNOWN
    constant: object = UNKNOWN_VALUE


@dataclass(frozen=True)
class Facts:
    """Facts known to hold on the current path."""

    zero: frozenset[str] = frozenset()
    nonzero: frozenset[str] = frozenset()


@dataclass
class FlowResult:
    """Summary returned by recursively analyzing a statement."""

    continues: Possibility = Possibility.POSSIBLE
    returns: Possibility = Possibility.IMPOSSIBLE
    outcomes: dict[str, Possibility] = field(default_factory=no_outcomes)
    facts: Facts = Facts()


def blind_guess() -> dict[str, str]:
    """Blind guess. Inadequate analysis to make a justified bet."""
    return dict.fromkeys(OUTCOMES, "50%")


def parse_target(command: str) -> tuple[str, str]:
    """Return the Java class and method name from a JPAMB method identifier."""
    match = re.fullmatch(r"(?P<class>.+)\.(?P<method>[^.:]+):.+", command)
    if match is None:
        raise ValueError(
            "Correct format: jpamb.cases.Simple.divideByZero:()I"
        )
    return match["class"], match["method"]


def init_context(command: str) -> MethodContext | None:
    class_name, method_name = parse_target(command)

    # Read Java file.
    source_file = Path("cases", *class_name.split(".")).with_suffix(".java")
    try:
        source = source_file.read_bytes()
    except OSError as error:
        print(f"Could not read {source_file}: {error}", file=sys.stderr)
        return None

    # Initialize Tree-sitter object.
    parser = tree_sitter.Parser(TS_JAVA_LANGUAGE)
    tree = parser.parse(source)

    # Find target method in syntax tree.
    query = tree_sitter.Query(
        TS_JAVA_LANGUAGE,
        f"""
        (method_declaration
            type: (_) @method-type
            name: ((identifier) @method-name (#eq? @method-name "{method_name}"))
            parameters: (formal_parameters) @method-parameters
            body: (block) @method-body
        )
        """
    )
    query_cursor = tree_sitter.QueryCursor(query)
    captures = query_cursor.captures(tree.root_node)

    method_names = captures.get("method-name", [])
    if len(method_names) != 1:
        print(f"Expected exactly one method name: {method_names}", file=sys.stderr)
        return None

    parameters: dict[str, str] = {}
    for parameter in captures["method-parameters"][0].named_children:
        if parameter.type not in {"formal_parameter", "spread_parameter"}:
            continue
        parameter_name = parameter.child_by_field_name("name")
        parameter_type = parameter.child_by_field_name("type")
        if parameter_name is not None and parameter_type is not None:
            parameters[parameter_name.text.decode()] = parameter_type.text.decode()

    context = MethodContext(
        return_type=captures["method-type"][0].text.decode(),
        name=method_names[0].text.decode(),
        body=captures["method-body"][0],
        parameters=parameters,
    )

    # DEBUG
    print("-" * 50, file=sys.stderr)
    print(f"Method: {context.return_type} {context.name}", file=sys.stderr)
    print("-" * 50, file=sys.stderr)
    print(context.body, file=sys.stderr)

    return context


def merge_outcomes(
    first: dict[str, Possibility],
    second: dict[str, Possibility],
    second_is_reachable: Possibility = Possibility.POSSIBLE,
) -> dict[str, Possibility]:
    """Join outcomes while accounting for whether the second node is reached."""
    return {
        outcome: either(first[outcome], both(second_is_reachable, second[outcome]))
        for outcome in RUNTIME_OUTCOMES
    }


def parse_integer_literal(node: tree_sitter.Node) -> int | None:
    if node.type not in {
        "decimal_integer_literal",
        "hex_integer_literal",
        "octal_integer_literal",
        "binary_integer_literal",
    }:
        return None
    text = node.text.decode().replace("_", "").removesuffix("L").removesuffix("l")
    try:
        if node.type == "decimal_integer_literal":
            return int(text, 10)
        if node.type == "octal_integer_literal":
            return int(text.removeprefix("0") or "0", 8)
        return int(text, 0)
    except ValueError:
        return None


class RecursiveAnalyzer:
    """A small recursive, path-sensitive analyzer over the Java syntax tree."""

    def __init__(self, context: MethodContext):
        self.context = context

    def unknown_expression(self) -> ExpressionResult:
        return ExpressionResult(
            completes=Possibility.UNKNOWN,
            outcomes=unknown_outcomes(),
        )

    def expression(self, node: tree_sitter.Node, facts: Facts) -> ExpressionResult:
        """Analyze an expression and recursively summarize its children."""
        integer = parse_integer_literal(node)
        if integer is not None:
            return ExpressionResult(
                can_be_zero=(
                    Possibility.POSSIBLE if integer == 0 else Possibility.IMPOSSIBLE
                ),
                can_be_nonzero=(
                    Possibility.IMPOSSIBLE if integer == 0 else Possibility.POSSIBLE
                ),
                constant=integer,
            )

        if node.type in {"true", "false"}:
            value = node.type == "true"
            return ExpressionResult(
                can_be_true=(Possibility.POSSIBLE if value else Possibility.IMPOSSIBLE),
                can_be_false=(Possibility.IMPOSSIBLE if value else Possibility.POSSIBLE),
                constant=value,
            )

        if node.type == "identifier":
            name = node.text.decode()
            parameter_type = self.context.parameters.get(name)
            result = ExpressionResult()
            if name in facts.zero:
                result.can_be_zero = Possibility.POSSIBLE
                result.can_be_nonzero = Possibility.IMPOSSIBLE
                result.constant = 0
            elif name in facts.nonzero:
                result.can_be_zero = Possibility.IMPOSSIBLE
                result.can_be_nonzero = Possibility.POSSIBLE
            elif parameter_type in {"byte", "short", "int", "long"}:
                result.can_be_zero = Possibility.POSSIBLE
                result.can_be_nonzero = Possibility.POSSIBLE
            if parameter_type == "boolean":
                result.can_be_true = Possibility.POSSIBLE
                result.can_be_false = Possibility.POSSIBLE
            return result

        if node.type == "parenthesized_expression" and node.named_children:
            return self.expression(node.named_children[0], facts)

        if node.type == "binary_expression":
            return self.binary_expression(node, facts)

        if "literal" in node.type:
            # Reading a literal is safe even when its exact value is not modeled.
            return ExpressionResult()

        # Calls, array accesses, and field accesses need dedicated rules. Until
        # then, lack of support must not become a false 0% proof.
        return self.unknown_expression()

    def binary_expression(self, node: tree_sitter.Node, facts: Facts) -> ExpressionResult:
        """Recursively analyze both operands of a binary expression."""
        left_node = node.child_by_field_name("left")
        operator_node = node.child_by_field_name("operator")
        right_node = node.child_by_field_name("right")
        if left_node is None or operator_node is None or right_node is None:
            return self.unknown_expression()

        operator = operator_node.text.decode()
        left = self.expression(left_node, facts)

        # Java's && and || do not necessarily evaluate the right operand.
        if operator in {"&&", "||"}:
            right_reachable = (
                left.can_be_true if operator == "&&" else left.can_be_false
            )
            short_circuit = (
                left.can_be_false if operator == "&&" else left.can_be_true
            )
            right_facts = self.refine(left_node, operator == "&&", facts)
            right = self.expression(right_node, right_facts)
            outcomes = merge_outcomes(left.outcomes, right.outcomes, right_reachable)
            if operator == "&&":
                can_be_true = both(left.can_be_true, right.can_be_true)
                can_be_false = either(
                    left.can_be_false,
                    both(left.can_be_true, right.can_be_false),
                )
            else:
                can_be_true = either(
                    left.can_be_true,
                    both(left.can_be_false, right.can_be_true),
                )
                can_be_false = both(left.can_be_false, right.can_be_false)
            return ExpressionResult(
                completes=both(
                    left.completes,
                    either(short_circuit, both(right_reachable, right.completes)),
                ),
                outcomes=outcomes,
                can_be_true=can_be_true,
                can_be_false=can_be_false,
            )

        right = self.expression(right_node, facts)
        operands_complete = both(left.completes, right.completes)
        outcomes = merge_outcomes(left.outcomes, right.outcomes, left.completes)

        if operator in {"/", "%"}:
            outcomes["divide by zero"] = either(
                outcomes["divide by zero"],
                both(operands_complete, right.can_be_zero),
            )
            return ExpressionResult(
                completes=both(operands_complete, right.can_be_nonzero),
                outcomes=outcomes,
            )

        if operator in {"==", "!=", "<", "<=", ">", ">="}:
            can_be_true = Possibility.UNKNOWN
            can_be_false = Possibility.UNKNOWN
            if left.constant is not UNKNOWN_VALUE and right.constant is not UNKNOWN_VALUE:
                comparisons = {
                    "==": left.constant == right.constant,
                    "!=": left.constant != right.constant,
                    "<": left.constant < right.constant,
                    "<=": left.constant <= right.constant,
                    ">": left.constant > right.constant,
                    ">=": left.constant >= right.constant,
                }
                value = comparisons[operator]
                can_be_true = (
                    Possibility.POSSIBLE if value else Possibility.IMPOSSIBLE
                )
                can_be_false = (
                    Possibility.IMPOSSIBLE if value else Possibility.POSSIBLE
                )
            elif self.is_parameter_compared_with_constant(left_node, right) or (
                self.is_parameter_compared_with_constant(right_node, left)
            ):
                can_be_true = Possibility.POSSIBLE
                can_be_false = Possibility.POSSIBLE
            return ExpressionResult(
                completes=operands_complete,
                outcomes=outcomes,
                can_be_true=can_be_true,
                can_be_false=can_be_false,
            )

        # Other primitive binary operators cannot themselves produce a JPAMB
        # outcome. Exceptions in nested operands have already been retained.
        return ExpressionResult(completes=operands_complete, outcomes=outcomes)

    def is_parameter_compared_with_constant(
        self, parameter_node: tree_sitter.Node, other: ExpressionResult
    ) -> bool:
        if parameter_node.type != "identifier" or other.constant is UNKNOWN_VALUE:
            return False
        parameter_type = self.context.parameters.get(parameter_node.text.decode())
        return parameter_type in {"byte", "short", "int", "long", "boolean"}

    def refine(self, node: tree_sitter.Node, value: bool, facts: Facts) -> Facts:
        """Learn the first useful path fact: ``name == 0`` or ``name != 0``."""
        if node.type == "parenthesized_expression" and node.named_children:
            return self.refine(node.named_children[0], value, facts)
        if node.type != "binary_expression":
            return facts

        left = node.child_by_field_name("left")
        operator = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if left is None or operator is None or right is None:
            return facts

        if left.type == "identifier" and parse_integer_literal(right) == 0:
            name = left.text.decode()
        elif right.type == "identifier" and parse_integer_literal(left) == 0:
            name = right.text.decode()
        else:
            return facts

        operator_text = operator.text.decode()
        if operator_text not in {"==", "!="}:
            return facts
        is_zero = value == (operator_text == "==")
        if is_zero:
            return Facts(facts.zero | {name}, facts.nonzero - {name})
        return Facts(facts.zero - {name}, facts.nonzero | {name})

    def statement(self, node: tree_sitter.Node, facts: Facts) -> FlowResult:
        """Analyze a statement, recursively combining child summaries."""
        if node.type == "block":
            result = FlowResult(facts=facts)
            for child in node.named_children:
                child_result = self.statement(child, result.facts)
                result.outcomes = merge_outcomes(
                    result.outcomes, child_result.outcomes, result.continues
                )
                result.returns = either(
                    result.returns, both(result.continues, child_result.returns)
                )
                result.continues = both(result.continues, child_result.continues)
                result.facts = child_result.facts
            return result

        if node.type == "return_statement":
            if not node.named_children:
                return FlowResult(
                    continues=Possibility.IMPOSSIBLE,
                    returns=Possibility.POSSIBLE,
                    facts=facts,
                )
            expression = self.expression(node.named_children[0], facts)
            return FlowResult(
                continues=Possibility.IMPOSSIBLE,
                returns=expression.completes,
                outcomes=expression.outcomes,
                facts=facts,
            )

        if node.type == "assert_statement" and node.named_children:
            condition_node = node.named_children[0]
            condition = self.expression(condition_node, facts)
            outcomes = dict(condition.outcomes)
            outcomes["assertion error"] = either(
                outcomes["assertion error"],
                both(condition.completes, condition.can_be_false),
            )
            return FlowResult(
                continues=both(condition.completes, condition.can_be_true),
                outcomes=outcomes,
                facts=self.refine(condition_node, True, facts),
            )

        if node.type == "if_statement":
            return self.if_statement(node, facts)

        if node.type == "empty_statement":
            return FlowResult(facts=facts)

        return self.unknown_statement()

    def if_statement(self, node: tree_sitter.Node, facts: Facts) -> FlowResult:
        condition_node = node.child_by_field_name("condition")
        consequence = node.child_by_field_name("consequence")
        alternative = node.child_by_field_name("alternative")
        if condition_node is None or consequence is None:
            return self.unknown_statement()

        condition = self.expression(condition_node, facts)
        true_reachable = both(condition.completes, condition.can_be_true)
        false_reachable = both(condition.completes, condition.can_be_false)
        true_result = self.statement(
            consequence, self.refine(condition_node, True, facts)
        )
        false_result = (
            self.statement(alternative, self.refine(condition_node, False, facts))
            if alternative is not None
            else FlowResult(facts=self.refine(condition_node, False, facts))
        )
        outcomes = merge_outcomes(
            condition.outcomes, true_result.outcomes, true_reachable
        )
        outcomes = merge_outcomes(outcomes, false_result.outcomes, false_reachable)

        continuing_facts: list[Facts] = []
        if both(true_reachable, true_result.continues) != Possibility.IMPOSSIBLE:
            continuing_facts.append(true_result.facts)
        if both(false_reachable, false_result.continues) != Possibility.IMPOSSIBLE:
            continuing_facts.append(false_result.facts)
        merged_facts = continuing_facts[0] if continuing_facts else Facts()
        for branch_facts in continuing_facts[1:]:
            merged_facts = Facts(
                merged_facts.zero & branch_facts.zero,
                merged_facts.nonzero & branch_facts.nonzero,
            )

        return FlowResult(
            continues=either(
                both(true_reachable, true_result.continues),
                both(false_reachable, false_result.continues),
            ),
            returns=either(
                both(true_reachable, true_result.returns),
                both(false_reachable, false_result.returns),
            ),
            outcomes=outcomes,
            facts=merged_facts,
        )

    def unknown_statement(self) -> FlowResult:
        """Unsupported syntax stays uncertain instead of becoming a false proof."""
        return FlowResult(
            continues=Possibility.UNKNOWN,
            returns=Possibility.UNKNOWN,
            outcomes=unknown_outcomes(),
            facts=Facts(),
        )

    def analyze(self) -> dict[str, str]:
        flow = self.statement(self.context.body, Facts())
        evidence = dict(flow.outcomes)
        evidence["ok"] = either(flow.continues, flow.returns)
        labels = {
            Possibility.IMPOSSIBLE: "0%",
            Possibility.UNKNOWN: "50%",
            Possibility.POSSIBLE: "100%",
        }
        return {outcome: labels[evidence[outcome]] for outcome in OUTCOMES}


def analyze(context: MethodContext) -> dict[str, str]:
    return RecursiveAnalyzer(context).analyze()


def main():
    # Parse command line arguments.
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("command", help="Either 'info' or a method name.")
    args = arg_parser.parse_args()

    # If 'info' is given, then just print analyzer info and exit.
    if args.command == "info":
        print(PROG_NAME)
        print(VERSION)
        print(GROUP_NAME)
        print(TAGS)
        print(INFO)
        return

    context = init_context(args.command)

    # Analyze method.
    predictions = blind_guess() if context is None else analyze(context)

    # Print final predictions.
    for outcome in OUTCOMES:
        print(f"{outcome};{predictions[outcome]}")


if __name__ == "__main__":
    main()
