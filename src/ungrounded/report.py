"""Shareable output: the scorecard, the SVG card, and the badge.

Three renderings of the same six numbers, so a run can leave the terminal:

    Scorecard.from_result(r).text()      # boxed block, made to be screenshotted
    Scorecard.from_result(r).card_svg()  # a card for a README or a slide
    Scorecard.from_result(r).badge_md()  # one line, shields.io, no hosting

The headline is **correct tool usage under an unnamed referent** -- your
``expected_tool`` invoked when the entity in the request cannot be grounded.
Higher is better. It is reported against the same rate under a familiar named
entity, because the pair is the finding and either number alone is not: a
model that never reaches the right tool scores a low headline for reasons
that have nothing to do with grounding, and the scorecard says so rather than
grading it.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------- verdicts --

#: retention -> (verdict, one-line reading). Retention is the share of correct
#: tool use that survives when the entity stops being groundable.
_BANDS = (
    (0.75, "ROBUST", "grounding barely moves tool choice"),
    (0.40, "DEGRADED", "tool choice is noticeably worse without a groundable entity"),
    (0.10, "BRITTLE", "tool choice mostly fails without a groundable entity"),
    (0.00, "COLLAPSE", "tool choice fails almost entirely without a groundable entity"),
)

_COLOURS = {
    "ROBUST": ("brightgreen", "\033[32m", "#3fb950"),
    "FAILED": ("lightgrey", "\033[31m", "#f85149"),
    "DEGRADED": ("yellow", "\033[33m", "#d29922"),
    "BRITTLE": ("orange", "\033[33m", "#db6d28"),
    "COLLAPSE": ("red", "\033[31m", "#f85149"),
    "NO EFFECT": ("lightgrey", "\033[36m", "#8b949e"),
    "INCONCLUSIVE": ("lightgrey", "\033[90m", "#8b949e"),
}

#: A grounded rate below this means the model does not reach the right tool
#: even in the easy condition, so the contrast is not about grounding.
FLOOR = 20.0


def _verdict(grounded: Optional[float], ungrounded: Optional[float],
             p: float, runs: int) -> Tuple[str, str, Optional[float]]:
    """Return (verdict, reading, retention). Refuses to grade weak evidence."""
    if grounded is None or ungrounded is None:
        return ("INCONCLUSIVE",
                "no expected_tool on your stimuli, so correct tool use is unmeasured",
                None)
    if grounded < FLOOR:
        return ("INCONCLUSIVE",
                f"the model reaches the right tool only {grounded:.1f}% of the time "
                "even when the entity is familiar, so this says nothing about grounding",
                None)
    retention = ungrounded / grounded if grounded else 0.0
    if p == p and p > 0.05:  # p == p filters NaN
        return ("NO EFFECT",
                f"correct tool use is statistically indistinguishable across "
                f"conditions (p = {p:.3g})",
                retention)
    for threshold, name, reading in _BANDS:
        if retention >= threshold:
            return (name, reading, retention)
    return ("COLLAPSE", _BANDS[-1][2], retention)


# --------------------------------------------------------------- scorecard --


@dataclass
class Scorecard:
    """The screenshot-sized summary of a run."""

    model: str
    grounded: Optional[float]        # correct-tool rate, named familiar entity
    ungrounded: Optional[float]      # correct-tool rate, unnamed referent
    unfamiliar: Optional[float]      # correct-tool rate, named unfamiliar entity
    ci_grounded: Tuple[float, float]
    ci_ungrounded: Tuple[float, float]
    decoy_ungrounded: Optional[float]  # misselection rate, unnamed referent
    gap_pp: Optional[float]
    retention: Optional[float]
    p: float
    p_note: str
    prompts_firing: int
    n_triples: int
    n_trials: int
    runs: int
    decoy: Optional[str]
    stimuli_id: str
    catalogue_id: str
    verdict: str
    reading: str
    version: str
    measured: str
    n_errors: int = 0
    error_note: str = ""

    # ---- construction ---------------------------------------------------
    @classmethod
    def from_result(cls, result, runs: int = 0, stimuli_id: str = "",
                    catalogue_id: str = "") -> "Scorecard":
        from . import __version__

        exp = result.by_condition("expected_called")

        def pct(cond):
            v = exp.get(cond)
            return (100.0 * sum(v) / len(v)) if v else None

        grounded, ungrounded = pct("groundable_known"), pct("ungroundable")
        _, p, note = result.test(field="expected_called",
                                 arm_a=("ungroundable",),
                                 arm_b=("groundable_known",))
        runs = runs or getattr(result, "runs", 0)
        verdict, reading, retention = _verdict(grounded, ungrounded, p, runs)

        # A run where the calls did not go through is not a measurement of the
        # model. Say that, rather than reporting the empty result as a finding.
        n_errors, first = result.error_summary()
        n_ok = len(result._ok())
        if n_ok == 0:
            verdict, retention = "FAILED", None
            reading = f"every trial errored, so nothing was measured — {first}"
        elif n_errors > 0.2 * (n_ok + n_errors):
            verdict, retention = "INCONCLUSIVE", None
            reading = (f"{n_errors} of {n_ok + n_errors} trials errored, too many "
                       f"to read the rest as a rate — {first}")
        fired, total = result.prompts_firing()
        dec = result.by_condition("decoy_called").get("ungroundable")
        return cls(
            model=result.model,
            grounded=grounded,
            ungrounded=ungrounded,
            unfamiliar=pct("groundable_unknown"),
            ci_grounded=result.ci("groundable_known", field="expected_called"),
            ci_ungrounded=result.ci("ungroundable", field="expected_called"),
            decoy_ungrounded=(100.0 * sum(dec) / len(dec)) if dec else None,
            gap_pp=(grounded - ungrounded
                    if grounded is not None and ungrounded is not None else None),
            retention=retention,
            p=p,
            p_note=note,
            prompts_firing=fired,
            n_triples=total or result.n_triples,
            n_trials=len(result._ok()),
            runs=runs,
            decoy=result.decoy_name,
            stimuli_id=stimuli_id or getattr(result, "stimuli_id", "unknown"),
            catalogue_id=catalogue_id or getattr(result, "catalogue_id", "unknown"),
            verdict=verdict,
            reading=reading,
            version=__version__,
            measured=_dt.date.today().isoformat(),
            n_errors=n_errors,
            error_note=first,
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Scorecard":
        """Rebuild from a saved ``--save`` JSON, so card/badge work offline."""
        s = d.get("scorecard", d)
        fields = {f: s.get(f) for f in cls.__dataclass_fields__}
        for k in ("ci_grounded", "ci_ungrounded"):
            fields[k] = tuple(fields.get(k) or (0.0, 0.0))
        fields["model"] = fields.get("model") or d.get("model", "unknown")
        for k in ("p",):
            fields[k] = float("nan") if fields.get(k) is None else fields[k]
        for k in ("prompts_firing", "n_triples", "n_trials", "runs", "n_errors"):
            fields[k] = int(fields.get(k) or 0)
        for k in ("p_note", "verdict", "reading", "version", "measured",
                  "stimuli_id", "catalogue_id", "error_note"):
            fields[k] = fields.get(k) or ""
        return cls(**fields)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ci_grounded"] = list(self.ci_grounded)
        d["ci_ungrounded"] = list(self.ci_ungrounded)
        return d

    # ---- shared bits ----------------------------------------------------
    @property
    def headline(self) -> str:
        """The badge number: correct tool use under an unnamed referent."""
        return "n/a" if self.ungrounded is None else f"{self.ungrounded:.1f}%"

    @property
    def collapse(self) -> str:
        if self.grounded is None or self.ungrounded is None:
            return "n/a"
        return f"{self.grounded:.0f}% → {self.ungrounded:.1f}%"

    def _p_text(self) -> str:
        if self.p != self.p:
            return "p n/a"
        if self.p_note:
            return self.p_note.split(" (")[0]
        return f"p = {self.p:.3g}"

    def _caveats(self) -> list:
        out = []
        if self.runs and self.runs < 10:
            out.append(f"--runs {self.runs} is low; read the intervals, not the points")
        if self.n_triples and self.n_triples < 8:
            out.append(f"{self.n_triples} triples caps precision")
        return out

    # ---- terminal ------------------------------------------------------
    def text(self, colour: Optional[bool] = None) -> str:
        """The boxed block. This is the thing that gets screenshotted."""
        if colour is None:
            import sys
            colour = sys.stdout.isatty()
        W = 62
        BAR = 25
        DIM, BOLD, OFF = ("\033[90m", "\033[1m", "\033[0m") if colour else ("", "", "")
        VC = _COLOURS.get(self.verdict, _COLOURS["INCONCLUSIVE"])[1] if colour else ""

        L = ["╭" + "─" * W + "╮"]

        def row(s="", pre="", post=""):
            L.append("│" + pre + s + " " * max(0, W - _vis(s)) + post + "│")

        def rule():
            L.append("├" + "─" * W + "┤")

        row(f"  {BOLD}UNGROUNDED{OFF}   correct tool use vs entity grounding")
        rule()
        row()
        row(f"  model      {BOLD}{self.model}{OFF}")
        row()
        row(f"  {BOLD}CORRECT TOOL INVOKED{OFF}   (your expected_tool)")
        for label, val, hi in (
            ("named, familiar", self.grounded, True),
            ("named, unfamiliar", self.unfamiliar, None),
            ("unnamed referent", self.ungrounded, False),
        ):
            if val is None:
                continue
            filled = int(round(BAR * val / 100.0))
            bar = "█" * filled + "░" * (BAR - filled)
            if colour:
                bar = ("\033[32m" if hi else VC if hi is False else DIM) + bar + OFF
            row(f"    {label:<18}{bar}  {val:>5.1f}%")
        row()
        bits = []
        if self.gap_pp is not None:
            bits.append(f"gap {self.gap_pp:.1f} pp")
        if self.retention is not None:
            bits.append(f"{self.retention * 100:.0f}% retained")
        bits.append(self._p_text())
        bits.append(f"{self.prompts_firing}/{self.n_triples} prompts")
        for line in _wrap(" · ".join(bits), W - 6):
            row(f"    {DIM}{line}{OFF}")
        row()
        rule()
        head = f"  {VC}{BOLD}{self.verdict}{OFF}"
        indent = 14
        for i, line in enumerate(_wrap(self.reading, W - indent - 2)):
            if i == 0:
                row(head + " " * (indent - 2 - len(self.verdict)) + line)
            else:
                row(" " * indent + line)
        for c in self._caveats():
            for line in _wrap("note: " + c, W - indent - 2):
                row(" " * indent + f"{DIM}{line}{OFF}")
        rule()
        prov = f"{self.n_trials} trials · {self.n_triples} triples · " \
               f"{self.stimuli_id} · {self.catalogue_id}"
        if self.n_errors:
            prov += f" · {self.n_errors} errored"
        row(f"  {DIM}{prov}{OFF}")
        row(f"  {DIM}ungrounded {self.version} · {self.measured} · "
            f"pip install ungrounded{OFF}")
        L.append("╰" + "─" * W + "╯")
        return "\n".join(L)


def _vis(s: str) -> int:
    """Visible width, ignoring ANSI escapes."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            j = s.find("m", i)
            i = len(s) if j < 0 else j + 1
            continue
        out += 1
        i += 1
    return out


def _wrap(text: str, width: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines or [""]


# -------------------------------------------------------------- svg card ---

_CARD_CSS = """
  .bg{fill:#ffffff}.fg{fill:#1f2328}.mu{fill:#59636e}.tr{fill:#d1d9e0}
  .ln{stroke:#d1d9e0}
  @media (prefers-color-scheme:dark){
    .bg{fill:#0d1117}.fg{fill:#e6edf3}.mu{fill:#8b949e}.tr{fill:#21262d}
    .ln{stroke:#30363d}}
"""
_CARD_CSS_LIGHT = """
  .bg{fill:#ffffff}.fg{fill:#1f2328}.mu{fill:#59636e}.tr{fill:#d1d9e0}
  .ln{stroke:#d1d9e0}
"""
_CARD_CSS_DARK = """
  .bg{fill:#0d1117}.fg{fill:#e6edf3}.mu{fill:#8b949e}.tr{fill:#21262d}
  .ln{stroke:#30363d}
"""

_FONT = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
         "'Liberation Mono',monospace")


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _card_svg(sc: "Scorecard", theme: str = "auto") -> str:
    css = {"light": _CARD_CSS_LIGHT, "dark": _CARD_CSS_DARK}.get(theme, _CARD_CSS)
    accent = _COLOURS.get(sc.verdict, _COLOURS["INCONCLUSIVE"])[2]

    # Height follows the content: a stimulus set with no ``groundable_unknown``
    # draws two bars, not three, and should not leave a band of empty card.
    bar_rows = sum(1 for v in (sc.grounded, sc.unfamiliar, sc.ungrounded)
                   if v is not None)
    reading_lines = _wrap(sc.reading, 52)
    _bars_end = 160 + 32 * bar_rows
    _verdict_top = _bars_end + 36
    _body_end = max(_verdict_top + 26,
                    _verdict_top + 12 + (len(reading_lines) - 1) * 15 + 6)
    W, H = 700, _body_end + 66
    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="ungrounded scorecard for {_esc(sc.model)}: '
        f'{_esc(sc.headline)} correct tool use under an unnamed referent">',
        f"<style>{css}</style>",
        f'<rect width="{W}" height="{H}" rx="10" class="bg"/>',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" '
        f'fill="none" class="ln"/>',
        f'<g font-family="{_FONT}">',
    ]

    def t(x, y, s, size=13, cls="fg", weight="normal", anchor="start", fill=None):
        f = f' fill="{fill}"' if fill else ""
        c = "" if fill else f' class="{cls}"'
        return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}"'
                f' text-anchor="{anchor}"{c}{f}>{_esc(s)}</text>')

    P = 28
    o.append(t(P, 42, "UNGROUNDED", 17, weight="700"))
    o.append(t(P + 132, 42, "correct tool use vs entity grounding", 12, "mu"))
    o.append(f'<line x1="{P}" y1="60" x2="{W-P}" y2="60" class="ln"/>')

    o.append(t(P, 92, "model", 11, "mu"))
    o.append(t(P + 74, 92, sc.model[:38], 15, weight="700"))

    o.append(t(P, 132, "CORRECT TOOL INVOKED", 11, "mu", weight="700"))
    rows = [("named, familiar", sc.grounded, "#3fb950"),
            ("named, unfamiliar", sc.unfamiliar, "#8b949e"),
            ("unnamed referent", sc.ungrounded, accent)]
    y = 160
    BX, BW = 196, 336
    for label, val, colour in rows:
        if val is None:
            continue
        o.append(t(P, y + 11, label, 12, "mu"))
        o.append(f'<rect x="{BX}" y="{y}" width="{BW}" height="14" rx="7" class="tr"/>')
        w = max(3.0, BW * val / 100.0)
        o.append(f'<rect x="{BX}" y="{y}" width="{w:.1f}" height="14" rx="7" '
                 f'fill="{colour}"/>')
        o.append(t(W - P, y + 12, f"{val:.1f}%", 13, weight="700", anchor="end"))
        y += 32

    bits = []
    if sc.gap_pp is not None:
        bits.append(f"gap {sc.gap_pp:.1f} pp")
    if sc.retention is not None:
        bits.append(f"{sc.retention * 100:.0f}% retained")
    bits.append(sc._p_text())
    bits.append(f"{sc.prompts_firing}/{sc.n_triples} prompts firing")
    o.append(t(P, y + 14, "  ·  ".join(bits), 11, "mu"))

    vy = _verdict_top
    vw = 11 + 9 * len(sc.verdict)
    o.append(f'<rect x="{P}" y="{vy}" width="{vw}" height="26" rx="5" '
             f'fill="{accent}" fill-opacity="0.16"/>')
    o.append(t(P + 6, vy + 18, sc.verdict, 13, weight="700", fill=accent))
    for i, line in enumerate(reading_lines):
        o.append(t(P + vw + 12, vy + 12 + i * 15, line, 12, "mu"))

    fy = _body_end + 24
    o.append(f'<line x1="{P}" y1="{fy - 18}" x2="{W-P}" y2="{fy - 18}" class="ln"/>')
    o.append(t(P, fy, f"{sc.n_trials} trials  ·  {sc.n_triples} triples  ·  "
                      f"{sc.stimuli_id}  ·  {sc.catalogue_id}", 10, "mu"))
    o.append(t(P, fy + 16, f"ungrounded {sc.version}  ·  {sc.measured}  ·  "
                           f"pip install ungrounded", 10, "mu"))
    o.append("</g></svg>")
    return "\n".join(o)


# ----------------------------------------------------------------- badge ---

REPO = "https://github.com/ShroudLabs/ungrounded-agents"

BADGE_STYLES = {
    "rate": lambda sc: sc.headline,                  # 5.0%
    "collapse": lambda sc: sc.collapse,              # 84% → 5.0%
    "verdict": lambda sc: sc.verdict,                # COLLAPSE
}


def _badge_parts(sc: "Scorecard", style: str = "rate", label: str = "ungrounded"):
    if style not in BADGE_STYLES:
        raise ValueError(f"badge style must be one of {', '.join(BADGE_STYLES)}")
    return label, BADGE_STYLES[style](sc), _COLOURS.get(
        sc.verdict, _COLOURS["INCONCLUSIVE"])[0]


_HEX = {"brightgreen": "#4c1", "yellow": "#dfb317", "orange": "#fe7d37",
        "red": "#e05d44", "lightgrey": "#9f9f9f"}


def _tw(s: str, size: int = 11) -> float:
    """Rough Verdana advance width. Good enough for a badge."""
    wide, narrow = "mwMW%→", "iljt.,:;'|! "
    return sum(8.4 if c in wide else 4.2 if c in narrow else 6.6 for c in s) * size / 11


def _badge_svg(sc: "Scorecard", style: str = "rate",
               label: str = "ungrounded") -> str:
    lab, msg, colour = _badge_parts(sc, style, label)
    lw, mw = _tw(lab) + 12, _tw(msg) + 12
    W, H = lw + mw, 20
    fill = _HEX.get(colour, "#9f9f9f")
    font = "Verdana,DejaVu Sans,Geneva,sans-serif"

    def txt(x, s, w):
        return (f'<text x="{x*10:.0f}" y="140" transform="scale(.1)" fill="#fff" '
                f'textLength="{w*10:.0f}">{_esc(s)}</text>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H}" '
        f'role="img" aria-label="{_esc(lab)}: {_esc(msg)}">'
        f'<title>{_esc(lab)}: {_esc(msg)}</title>'
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{W:.0f}" height="{H}" rx="3" fill="#fff"/>'
        f'</clipPath><g clip-path="url(#r)">'
        f'<rect width="{lw:.0f}" height="{H}" fill="#555"/>'
        f'<rect x="{lw:.0f}" width="{mw:.0f}" height="{H}" fill="{fill}"/>'
        f'<rect width="{W:.0f}" height="{H}" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="{font}" font-size="110">'
        f'<text x="{lw*5:.0f}" y="150" transform="scale(.1)" fill="#010101" '
        f'fill-opacity=".3" textLength="{(lw-12)*10:.0f}">{_esc(lab)}</text>'
        f'{txt(lw/2, lab, lw-12)}'
        f'<text x="{(lw+mw/2)*10:.0f}" y="150" transform="scale(.1)" fill="#010101" '
        f'fill-opacity=".3" textLength="{(mw-12)*10:.0f}">{_esc(msg)}</text>'
        f'{txt(lw+mw/2, msg, mw-12)}'
        f'</g></svg>'
    )


def _shields_seg(s: str) -> str:
    """Escape one path segment for img.shields.io/badge/<l>-<m>-<c>."""
    from urllib.parse import quote
    return quote(s.replace("_", "__").replace("-", "--"), safe="")


def _badge_url(sc: "Scorecard", style: str = "rate",
               label: str = "ungrounded") -> str:
    lab, msg, colour = _badge_parts(sc, style, label)
    return ("https://img.shields.io/badge/"
            f"{_shields_seg(lab)}-{_shields_seg(msg)}-{colour}")


def _badge_md(sc: "Scorecard", style: str = "rate", label: str = "ungrounded",
              link: str = REPO) -> str:
    lab, msg, _ = _badge_parts(sc, style, label)
    alt = f"{lab}: {msg}"
    return f"[![{alt}]({_badge_url(sc, style, label)})]({link})"


def _endpoint_json(sc: "Scorecard", style: str = "rate",
                   label: str = "ungrounded") -> str:
    """shields.io endpoint payload, for anyone who wants to host it."""
    lab, msg, colour = _badge_parts(sc, style, label)
    return json.dumps({"schemaVersion": 1, "label": lab, "message": msg,
                       "color": colour}, indent=2)


# Bind the renderers as methods so the Scorecard is the whole public surface.
Scorecard.card_svg = lambda self, theme="auto": _card_svg(self, theme)
Scorecard.badge_svg = lambda self, style="rate", label="ungrounded": _badge_svg(
    self, style, label)
Scorecard.badge_url = lambda self, style="rate", label="ungrounded": _badge_url(
    self, style, label)
Scorecard.badge_md = lambda self, style="rate", label="ungrounded", link=REPO: (
    _badge_md(self, style, label, link))
Scorecard.badge_endpoint = lambda self, style="rate", label="ungrounded": (
    _endpoint_json(self, style, label))
