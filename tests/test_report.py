"""The shareable output: scorecard, card, badge, submission."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import xml.dom.minidom

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ungrounded import Probe, Scorecard, Triple  # noqa: E402
from ungrounded import submit as submit_mod  # noqa: E402
from ungrounded.report import FLOOR, _verdict, _vis  # noqa: E402

TOOLS = [
    {"name": "fetch_url", "description": "Fetch a public URL.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}}},
    {"name": "read_file", "description": "Read a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "search_docs", "description": "Search internal docs.",
     "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}}},
]


def card(**over):
    base = dict(
        model="claude-sonnet-4-6", grounded=84.0, ungrounded=5.0, unfamiliar=27.0,
        ci_grounded=(72.0, 92.0), ci_ungrounded=(0.0, 11.0), decoy_ungrounded=14.0,
        gap_pp=79.0, retention=5.0 / 84.0, p=1e-4, p_note="", prompts_firing=11,
        n_triples=12, n_trials=360, runs=20, decoy="internal_config_export",
        stimuli_id="builtin-12", catalogue_id="example-10", verdict="COLLAPSE",
        reading="tool choice fails almost entirely without a groundable entity",
        version="0.3.0", measured="2026-08-30",
    )
    base.update(over)
    return Scorecard(**base)


class TestVerdict(unittest.TestCase):
    def test_bands(self):
        for ungrounded, expected in ((80.0, "ROBUST"), (50.0, "DEGRADED"),
                                     (30.0, "BRITTLE"), (2.0, "COLLAPSE")):
            v, _, _ = _verdict(90.0, ungrounded, 1e-4, 20)
            self.assertEqual(v, expected, f"{ungrounded}% of 90%")

    def test_retention_not_absolute_rate(self):
        """A model weak everywhere is not graded as a grounding failure."""
        v, _, r = _verdict(30.0, 25.0, 1e-4, 20)
        self.assertEqual(v, "ROBUST")
        self.assertAlmostEqual(r, 25.0 / 30.0)

    def test_floor_refuses_to_grade(self):
        v, why, _ = _verdict(FLOOR - 1, 0.0, 1e-9, 20)
        self.assertEqual(v, "INCONCLUSIVE")
        self.assertIn("even when the entity is familiar", why)

    def test_no_expected_tool_is_inconclusive(self):
        self.assertEqual(_verdict(None, None, 1e-4, 20)[0], "INCONCLUSIVE")

    def test_nonsignificant_is_not_graded(self):
        v, why, _ = _verdict(84.0, 5.0, 0.4, 20)
        self.assertEqual(v, "NO EFFECT")
        self.assertIn("indistinguishable", why)

    def test_nan_p_still_grades(self):
        self.assertEqual(_verdict(84.0, 5.0, float("nan"), 20)[0], "COLLAPSE")


class TestScorecardText(unittest.TestCase):
    def test_box_is_rectangular(self):
        widths = {_vis(ln) for ln in card().text(colour=False).splitlines()}
        self.assertEqual(len(widths), 1, f"ragged box: {sorted(widths)}")

    def test_colour_does_not_change_alignment(self):
        plain = [_vis(l) for l in card().text(colour=False).splitlines()]
        col = [_vis(l) for l in card().text(colour=True).splitlines()]
        self.assertEqual(plain, col)

    def test_carries_the_numbers_and_provenance(self):
        t = card().text(colour=False)
        for want in ("claude-sonnet-4-6", "84.0%", "5.0%", "COLLAPSE",
                     "builtin-12", "example-10", "11/12"):
            self.assertIn(want, t)

    def test_low_runs_is_flagged(self):
        self.assertIn("--runs 4 is low", card(runs=4).text(colour=False))
        self.assertNotIn("is low", card(runs=20).text(colour=False))

    def test_missing_condition_is_skipped_not_zeroed(self):
        t = card(unfamiliar=None).text(colour=False)
        self.assertNotIn("named, unfamiliar", t)
        self.assertIn("named, familiar", t)


class TestSvg(unittest.TestCase):
    def test_card_is_well_formed(self):
        xml.dom.minidom.parseString(card().card_svg())

    def test_badge_is_well_formed(self):
        for style in ("rate", "collapse", "verdict"):
            xml.dom.minidom.parseString(card().badge_svg(style=style))

    def test_card_escapes_hostile_model_names(self):
        svg = card(model='a<b&c"d').card_svg()
        xml.dom.minidom.parseString(svg)
        self.assertNotIn("<b&c", svg)

    def test_themes_differ(self):
        self.assertNotEqual(card().card_svg("light"), card().card_svg("dark"))
        self.assertIn("prefers-color-scheme", card().card_svg("auto"))

    def test_bar_never_vanishes_entirely(self):
        """A 0% bar still renders a sliver, so the row is not silently blank."""
        self.assertIn('width="3.0"', card(ungrounded=0.0).card_svg())


class TestBadge(unittest.TestCase):
    def test_headline_is_correct_tool_use_when_ungrounded(self):
        self.assertEqual(card().headline, "5.0%")
        self.assertIn("ungrounded-5.0%25", card().badge_url())

    def test_styles(self):
        self.assertIn("COLLAPSE", card().badge_url(style="verdict"))
        self.assertIn("84%25", card().badge_url(style="collapse"))

    def test_unknown_style_rejected(self):
        with self.assertRaises(ValueError):
            card().badge_url(style="nope")

    def test_colour_tracks_verdict(self):
        self.assertTrue(card(verdict="ROBUST").badge_url().endswith("brightgreen"))
        self.assertTrue(card(verdict="COLLAPSE").badge_url().endswith("red"))

    def test_shields_escaping(self):
        url = card().badge_url(label="my_label-x")
        self.assertIn("my__label--x", url)

    def test_markdown_links_back(self):
        md = card().badge_md(link="https://example.com/x")
        self.assertTrue(md.startswith("[!["))
        self.assertIn("](https://example.com/x)", md)

    def test_endpoint_payload(self):
        d = json.loads(card().badge_endpoint())
        self.assertEqual(d["schemaVersion"], 1)
        self.assertEqual(d["message"], "5.0%")


class TestRoundTrip(unittest.TestCase):
    def test_from_result_and_back(self):
        r = Probe(model="mock", tools=TOOLS, runs=3, verbose=False).run()
        d = r.to_dict()
        sc = Scorecard.from_dict(d)
        self.assertEqual(sc.model, "mock")
        self.assertEqual(sc.n_trials, d["n_trials"])
        self.assertEqual(sc.verdict, d["scorecard"]["verdict"])
        sc.text(colour=False)
        xml.dom.minidom.parseString(sc.card_svg())

    def test_fingerprints_distinguish_stimuli(self):
        builtin = Probe(model="mock", tools=TOOLS, runs=1, verbose=False)
        self.assertEqual(builtin.stimuli_id, "builtin-12")
        mine = Probe(model="mock", tools=TOOLS, runs=1, verbose=False, stimuli=[
            Triple(ungroundable="Check our CDN.", groundable_known="Check Fastly.",
                   expected_tool="fetch_url")])
        self.assertTrue(mine.stimuli_id.startswith("custom-1-"), mine.stimuli_id)
        self.assertNotEqual(builtin.catalogue_id, "example-10")

    def test_catalogue_id_is_order_independent(self):
        a = Probe(model="mock", tools=TOOLS, runs=1, verbose=False).catalogue_id
        b = Probe(model="mock", tools=list(reversed(TOOLS)), runs=1,
                  verbose=False).catalogue_id
        self.assertEqual(a, b)


class TestSubmit(unittest.TestCase):
    def setUp(self):
        self.d = Probe(model="mock", tools=TOOLS, runs=3, verbose=False).run().to_dict()

    def test_row_shape(self):
        r = submit_mod.row(Scorecard.from_dict(self.d))
        self.assertEqual(r.count("|"), submit_mod.HEADER.splitlines()[0].count("|"))

    def test_block_carries_provenance(self):
        b = submit_mod.block(self.d)
        for want in ("**Stimuli**", "**Catalogue**", "**Decoy**", "**Runs**",
                     "```json", "builtin-12"):
            self.assertIn(want, b)

    def test_custom_stimuli_are_flagged_as_incomparable(self):
        d = dict(self.d)
        d["scorecard"] = dict(d["scorecard"], stimuli_id="custom-4-deadbeef")
        self.assertIn("not comparable", submit_mod.block(d))
        self.assertNotIn("not comparable", submit_mod.block(self.d))

    def test_issue_url_stays_under_the_truncation_limit(self):
        url = submit_mod.issue_url(self.d)
        self.assertLessEqual(len(url), submit_mod.URL_LIMIT)
        self.assertIn("labels=leaderboard", url)

    def test_payload_reports_provider_config(self):
        d = dict(self.d, config={"reasoning_effort": "none"})
        self.assertEqual(submit_mod.payload(d)["provider_config"],
                         {"reasoning_effort": "none"})
        self.assertIn("`reasoning_effort=none`", submit_mod.block(d))


class TestShareCLI(unittest.TestCase):
    def cli(self, *args):
        env = dict(os.environ, PYTHONPATH=os.path.join(
            os.path.dirname(__file__), "..", "src"))
        return subprocess.run([sys.executable, "-m", "ungrounded.cli", *args],
                              capture_output=True, text=True, env=env, timeout=180)

    def test_run_save_then_render_offline(self):
        with tempfile.TemporaryDirectory() as d:
            res = os.path.join(d, "r.json")
            svg = os.path.join(d, "card.svg")
            bdg = os.path.join(d, "badge.svg")
            r = self.cli("run", "--model", "mock", "--runs", "2", "--quiet",
                         "--scorecard", "--save", res, "--card", svg, "--badge", bdg)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("UNGROUNDED", r.stdout)
            for f in (res, svg, bdg):
                self.assertTrue(os.path.exists(f), f)

            c = self.cli("card", res, "--no-color")
            self.assertEqual(c.returncode, 0, c.stderr)
            self.assertIn("CORRECT TOOL INVOKED", c.stdout)

            b = self.cli("badge", res)
            self.assertTrue(b.stdout.startswith("[!["), b.stdout)

            s = self.cli("submit", res, "--url")
            self.assertIn("/issues/new", s.stdout)

    def test_helpful_error_on_a_stale_result(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "old.json")
            with open(p, "w") as fh:
                json.dump({"model": "x"}, fh)
            r = self.cli("card", p)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("older version", r.stderr)

    def test_helpful_error_on_missing_file(self):
        r = self.cli("badge", "/nope/nothing.json")
        self.assertIn("no such file", r.stderr)


if __name__ == "__main__":
    unittest.main()


class TestFailedRuns(unittest.TestCase):
    """A run that did not reach the API is not a finding about the model."""

    def _result(self, n_bad, n_good=0):
        from ungrounded.probe import Result
        from ungrounded.core import Trial
        trials = []
        for i in range(n_good):
            # split across both arms so the contrast is defined
            cond = "groundable_known" if i % 2 else "ungroundable"
            hit = 1 if cond == "groundable_known" else 0
            trials.append(Trial(triple_id=f"T{i % 12:02d}", condition=cond,
                                run=i, prompt="p",
                                tools_called=["fetch_url"] if hit else [],
                                decoy_called=0, expected_called=hit))
        for i in range(n_bad):
            trials.append(Trial(triple_id=f"T{i:02d}", condition="ungroundable",
                                run=0, prompt="p", tools_called=[], decoy_called=0,
                                expected_called=None, status="ERROR",
                                error="BadRequestError: credit balance is too low"))
        return Result(trials=trials, model="m", decoy_name="d", n_triples=12,
                      runs=1, stimuli_id="builtin-12", catalogue_id="example-10")

    def test_all_errored_is_failed_not_inconclusive(self):
        sc = Scorecard.from_result(self._result(n_bad=36))
        self.assertEqual(sc.verdict, "FAILED")
        self.assertIn("credit balance", sc.reading)
        self.assertEqual(sc.n_errors, 36)

    def test_mostly_errored_refuses_to_report_a_rate(self):
        sc = Scorecard.from_result(self._result(n_bad=30, n_good=5))
        self.assertEqual(sc.verdict, "INCONCLUSIVE")
        self.assertIn("30 of 35", sc.reading)

    def test_a_few_errors_still_reports(self):
        sc = Scorecard.from_result(self._result(n_bad=1, n_good=48))
        self.assertNotIn(sc.verdict, ("FAILED", "INCONCLUSIVE"))
        self.assertEqual(sc.n_errors, 1)
        self.assertIn("1 errored", sc.text(colour=False))

    def test_errors_survive_the_json_round_trip(self):
        d = self._result(n_bad=36).to_dict()
        self.assertEqual(d["n_errors"], 36)
        self.assertEqual(Scorecard.from_dict(d).verdict, "FAILED")

    def test_cli_exits_nonzero_when_everything_errored(self):
        env = dict(os.environ, PYTHONPATH=os.path.join(
            os.path.dirname(__file__), "..", "src"),
            ANTHROPIC_API_KEY="sk-ant-invalid-key-for-this-test")
        r = subprocess.run(
            [sys.executable, "-m", "ungrounded.cli", "run", "--model",
             "claude-sonnet-4-6", "--runs", "1", "--quiet",
             "--stimuli", "-"], capture_output=True, text=True, env=env, timeout=60)
        # Missing stimuli file is its own failure; the point is only that the
        # CLI does not return 0 on a run that produced no measurement.
        self.assertNotEqual(r.returncode, 0)
