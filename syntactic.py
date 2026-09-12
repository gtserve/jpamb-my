#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path

import tree_sitter
import tree_sitter_java

PROG_NAME = "Syntactic Analyzer"
VERSION = "1.0"
GROUP_NAME = "My Group"
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


def is_direct_assert_false(method_body: tree_sitter.Node) -> bool:
    """Recognize a method whose only statement is ``assert false;``."""

    statements = method_body.named_children
    if len(statements) != 1 or statements[0].type != "assert_statement":
        return False

    # In the Java grammar, the expression after ``assert`` is the second
    # child.  Checking its node type avoids brittle string matching.
    return any(child.type == "false" for child in statements[0].named_children)


def analyze(command: str) -> dict[str, str]:
    """Analyze method and return predictions, one for each outcome."""

    class_name, method_name = parse_target(command)

    # Read Java file.
    source_file = Path("cases", *class_name.split(".")).with_suffix(".java")
    try:
        source = source_file.read_bytes()
    except OSError as error:
        print(f"Could not read {source_file}: {error}", file=sys.stderr)
        return blind_guess()

    # Initialize Tree-sitter object.
    language = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(language)
    tree = parser.parse(source)

    # Find target method in syntax tree.
    query = tree_sitter.Query(
        language,
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
        return blind_guess()

    method_type = captures['method-type'][0].text.decode('utf-8')
    method_name = captures['method-name'][0].text.decode('utf-8')
    method_body = captures['method-body'][0]

    # DEBUG
    print("-" * 50)
    print(f"Method: {method_type} {method_name}")
    print("-" * 50)
    print(method_body)

    if is_direct_assert_false(method_body):
        # This is the first proved pattern, demonstrated by
        # jpamb.cases.Simple.assertFalse:()V.
        predictions = dict.fromkeys(OUTCOMES, "0%")
        predictions["assertion error"] = "100%"
        return predictions

    return blind_guess()


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

    # Analyze method.
    predictions = analyze(args.command)

    # Print final predictions.
    for outcome in OUTCOMES:
        print(f"{outcome};{predictions[outcome]}")


if __name__ == "__main__":
    main()
