"""Prompt-clustered inference. Pure stdlib -- no numpy, scipy or statsmodels.

Why clustering matters here: you run each prompt several times, so trials
within a prompt are not independent. Treating them as independent is
pseudo-replication -- it inflates the effective sample size and produces
p-values that are far too small. The unit of analysis is the *prompt*, not
the trial, and with a dozen prompts that is the number governing precision.

The primary test is a permutation test that shuffles the condition label
*within* each prompt. It assumes nothing about the distribution and stays
valid when a cell contains zero events, which is common here and which
breaks logistic regression outright.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple


def rate(hits: int, n: int) -> float:
    return 100.0 * hits / n if n else 0.0


def cluster_bootstrap_ci(
    by_cluster: Sequence[Sequence[int]], reps: int = 4000, seed: int = 17
) -> Tuple[float, float]:
    """Resample whole prompts, not trials.

    The interval then reflects uncertainty about which prompts you happened
    to choose, which is the real uncertainty in a study with a dozen of them.
    """
    groups = [list(g) for g in by_cluster if g]
    k = len(groups)
    if k == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        pool = []
        for _ in range(k):
            pool.extend(groups[rng.randrange(k)])
        means.append(sum(pool) / len(pool) if pool else 0.0)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return (100.0 * lo, 100.0 * hi)


def cluster_permutation(
    clusters: Dict[str, Dict[str, List[int]]],
    arm_a: Sequence[str],
    arm_b: Sequence[str],
    reps: int = 20000,
    seed: int = 17,
) -> Tuple[float, float, str]:
    """Permute the condition label within each prompt.

    ``clusters`` maps prompt id -> condition -> list of 0/1 outcomes.
    Returns (observed rate difference in percentage points, p, note).
    """
    rng = random.Random(seed)

    def split(assign):
        a = b = na = nb = 0
        for pid, conds in clusters.items():
            labels, values = [], []
            for cond, vals in conds.items():
                arm = assign.get((pid, cond))
                if arm is None:
                    continue
                labels.extend([arm] * len(vals))
                values.extend(vals)
            if not values:
                continue
            for lab, v in zip(labels, values):
                if lab == 0:
                    a += v
                    na += 1
                else:
                    b += v
                    nb += 1
        return a, na, b, nb

    base = {}
    for pid, conds in clusters.items():
        for cond in conds:
            if cond in arm_a:
                base[(pid, cond)] = 0
            elif cond in arm_b:
                base[(pid, cond)] = 1
    a, na, b, nb = split(base)
    if na == 0 or nb == 0:
        return (0.0, float("nan"), "one arm is empty")
    obs = rate(a, na) - rate(b, nb)

    count = 0
    for _ in range(reps):
        shuffled = {}
        for pid, conds in clusters.items():
            keys = [c for c in conds if (pid, c) in base]
            labs = [base[(pid, c)] for c in keys]
            rng.shuffle(labs)
            for c, lab in zip(keys, labs):
                shuffled[(pid, c)] = lab
        a2, na2, b2, nb2 = split(shuffled)
        if abs(rate(a2, na2) - rate(b2, nb2)) >= abs(obs) - 1e-12:
            count += 1
    p = (count + 1) / (reps + 1)
    floor = 1.0 / (reps + 1)
    note = f"p < {floor:.0e} (Monte Carlo floor)" if p <= floor * 1.5 else ""
    return (obs, p, note)


def resolution_floor(n_clusters: int) -> float:
    """Smallest two-sided p a paired test over this many prompts can produce.

    Worth reporting. With twelve prompts nothing below roughly 5e-4 is
    obtainable no matter how large the effect, so any claim beyond that
    order of magnitude is not supported by the design.
    """
    if n_clusters < 1:
        return 1.0
    return min(1.0, 2.0 / (2 ** n_clusters))
