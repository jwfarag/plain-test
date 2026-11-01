"""clarify: one description + the code under test -> Drafts (Specs with the questions behind them).

clarify never leaves a gap. When something is ambiguous (an edge case, an expected value,
error behavior) it picks an answer, writes the Checks using that answer, and records a
Question with the answer as its suggestion. Whoever reviews decides what happens next:
batch keeps every suggestion as an assumption; a person can accept it or answer
differently, in which case clarify runs again with their answer.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from . import llm as llm_
from .models import Check, Draft, Question, Spec


def clarify(
    description: str,
    code: str,
    llm: llm_.LLM,
    decided: dict[str, str] | None = None,
    taken: Iterable[str] = (),
) -> list[Draft]:
    """Split one description into one Draft per component it touches.

    `decided` holds answers a person already gave (question -> answer); they are followed
    and not asked again. `taken` holds Spec IDs already in use, so new ones don't collide.
    """
    reply = llm_.ask_json(
        llm, "clarify",
        description=description,
        code=code or "(no code yet)",
        decided=json.dumps(decided or {}, indent=2),
    )
    drafts, used = [], set(taken)
    for s in reply["specs"]:
        spec_id = _unique(_slug(s["id"]), used)
        used.add(spec_id)
        drafts.append(Draft(
            spec=Spec(
                id=spec_id,
                subject=s["subject"],
                description=description,  # verbatim, never the model's paraphrase
                checks=_checks(spec_id, s["checks"]),
            ),
            questions=[Question(q["text"], q["suggestion"]) for q in s.get("questions", [])],
        ))
    return drafts


def _checks(spec_id: str, raw: list[dict]) -> list[Check]:
    """Check IDs are always `<spec id>.<name>` and unique within the Spec."""
    checks, used = [], set()
    for c in raw:
        name = _slug(c["id"].split(".")[-1])
        check_id = _unique(f"{spec_id}.{name}", used)
        used.add(check_id)
        checks.append(Check(check_id, c["given"], c["when"], c["then"]))
    return checks


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "spec"


def _unique(name: str, used: set[str]) -> str:
    n, candidate = 2, name
    while candidate in used:
        candidate, n = f"{name}-{n}", n + 1
    return candidate
