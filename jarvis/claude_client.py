"""The one Claude call.

Model specifics that are easy to get wrong (all verified against the current API):
- Fable 5.1 thinks on every request, so `thinking` is omitted entirely — passing
  `{"type": "enabled", "budget_tokens": N}` is a 400, and so is `temperature`.
  Depth is controlled by `output_config.effort`.
- Safety classifiers can return HTTP 200 with stop_reason == "refusal", so
  stop_reason is checked before the content is read.
- Server-side fallbacks are on (`fallbacks="default"`): if a refusal category would
  otherwise sink the morning's brief, the request is routed to another model
  automatically instead of coming back empty.
- No prompt caching. Cache entries live 5 minutes (1 hour at most) and this runs
  once a day, so a cache write could never be read — it would add ~25% to the input
  cost and return nothing. Worth revisiting only if Jarvis starts running several
  times an hour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .prompt import BRIEF_SCHEMA

DEFAULT_MODEL = "claude-fable-5-1"
DEFAULT_EFFORT = "medium"
# The brief is a few hundred words by design; 4k leaves generous headroom without
# inviting an essay.
MAX_TOKENS = 4000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeError(RuntimeError):
    pass


class RefusalError(ClaudeError):
    def __init__(self, category: str | None, explanation: str | None) -> None:
        super().__init__(
            f"the model declined to answer (category={category or 'unknown'})"
            + (f": {explanation}" if explanation else "")
        )
        self.category = category
        self.explanation = explanation


@dataclass
class BriefResponse:
    brief: dict[str, Any]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw_text: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def estimated_cost_usd(self) -> float:
        """Fable 5.1 list price: $10/MTok in, $50/MTok out."""
        if not self.model.startswith("claude-fable-5"):
            return 0.0
        return self.input_tokens / 1_000_000 * 10 + self.output_tokens / 1_000_000 * 50


def generate_brief(
    *,
    system_prompt: str,
    user_content: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    client: Any = None,
) -> BriefResponse:
    if client is None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ClaudeError(
                "the anthropic package is not installed — pip install -r jarvis/requirements.txt"
            ) from exc
        client = anthropic.Anthropic(api_key=api_key)

    response = client.beta.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": BRIEF_SCHEMA}},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )

    notes: list[str] = []
    stop_reason = getattr(response, "stop_reason", None)
    if stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise RefusalError(getattr(details, "category", None), getattr(details, "explanation", None))
    if stop_reason == "max_tokens":
        notes.append("the response hit max_tokens and may be truncated")

    served_model = getattr(response, "model", model) or model
    if served_model != model:
        notes.append(f"served by {served_model} instead of {model} (fallback)")

    text = _first_text_block(response)
    if not text:
        raise ClaudeError("no text block in the response")

    try:
        brief = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaudeError(f"response was not valid JSON: {exc}") from exc

    usage = getattr(response, "usage", None)
    return BriefResponse(
        brief=brief,
        model=served_model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        raw_text=text,
        notes=notes,
    )


def _first_text_block(response: Any) -> str:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""
