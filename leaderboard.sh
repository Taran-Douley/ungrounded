#!/usr/bin/env bash
# Generate the README leaderboard. Needs ANTHROPIC_API_KEY and OPENAI_API_KEY.
# ~20 runs x 3 conditions x 12 triples x N models. Budget a few pounds.
set -uo pipefail
cd "$(dirname "$0")"
RUNS="${RUNS:-20}"
mkdir -p leaderboard

MODELS=(
  "claude-opus-5"
  "claude-sonnet-4-6"
  "claude-haiku-4-5-20251001"
  "gpt-5.6-sol"
  "gpt-5.6-terra"
  "gpt-5.6-luna"
)

for m in "${MODELS[@]}"; do
  out="leaderboard/${m}.json"
  if [ -f "$out" ]; then echo "skip $m (already done)"; continue; fi
  echo "=== $m ==="
  if ungrounded run --model "$m" --runs "$RUNS" \
       --out "leaderboard/${m}.csv" --json --quiet > "$out"; then
    echo "  ok"
  else
    echo "  FAILED -- see above; rerun to retry just this model"
    rm -f "$out"
  fi
done

python3 - << 'PY'
import glob, json, os, csv
rows = []
for f in sorted(glob.glob("leaderboard/*.json")):
    d = json.load(open(f))
    csvf = f[:-5] + ".csv"
    exp = {}
    if os.path.exists(csvf):
        for r in csv.DictReader(open(csvf)):
            if r["status"] == "OK" and r["expected_called"] not in ("", "None"):
                exp.setdefault(r["condition"], []).append(int(r["expected_called"]))
    pct = lambda c: (100*sum(exp[c])/len(exp[c])) if exp.get(c) else float("nan")
    rows.append((d["model"], pct("ungroundable"), pct("groundable_unknown"),
                 pct("groundable_known"), d["rates"].get("ungroundable", float("nan"))))
rows.sort(key=lambda r: -r[3])
print("\n| Model | Unnamed referent | Named, unfamiliar | Named, familiar | Decoy rate (unnamed) |")
print("|---|---|---|---|---|")
for m, a, b, c, dec in rows:
    print(f"| `{m}` | {a:.1f}% | {b:.1f}% | {c:.1f}% | {dec:.1f}% |")
print("\nPaste into README.md under ## Leaderboard.")
PY
