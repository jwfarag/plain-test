"""generate: one Spec -> the source of its test file, at least one tagged test per Check.

The Check says what should happen; the code is read only to learn how to call it.
When a round of verify finds broken or weak tests, generate runs again with the previous
file and what was wrong with it. Tests that disagree with the existing code are never sent
back here: weakening them to pass would hide either a wrong Check or a real bug.
"""

from __future__ import annotations

from dataclasses import asdict

import yaml

from . import llm as llm_
from .models import Spec
from .targets import Target


def generate(
    spec: Spec,
    code: str,
    target: Target,
    llm: llm_.LLM,
    feedback: dict[str, list[str]] | None = None,
    previous: str | None = None,
) -> str:
    """Return the full test file for `spec`.

    `feedback` maps Check IDs to what was wrong with their tests last round;
    `previous` is last round's file, so tests that were fine can stay as they were.
    """
    return llm_.ask_code(
        llm, "generate",
        language=target.language,
        framework=target.name,
        notes=target.notes,
        tag=target.tag("<check id>"),
        spec=yaml.safe_dump(asdict(spec), sort_keys=False, width=100),
        code=code or "(no code yet: write the tests against the subject as the Spec names it)",
        feedback=_feedback(feedback, previous),
    )


def _feedback(feedback: dict[str, list[str]] | None, previous: str | None) -> str:
    if not feedback:
        return "None. This is the first version of the file."
    lines = ["Rewrite the tests for these Checks. Keep every other test exactly as it is.", ""]
    for check_id, problems in feedback.items():
        lines.append(f"- {check_id}:")
        lines += [f"    {p}" for p in problems]
    if previous:
        lines += ["", "Previous file:", "```", previous.rstrip(), "```"]
    return "\n".join(lines)
