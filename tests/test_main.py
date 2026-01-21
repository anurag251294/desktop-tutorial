"""Tests for the main module."""

import sys
sys.path.insert(0, '../src')

from main import greet, add


def test_greet():
    """Test the greet function."""
    result = greet("Alice")
    assert result == "Hello, Alice! Welcome to the demo repository."


def test_add():
    """Test the add function."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


if __name__ == "__main__":
    test_greet()
    test_add()
    print("All tests passed!")
