"""Type aliases used across the package."""

from __future__ import annotations

from typing import TypeAlias

#: Select options: ``(value, label)`` pairs.
Choices: TypeAlias = list[tuple[str, str]]

__all__ = ["Choices"]
