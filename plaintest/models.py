"""The vocabulary of plaintest as plain dataclasses, plus reading and writing Spec files.

    Description  a plain `str`, kept verbatim inside the Spec it produced
    Spec         one description scoped to one component (its subject), broken into Checks
    Check        one atomic, testable statement in given / when / then form
    Test         a generated test, tagged with the ID of the Check it covers
    Report       the verification status of every Check

Two working types exist only between stages and are never written to disk:
    Question     something clarify had to guess, with the answer it guessed
    Draft        a Spec from clarify plus the Questions behind it
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path

import yaml


# --- Specs -------------------------------------------------------------------


@dataclass
class Check:
    id: str
    given: str
    when: str
    then: str


@dataclass
class Spec:
    id: str
    subject: str  # e.g. "cart.py::Cart.apply_discount"; the Target knows how to resolve it
    description: str  # the user's words, verbatim
    checks: list[Check]
    assumptions: list[str] = field(default_factory=list)  # choices no person made


@dataclass
class Question:
    text: str  # "Are discounts fixed amounts or percentages?"
    suggestion: str  # phrased as a statement: "Discounts are fixed amounts, not percentages."


@dataclass
class Draft:
    """A Spec written with clarify's suggested answers already applied."""

    spec: Spec
    questions: list[Question] = field(default_factory=list)

    def settle(self, decided: dict[str, str]) -> Spec:
        """Turn the draft into a Spec. Every question nobody decided becomes an assumption."""
        guessed = [q.suggestion for q in self.questions if q.text not in decided]
        return replace(self.spec, assumptions=self.spec.assumptions + guessed)


def load_spec(path: Path) -> Spec:
    data = yaml.safe_load(Path(path).read_text())
    return Spec(
        id=data["id"],
        subject=data["subject"],
        description=data["description"],
        checks=[Check(**c) for c in data.get("checks") or []],
        assumptions=list(data.get("assumptions") or []),
    )


def save_spec(spec: Spec, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(asdict(spec), sort_keys=False, allow_unicode=True, width=100))


def load_specs(folder: Path) -> list[Spec]:
    return [load_spec(p) for p in sorted(Path(folder).glob("*.yaml"))]


# --- Tests -------------------------------------------------------------------


@dataclass
class Test:
    __test__ = False  # keep pytest from collecting this class

    check_id: str
    name: str  # the Target's ID for the test, e.g. a pytest node ID
    file: Path


# --- Reports -----------------------------------------------------------------


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"  # the test is at fault: send it back to generate
    DISAGREES = "disagrees"  # the test and the existing code disagree: only a person can say which is wrong
    PENDING = "pending"  # can't be checked yet (no code, no test, not built yet)


@dataclass
class Finding:
    status: Status
    detail: str = ""


@dataclass
class CheckReport:
    check_id: str
    linked: Finding  # is there a test tagged with this Check?
    runs: Finding  # does it run, and pass?
    faithful: Finding  # does it test what the Check says?
    catches: Finding  # would it catch a bug?

    def findings(self) -> dict[str, Finding]:
        return {"linked": self.linked, "runs": self.runs, "faithful": self.faithful, "catches": self.catches}


@dataclass
class Report:
    checks: list[CheckReport]

    def with_status(self, status: Status) -> dict[str, list[str]]:
        """Check ID -> details of every finding with this status."""
        out: dict[str, list[str]] = {}
        for c in self.checks:
            for name, f in c.findings().items():
                if f.status is status:
                    out.setdefault(c.check_id, []).append(f"{name}: {f.detail}")
        return out

    @property
    def ok(self) -> bool:
        """True when nothing failed and nothing disagrees. Pending is fine."""
        return not self.with_status(Status.FAIL) and not self.with_status(Status.DISAGREES)
