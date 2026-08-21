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
from dataclasses import dataclass
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


@dataclass
class Result:
    trials: List[Trial]
    model: str
    decoy_name: Optional[str]
    n_triples: int

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

    def by_condition(self, field: str = "decoy_called"):
        agg: Dict[str, List[int]] = defaultdict(list)
        for t in self._ok():
            v = getattr(t, field)
            if v is not None:
                agg[t.condition].append(int(v))
        return dict(agg)

    def misselection_rate(self, condition: str) -> float:
        vals = self.by_condition().get(condition, [])
        return rate(sum(vals), len(vals))

    def ci(self, condition: str):
        per = defaultdict(list)
        for t in self._ok():
            if t.condition == condition:
                per[t.triple_id].append(t.decoy_called)
        return cluster_bootstrap_ci(list(per.values()))

    def test(self, reps: int = 20000):
        return cluster_permutation(self._clusters(), UNGROUNDABLE, GROUNDABLE, reps=reps)

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
        L.append("  MISSELECTION RATE  (decoy invoked, by grounding condition)")
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
        return {
            "model": self.model,
            "decoy": self.decoy_name,
            "n_triples": self.n_triples,
            "n_trials": len(self._ok()),
            "rates": {c: self.misselection_rate(c) for c in CONDITIONS
                      if self.by_condition().get(c)},
            "difference_pp": obs,
            "p_cluster_permutation": p,
            "p_note": note,
            "prompts_firing": fired,
            "resolution_floor": resolution_floor(total),
        }


class Probe:
    """Measure tool misselection under entity grounding failure.

        from ungrounded import Probe
        r = Probe(model="claude-sonnet-4-6", tools=MY_TOOLS).run()
        print(r.summary())

    ``tools`` takes your real catalogue in Anthropic or OpenAI schema. A decoy
    is injected -- a tool nothing in the stimulus set should call -- so that
    misselection is observable without a ground-truth trajectory per call.
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
                     decoy_name=self.decoy_name, n_triples=len(self.stimuli))
        if self.out:
            res.to_csv(self.out)
            if self.verbose:
                print(f"  per-trial data written to {self.out}", file=sys.stderr)
        return res
