#!/usr/bin/env python3

import argparse
import re
import sys
import tree_sitter
import tree_sitter_java
from pathlib import Path
from enum import IntEnum
from dataclasses import dataclass, field

# GLOBAL VARIABLES
PROG_NAME = "Syntactic Analyzer"
VERSION = "1.0"
GROUP_NAME = "My Group"
TAGS = "syntactic,python"
INFO = "macos"

TS_JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())
UNKNOWN_VALUE = object()
OUTCOMES = (
    "ok",
    "divide by zero",
    "assertion error",
    "out of bounds",
    "null pointer",
    "*",
)


# A class to hold relevant info on a given method.
class MethodContext:
    type: str
    name: str
    body: tree_sitter.Node

    def __init__(self, type: str, name: str, body: tree_sitter.Node):
        self.type = type
        self.name = name
        self.body = body
        pass

    def name(self) -> str:
        return self.name

    def body(self) -> tree_sitter.Node:
        return self.body


class Possibility(IntEnum):
    """Evidence that an outcome can happen."""
    IMPOSSIBLE = 0
    POSSIBLE = 1
    UNKNOWN = 2


@dataclass
class AbstractValue:
    """An abstract representation of an expression value."""
    exact_value: object = UNKNOWN_VALUE
    may_be_zero: bool = True
    may_be_nonzero: bool = True
    may_be_none: bool = True


@dataclass()
class ExpressionResult:
    """A representation of an expression result."""
    can_terminate: bool = True
    outcomes: dict[str, Possibility] = field(default_factory=dict[str, Possibility])
    value: AbstractValue = field(default_factory=AbstractValue)
    analysis_incomplete: bool = True


class SyntacticAnalyzer:

    def __init__(self, context: MethodContext):
        self.context = context
        self.predictions = blind_guess()
        pass

    def predictions(self) -> dict[str, str]:
        return self.predictions

    def analyze(self) -> None:
        self.block_statement(self.context.body)
        return

    def assert_statement(self, node: tree_sitter.Node) -> None:
        # (assert_statement (_))
        # TODO: support nested expressions

        if node.named_children[0].type == "false":
            # Trivial: (assert_statement (false))
            self.predictions['ok'] = "0%"
            self.predictions['divide by zero'] = "0%"
            self.predictions['assertion error'] = "100%"
            self.predictions['out of bounds'] = "0%"
            self.predictions['null pointer'] = "0%"
            self.predictions['*'] = "0%"
            return

        if node.named_children[0].type == "true":
            # Trivial: (assert_statement (true))
            self.predictions['ok'] = "100%"
            self.predictions['divide by zero'] = "0%"
            self.predictions['assertion error'] = "0%"
            self.predictions['out of bounds'] = "0%"
            self.predictions['null pointer'] = "0%"
            self.predictions['*'] = "0%"
            return

        if node.named_children[0].type == "identifier":
            # Trivial: (assert_statement (identifier))
            self.predictions['ok'] = "assert-is-true"
            self.predictions['divide by zero'] = "0%"
            self.predictions['assertion error'] = "assert-is-false"
            self.predictions['out of bounds'] = "0%"
            self.predictions['null pointer'] = "0%"
            self.predictions['*'] = "0%"
            return

        if node.named_children[0].type == "binary_expression":
            # (assert_statement (binary_expression (_)))
            binary_expression = node.named_children[0]

            # TODO: support nested expressions
            if binary_expression.child_by_field_name("right").type == "binary_expression":
                return

            binary_expression = node.named_children[0]
            operator = binary_expression.named_children[1].text.decode('utf-8')
            if operator not in ["/", "%"]:
                self.predictions['ok'] = "assert-is-true"
                self.predictions['divide by zero'] = "0%"
                self.predictions['assertion error'] = "assert-is-false"
                self.predictions['out of bounds'] = "0%"
                self.predictions['null pointer'] = "0%"
                self.predictions['*'] = "0%"
                return

        return

    def return_statement(self, node: tree_sitter.Node) -> None:
        # (return_statement (_))
        # TODO: support nested expressions

        if node.type != "return_statement":
            print(f"Error when analyzing: {node} -- return_statement()", file=sys.stderr)
            return

        if len(node.named_children) == 0:
            # Trivial: (return_statement)
            self.predictions['ok'] = "100%"
            self.predictions['divide by zero'] = "0%"
            self.predictions['assertion error'] = "0%"
            self.predictions['out of bounds'] = "0%"
            self.predictions['null pointer'] = "0%"
            self.predictions['*'] = "0%"
            return

        if len(node.named_children) == 1:
            # (return_statement (_))
            child = node.named_children[0]

            if "literal" in child.type:
                # (return_statement (*_literal)
                self.predictions['ok'] = "100%"
                self.predictions['divide by zero'] = "0%"
                self.predictions['assertion error'] = "0%"
                self.predictions['out of bounds'] = "0%"
                self.predictions['null pointer'] = "0%"
                self.predictions['*'] = "0%"
                return

            if child.type == "binary_expression":
                operator = child.children[1].text.decode('utf-8')

                if operator not in ["/", "%"]:
                    # Trivial: (return_statement (<non-div-bin-expression>))
                    self.predictions['ok'] = "100%"
                    self.predictions['divide by zero'] = "0%"
                    self.predictions['assertion error'] = "0%"
                    self.predictions['out of bounds'] = "0%"
                    self.predictions['null pointer'] = "0%"
                    self.predictions['*'] = "0%"
                    return

                if operator in ["/", "%"]:
                    right_expression = child.children[2]
                    if right_expression.text.decode('utf-8') == "0":
                        # Trivial: return <?> / 0;
                        self.predictions['ok'] = "0%"
                        self.predictions['divide by zero'] = "100%"
                        self.predictions['assertion error'] = "0%"
                        self.predictions['out of bounds'] = "0%"
                        self.predictions['null pointer'] = "0%"
                        self.predictions['*'] = "0%"
                        return

                    if right_expression.type == "identifier":
                        # Trivial: return <?> / <I>;
                        self.predictions['ok'] = "right-id-non-zero"
                        self.predictions['divide by zero'] = "right-id-zero"
                        self.predictions['assertion error'] = "0%"
                        self.predictions['out of bounds'] = "0%"
                        self.predictions['null pointer'] = "0%"
                        self.predictions['*'] = "0%"
                        return

        return

    def expression(self, node: tree_sitter.Node) -> ExpressionResult:
        expr_result = ExpressionResult()

        if node.type == "decimal_integer_literal":
            value = int(node.text.decode('utf-8'))
            expr_result.can_terminate = True
            expr_result.value.exact_value = value
            expr_result.value.may_be_zero = (value == 0)
            expr_result.value.may_be_nonzero = (value != 0)
            expr_result.value.may_be_none = False
            return expr_result

        if node.type == "identifier":
            expr_result.can_terminate = True
            return expr_result

        if node.type == "binary_expression":
            return self.binary_expression(node)

        return expr_result

    def binary_expression(self, node: tree_sitter.Node) -> ExpressionResult:
        # (binary_expression left: (_) right: (_))
        expr_result = ExpressionResult()

        if node.type != "binary_expression":
            print(f"Error when analyzing: {node} -- binary_expression()", file=sys.stderr)
            return expr_result

        left_node = node.child_by_field_name('left')
        operator = node.child_by_field_name('operator')
        right_node = node.child_by_field_name('right')

        left_result = self.expression(left_node)

        if not left_result.can_terminate:
            return left_result

        right_result = self.expression(right_node)



        return expr_result

    def block_statement(self, node: tree_sitter.Node) -> None:
        """Recursively analyze block statement and calculate predictions."""

        if node.type != "block":
            print(f"Error when analyzing: {node} -- block_statement()", file=sys.stderr)
            return

        if len(node.named_children) == 0:
            # Trivial: (block)
            self.predictions['ok'] = "100%"
            self.predictions['divide by zero'] = "0%"
            self.predictions['assertion error'] = "0%"
            self.predictions['out of bounds'] = "0%"
            self.predictions['null pointer'] = "0%"
            self.predictions['*'] = "0%"
            return

        if len(node.named_children) == 1:
            # (block (_))
            child = node.named_children[0]

            if child.type == "assert_statement":
                self.assert_statement(child)
                return

            if child.type == "return_statement":
                self.return_statement(child)
                return

            # if child.type == "binary_expression":
            #     self.binary_expression(child)
            #     return

        return


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


def query_captures(query: str, context: MethodContext) -> dict[str, list]:
    """Get captures/results of a tree-sitter query."""
    q = tree_sitter.Query(TS_JAVA_LANGUAGE, query)
    return tree_sitter.QueryCursor(q).captures(context.body)


def init_context(command: str) -> MethodContext:
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
            body: (block) @method-body
        )
        """
    )
    query_cursor = tree_sitter.QueryCursor(query)
    captures = query_cursor.captures(tree.root_node)

    if len(captures['method-name']) != 1:
        print(f"Expected exactly one method name: {captures['method-name']}", file=sys.stderr)
        return None

    context = MethodContext(
        type=captures['method-type'][0].text.decode('utf-8'),
        name=captures['method-name'][0].text.decode('utf-8'),
        body=captures['method-body'][0]
    )

    # DEBUG
    print("-" * 50, file=sys.stderr)
    print(f"Method: {context.type} {context.name}", file=sys.stderr)
    print("-" * 50, file=sys.stderr)
    print(context.body, file=sys.stderr)

    return context


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
    analyzer = SyntacticAnalyzer(context)
    analyzer.analyze()

    # Print final predictions.
    for outcome in OUTCOMES:
        print(f"{outcome};{analyzer.predictions[outcome]}")


if __name__ == "__main__":
    main()
