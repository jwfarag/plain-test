"""The Target interface: everything plaintest needs to know about one language and test framework.

A Target reads the code under test, says how to tag a test with a Check ID, finds which
tests cover which Checks, and runs them. Nothing outside `targets/` knows the language.
To add a language, implement this Protocol in a new module; no other code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from ..models import Test


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"  # an assertion did not hold: the test ran and disagreed with the code
    ERROR = "error"  # the test is broken: it could not be collected, set up, or run to an assertion


@dataclass
class Run:
    outcome: Outcome
    detail: str = ""  # failure text, short enough to show a person or feed back to generate


class Target(Protocol):
    name: str  # "pytest"
    language: str  # "Python"
    notes: str  # how tests are run and how they should import the code; goes into the generate prompt

    def read_code(self, project: Path, paths: list[Path]) -> str:
        """Source of the given files, each headed by its path relative to `project`."""

    def subject_exists(self, project: Path, subject: str) -> bool:
        """Is the thing this Spec is about already written?"""

    def subject_file(self, project: Path, subject: str) -> Path:
        """The file that holds (or will hold) the subject."""

    def test_file(self, project: Path, spec_id: str) -> Path:
        """Where the generated tests for one Spec live."""

    def tag(self, check_id: str) -> str:
        """The line that tags a test with a Check, e.g. a decorator."""

    def find_tests(self, project: Path) -> list[Test]:
        """Every tagged test in the project, one entry per (test, Check) pair. Reads, never runs."""

    def run(self, project: Path, tests: list[Test]) -> dict[str, Run]:
        """Run the tests and return each one's Run, keyed by `Test.name`."""
