"""All user interaction: arguments, prompts, and printing. Nothing else in plaintest prints.

    plaintest build DESCRIPTIONS --code FILE...   descriptions → Specs → tests → Report
    plaintest generate SPECS                      Specs (after you edit them) → tests → Report
    plaintest verify SPECS                        the Report for the tests as they are

Add --interactive to build or generate to make the judgment calls yourself.
Exits 1 if any test failed or any test disagrees with the code; pending is fine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import llm as llm_
from .models import Check, Draft, Report, Spec, Status, load_specs
from .pipeline import build, generate_and_verify
from .review import BatchReviewer
from .targets import PytestTarget
from .verify import verify

SYMBOLS = {Status.PASS: "✓", Status.FAIL: "✗", Status.DISAGREES: "≠", Status.PENDING: "…"}


def main(argv: list[str] | None = None, llm: llm_.LLM | None = None) -> int:
    """Run the CLI and return the exit code. `llm` is for tests; normally it comes from --llm."""
    args = _parser().parse_args(argv)
    target = PytestTarget()
    reviewer = InteractiveReviewer() if getattr(args, "interactive", False) else BatchReviewer()
    try:
        if args.command == "build":
            project = Path(args.project or args.descriptions.parent)
            descriptions = [line.strip() for line in args.descriptions.read_text().splitlines()
                            if line.strip() and not line.startswith("#")]
            llm = llm or llm_.from_spec(args.llm)
            specs, report = build(descriptions, args.code, project, llm, target, reviewer)
            print(f"wrote {len(specs)} Specs to {project / 'specs'}")
        else:
            project = Path(args.project or args.specs.parent)
            specs = load_specs(args.specs)
            if args.command == "generate":
                report = generate_and_verify(specs, project, llm or llm_.from_spec(args.llm),
                                             target, reviewer)
            else:  # verify: no model needed until faithful and catches are built
                report = verify(specs, project, target, llm or _optional_llm(args.llm))
    except llm_.LLMError as e:
        print(f"plaintest: {e}", file=sys.stderr)
        return 2
    print(format_report(report))
    return 0 if report.ok else 1


def format_report(report: Report) -> str:
    """One line per Check, with the reasons for anything not passing underneath."""
    width = max((len(c.check_id) for c in report.checks), default=0) + 3
    lines = []
    for c in report.checks:
        cells = "   ".join(f"{name} {SYMBOLS[f.status]}" for name, f in c.findings().items())
        lines.append(f"{c.check_id:<{width}}{cells}")
        for name, f in c.findings().items():
            if f.status in (Status.FAIL, Status.DISAGREES):
                lines.append(f"  ↳ {name}: {_first_lines(f.detail)}")
    lines.append(f"\n{SYMBOLS[Status.PASS]} pass   {SYMBOLS[Status.FAIL]} fail   "
                 f"{SYMBOLS[Status.DISAGREES]} disagrees with the code   {SYMBOLS[Status.PENDING]} pending")
    return "\n".join(lines)


class InteractiveReviewer:
    """The Reviewer for --interactive: a person answers, edits, and decides."""

    def answer(self, draft: Draft) -> dict[str, str]:
        if not draft.questions:
            return {}
        print(f"\n{draft.spec.id}  ({draft.spec.subject})")
        answers = {}
        for q in draft.questions:
            print(f"  ? {q.text}")
            reply = input(f"    [{q.suggestion}] ").strip()
            answers[q.text] = reply or q.suggestion
        return answers

    def review(self, spec: Spec) -> Spec:
        while True:
            print(f"\n{spec.id}  ({spec.subject})")
            for i, c in enumerate(spec.checks, 1):
                print(f"  {i}. {c.id}\n     given {c.given}\n     when  {c.when}\n     then  {c.then}")
            cmd = input("  Enter to accept · e N edit · d N delete · a add: ").strip().split()
            if not cmd:
                return spec
            if cmd[0] == "a":
                spec.checks.append(_ask_check(f"{spec.id}.check-{len(spec.checks) + 1}"))
            elif cmd[0] in ("e", "d") and len(cmd) == 2 and cmd[1].isdigit() and 0 < int(cmd[1]) <= len(spec.checks):
                i = int(cmd[1]) - 1
                if cmd[0] == "d":
                    del spec.checks[i]
                else:
                    spec.checks[i] = _ask_check(spec.checks[i].id, spec.checks[i])

    def resolve(self, report: Report, specs: list[Spec]) -> list[Spec]:
        disagreements = report.with_status(Status.DISAGREES)
        if not disagreements:
            return []
        by_check = {c.id: (s, c) for s in specs for c in s.checks}
        changed: dict[str, Spec] = {}
        for check_id, details in disagreements.items():
            spec, check = by_check[check_id]
            print(f"\n{check_id}: the test and the code disagree.\n  {_first_lines(details[0])}")
            if input("  Is the Check wrong (c) or the code (Enter)? ").strip() == "c":
                i = spec.checks.index(check)
                spec.checks[i] = _ask_check(check.id, check)
                changed[spec.id] = spec
        return list(changed.values())


def _ask_check(check_id: str, old: Check | None = None) -> Check:
    def ask(field: str) -> str:
        default = getattr(old, field) if old else ""
        return input(f"     {field:<5} [{default}] ").strip() or default
    return Check(check_id, ask("given"), ask("when"), ask("then"))


def _optional_llm(spec: str | None) -> llm_.LLM | None:
    try:
        return llm_.from_spec(spec)
    except llm_.LLMError:
        return None


def _first_lines(text: str, n: int = 3) -> str:
    return "\n    ".join(text.strip().splitlines()[:n])


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="plaintest", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="descriptions → Specs → tests → Report")
    b.add_argument("descriptions", type=Path, help="a text file, one description per line")
    b.add_argument("--code", type=Path, nargs="+", default=[], help="the code under test")

    g = sub.add_parser("generate", help="Specs → tests → Report")
    v = sub.add_parser("verify", help="Report for the tests as they are")
    for s in (g, v):
        s.add_argument("specs", type=Path, help="the folder of Spec files")
    for s in (b, g):
        s.add_argument("--interactive", action="store_true", help="make the judgment calls yourself")
    for s in (b, g, v):
        s.add_argument("--project", type=Path, help="project root (default: next to the input)")
        s.add_argument("--llm", help="provider:model (default: $PLAINTEST_LLM)")
    return p


if __name__ == "__main__":
    sys.exit(main())
