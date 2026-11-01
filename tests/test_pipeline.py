"""The thin path end to end on examples/cart, with a fake model.

Each test copies the example into a temporary folder, so the real example is never touched.
The fake model's replies are below: what clarify and generate would plausibly return.
"""

import json
import shutil
from pathlib import Path

import pytest

from plaintest.cli import main
from plaintest.llm import FakeLLM
from plaintest.models import Check, Draft, Spec, Status, load_spec, save_spec
from plaintest.pipeline import build
from plaintest.review import BatchReviewer
from plaintest.targets import PytestTarget
from plaintest.verify import verify

EXAMPLE = Path(__file__).parents[1] / "examples" / "cart"

DISCOUNT = {"specs": [{
    "id": "discount",
    "subject": "cart.py::Cart.apply_discount",
    "checks": [
        {"id": "floor", "given": "a cart totaling 10", "when": "a discount of 15 is applied", "then": "the total is 0"},
        {"id": "exact", "given": "a cart totaling 10", "when": "a discount of 10 is applied", "then": "the total is 0"},
    ],
    "questions": [{"text": "Are discounts fixed amounts or percentages?",
                   "suggestion": "Discounts are fixed amounts, not percentages."}],
}]}

CHECKOUT = {"specs": [{
    "id": "empty-checkout",
    "subject": "cart.py::Cart.checkout",
    "checks": [{"id": "error", "given": "an empty cart", "when": "checkout is called",
                "then": "it raises CartError with a message saying the cart is empty"}],
    "questions": [{"text": "Which error is raised?", "suggestion": "Checkout raises CartError."}],
}]}

DISCOUNT_TESTS = '''```python
import pytest
from cart import Cart


@pytest.mark.check("discount.floor")
def test_discount_larger_than_total_stops_at_zero():
    cart = Cart()
    cart.add("book", 10)
    cart.apply_discount(15)
    assert cart.total() == 0


@pytest.mark.check("discount.exact")
def test_discount_equal_to_total_is_zero():
    cart = Cart()
    cart.add("book", 10)
    cart.apply_discount(10)
    assert cart.total() == 0
```'''

CHECKOUT_TESTS = '''```python
import pytest
from cart import Cart, CartError


@pytest.mark.check("empty-checkout.error")
def test_checkout_of_empty_cart_raises_clear_error():
    with pytest.raises(CartError, match="empty"):
        Cart().checkout()
```'''


def clarify_reply(prompt: str) -> str:
    return json.dumps(DISCOUNT if "A discount code can't" in prompt else CHECKOUT)


def generate_reply(discount_tests: str = DISCOUNT_TESTS):
    return lambda prompt: discount_tests if "id: discount\n" in prompt else CHECKOUT_TESTS


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return Path(shutil.copytree(EXAMPLE, tmp_path / "cart"))


def build_args(project: Path) -> list[str]:
    return ["build", str(project / "descriptions.txt"), "--code", str(project / "cart.py")]


def test_build_writes_specs_and_tests_and_reports_linked_and_runs(project, capsys):
    llm = FakeLLM({"clarify": clarify_reply, "generate": generate_reply()})

    assert main(build_args(project), llm=llm) == 0

    spec = load_spec(project / "specs" / "discount.yaml")
    assert spec.subject == "cart.py::Cart.apply_discount"
    assert spec.description == "A discount code can't bring the total below zero."  # verbatim
    assert [c.id for c in spec.checks] == ["discount.floor", "discount.exact"]
    assert spec.assumptions == ["Discounts are fixed amounts, not percentages."]  # batch records its guesses
    assert (project / "specs" / "empty-checkout.yaml").exists()

    tests = (project / "tests" / "plaintest" / "test_discount.py").read_text()
    assert '@pytest.mark.check("discount.floor")' in tests

    out = capsys.readouterr().out
    for check_id in ("discount.floor", "discount.exact", "empty-checkout.error"):
        line = next(l for l in out.splitlines() if l.startswith(check_id))
        assert "linked ✓   runs ✓   faithful …   catches …" in line


def test_broken_test_goes_back_to_generate_with_the_reason(project, capsys):
    broken = DISCOUNT_TESTS.replace("from cart import Cart", "from cart import Kart")
    replies = iter([broken, DISCOUNT_TESTS])
    llm = FakeLLM({"clarify": clarify_reply,
                   "generate": lambda p: next(replies) if "id: discount\n" in p else CHECKOUT_TESTS})

    assert main(build_args(project), llm=llm) == 0

    discount_prompts = [p for name, p in llm.prompts if name == "generate" and "id: discount\n" in p]
    assert len(discount_prompts) == 2
    assert "test is broken" in discount_prompts[1] and "Kart" in discount_prompts[1]


def test_a_test_that_disagrees_with_the_code_is_never_regenerated(project, capsys):
    wrong = DISCOUNT_TESTS.replace("cart.apply_discount(15)\n    assert cart.total() == 0",
                                   "cart.apply_discount(15)\n    assert cart.total() == 5")
    llm = FakeLLM({"clarify": clarify_reply, "generate": generate_reply(wrong)})

    assert main(build_args(project), llm=llm) == 1  # disagreement exits non-zero

    assert sum(name == "generate" for name, _ in llm.prompts) == 2  # once per Spec, no retries
    out = capsys.readouterr().out
    assert "discount.floor" in out and "runs ≠" in out


def test_failing_before_the_code_exists_is_pending_not_failed(project):
    spec = Spec("wrap", "cart.py::Cart.gift_wrap", "Items can be gift wrapped.",
                [Check("wrap.fee", "a cart", "gift wrap is added", "the total rises by 3")])
    test = project / "tests" / "plaintest" / "test_wrap.py"
    test.parent.mkdir(parents=True)
    test.write_text('import pytest\n\n@pytest.mark.check("wrap.fee")\ndef test_fee():\n    assert False\n')

    report = verify([spec], project, PytestTarget(), llm=None)

    assert report.checks[0].linked.status is Status.PASS
    assert report.checks[0].runs.status is Status.PENDING


def test_an_answer_that_differs_from_the_suggestion_reruns_clarify(project):
    class Overrides(BatchReviewer):
        def answer(self, draft: Draft) -> dict[str, str]:
            return {q.text: "Percentages." for q in draft.questions if "percentages" in q.text}

    llm = FakeLLM({"clarify": clarify_reply, "generate": generate_reply()})
    specs, report = build(["A discount code can't bring the total below zero."], [project / "cart.py"],
                          project, llm, PytestTarget(), Overrides())

    clarify_prompts = [p for name, p in llm.prompts if name == "clarify"]
    assert len(clarify_prompts) == 2 and "Percentages." in clarify_prompts[1]
    assert specs[0].assumptions == []  # a person decided it, so it isn't an assumption
    assert report.ok


def test_spec_files_round_trip(tmp_path):
    spec = Spec("discount", "cart.py::Cart.apply_discount", "A discount code can't bring the total below zero.",
                [Check("discount.floor", "a cart totaling 10", "a discount of 15 is applied", "the total is 0")],
                ["Discounts are fixed amounts, not percentages."])
    save_spec(spec, tmp_path / "discount.yaml")
    assert load_spec(tmp_path / "discount.yaml") == spec
