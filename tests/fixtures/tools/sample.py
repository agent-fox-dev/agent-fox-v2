import json  # noqa: F401
import logging  # noqa: F401
import os  # noqa: F401
import sys  # noqa: F401
from pathlib import Path  # noqa: F401

GLOBAL_CONST = 42


def foo(x: int) -> int:
    """A simple function."""
    return x + 1


def bar(y: str, z: str) -> str:
    """Another function."""
    if y:
        return y
    return z


class MyClass:
    """A sample class."""

    def __init__(self, value: int) -> None:
        self.value = value

    def method(self) -> int:
        return self.value
