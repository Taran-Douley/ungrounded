"""Turn a finished run into a leaderboard submission.

    ungrounded submit result.json            # print the block, and a link
    ungrounded submit result.json --open     # file the issue for me

A submission is a table row plus the provenance needed to believe it: which
stimuli, which catalogue, how many runs, and the exact provider configuration
the adapter ended up using. A row without those is not comparable to the rows
above it, so they are assembled for you rather than requested in prose.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional
from urllib.parse import quote

from .report import REPO, Scorecard

ISSUE_LABEL = "leaderboard"


def _fmt(v: Optional[float], suffix: str = "%") -> str:
    return "—" if v is None else f"{v:.1f}{suffix}"


def row(sc: Scorecard) -> str:
    """One markdown row in the README leaderboard's shape."""
    return (f"| `{sc.model}` | {_fmt(sc.ungrounded)} | {_fmt(sc.unfamiliar)} | "
            f"{_fmt(sc.grounded)} | {_fmt(sc.decoy_ungrounded)} | "
            f"{sc.verdict} | {sc.stimuli_id} · {sc.runs} runs |")


HEADER = ("| Model | Unnamed referent | Named, unfamiliar | Named, familiar | "
          "Decoy rate (unnamed) | Verdict | Provenance |\n"
          "|---|---|---|---|---|---|---|")


def payload(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """The machine-readable half, so rows can be ingested without retyping."""
    sc = Scorecard.from_dict(result_dict)
    return {
        "model": sc.model,
        "correct_tool": {
            "ungroundable": sc.ungrounded,
            "groundable_unknown": sc.unfamiliar,
            "groundable_known": sc.grounded,
        },
        "decoy_rate_ungroundable": sc.decoy_ungrounded,
        "gap_pp": sc.gap_pp,
        "retention": sc.retention,
        "verdict": sc.verdict,
        "p_cluster_permutation": None if sc.p != sc.p else sc.p,
        "prompts_firing": f"{sc.prompts_firing}/{sc.n_triples}",
        "runs": sc.runs,
        "n_trials": sc.n_trials,
        "stimuli": sc.stimuli_id,
        "catalogue": sc.catalogue_id,
        "decoy": sc.decoy,
        "provider_config": result_dict.get("config", {}),
        "ungrounded_version": sc.version,
        "measured": sc.measured,
    }


def block(result_dict: Dict[str, Any], scorecard_text: bool = True) -> str:
    """The copy-pasteable submission. Paste anywhere; it stands on its own."""
    sc = Scorecard.from_dict(result_dict)
    cfg = result_dict.get("config") or {}
    custom = not sc.stimuli_id.startswith("builtin")
    L = [f"### `{sc.model}` — {sc.verdict}", ""]
    L += [HEADER, row(sc), ""]
    if scorecard_text:
        L += ["<details><summary>Scorecard</summary>", "",
              "```", sc.text(colour=False), "```", "", "</details>", ""]
    L += ["<details><summary>Machine-readable</summary>", "",
          "```json", json.dumps(payload(result_dict), indent=2), "```",
          "", "</details>", ""]
    L.append(f"**Stimuli** `{sc.stimuli_id}` · **Catalogue** `{sc.catalogue_id}` "
             f"· **Decoy** `{sc.decoy}` · **Runs** {sc.runs} "
             f"· **ungrounded** {sc.version}")
    if cfg:
        L.append("**Provider config** "
                 + ", ".join(f"`{k}={v}`" for k, v in cfg.items()))
    if custom:
        L.append("")
        L.append("> Ran against custom stimuli, so this row is not comparable "
                 "to the built-in rows and should be listed separately.")
    return "\n".join(L)


#: Browsers and proxies start truncating query strings past roughly this.
URL_LIMIT = 7500


def issue_url(result_dict: Dict[str, Any], repo: str = REPO) -> str:
    """A prefilled 'new issue' link. No `gh`, no account setup, one click.

    Drops the rendered scorecard from the prefill if the URL would get long
    enough to be truncated in transit -- a short, complete body beats a long
    one that arrives cut in half. The table row and the JSON always survive.
    """
    sc = Scorecard.from_dict(result_dict)
    title = f"leaderboard: {sc.model} — {sc.verdict} ({_fmt(sc.ungrounded)})"

    def build(**kw):
        return (f"{repo.rstrip('/')}/issues/new"
                f"?labels={quote(ISSUE_LABEL)}"
                f"&title={quote(title)}&body={quote(block(result_dict, **kw))}")

    url = build()
    if len(url) > URL_LIMIT:
        url = build(scorecard_text=False)
    return url


def file_issue(result_dict: Dict[str, Any], repo: str = REPO,
               open_browser: bool = True) -> int:
    """Submit with `gh` if it is here and authenticated; otherwise open a link."""
    sc = Scorecard.from_dict(result_dict)
    title = f"leaderboard: {sc.model} — {sc.verdict} ({_fmt(sc.ungrounded)})"
    slug = repo.rstrip("/").split("github.com/")[-1]
    if shutil.which("gh"):
        try:
            r = subprocess.run(
                ["gh", "issue", "create", "--repo", slug, "--title", title,
                 "--label", ISSUE_LABEL, "--body-file", "-"],
                input=block(result_dict), text=True, capture_output=True, timeout=60)
            if r.returncode == 0:
                print(r.stdout.strip())
                return 0
            print(f"  gh could not file it ({r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'no output'});"
                  " falling back to a link", file=sys.stderr)
        except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover
            print(f"  gh failed ({e}); falling back to a link", file=sys.stderr)

    url = issue_url(result_dict, repo)
    if open_browser:
        import webbrowser
        try:
            if webbrowser.open(url):
                print("  opened a prefilled issue in your browser", file=sys.stderr)
                return 0
        except Exception:  # pragma: no cover
            pass
    print(url)
    return 0
