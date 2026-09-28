"""The Claude call, exercised with a fake client.

Worth testing properly: the refusal path and the truncation path only show up on a
bad morning, which is exactly when a crash is most annoying.
"""

import json
import unittest

from jarvis import claude_client
from jarvis.prompt import BRIEF_SCHEMA, build_system_prompt


class Block:
    def __init__(self, text, type="text"):
        self.text = text
        self.type = type


class Usage:
    def __init__(self, i, o):
        self.input_tokens = i
        self.output_tokens = o


class Response:
    def __init__(self, content, stop_reason="end_turn", model="claude-fable-5-1", usage=None, stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model
        self.usage = usage or Usage(9000, 500)
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class FakeClient:
    def __init__(self, response):
        self.beta = type("Beta", (), {"messages": FakeMessages(response)})()


VALID = {
    "bottom_line": "Quiet day.",
    "changed": [],
    "matters": [],
    "needs_attention": [],
    "noise_filtered": 4,
}


def call(response, **overrides):
    client = FakeClient(response)
    kwargs = dict(
        system_prompt="system",
        user_content="bundle",
        api_key="unused",
        client=client,
    )
    kwargs.update(overrides)
    return claude_client.generate_brief(**kwargs), client


class TestRequestShape(unittest.TestCase):
    def test_request_matches_what_fable_accepts(self):
        _, client = call(Response([Block(json.dumps(VALID))]))
        kwargs = client.beta.messages.kwargs
        self.assertEqual(kwargs["model"], "claude-fable-5-1")
        # Thinking is always on for this model; sending the parameter at all is a 400.
        self.assertNotIn("thinking", kwargs)
        self.assertNotIn("temperature", kwargs)
        self.assertEqual(kwargs["output_config"]["effort"], "medium")
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["output_config"]["format"]["schema"], BRIEF_SCHEMA)
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertIn(claude_client.FALLBACK_BETA, kwargs["betas"])
        self.assertEqual(kwargs["max_tokens"], claude_client.MAX_TOKENS)

    def test_effort_override(self):
        _, client = call(Response([Block(json.dumps(VALID))]), effort="high")
        self.assertEqual(client.beta.messages.kwargs["output_config"]["effort"], "high")


class TestResponseHandling(unittest.TestCase):
    def test_parses_json_and_usage(self):
        result, _ = call(Response([Block(json.dumps(VALID))], usage=Usage(12_000, 600)))
        self.assertEqual(result.brief["bottom_line"], "Quiet day.")
        self.assertEqual(result.input_tokens, 12_000)
        self.assertEqual(result.output_tokens, 600)
        # 12k in at $10/MTok + 600 out at $50/MTok
        self.assertAlmostEqual(result.estimated_cost_usd, 0.12 + 0.03, places=4)

    def test_refusal_raises_a_clear_error(self):
        details = type("D", (), {"category": "cyber", "explanation": "nope"})()
        with self.assertRaises(claude_client.RefusalError) as ctx:
            call(Response([], stop_reason="refusal", stop_details=details))
        self.assertIn("cyber", str(ctx.exception))

    def test_fallback_to_another_model_is_noted(self):
        result, _ = call(Response([Block(json.dumps(VALID))], model="claude-opus-4-8"))
        self.assertEqual(result.model, "claude-opus-4-8")
        self.assertTrue(any("fallback" in n for n in result.notes))
        self.assertEqual(result.estimated_cost_usd, 0.0)  # not priced as Fable

    def test_truncation_is_noted(self):
        result, _ = call(Response([Block(json.dumps(VALID))], stop_reason="max_tokens"))
        self.assertTrue(any("max_tokens" in n for n in result.notes))

    def test_non_json_text_is_reported(self):
        with self.assertRaises(claude_client.ClaudeError):
            call(Response([Block("I'm afraid I can't do that, Dave")]))

    def test_no_text_block_is_reported(self):
        with self.assertRaises(claude_client.ClaudeError):
            call(Response([Block("", type="thinking")]))


class TestSystemPrompt(unittest.TestCase):
    def test_profile_is_injected(self):
        prompt = build_system_prompt("MY CUSTOM PROFILE")
        self.assertIn("MY CUSTOM PROFILE", prompt)
        self.assertIn("Never invent a number", prompt)

    def test_real_profile_file_loads(self):
        prompt = build_system_prompt()
        self.assertIn("Thesis", prompt)
        self.assertIn("Bar for telling me something", prompt)

    def test_schema_requires_every_field(self):
        self.assertEqual(
            set(BRIEF_SCHEMA["required"]),
            {"bottom_line", "changed", "matters", "needs_attention", "noise_filtered"},
        )
        self.assertFalse(BRIEF_SCHEMA["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
