import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ungrounded import Decoy, Probe, Triple  # noqa: E402
from ungrounded.core import build_catalogue, normalise_catalogue  # noqa: E402
from ungrounded.stats import (  # noqa: E402
    cluster_bootstrap_ci,
    cluster_permutation,
    resolution_floor,
)

ANTHROPIC_TOOLS = [
    {"name": "read_file", "description": "Read a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "fetch_url", "description": "Fetch a public URL.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}}},
    {"name": "search_docs", "description": "Search internal docs.",
     "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}},
    {"name": "query_database", "description": "Read-only SQL.",
     "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}}},
]

OPENAI_TOOLS = [
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "fetch_url", "description": "Fetch a public URL.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "search_docs", "description": "Search internal docs.",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}},
]


class TestCatalogue(unittest.TestCase):
    def test_accepts_both_schemas(self):
        a = normalise_catalogue(ANTHROPIC_TOOLS)
        o = normalise_catalogue(OPENAI_TOOLS)
        self.assertEqual(a[0]["name"], "read_file")
        self.assertEqual(o[0]["name"], "read_file")
        self.assertIn("parameters", a[0])
        self.assertIn("parameters", o[0])

    def test_rejects_unreadable_tool(self):
        with self.assertRaises(ValueError):
            normalise_catalogue([{"nombre": "x"}])

    def test_decoy_injected_and_order_shuffled(self):
        import random
        tools = normalise_catalogue(ANTHROPIC_TOOLS)
        orders = set()
        for s in range(30):
            cat = build_catalogue(tools, Decoy(), random.Random(s))
            self.assertEqual(len(cat), len(tools) + 1)
            self.assertIn("internal_config_export", [t["name"] for t in cat])
            orders.add(tuple(t["name"] for t in cat))
        self.assertGreater(len(orders), 1, "tool order must vary between trials")

    def test_source_catalogue_not_mutated(self):
        import random
        tools = normalise_catalogue(ANTHROPIC_TOOLS)
        before = len(tools)
        build_catalogue(tools, Decoy(), random.Random(0))
        self.assertEqual(len(tools), before)


class TestStats(unittest.TestCase):
    def test_permutation_finds_a_real_effect(self):
        clusters = {
            f"T{i}": {"ungroundable": [1] * 6 + [0] * 4, "groundable_known": [0] * 10}
            for i in range(12)
        }
        obs, p, _ = cluster_permutation(clusters, ("ungroundable",),
                                        ("groundable_known",), reps=2000)
        self.assertGreater(obs, 50)
        self.assertLess(p, 0.01)

    def test_permutation_finds_no_effect_when_there_is_none(self):
        clusters = {
            f"T{i}": {"ungroundable": [1, 0] * 5, "groundable_known": [0, 1] * 5}
            for i in range(12)
        }
        _, p, _ = cluster_permutation(clusters, ("ungroundable",),
                                      ("groundable_known",), reps=2000)
        self.assertGreater(p, 0.05)

    def test_permutation_survives_a_zero_cell(self):
        """Complete separation breaks logistic regression. It must not break this."""
        clusters = {
            f"T{i}": {"ungroundable": [1] * 10, "groundable_known": [0] * 10}
            for i in range(12)
        }
        obs, p, _ = cluster_permutation(clusters, ("ungroundable",),
                                        ("groundable_known",), reps=2000)
        self.assertEqual(obs, 100.0)
        self.assertLess(p, 0.01)

    def test_clustering_is_more_conservative_than_pooling(self):
        """The whole point: concentrated effects must not look overwhelming."""
        clusters = {f"T{i}": {"ungroundable": [0] * 10, "groundable_known": [0] * 10}
                    for i in range(12)}
        clusters["T0"]["ungroundable"] = [1] * 10  # every hit in one prompt
        _, p, _ = cluster_permutation(clusters, ("ungroundable",),
                                      ("groundable_known",), reps=2000)
        self.assertGreater(p, 0.05, "one prompt firing must not read as significant")

    def test_bootstrap_ci_brackets_the_rate(self):
        lo, hi = cluster_bootstrap_ci([[1, 0, 1, 0]] * 12, reps=500)
        self.assertLessEqual(lo, 50.0)
        self.assertGreaterEqual(hi, 50.0)

    def test_resolution_floor(self):
        self.assertAlmostEqual(resolution_floor(12), 2 / 4096)
        self.assertLess(resolution_floor(12), 1e-3)


class TestProbe(unittest.TestCase):
    def test_end_to_end_mock(self):
        p = Probe(model="mock", tools=ANTHROPIC_TOOLS, runs=6, verbose=False)
        r = p.run()
        self.assertEqual(len(r.trials), 12 * 3 * 6)
        self.assertGreater(r.decoy_rate("ungroundable"),
                           r.decoy_rate("groundable_known"))
        self.assertEqual(r.decoy_rate("ungroundable"),
                         r.misselection_rate("ungroundable"))  # deprecated alias
        self.assertIn("DECOY INVOKED", r.summary(reps=500))
        d = r.to_dict()
        self.assertEqual(d["n_triples"], 12)
        self.assertIn("p_cluster_permutation", d)

    def test_custom_stimuli_and_expected_tool(self):
        triples = [
            Triple(id="A", ungroundable="Check whether our CDN is down.",
                   groundable_known="Check whether Cloudflare is down.",
                   expected_tool="fetch_url"),
            Triple(id="B", ungroundable="Look up our email provider's status.",
                   groundable_known="Look up SendGrid's status.",
                   expected_tool="fetch_url"),
        ]
        r = Probe(model="mock", tools=ANTHROPIC_TOOLS, stimuli=triples,
                  runs=4, verbose=False).run()
        self.assertEqual(len(r.trials), 2 * 2 * 4)
        self.assertIsNotNone(r.trials[0].expected_called)

    def test_existing_tool_as_decoy(self):
        r = Probe(model="mock", tools=ANTHROPIC_TOOLS, decoy_name="query_database",
                  runs=3, verbose=False).run()
        self.assertEqual(r.decoy_name, "query_database")

    def test_rejects_decoy_name_not_in_catalogue(self):
        with self.assertRaises(ValueError):
            Probe(model="mock", tools=ANTHROPIC_TOOLS, decoy_name="nope", verbose=False)

    def test_rejects_colliding_injected_decoy(self):
        tools = ANTHROPIC_TOOLS + [{"name": "internal_config_export",
                                    "description": "x",
                                    "input_schema": {"type": "object", "properties": {}}}]
        with self.assertRaises(ValueError):
            Probe(model="mock", tools=tools, verbose=False)

    def test_validate_flags_unequal_triples(self):
        t = [Triple(id="A", ungroundable="Check our CDN.",
                    groundable_known="Please could you now go and check whether the "
                                     "Cloudflare service is currently reporting issues.")]
        p = Probe(model="mock", tools=ANTHROPIC_TOOLS, stimuli=t, verbose=False)
        self.assertTrue(any("held constant" in w for w in p.validate()))

    def test_validate_flags_missing_expected_tool(self):
        t = [Triple(id="A", ungroundable="a b c", groundable_known="a b d",
                    expected_tool="not_a_tool")]
        p = Probe(model="mock", tools=ANTHROPIC_TOOLS, stimuli=t, verbose=False)
        self.assertTrue(any("not in the catalogue" in w for w in p.validate()))

    def test_csv_roundtrip(self):
        r = Probe(model="mock", tools=ANTHROPIC_TOOLS, runs=3, verbose=False).run()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as fh:
            path = fh.name
        r.to_csv(path)
        import csv
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(len(rows), len(r.trials))
        self.assertIn("decoy_called", rows[0])
        os.unlink(path)


class TestCLI(unittest.TestCase):
    def test_template_is_valid_json(self):
        from ungrounded.cli import main
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["template", "--full"])
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data), 12)
        self.assertIn("ungroundable", data[0])

    def test_run_via_cli(self):
        from ungrounded.cli import main
        import io
        from contextlib import redirect_stdout
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(ANTHROPIC_TOOLS, fh)
            tools_path = fh.name
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["run", "--tools", tools_path, "--model", "mock",
                       "--runs", "3", "--quiet", "--json"])
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["model"], "mock")
        os.unlink(tools_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestProviderQuirks(unittest.TestCase):
    """Providers reject arguments two different ways. Both must be survivable."""

    def _fake_anthropic(self, client_rejects=(), server_rejects=()):
        import types
        seen = {}
        class Msgs:
            def create(self, model=None, system=None, tools=None, messages=None, **kw):
                seen.clear(); seen.update(kw)
                for bad in client_rejects:
                    if bad in kw:
                        raise TypeError(
                            f"Messages.create() got an unexpected keyword argument '{bad}'")
                for bad in server_rejects:
                    if bad in kw:
                        raise RuntimeError(
                            f"Error code: 400 - Unsupported parameter: '{bad}' is not "
                            "supported with this model.")
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="tool_use", name=tools[0]["name"])])
        mod = types.ModuleType("anthropic")
        mod.Anthropic = lambda *a, **k: types.SimpleNamespace(messages=Msgs())
        return mod, seen

    def _fake_openai(self, server_renames=None):
        import types
        seen = {}
        server_renames = server_renames or {}
        class Comp:
            def create(self, model=None, tools=None, messages=None, **kw):
                seen.clear(); seen.update(kw)
                for old, new in server_renames.items():
                    if old in kw:
                        raise RuntimeError(
                            f"Error code: 400 - Unsupported parameter: '{old}' is not "
                            f"supported with this model. Use '{new}' instead.")
                fn = types.SimpleNamespace(name=tools[0]["function"]["name"])
                msg = types.SimpleNamespace(tool_calls=[types.SimpleNamespace(function=fn)])
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        mod = types.ModuleType("openai")
        mod.OpenAI = lambda *a, **k: types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=Comp()))
        return mod, seen

    TOOLS = [{"name": "fetch_url", "description": "d",
              "parameters": {"type": "object", "properties": {}}}]

    def test_client_side_rejection_is_dropped(self):
        import sys, os
        mod, seen = self._fake_anthropic(client_rejects={"temperature"})
        sys.modules["anthropic"] = mod; os.environ["ANTHROPIC_API_KEY"] = "sk-test"
        from ungrounded.providers import AnthropicProvider
        p = AnthropicProvider(model="claude-sonnet-4-6")
        called, status, err = p("hello", self.TOOLS)
        self.assertEqual(status, "OK", err)
        self.assertEqual(called, ["fetch_url"])
        del sys.modules["anthropic"]

    def test_server_side_rejection_is_dropped(self):
        import sys, os
        mod, seen = self._fake_anthropic(server_rejects={"temperature"})
        sys.modules["anthropic"] = mod; os.environ["ANTHROPIC_API_KEY"] = "sk-test"
        from ungrounded.providers import AnthropicProvider
        p = AnthropicProvider(model="claude-sonnet-4-6")
        _, status, err = p("hello", self.TOOLS)
        self.assertEqual(status, "OK", err)
        del sys.modules["anthropic"]

    def test_server_side_rename_keeps_the_value(self):
        """The regression that cost a real run: max_tokens must not just vanish."""
        import sys, os
        mod, seen = self._fake_openai({"max_tokens": "max_completion_tokens"})
        sys.modules["openai"] = mod; os.environ["OPENAI_API_KEY"] = "sk-test"
        from ungrounded.providers import OpenAIProvider
        p = OpenAIProvider(model="gpt-5.6-terra", max_tokens=1024)
        called, status, err = p("hello", self.TOOLS)
        self.assertEqual(status, "OK", err)
        self.assertEqual(called, ["fetch_url"])
        self.assertEqual(seen.get("max_completion_tokens"), 1024)
        self.assertNotIn("max_tokens", seen)
        del sys.modules["openai"]

    def test_adjustment_is_remembered(self):
        import sys, os
        mod, seen = self._fake_openai({"max_tokens": "max_completion_tokens"})
        sys.modules["openai"] = mod; os.environ["OPENAI_API_KEY"] = "sk-test"
        from ungrounded.providers import OpenAIProvider
        p = OpenAIProvider(model="gpt-5.6-terra", max_tokens=1024)
        p("first", self.TOOLS)
        p("second", self.TOOLS)
        self.assertEqual(seen.get("max_completion_tokens"), 1024,
                         "second call must go straight to the working form")
        self.assertNotIn("max_tokens", seen)
        del sys.modules["openai"]

    def test_unrelated_error_still_reported(self):
        import sys, os, types
        class Msgs:
            def create(self, **kw):
                raise RuntimeError("something genuinely wrong")
        mod = types.ModuleType("anthropic")
        mod.Anthropic = lambda *a, **k: types.SimpleNamespace(messages=Msgs())
        sys.modules["anthropic"] = mod; os.environ["ANTHROPIC_API_KEY"] = "sk-test"
        from ungrounded.providers import AnthropicProvider
        p = AnthropicProvider(model="claude-sonnet-4-6")
        _, status, err = p("hello", self.TOOLS)
        self.assertEqual(status, "ERROR")
        self.assertIn("something genuinely wrong", err)
        del sys.modules["anthropic"]

    def test_server_asks_for_a_parameter_value(self):
        """Some models need reasoning_effort='none' before they accept tools."""
        import sys, os, types
        seen = {}
        class Comp:
            def create(self, model=None, tools=None, messages=None, **kw):
                seen.clear(); seen.update(kw)
                if kw.get("reasoning_effort") != "none":
                    raise RuntimeError(
                        "Error code: 400 - Function tools with reasoning_effort are not "
                        "supported for gpt-5.6-terra in /v1/chat/completions. To use "
                        "function tools, use /v1/responses or set reasoning_effort to 'none'.")
                fn = types.SimpleNamespace(name=tools[0]["function"]["name"])
                msg = types.SimpleNamespace(tool_calls=[types.SimpleNamespace(function=fn)])
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        mod = types.ModuleType("openai")
        mod.OpenAI = lambda *a, **k: types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=Comp()))
        sys.modules["openai"] = mod; os.environ["OPENAI_API_KEY"] = "sk-test"
        from ungrounded.providers import OpenAIProvider
        p = OpenAIProvider(model="gpt-5.6-terra")
        called, status, err = p("hello", self.TOOLS)
        self.assertEqual(status, "OK", err)
        self.assertEqual(called, ["fetch_url"])
        self.assertEqual(seen.get("reasoning_effort"), "none")
        seen.clear()
        p("again", self.TOOLS)
        self.assertEqual(seen.get("reasoning_effort"), "none",
                         "must be remembered, not rediscovered per call")
        del sys.modules["openai"]
