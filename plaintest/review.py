"""The Reviewer: whoever makes the judgment calls. The one difference between the two modes.

The pipeline asks the reviewer at three points:
    answer   clarify guessed at some questions; which guesses does a person want to decide?
    review   here is a Spec; add, remove, or reword Checks until it's right
    resolve  here is the Report; which Specs should change to close its gaps?

BatchReviewer (here) decides nothing: every guess stays and is recorded as an assumption,
and the Report waits for a person. InteractiveReviewer lives in cli.py, because it prompts.
"""

from __future__ import annotations

from typing import Protocol

from .models import Draft, Report, Spec


class Reviewer(Protocol):
    def answer(self, draft: Draft) -> dict[str, str]:
        """Answers a person gave, keyed by question text. A question left out stays a guess."""

    def review(self, spec: Spec) -> Spec:
        """The Spec to keep, after any edits to its Checks."""

    def resolve(self, report: Report, specs: list[Spec]) -> list[Spec]:
        """Specs a person changed to close gaps in the Report. They get regenerated."""


class BatchReviewer:
    def answer(self, draft: Draft) -> dict[str, str]:
        return {}

    def review(self, spec: Spec) -> Spec:
        return spec

    def resolve(self, report: Report, specs: list[Spec]) -> list[Spec]:
        return []
