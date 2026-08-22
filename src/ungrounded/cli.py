"""Command line interface.

    ungrounded run --tools tools.json --model claude-sonnet-4-6
    ungrounded template > stimuli.json
    ungrounded run --tools tools.json --stimuli stimuli.json --runs 10 --out trials.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .core import Decoy, Triple
from .probe import Probe
from .stimuli import TEMPLATE, example_catalogue


def _load_triples(path: str) -> List[Triple]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = []
    for i, d in enumerate(raw):
        missing = [k for k in ("ungroundable", "groundable_known") if k not in d]
        if missing:
            raise SystemExit(f"stimulus {i}: missing {', '.join(missing)}")
        out.append(
            Triple(
                id=d.get("id", f"T{i:02d}"),
                ungroundable=d["ungroundable"],
                groundable_known=d["groundable_known"],
                groundable_unknown=d.get("groundable_unknown"),
                expected_tool=d.get("expected_tool"),
            )
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ungrounded",
        description="Measure tool misselection under entity grounding failure.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="print a stimulus file to start from")
    t.add_argument("--full", action="store_true",
                   help="print the twelve built-in triples instead of a blank template")

    r = sub.add_parser("run", help="run the probe")
    r.add_argument("--tools",
                   help="JSON file: your tool catalogue (Anthropic or OpenAI schema). "
                        "Defaults to the paper's ten-tool example catalogue so you can "
                        "get a number before wiring up your own.")
    r.add_argument("--model", required=True,
                   help="e.g. claude-sonnet-4-6, gpt-5.6-terra, or 'mock' to test plumbing")
    r.add_argument("--stimuli", help="JSON file of triples (default: built-in set)")
    r.add_argument("--runs", type=int, default=10,
                   help="repetitions per prompt per condition (default 10)")
    r.add_argument("--workers", type=int, default=6)
    r.add_argument("--decoy-name",
                   help="use an existing tool as the probe instead of injecting one")
    r.add_argument("--out", help="write per-trial CSV here")
    r.add_argument("--json", action="store_true", help="print machine-readable summary")
    r.add_argument("--seed", type=int, default=17)
    r.add_argument("--quiet", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd == "template":
        if a.full:
            from .stimuli import DEFAULT_TRIPLES
            print(json.dumps(
                [{"id": x.id, "ungroundable": x.ungroundable,
                  "groundable_known": x.groundable_known,
                  "groundable_unknown": x.groundable_unknown,
                  "expected_tool": x.expected_tool} for x in DEFAULT_TRIPLES],
                indent=2))
        else:
            print(TEMPLATE, end="")
        return 0

    if a.tools:
        with open(a.tools, encoding="utf-8") as fh:
            tools = json.load(fh)
    else:
        tools = example_catalogue()
        print("  using the built-in example catalogue "
              "(pass --tools yours.json to measure your own)", file=sys.stderr)
    if isinstance(tools, dict) and "tools" in tools:
        tools = tools["tools"]

    probe = Probe(
        model=a.model,
        tools=tools,
        stimuli=_load_triples(a.stimuli) if a.stimuli else None,
        runs=a.runs,
        workers=a.workers,
        decoy_name=a.decoy_name,
        out=a.out,
        seed=a.seed,
        verbose=not a.quiet,
    )
    result = probe.run()

    if a.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.summary())
    return 0


def _entry() -> int:
    """Wrapper so piping to head/less does not produce a traceback."""
    try:
        return main()
    except BrokenPipeError:
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(_entry())
