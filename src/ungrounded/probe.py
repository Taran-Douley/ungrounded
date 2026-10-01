"""The Probe: run the grounding contrast against your own tool catalogue."""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .core import (
    CONDITIONS,
    Decoy,
    Trial,
    Triple,
    build_catalogue,
    normalise_catalogue,
)
from .providers import resolve_provider
from .stats import cluster_bootstrap_ci, cluster_permutation, rate, resolution_floor
from .stimuli import DEFAULT_TRIPLES

UNGROUNDABLE = ("ungroundable", "groundable_unknown")
GROUNDABLE = ("groundable_known",)


def _digest(parts) -> str:
    import hashlib
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:8]


def _stimuli_id(stimuli) -> str:
    """Identify the stimulus set, so leaderboard rows are comparable.

    Two runs are only comparable if they asked the same questions. A row that
    does not say which prompts produced it is not a result anyone can use.
    """
    parts = []
    for t in stimuli:
        parts += [t.ungroundable, t.groundable_known,
                  t.groundable_unknown or "", t.expected_tool or ""]
    d = _digest(parts)
    return (f"builtin-{len(stimuli)}" if d == _digest(_default_parts())
            else f"custom-{len(stimuli)}-{d}")


def _default_parts():
    parts = []
    for t in DEFAULT_TRIPLES:
        parts += [t.ungroundable, t.groundable_known,
                  t.groundable_unknown or "", t.expected_tool or ""]
    return parts


def _catalogue_id(tools) -> str:
    names = sorted(t["name"] for t in tools)
    from .stimuli import example_catalogue
    from .core import normalise_catalogue
    example = sorted(t["name"] for t in normalise_catalogue(example_catalogue()))
    if names == example:
        return f"example-{len(names)}"
    return f"custom-{len(names)}-{_digest(names)}"


@dataclass
class Result:
    trials: List[Trial]
    model: str
    decoy_name: Optional[str]
    n_triples: int
    runs: int = 0
    stimuli_id: str = "unknown"
    catalogue_id: str = "unknown"
    config: Dict[str, Any] = field(default_factory=dict)

    # ---- aggregation ----------------------------------------------------
    def _ok(self):
        return [t for t in self.trials if t.status == "OK"]

    def _clusters(self, field: str = "decoy_called"):
        out: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
        for t in self._ok():
            v = getattr(t, field)
            if v is None:
                continue
            out[t.triple_id][t.condition].append(int(v))
        return {k: dict(v) for k, v in out.items()}

    def error_summary(self):
        """(how many trials failed, what the first failure said).

        Reported rather than silently dropped: a rate computed over the few
        calls that happened to get through is not the rate you asked for.
        """
        bad = [t for t in self.trials if t.status != "OK"]
        first = ""
        if bad:
            first = (bad[0].error or bad[0].status).strip().replace("\n", " ")
            if len(first) > 120:
                first = first[:117] + "..."
        return len(bad), first

    def by_condition(self, field: str = "decoy_called"):
        agg: Dict[str, List[int]] = defaultdict(list)
        for t in self._ok():
            v = getattr(t, field)
            if v is not None:
                agg[t.condition].append(int(v))
        return dict(agg)

    def decoy_rate(self, condition: str) -> float:
        """Share of trials in ``condition`` that invoked the decoy, in percent."""
        vals = self.by_condition().get(condition, [])
        return rate(sum(vals), len(vals))

    def misselection_rate(self, condition: str) -> float:
        """Deprecated alias for :meth:`decoy_rate`, kept for 0.2.x callers."""
        return self.decoy_rate(condition)

    def ci(self, condition: str, field: str = "decoy_called"):
        per = defaultdict(list)
        for t in self._ok():
            if t.condition == condition:
                v = getattr(t, field)
                if v is not None:
                    per[t.triple_id].append(int(v))
        return cluster_bootstrap_ci(list(per.values()))

    def test(self, reps: int = 20000, field: str = "decoy_called",
             arm_a: Sequence[str] = UNGROUNDABLE,
             arm_b: Sequence[str] = GROUNDABLE):
        """Permute the condition label within each prompt.

        Defaults to the decoy contrast. The scorecard passes
        ``field="expected_called"`` with the narrower ungroundable-vs-familiar
        arms, because that pair is what the headline number reports.
        """
        return cluster_permutation(self._clusters(field), arm_a, arm_b, reps=reps)

    def scorecard(self):
        """The shareable summary: see :mod:`ungrounded.report`."""
        from .report import Scorecard
        return Scorecard.from_result(self)

    def prompts_firing(self) -> tuple:
        c = self._clusters()
        fired = sum(
            1
            for pid, conds in c.items()
            if any(sum(conds.get(k, [])) > 0 for k in UNGROUNDABLE)
        )
        return fired, len(c)

    # ---- output ---------------------------------------------------------
    def summary(self, reps: int = 20000) -> str:
        errs = len(self.trials) - len(self._ok())
        L = []
        L.append("")
        L.append("=" * 66)
        L.append(f"  ungrounded  |  model: {self.model}")
        L.append("=" * 66)
        L.append(f"  {len(self._ok())} trials, {self.n_triples} prompt triples"
                 + (f", {errs} errors excluded" if errs else ""))
        if self.decoy_name:
            L.append(f"  decoy tool: {self.decoy_name}")
        L.append("")
        L.append("  DECOY INVOKED  (by referent condition)")
        L.append(f"  {'condition':<22}{'rate':>9}   {'95% CI (clustered)':>22}")
        L.append("  " + "-" * 56)
        labels = {
            "ungroundable": "unnamed referent",
            "groundable_unknown": "named, unfamiliar",
            "groundable_known": "named, familiar",
        }
        for c in CONDITIONS:
            vals = self.by_condition().get(c)
            if not vals:
                continue
            lo, hi = self.ci(c)
            L.append(f"  {labels[c]:<22}{rate(sum(vals), len(vals)):>8.2f}%   "
                     f"{lo:>8.2f}% - {hi:.2f}%")

        exp = self.by_condition("expected_called")
        if any(exp.values()):
            L.append("")
            L.append("  CORRECT TOOL USAGE  (your expected_tool invoked)")
            for c in CONDITIONS:
                vals = exp.get(c)
                if vals:
                    L.append(f"  {labels[c]:<22}{rate(sum(vals), len(vals)):>8.2f}%")

        obs, p, note = self.test(reps=reps)
        fired, total = self.prompts_firing()
        floor = resolution_floor(total)
        L.append("")
        L.append("  UNGROUNDABLE vs GROUNDABLE")
        L.append(f"  difference          {obs:>8.2f} pp")
        L.append(f"  cluster permutation {'p = %.4g' % p if not note else note:>18}")
        L.append(f"  prompts firing      {fired:>8} / {total}")
        L.append("")
        L.append(f"  Note: with {total} prompt triples the smallest two-sided p a")
        L.append(f"  paired test on this design can produce is ~{floor:.1e}. Claims")
        L.append("  beyond that order of magnitude are not supported by the design.")
        L.append("=" * 66)
        L.append("")
        return "\n".join(L)

    def to_csv(self, path: str) -> None:
        rows = [t.as_row() for t in self.trials]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def to_dict(self) -> Dict[str, Any]:
        obs, p, note = self.test()
        fired, total = self.prompts_firing()
        exp = self.by_condition("expected_called")
        return {
            "model": self.model,
            "decoy": self.decoy_name,
            "runs": self.runs,
            "stimuli_id": self.stimuli_id,
            "catalogue_id": self.catalogue_id,
            "config": self.config,
            "n_triples": self.n_triples,
            "n_trials": len(self._ok()),
            "rates": {c: self.decoy_rate(c) for c in CONDITIONS
                      if self.by_condition().get(c)},
            "correct_tool_rates": {c: rate(sum(v), len(v))
                                   for c, v in exp.items() if v},
            "difference_pp": obs,
            "p_cluster_permutation": p,
            "p_note": note,
            "prompts_firing": fired,
            "n_errors": self.error_summary()[0],
            "resolution_floor": resolution_floor(total),
            "scorecard": self.scorecard().to_dict(),
        }


class Probe:
    """Measure how tool routing shifts when an entity in a request can't be resolved.

        from ungrounded import Probe
        r = Probe(model="claude-sonnet-4-6", tools=MY_TOOLS).run()
        print(r.summary())

    ``tools`` takes your real catalogue in Anthropic or OpenAI schema. A decoy
    is injected -- a tool none of the stimuli needs -- so that routing towards it
    is observable without a ground-truth trajectory per call. An invocation is
    not automatically an error.
    Tool order is shuffled every trial so position cannot confound condition.
    """

    def __init__(
        self,
        model: str,
        tools: Sequence[Dict[str, Any]],
        stimuli: Optional[Sequence[Triple]] = None,
        runs: int = 10,
        decoy: Optional[Decoy] = None,
        decoy_name: Optional[str] = None,
        provider: Optional[Callable] = None,
        workers: int = 6,
        seed: int = 17,
        out: Optional[str] = None,
        verbose: bool = True,
        **provider_kwargs,
    ):
        self.model = model
        self.tools = normalise_catalogue(tools)
        self.stimuli = list(stimuli) if stimuli is not None else list(DEFAULT_TRIPLES)
        for i, t in enumerate(self.stimuli):
            if t.id is None:
                t.id = f"T{i:02d}"
        self.runs = runs
        self.workers = workers
        self.seed = seed
        self.out = out
        self.verbose = verbose

        if decoy_name:
            names = {t["name"] for t in self.tools}
            if decoy_name not in names:
                raise ValueError(
                    f"decoy_name={decoy_name!r} is not in your catalogue. Either "
                    "name a tool that is in it, or leave it unset to inject one."
                )
            self.decoy = None
            self.decoy_name = decoy_name
        else:
            self.decoy = decoy or Decoy()
            self.decoy_name = self.decoy.name
            if any(t["name"] == self.decoy_name for t in self.tools):
                raise ValueError(
                    f"Your catalogue already contains {self.decoy_name!r}. Pass "
                    "decoy_name= to use it as the probe rather than injecting a copy."
                )

        self.provider = provider or resolve_provider(model, **provider_kwargs)
        self.stimuli_id = _stimuli_id(self.stimuli)
        self.catalogue_id = _catalogue_id(self.tools)

    def validate(self) -> List[str]:
        problems = []
        for t in self.stimuli:
            problems.extend(t.validate())
        if len(self.tools) < 3:
            problems.append(
                f"only {len(self.tools)} tools in the catalogue -- with a very small "
                "catalogue the decoy is one of few options and the rate will overstate"
            )
        if self.runs < 5:
            problems.append(f"runs={self.runs} is low; the clustered CI will be wide")
        expected = {t.expected_tool for t in self.stimuli if t.expected_tool}
        names = {t["name"] for t in self.tools}
        for e in expected - names:
            problems.append(f"expected_tool {e!r} is not in the catalogue")
        return problems

    def _config(self) -> Dict[str, Any]:
        """What the provider was actually called with.

        Includes anything the adapter had to change to get the request
        accepted -- notably ``reasoning_effort``, which some models require
        before they will take function tools at all. That is a deliberate
        configuration rather than the API default, so it travels with the
        result instead of being left for the reader to guess at.
        """
        cfg = {}
        for attr in ("temperature", "max_tokens"):
            v = getattr(self.provider, attr, None)
            if v is not None:
                cfg[attr] = v
        cfg.update(getattr(self.provider, "_extra", {}) or {})
        adjust = getattr(self.provider, "_adjust", {}) or {}
        cfg.update(adjust.get("set", {}))
        for bad in adjust.get("drop", ()):
            cfg.pop(bad, None)
        for old, new in adjust.get("rename", {}).items():
            if old in cfg:
                cfg[new] = cfg.pop(old)
        return {k: v for k, v in sorted(cfg.items())}

    def _grid(self):
        g = []
        for triple in self.stimuli:
            for cond, text in triple.prompts().items():
                for run in range(self.runs):
                    g.append((triple, cond, text, run))
        return g

    def run(self) -> Result:
        for w in self.validate():
            print(f"  warning: {w}", file=sys.stderr)

        grid = self._grid()
        trials: List[Trial] = []
        lock = threading.Lock()
        done = [0]

        def work(item):
            triple, cond, text, run = item
            rng = random.Random(f"{self.seed}|{triple.id}|{cond}|{run}")
            cat = build_catalogue(self.tools, self.decoy, rng)
            # context hook: providers may read these (the mock does).
            for attr, val in (("_condition", cond), ("_run", run)):
                try:
                    setattr(self.provider, attr, val)
                except Exception:
                    pass
            called, status, err = self.provider(text, cat)
            tr = Trial(
                triple_id=triple.id,
                condition=cond,
                run=run,
                prompt=text,
                tools_called=list(called),
                decoy_called=int(self.decoy_name in called),
                expected_called=(int(triple.expected_tool in called)
                                 if triple.expected_tool else None),
                status=status,
                error=err,
            )
            with lock:
                trials.append(tr)
                done[0] += 1
                if self.verbose and done[0] % 50 == 0:
                    print(f"  {done[0]}/{len(grid)}", file=sys.stderr)

        if self.verbose:
            print(f"  {len(grid)} trials "
                  f"({len(self.stimuli)} triples x {len(CONDITIONS)} conditions "
                  f"x {self.runs} runs)", file=sys.stderr)

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            list(ex.map(work, grid))

        res = Result(trials=trials, model=self.model,
                     decoy_name=self.decoy_name, n_triples=len(self.stimuli),
                     runs=self.runs, stimuli_id=self.stimuli_id,
                     catalogue_id=self.catalogue_id, config=self._config())
        if self.out:
            res.to_csv(self.out)
            if self.verbose:
                print(f"  per-trial data written to {self.out}", file=sys.stderr)
        return res
