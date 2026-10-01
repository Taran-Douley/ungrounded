"""The first run: nothing configured, wrong name, dead key.

Every path here is one a person hits before they have anything working, so
none of them may produce a traceback and all of them must say what to do.
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ungrounded import providers  # noqa: E402
from ungrounded.providers import (  # noqa: E402
    PROVIDERS,
    SetupError,
    preflight,
    provider_for,
    resolve_provider,
    setup_help,
)

SRC = os.path.join(os.path.dirname(__file__), "..", "src")


def cli(*args, **env):
    e = dict(os.environ, PYTHONPATH=SRC)
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_WORKSPACE_ID"):
        e.pop(k, None)
    e.update({k: v for k, v in env.items()})
    return subprocess.run([sys.executable, "-m", "ungrounded.cli", *args],
                          capture_output=True, text=True, env=e, timeout=120)


class TestNoTracebacks(unittest.TestCase):
    """A stack trace tells a first-time user nothing they can act on."""

    def assert_clean(self, r, *must_contain):
        self.assertNotIn("Traceback", r.stderr + r.stdout)
        self.assertNotEqual(r.returncode, 0)
        blob = r.stderr + r.stdout
        for want in must_contain:
            self.assertIn(want, blob)

    def test_nothing_configured(self):
        self.assert_clean(cli("run"),
                          "No model provider is configured",
                          "ANTHROPIC_API_KEY", "ungrounded run --model mock")

    def test_missing_key_names_the_variable_and_the_console(self):
        self.assert_clean(cli("run", "--model", "claude-sonnet-4-6"),
                          "ANTHROPIC_API_KEY is not set",
                          "console.anthropic.com", "--model mock")

    def test_unknown_provider_lists_what_is_supported(self):
        self.assert_clean(cli("run", "--model", "gemini-2.0-flash"),
                          "Could not tell which provider",
                          "claude-*", "gpt-*", "mock")

    def test_error_comes_before_incidental_chatter(self):
        """The failure should be the first thing printed, not the third."""
        r = cli("run", "--model", "claude-sonnet-4-6")
        self.assertNotIn("example catalogue", r.stderr.split("is not set")[0])


class TestMockNeedsNothing(unittest.TestCase):
    def test_mock_runs_with_no_keys_at_all(self):
        r = cli("run", "--model", "mock", "--runs", "2", "--quiet", "--scorecard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("UNGROUNDED", r.stdout)

    def test_mock_skips_the_preflight(self):
        r = cli("run", "--model", "mock", "--runs", "1", "--scorecard")
        self.assertNotIn("checking credentials", r.stderr)


class TestDoctor(unittest.TestCase):
    def test_reports_what_is_missing_without_calling_anything(self):
        r = cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Nothing is configured", r.stdout)
        # names the exact remedy for whatever is actually missing
        self.assertIn("export ANTHROPIC_API_KEY", r.stdout)
        self.assertIn("export OPENAI_API_KEY", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_mock_is_always_offered(self):
        self.assertIn("mock", cli("doctor").stdout)


class TestProviderMapping(unittest.TestCase):
    def test_names_map_to_vendors(self):
        self.assertEqual(provider_for("claude-opus-5"), "anthropic")
        self.assertEqual(provider_for("gpt-5.6-terra"), "openai")
        self.assertEqual(provider_for("o3-mini"), "openai")
        self.assertEqual(provider_for("mock"), "mock")
        self.assertIsNone(provider_for("gemini-2.0-flash"))

    def test_explicit_prefixes_win(self):
        self.assertEqual(provider_for("anthropic:some-new-name"), "anthropic")
        self.assertEqual(provider_for("openai:some-new-name"), "openai")

    def test_unknown_name_raises_setup_error_not_value_error(self):
        with self.assertRaises(SetupError):
            resolve_provider("gemini-2.0-flash")

    def test_setup_help_covers_every_provider(self):
        h = setup_help()
        for env, _, _, _ in PROVIDERS.values():
            self.assertIn(env, h)
        self.assertIn("mock", h)


class TestPreflight(unittest.TestCase):
    """One call before hundreds, and the diagnosis has to be right."""

    def _fake(self, error):
        return lambda prompt, tools: ([], "ERROR", error)

    def test_passes_silently_when_the_call_works(self):
        preflight(lambda p, t: (["fetch_url"], "OK", ""), "m")

    def test_billing_is_not_reported_as_a_bad_key(self):
        with self.assertRaises(SetupError) as c:
            preflight(self._fake("credit balance is too low"), "m")
        self.assertIn("cannot pay", str(c.exception))
        self.assertNotIn("revoked", str(c.exception))

    def test_workspace_id_is_diagnosed_specifically(self):
        with self.assertRaises(SetupError) as c:
            preflight(self._fake(
                "anthropic-workspace-id is required when authenticating with an "
                "identity-linked API key"), "m")
        msg = str(c.exception)
        self.assertIn("ANTHROPIC_WORKSPACE_ID", msg)
        self.assertNotIn("has not been revoked", msg)

    def test_bad_model_name_is_diagnosed(self):
        with self.assertRaises(SetupError) as c:
            preflight(self._fake("model not found"), "claude-sonet-4-6")
        self.assertIn("claude-sonet-4-6", str(c.exception))

    def test_the_api_message_is_always_shown_verbatim(self):
        with self.assertRaises(SetupError) as c:
            preflight(self._fake("something nobody anticipated"), "m")
        self.assertIn("something nobody anticipated", str(c.exception))

    def test_escape_hatch_is_advertised(self):
        with self.assertRaises(SetupError) as c:
            preflight(self._fake("nope"), "m")
        self.assertIn("--no-preflight", str(c.exception))


class TestWorkspaceHeader(unittest.TestCase):
    def test_header_is_sent_only_when_the_variable_is_set(self):
        seen = {}

        class FakeAnthropic:
            def __init__(self, default_headers=None):
                seen["headers"] = default_headers

        fake = type(sys)("anthropic")
        fake.Anthropic = FakeAnthropic
        old = sys.modules.get("anthropic")
        sys.modules["anthropic"] = fake
        old_key = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["ANTHROPIC_API_KEY"] = "k"
        try:
            os.environ.pop("ANTHROPIC_WORKSPACE_ID", None)
            providers.AnthropicProvider(model="claude-sonnet-4-6")
            self.assertIsNone(seen["headers"])

            os.environ["ANTHROPIC_WORKSPACE_ID"] = "wrkspc_abc"
            providers.AnthropicProvider(model="claude-sonnet-4-6")
            self.assertEqual(seen["headers"],
                             {"anthropic-workspace-id": "wrkspc_abc"})
        finally:
            os.environ.pop("ANTHROPIC_WORKSPACE_ID", None)
            if old_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            if old is None:
                sys.modules.pop("anthropic", None)
            else:
                sys.modules["anthropic"] = old


if __name__ == "__main__":
    unittest.main()
