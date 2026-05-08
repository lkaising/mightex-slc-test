"""Shared terminal UI helpers for the project's interactive scripts.

Internal to ``scripts/``; not part of the public package API.
"""

from __future__ import annotations

import sys


class C:
    """ANSI color codes (no-op on non-TTY)."""

    if sys.stdout.isatty():
        BOLD = "\033[1m"
        DIM = "\033[2m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        RED = "\033[31m"
        CYAN = "\033[36m"
        RESET = "\033[0m"
    else:
        BOLD = DIM = GREEN = YELLOW = RED = CYAN = RESET = ""


def ok(text: str) -> None:
    """Print a success line (green check)."""
    print(f"  {C.GREEN}✓{C.RESET} {text}")


def fail(text: str) -> None:
    """Print a failure line (red cross)."""
    print(f"  {C.RED}✗{C.RESET} {text}")


def warn(text: str) -> None:
    """Print a warning line (yellow ⚠)."""
    print(f"  {C.YELLOW}⚠{C.RESET} {text}")


def info(text: str) -> None:
    """Print a dim status line (no marker)."""
    print(f"  {C.DIM}{text}{C.RESET}")


def banner(text: str) -> None:
    print(f"\n{C.BOLD}{'═' * 60}")
    print(f"  {text}")
    print(f"{'═' * 60}{C.RESET}")


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {text}{suffix}: ").strip()
    except EOFError:
        return default
    return val if val else default


def prompt_int(text: str, default: int | None = None) -> int | None:
    """Prompt for an integer. Returns None on empty input with no default."""
    raw = prompt(text, str(default) if default is not None else "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        fail(f"Invalid number: {raw}")
        return None


def confirm(text: str) -> bool:
    return prompt(f"{text} (y/n)", "n").lower().startswith("y")
