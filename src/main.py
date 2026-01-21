"""
Demo Application
A simple example to demonstrate project structure.
"""


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"Hello, {name}! Welcome to the demo repository."


def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def main():
    """Main entry point."""
    print(greet("Developer"))
    print(f"2 + 3 = {add(2, 3)}")


if __name__ == "__main__":
    main()
