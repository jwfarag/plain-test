# plaintest

Describe what should be tested in plain English. plaintest turns your words into real tests,
then proves the tests actually check what you described.

Plain English is ambiguous and test code is hard to audit, so plaintest puts a small,
human-readable **Spec** between them. Specs are the source of truth: plain YAML files you
read and edit. Tests are derived from them, and verification checks the tests against them.

## The pipeline

```
descriptions → clarify → Specs → generate → tests → verify → Report
                                    ↑                 │
                                    └── weak tests ───┘
```

- **clarify** reads a description and the code under test, writes one Spec per component it
  touches, and breaks each into Checks. When something is ambiguous it doesn't stop: it picks
  an answer, writes the Checks with it, and raises a question with that answer as the suggestion.
- **generate** writes at least one test per Check, tagged with the Check's ID. The Check says
  what should happen; the code is read only to learn how to call it.
- **verify** answers four questions for every Check. Broken or weak tests go back to generate,
  at most twice. A test that disagrees with existing code never goes back: weakening it would
  hide either a wrong Check or a real bug, and only you can say which.

## Vocabulary

| Word | What it is |
|---|---|
| **Description** | What you wrote, kept verbatim. |
| **Spec** | One description scoped to one component (its *subject*), broken into Checks, plus the assumptions made along the way. |
| **Check** | One atomic, testable statement in given / when / then form, with a stable ID. |
| **Test** | Generated test code, tagged with the ID of the Check it covers. |
| **Report** | The verification status of every Check. |

## Verification: four questions per Check

| | Question | Catches |
|---|---|---|
| **linked** | Is there a test tagged with this Check? | missing tests |
| **runs** | Does it run and pass? | broken tests |
| **faithful** | Does it test the right thing? A model describes the test without seeing the Check; a second call compares the two. | tests of the wrong thing |
| **catches** | Would it catch a bug? A model proposes the smallest change that breaks the Check; the tool applies it to a temporary copy and confirms the test now fails. | tests that pass no matter what |

Each answer is one of: `✓` pass · `✗` fail (the test is at fault) · `≠` disagrees (the test
and the existing code disagree: fix the Check or the code) · `…` pending (can't be answered
yet, e.g. the code isn't written, so failing is expected).

*linked* and *runs* work today. *faithful* and *catches* are stubs that report pending;
their docstrings in `verify.py` describe how they'll work.

## Two modes, one pipeline

The only difference is who makes the judgment calls: the **Reviewer** passed into the pipeline.

- **Batch** (default): accepts every suggestion and records it in the Spec's `assumptions`,
  so nothing is guessed silently. The Report waits for you.
- **Interactive** (`--interactive`): you answer clarify's questions (Enter accepts the
  suggestion), add, remove, or reword Checks, and decide what to do when a test and the code
  disagree. An answer you give is not an assumption; if it differs from the suggestion,
  clarify runs again with it.

## Example

`examples/cart/descriptions.txt`:
```
A discount code can't bring the total below zero.
Checkout fails with a clear error when the cart is empty.
```

```bash
plaintest build examples/cart/descriptions.txt --code examples/cart/cart.py
```

writes `examples/cart/specs/discount.yaml`:
```yaml
id: discount
subject: cart.py::Cart.apply_discount
description: A discount code can't bring the total below zero.
checks:
- id: discount.floor
  given: a cart totaling 10
  when: a discount of 15 is applied
  then: the total is 0
- id: discount.exact
  given: a cart totaling 10
  when: a discount of 10 is applied
  then: the total is 0
assumptions:
- Discounts are fixed amounts, not percentages.
```

and `examples/cart/tests/plaintest/test_discount.py`:
```python
@pytest.mark.check("discount.floor")
def test_discount_larger_than_total_stops_at_zero(): ...
```

then prints the Report:
```
discount.floor         linked ✓   runs ✓   faithful …   catches …
discount.exact         linked ✓   runs ✓   faithful …   catches …
empty-checkout.error   linked ✓   runs ✓   faithful …   catches …
```

## Usage

```bash
pip install -e ".[anthropic]"    # or ".[openai]"
```

```bash
export PLAINTEST_LLM=anthropic:<model-id>    # provider:model; or pass --llm
```

| Command | Does |
|---|---|
| `plaintest build DESCRIPTIONS --code FILE...` | descriptions → Specs → tests → Report |
| `plaintest generate SPECS` | after you edit Specs: Specs → tests → Report |
| `plaintest verify SPECS` | the Report for the tests as they are |

`build` and `generate` take `--interactive`. The project root defaults to the folder holding
the descriptions file, or the parent of the Specs folder; `--project` overrides it. `build`
overwrites Specs with the same ID, so after editing Specs, use `generate`. The exit code is
1 if any test failed or disagrees with the code, 0 otherwise (pending is fine).

Generated tests are ordinary pytest tests. To run them yourself without an unknown-marker
warning, add `-p plaintest.targets.pytest_plugin` or register a `check` marker in your
pytest config.

## Where each piece lives

```
plaintest/
├── models.py         the vocabulary as dataclasses; read and write Spec files
├── clarify.py        description + code → Drafts (Specs + the questions behind them)
├── generate.py       Spec → test file source
├── verify.py         Specs + tests → Report (the four questions)
├── pipeline.py       the one place that knows the order and the retry loop; writes files
├── review.py         the Reviewer interface, and BatchReviewer
├── cli.py            all user interaction: arguments, printing, InteractiveReviewer
├── llm.py            the only code that calls a model: providers, prompt rendering, FakeLLM
├── prompts/          one file per model call: clarify, generate, describe, judge, break
└── targets/
    ├── base.py           the Target interface: the only language-specific seam
    ├── pytest_target.py  Python + pytest
    └── pytest_plugin.py  loaded into the test run: registers the marker, records outcomes
examples/cart/        a tiny app and its descriptions
tests/                tests for plaintest itself, using FakeLLM
```

## Three seams, and nothing else varies

- **Which model**: `llm.py`. A provider is any object with `complete(prompt) -> str`. Anthropic
  and OpenAI ship in; add one to `PROVIDERS` to support another. Tests use `FakeLLM`.
- **Which language**: a Target (`targets/base.py`). It reads code, says how to tag a test,
  finds which tests cover which Checks, and runs them. A new language is a new Target.
- **Who decides**: the Reviewer (`review.py`). Batch or interactive.

## Principles

- **Tests encode the Spec, not the code.** A test that fails against existing code is never
  weakened to pass.
- **Plain functions, thin edges.** Stages take data and return data. Only `cli.py` prints or prompts.
- **Prompts are files.** Each model call's prompt is in `prompts/`, readable and editable on
  its own. Placeholders are `$name`.
- **Boring code.** Plain dataclasses, two dependencies, no abstractions beyond the three seams.
