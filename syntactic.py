#!/usr/bin/env python3

import argparse
import sys

PROG_NAME = "Syntactic Analyzer"
VERSION = "1.0"
GROUP_NAME = "My Group"
TAGS = "syntactic,python"
INFO = "macos"


def parse_arguments():
    arg_parser = argparse.ArgumentParser(
        prog="Syntactic Analyzer",
        description="An analyzer for syntactic analysis.",
        add_help=True,
    )
    arg_parser.add_argument("commands", help="Either 'info' or a method")
    args = arg_parser.parse_args()
    return args


def main():
    args = parse_arguments()
    if args.commands == "info":
        print(PROG_NAME)
        print(VERSION)
        print(GROUP_NAME)
        print(TAGS)
        print(INFO)
        sys.exit(0)

    # Make predictions (improve these by looking at the Java code!)
    ok_chance = "yes"
    divide_by_zero_chance = "no"
    assertion_error_chance = "50%"
    out_of_bounds_chance = "-1.23"
    null_pointer_chance = "maybe"
    infinite_loop_chance = "yes"

    # Output predictions for all 6 possible outcomes
    print(f"ok;{ok_chance}")
    print(f"divide by zero;{divide_by_zero_chance}")
    print(f"assertion error;{assertion_error_chance}")
    print(f"out of bounds;{out_of_bounds_chance}")
    print(f"null pointer;{null_pointer_chance}")
    print(f"*;{infinite_loop_chance}")


if __name__ == "__main__":
    main()
