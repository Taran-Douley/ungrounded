"""Command line interface.

    ungrounded run --tools tools.json --model claude-sonnet-4-6
    ungrounded template > stimuli.json
    ungrounded run --tools tools.json --stimuli stimuli.json --runs 10 --out trials.csv

Sharing what came out:

    ungrounded run --model M --save r.json --card card.svg --badge badge.svg
    ungrounded card r.json               # the scorecard, again, without paying
    ungrounded badge r.json --md         # one line for a README
    ungrounded submit r.json --open      # file it to the leaderboard
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .core import Decoy, Triple
from .probe import Probe
from .providers import SetupError, detect_provider, preflight, setup_help
from .report import BADGE_STYLES, REPO, Scorecard
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


def _load_result(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"no such file: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not JSON ({e}). It should be the output of "
                         "`ungrounded run --save`.")
    if "scorecard" not in d:
        raise SystemExit(
            f"{path} has no scorecard -- it was written by an older version. "
            "Re-run with `ungrounded run --save`.")
    return d


def _write(path: str, text: str, what: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"  {what} written to {path}", file=sys.stderr)


def _share(a, result_dict: dict) -> None:
    """Emit whichever shareable artefacts were asked for."""
    from . import submit as _submit

    sc = Scorecard.from_dict(result_dict)
    if getattr(a, "save", None):
        _write(a.save, json.dumps(result_dict, indent=2) + "\n", "result")
    if getattr(a, "card", None):
        _write(a.card, sc.card_svg(theme=getattr(a, "theme", "auto")), "card")
    if getattr(a, "badge", None):
        _write(a.badge, sc.badge_svg(style=a.badge_style), "badge")
    if getattr(a, "badge_md", False):
        print(sc.badge_md(style=a.badge_style))
    if getattr(a, "submit", False):
        print()
        print(_submit.block(result_dict))
        print()
        print(f"  file it: {_submit.issue_url(result_dict)}", file=sys.stderr)


def _add_share_args(p, badge_md_help=True):
    g = p.add_argument_group("sharing")
    g.add_argument("--save", metavar="FILE",
                   help="write the full machine-readable result here; "
                        "`card`, `badge` and `submit` all read it back")
    g.add_argument("--card", metavar="FILE.svg",
                   help="write the scorecard as an SVG for a README or a slide")
    g.add_argument("--badge", metavar="FILE.svg", help="write a badge SVG")
    g.add_argument("--badge-md", action="store_true",
                   help="print a shields.io badge line to paste into a README")
    g.add_argument("--badge-style", choices=sorted(BADGE_STYLES), default="rate",
                   help="rate: 5.0%%  ·  collapse: 84%% -> 5.0%%  ·  verdict: COLLAPSE")
    g.add_argument("--theme", choices=("auto", "light", "dark"), default="auto",
                   help="SVG card theme (default: follows the reader's)")
    g.add_argument("--submit", action="store_true",
                   help="print a leaderboard submission block and a prefilled link")
    return g


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
    r.add_argument("--model",
                   help="e.g. claude-sonnet-4-6, gpt-5.6-terra, or 'mock' to test "
                        "plumbing. Omit it and whichever provider you have "
                        "configured is used.")
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
    r.add_argument("--no-preflight", dest="preflight", action="store_false",
                   help="skip the single test call made before the run starts")
    r.add_argument("--scorecard", action="store_true",
                   help="print only the scorecard -- the one-screenshot summary")
    _add_share_args(r)

    c = sub.add_parser("card", help="re-render the scorecard from a saved result")
    c.add_argument("result", help="a JSON file from `ungrounded run --save`")
    c.add_argument("--svg", metavar="FILE.svg", help="write the SVG card here")
    c.add_argument("--theme", choices=("auto", "light", "dark"), default="auto")
    c.add_argument("--no-color", action="store_true", help="plain text, no ANSI")

    b = sub.add_parser("badge", help="make a badge from a saved result")
    b.add_argument("result", help="a JSON file from `ungrounded run --save`")
    b.add_argument("--svg", metavar="FILE.svg", help="write a self-hosted badge SVG")
    b.add_argument("--endpoint", metavar="FILE.json",
                   help="write a shields.io endpoint payload")
    b.add_argument("--style", choices=sorted(BADGE_STYLES), default="rate",
                   help="rate: 5.0%%  ·  collapse: 84%% -> 5.0%%  ·  verdict: COLLAPSE")
    b.add_argument("--label", default="ungrounded", help="badge left-hand text")
    b.add_argument("--link", default=REPO, help="where the badge links to")
    b.add_argument("--url", action="store_true", help="print the shields.io URL only")

    sub.add_parser("doctor", help="check what is configured and working")

    su = sub.add_parser("submit", help="turn a saved result into a leaderboard entry")
    su.add_argument("result", help="a JSON file from `ungrounded run --save`")
    su.add_argument("--open", dest="open_", action="store_true",
                    help="file the issue with `gh`, or open a prefilled one")
    su.add_argument("--url", action="store_true", help="print the prefilled link only")
    su.add_argument("--repo", default=REPO, help="submit somewhere else")

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

    if a.cmd == "doctor":
        return _doctor()

    if a.cmd == "card":
        d = _load_result(a.result)
        sc = Scorecard.from_dict(d)
        if a.svg:
            _write(a.svg, sc.card_svg(theme=a.theme), "card")
        print(sc.text(colour=False if a.no_color else None))
        return 0

    if a.cmd == "badge":
        sc = Scorecard.from_dict(_load_result(a.result))
        if a.svg:
            _write(a.svg, sc.badge_svg(style=a.style, label=a.label), "badge")
        if a.endpoint:
            _write(a.endpoint, sc.badge_endpoint(style=a.style, label=a.label) + "\n",
                   "endpoint")
        if a.url:
            print(sc.badge_url(style=a.style, label=a.label))
        elif not (a.svg or a.endpoint):
            print(sc.badge_md(style=a.style, label=a.label, link=a.link))
        return 0

    if a.cmd == "submit":
        from . import submit as _submit
        d = _load_result(a.result)
        if a.url:
            print(_submit.issue_url(d, a.repo))
            return 0
        if a.open_:
            return _submit.file_issue(d, a.repo)
        print(_submit.block(d))
        print()
        print(f"  file it: {_submit.issue_url(d, a.repo)}", file=sys.stderr)
        return 0

    autodetected = None
    if not a.model:
        name, model = detect_provider()
        if not model:
            raise SetupError(setup_help())
        a.model, autodetected = model, name
        print(f"  no --model given; using {model} ({name} is configured). "
              f"Pass --model to choose another.", file=sys.stderr)

    # Resolve the provider before anything else is announced, so a missing
    # key is the first thing printed rather than the third.
    from .providers import resolve_provider
    provider = resolve_provider(a.model)

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
        provider=provider,
    )
    if a.preflight and a.model.lower() not in ("mock", "mock-model"):
        if not a.quiet:
            print("  checking credentials with one call...", file=sys.stderr)
        try:
            preflight(probe.provider, a.model)
        except SetupError as e:
            # We chose this provider on the user's behalf, so if it does not
            # work, name the other one they have configured rather than
            # leaving them to guess that a second option exists.
            others = [f"--model {m}" for n, m in _configured()
                      if n != autodetected] if autodetected else []
            if others:
                raise SetupError(f"{e}\n\nAlso configured: {', '.join(others)}")
            raise

    result = probe.run()
    as_dict = result.to_dict()

    if a.json:
        print(json.dumps(as_dict, indent=2))
    elif a.scorecard:
        print(result.scorecard().text())
    else:
        print(result.summary())
        print(result.scorecard().text())

    _share(a, as_dict)

    n_errors, first = result.error_summary()
    if not result._ok():
        print(f"  every trial errored -- nothing was measured. First: {first}",
              file=sys.stderr)
        return 1
    if n_errors:
        print(f"  note: {n_errors} of {len(result.trials)} trials errored and are "
              f"excluded. First: {first}", file=sys.stderr)
    return 0


def _configured():
    """Every provider with both an SDK and a key, as (name, default model)."""
    from .providers import PROVIDERS, status
    return [(n, PROVIDERS[n][2]) for n, i in status().items()
            if i["sdk"] and i["key"]]


def _doctor() -> int:
    """Say what is configured, then prove it with one call each."""
    import os

    from .providers import CONSOLES, PROVIDERS, resolve_provider, status

    st = status()
    print()
    print("  ungrounded doctor")
    print()
    ready = []
    for name, info in st.items():
        env, extra, default, _ = PROVIDERS[name]
        sdk = "installed" if info["sdk"] else "MISSING"
        key = "set" if info["key"] else "MISSING"
        print(f"  {name:<12} sdk {sdk:<10} {env} {key}")
        if name == "anthropic" and info["key"]:
            ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
            print(f"               ANTHROPIC_WORKSPACE_ID "
                  f"{'set' if ws else 'unset (only needed for identity-linked keys)'}")
        if not info["sdk"]:
            print(f"               pip install 'ungrounded[{extra}]'")
        if not info["key"]:
            print(f"               export {env}='...'   # {CONSOLES[name]}")
        if info["sdk"] and info["key"]:
            ready.append((name, default))
    print(f"  {'mock':<12} always available -- ungrounded run --model mock")
    print()

    if not ready:
        print("  Nothing is configured for a live run yet.")
        print("  `ungrounded run --model mock` works right now regardless.")
        print()
        return 1

    rc = 0
    for name, default in ready:
        print(f"  {name}: one test call to {default}...", end=" ", flush=True)
        try:
            preflight(resolve_provider(default), default)
            print("ok")
        except SetupError as e:
            rc = 1
            print("FAILED")
            for line in str(e).splitlines():
                if line.strip():
                    print(f"    {line}")
        except Exception as e:  # pragma: no cover
            rc = 1
            print(f"FAILED\n    {type(e).__name__}: {e}")
    print()
    return rc


def _entry() -> int:
    """Wrapper so piping to head/less does not produce a traceback."""
    try:
        return main()
    except SetupError as e:
        # An environment problem, not a bug. A traceback would tell someone
        # who has not set an API key nothing they can do about it.
        print(f"\n{e}\n", file=sys.stderr)
        return 2
    except BrokenPipeError:
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(_entry())
