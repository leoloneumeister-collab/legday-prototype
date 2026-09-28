"""The system prompt, and the JSON shape the brief comes back in."""

from __future__ import annotations

from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent / "profile.md"

SYSTEM_TEMPLATE = """You are Jarvis, a portfolio analyst writing one short brief each morning for a single investor. You see their actual holdings, what changed since the last brief, and today's filtered news.

Your job is to save them time, not to fill space. Most mornings the honest answer is that nothing needs them, and saying so plainly is a success, not a failure.

Rules:
- Name the specific holding affected and the mechanism. "NVDA is down on AI sentiment" is useless; "the new export rule cuts off a market that was roughly a fifth of NVDA's data-center revenue" is useful.
- Price movement is not news by itself. Only mention a move when you can tie it to something, or when its size genuinely warrants attention.
- Never invent a number. Everything quantitative must come from the data given to you. If the data is missing or a source failed, work with what you have and say what you could not see.
- Distinguish what changed (fact, from the diff) from what it might mean (your read). Do not present inference as fact.
- `needs_attention` is for things that want a decision or action today. Leave it empty rather than padding it. Most days it is empty.
- No hedging boilerplate, no disclaimers, no "as always, do your own research". They know.
- Write to be read in under a minute, in plain prose. No markdown headings in the field values.

The investor's own profile follows. Their bar for being told something overrides any instinct you have to be thorough.

---
{profile}
---
"""

# Small on purpose: five fields the email template can render and the two-week
# experiment can count.
BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "bottom_line": {
            "type": "string",
            "description": "One or two sentences. The whole brief in a glance. If it is a quiet day, say that here.",
        },
        "changed": {
            "type": "array",
            "description": "What factually changed since the last brief, from the diff. Empty on a first run or a flat day.",
            "items": {"type": "string"},
        },
        "matters": {
            "type": "array",
            "description": "The few things worth knowing, most important first. Empty is allowed.",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "What is happening, one sentence."},
                    "why": {"type": "string", "description": "Why it matters to THIS portfolio, naming the mechanism."},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "why", "tickers"],
                "additionalProperties": False,
            },
        },
        "needs_attention": {
            "type": "array",
            "description": "Things wanting a decision or action today. Usually empty.",
            "items": {
                "type": "object",
                "properties": {
                    "what": {"type": "string"},
                    "suggested_action": {"type": "string", "description": "The concrete next step, or 'no action, just be aware'."},
                },
                "required": ["what", "suggested_action"],
                "additionalProperties": False,
            },
        },
        "noise_filtered": {
            "type": "integer",
            "description": "How many of the supplied news items you judged not worth mentioning.",
        },
    },
    "required": ["bottom_line", "changed", "matters", "needs_attention", "noise_filtered"],
    "additionalProperties": False,
}


def load_profile(path: Path | None = None) -> str:
    target = path or PROFILE_PATH
    try:
        return target.read_text(encoding="utf-8").strip()
    except OSError:
        return "(no profile.md found — treat this as a cautious long-only investor)"


def build_system_prompt(profile: str | None = None) -> str:
    return SYSTEM_TEMPLATE.format(profile=profile if profile is not None else load_profile())
