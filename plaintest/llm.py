"""The only code that calls a language model.

A provider is anything with `complete(prompt) -> str`. Stages never see a provider's
SDK; they call `ask_json` or `ask_code` with a prompt name from `prompts/` and get data back.

Choose a provider with a spec string, `provider:model`, passed as `--llm` or set in the
`PLAINTEST_LLM` environment variable:

    PLAINTEST_LLM=anthropic:<model-id>
    PLAINTEST_LLM=openai:<model-id>

To add a provider, write a class with `complete` and add it to PROVIDERS.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from string import Template
from typing import Callable, Protocol

PROMPTS = Path(__file__).parent / "prompts"


class LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


class LLMError(RuntimeError):
    pass


# --- Talking to a model --------------------------------------------------------


def render(prompt_name: str, **values: str) -> str:
    """Fill `prompts/<name>.md`. Placeholders are `$name`; a literal dollar sign is `$$`."""
    return Template((PROMPTS / f"{prompt_name}.md").read_text()).substitute(values)


def ask_json(llm: LLM, prompt_name: str, **values: str):
    """Ask, and parse the reply as JSON (a ```json fence around it is fine)."""
    reply = llm.complete(render(prompt_name, **values))
    try:
        return json.loads(_unfence(reply))
    except json.JSONDecodeError as e:
        raise LLMError(f"{prompt_name}: reply was not JSON: {e}\n{reply[:500]}") from e


def ask_code(llm: LLM, prompt_name: str, **values: str) -> str:
    """Ask, and return the contents of the first fenced code block (or the whole reply)."""
    return _unfence(llm.complete(render(prompt_name, **values))).rstrip() + "\n"


def _unfence(text: str) -> str:
    m = re.search(r"```[\w-]*\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else text.strip()


# --- Providers -------------------------------------------------------------------


class Anthropic:
    """Claude, through the official `anthropic` SDK (`pip install plaintest[anthropic]`)."""

    def __init__(self, model: str, max_tokens: int = 16000):
        import anthropic  # imported here so the SDK is only needed if you use it

        self.client = anthropic.Anthropic()  # credentials come from the environment
        self.model, self.max_tokens = model, max_tokens

    def complete(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            raise LLMError(f"model stopped early: {response.stop_reason}")
        return "".join(b.text for b in response.content if b.type == "text")


class OpenAI:
    """OpenAI, through the official `openai` SDK (`pip install plaintest[openai]`)."""

    def __init__(self, model: str):
        import openai

        self.client = openai.OpenAI()
        self.model = model

    def complete(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content or ""


PROVIDERS: dict[str, Callable[[str], LLM]] = {"anthropic": Anthropic, "openai": OpenAI}


def from_spec(spec: str | None = None) -> LLM:
    """Build a provider from `provider:model`, falling back to $PLAINTEST_LLM."""
    spec = spec or os.environ.get("PLAINTEST_LLM")
    if not spec or ":" not in spec:
        raise LLMError("choose a model with --llm provider:model or PLAINTEST_LLM, "
                       f"e.g. anthropic:<model-id>. Providers: {', '.join(PROVIDERS)}")
    provider, model = spec.split(":", 1)
    if provider not in PROVIDERS:
        raise LLMError(f"unknown provider {provider!r}. Providers: {', '.join(PROVIDERS)}")
    return PROVIDERS[provider](model)


# --- For tests -------------------------------------------------------------------


class FakeLLM:
    """A stand-in model for tests. Replies are chosen by prompt name.

    Every prompt file starts with `# <name>`, so the fake reads the first line to know
    which prompt it got. A reply is a string, or a function of the full prompt.
    Every prompt it receives is kept in `.prompts` for assertions.
    """

    def __init__(self, replies: dict[str, str | Callable[[str], str]]):
        self.replies = replies
        self.prompts: list[tuple[str, str]] = []

    def complete(self, prompt: str) -> str:
        name = prompt.splitlines()[0].lstrip("# ").strip()
        self.prompts.append((name, prompt))
        if name not in self.replies:
            raise LLMError(f"FakeLLM has no reply for prompt {name!r}")
        reply = self.replies[name]
        return reply(prompt) if callable(reply) else reply
