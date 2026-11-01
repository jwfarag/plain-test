"""Targets: the only language-specific code. See base.py for the interface."""

from .base import Outcome, Run, Target
from .pytest_target import PytestTarget

__all__ = ["Outcome", "Run", "Target", "PytestTarget"]
