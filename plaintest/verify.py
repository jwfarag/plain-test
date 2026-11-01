"""verify: Specs + the tests in the project -> a Report answering four questions per Check.

    linked    is there a test tagged with this Check?
    runs      does it run and pass?
    faithful  does it test what the Check says?
    catches   would it catch a bug?

Each question catches a different failure: missing tests, broken tests, tests of the wrong
thing, and tests that pass no matter what. Anything that can't be answered yet is PENDING,
never FAIL. FAIL means the test is at fault and generate should try again; DISAGREES means
the test and the existing code disagree, and only a person can say which one is wrong.
"""

from __future__ import annotations

from pathlib import Path

from .llm import LLM
from .models import Check, CheckReport, Finding, Report, Spec, Status, Test
from .targets import Outcome, Run, Target


def verify(specs: list[Spec], project: Path, target: Target, llm: LLM | None) -> Report:
    """Find the tests, run them once, and answer the four questions for every Check."""
    wanted = {c.id for s in specs for c in s.checks}
    tests = [t for t in target.find_tests(project) if t.check_id in wanted]
    results = target.run(project, tests)

    reports = []
    for spec in specs:
        written = target.subject_exists(project, spec.subject)
        for check in spec.checks:
            mine = [t for t in tests if t.check_id == check.id]
            reports.append(CheckReport(
                check_id=check.id,
                linked=linked(mine),
                runs=runs(mine, results, written),
                faithful=faithful(check, mine, llm),
                catches=catches(check, spec, mine, project, target, llm),
            ))
    return Report(reports)


def linked(tests: list[Test]) -> Finding:
    """Is at least one test tagged with this Check?"""
    if not tests:
        return Finding(Status.FAIL, "no test is tagged with this Check")
    return Finding(Status.PASS, ", ".join(t.name for t in tests))


def runs(tests: list[Test], results: dict[str, Run], written: bool) -> Finding:
    """Do the tests run, and pass?

    A broken test (it errors before reaching an assertion) is always FAIL.
    A test whose assertion doesn't hold is PENDING if the subject isn't written yet,
    and DISAGREES if it is: the Check is wrong or the code has a bug.
    """
    if not tests:
        return Finding(Status.PENDING, "nothing to run")
    mine = [(t, results[t.name]) for t in tests]
    broken = [f"{t.name}\n{r.detail}" for t, r in mine if r.outcome is Outcome.ERROR]
    if broken:
        return Finding(Status.FAIL, "test is broken: " + "\n".join(broken))
    failed = [f"{t.name}\n{r.detail}" for t, r in mine if r.outcome is Outcome.FAILED]
    if failed and not written:
        return Finding(Status.PENDING, "fails as expected: the subject isn't written yet")
    if failed:
        return Finding(Status.DISAGREES, "the code does not do what the Check says: " + "\n".join(failed))
    return Finding(Status.PASS)


def faithful(check: Check, tests: list[Test], llm: LLM | None) -> Finding:
    """Does the test check what the Check says? (not built yet: always PENDING)

    How it will work: for each test, a model reads only the test's source, never the Check,
    and describes in plain English what it verifies (prompts/describe.md). A second call
    compares that description with the Check's given/when/then (prompts/judge.md) and
    returns faithful or not, with a reason. Reading the test blind is the point: a model
    shown the Check first will tend to see it in the test whether it's there or not.
    An unfaithful test is FAIL, and the judge's reason goes back to generate as feedback.
    """
    return Finding(Status.PENDING, "not built yet")


def catches(check: Check, spec: Spec, tests: list[Test], project: Path, target: Target,
            llm: LLM | None) -> Finding:
    """Would the test catch a bug? (not built yet: always PENDING)

    How it will work: given the Check and the subject's source, a model proposes the
    smallest code change that violates this Check (prompts/break.md) as a find/replace
    edit. The tool copies the project to a temporary folder, applies the edit there, and
    calls `target.run` on this Check's tests. If they now fail, the test catches the bug:
    PASS. If they still pass, it's FAIL, with the change as feedback for generate ("the
    test still passed after the floor was removed from apply_discount").
    It stays PENDING when the subject isn't written (there is nothing to break) or when
    `runs` didn't pass (a mutant only means something against a passing test).
    """
    return Finding(Status.PENDING, "not built yet")
