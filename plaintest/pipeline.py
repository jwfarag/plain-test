"""The one place that knows the order of the stages and the retry loop.

    descriptions → clarify → Specs → generate → tests → verify → Report
                                        ↑                 │
                                        └── weak tests ───┘

Stages take data and return data; this module is the only one that writes files
(Specs and test files). It never prints or prompts: the Reviewer passed in makes the calls.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .clarify import clarify
from .generate import generate
from .llm import LLM
from .models import Report, Spec, Status, save_spec
from .review import Reviewer
from .targets import Target
from .verify import verify

CLARIFY_ROUNDS = 3  # how many times a person's answers can send a description back to clarify
GENERATE_ROUNDS = 2  # how many times weak tests go back to generate


def build(descriptions: list[str], code_paths: list[Path], project: Path,
          llm: LLM, target: Target, reviewer: Reviewer) -> tuple[list[Spec], Report]:
    """descriptions → Specs (written to `<project>/specs/`) → tests → Report."""
    code = target.read_code(project, code_paths)
    specs: list[Spec] = []
    for description in descriptions:
        taken = {s.id for s in specs}
        specs += [reviewer.review(s) for s in _clarify_one(description, code, llm, reviewer, taken)]
    for spec in specs:
        save_spec(spec, spec_path(project, spec))
    return specs, generate_and_verify(specs, project, llm, target, reviewer)


def generate_and_verify(specs: list[Spec], project: Path, llm: LLM, target: Target,
                        reviewer: Reviewer) -> Report:
    """Specs → tests → Report, then let the reviewer close gaps until they stop changing Specs."""
    report = _generate_until_strong(specs, specs, project, llm, target)
    while changed := reviewer.resolve(report, specs):
        by_id = {s.id: s for s in changed}
        specs = [by_id.get(s.id, s) for s in specs]
        for spec in changed:
            save_spec(spec, spec_path(project, spec))
        report = _generate_until_strong(changed, specs, project, llm, target)
    return report


def spec_path(project: Path, spec: Spec) -> Path:
    return Path(project) / "specs" / f"{spec.id}.yaml"


def _clarify_one(description: str, code: str, llm: LLM, reviewer: Reviewer,
                 taken: set[str]) -> list[Spec]:
    """Clarify one description. If a person answers differently than suggested, clarify again."""
    decided: dict[str, str] = {}
    drafts = clarify(description, code, llm, taken=taken)
    for _ in range(CLARIFY_ROUNDS):
        answers: dict[str, str] = {}
        for draft in drafts:
            open_ = [q for q in draft.questions if q.text not in decided]  # never ask twice
            if open_:
                answers |= reviewer.answer(replace(draft, questions=open_))
        overridden = any(answers.get(q.text, q.suggestion) != q.suggestion
                         for d in drafts for q in d.questions if q.text not in decided)
        decided |= answers
        if not overridden:
            break
        drafts = clarify(description, code, llm, decided, taken)
    return [d.settle(decided) for d in drafts]


def _generate_until_strong(to_generate: list[Spec], specs: list[Spec], project: Path,
                           llm: LLM, target: Target) -> Report:
    """Generate tests, verify every Spec, and send FAIL-ed tests back, a bounded number of times."""
    feedback: dict[str, list[str]] = {}
    for round_ in range(GENERATE_ROUNDS + 1):
        for spec in to_generate:
            path = target.test_file(project, spec.id)
            mine = {c.id: feedback[c.id] for c in spec.checks if c.id in feedback}
            code_path = target.subject_file(project, spec.subject)
            code = target.read_code(project, [code_path]) if code_path.exists() else ""
            previous = path.read_text() if mine and path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(generate(spec, code, target, llm, mine, previous))
        report = verify(specs, project, target, llm)
        feedback = report.with_status(Status.FAIL)  # never DISAGREES: those wait for a person
        if not feedback or round_ == GENERATE_ROUNDS:
            return report
        to_generate = [s for s in specs if any(c.id in feedback for c in s.checks)]
    return report
