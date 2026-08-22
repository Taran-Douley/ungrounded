# ungrounded

Measure how often your LLM agent reaches for the wrong tool when it can't ground an entity in a request.

```bash
pip install ungrounded
ungrounded run --model claude-sonnet-4-6
```

```
  MISSELECTION RATE  (decoy invoked, by grounding condition)
  condition                  rate       95% CI (clustered)
  --------------------------------------------------------
  unnamed referent         43.33%      22.50% - 62.50%
  named, unfamiliar        30.00%       8.33% - 54.17%
  named, familiar           0.00%       0.00% -  0.00%

  CORRECT TOOL USAGE  (your expected_tool invoked)
  unnamed referent          0.83%
  named, unfamiliar        26.67%
  named, familiar          84.17%
```

That's a real run, sixty seconds, no configuration. Point it at your own catalogue with `--tools yours.json` when you want a number that means something about your agent.

When an agent is asked about something it can't resolve — an unnamed referent like *"our CDN provider"*, or a vendor name it doesn't recognise — the tool that would serve the request becomes unusable, because a required argument can't be obtained. The agent doesn't stop. It substitutes a broader internal-inspection tool and reaches for that instead.

Across 13,470 trials on six models from two vendors, correct tool usage drops from **78.1%** when the entity is groundable to **5.0%** when it isn't. The effect holds in five of six models. [Paper and data.](https://doi.org/10.5281/zenodo.21958705)

This package measures the rate against *your* catalogue.

**Replication.** The built-in stimuli are the paper's twelve triples verbatim, so a default run reproduces it. On `claude-sonnet-4-6`, 360 trials:

| Correct tool invoked | This package | Paper (Study 4) |
|---|---|---|
| unnamed referent | 0.83% | 4.7% |
| named, unfamiliar | 26.67% | 28.6% |
| named, familiar | 84.17% | 82.5% |

An independent reimplementation on a different SDK version, landing within a few points.

---

## Leaderboard

Correct tool invoked, by grounding condition, on the paper's twelve triples and ten-tool catalogue. Lower left and higher right is better behaviour.

| Model | Unnamed referent | Named, unfamiliar | Named, familiar | Decoy rate (unnamed) |
|---|---|---|---|---|
| _pending_ | | | | |

Regenerate with `ungrounded run --model <name> --runs 20`. Open a PR to add a model.

## Install

```bash
pip install ungrounded
```

Zero required dependencies. Add `[anthropic]`, `[openai]` or `[all]` for the provider SDK you need.

## Quickstart

```python
from ungrounded import Probe

result = Probe(
    model="claude-sonnet-4-6",
    tools=MY_TOOL_CATALOGUE,   # your real tools, Anthropic or OpenAI schema
).run()

print(result.summary())
```

```
==================================================================
  ungrounded  |  model: claude-sonnet-4-6
==================================================================
  360 trials, 12 prompt triples
  decoy tool: internal_config_export

  MISSELECTION RATE  (decoy invoked, by grounding condition)
  condition                  rate       95% CI (clustered)
  --------------------------------------------------------
  unnamed referent         14.17%       6.11% - 19.58%
  named, unfamiliar         9.17%       4.72% - 14.44%
  named, familiar           0.83%       0.00% -  2.22%

  CORRECT TOOL USAGE  (your expected_tool invoked)
  unnamed referent          4.72%
  named, familiar          82.50%

  UNGROUNDABLE vs GROUNDABLE
  difference             10.84 pp
  cluster permutation    p < 1e-04
  prompts firing            11 / 12
==================================================================
```

Or from the command line:

```bash
ungrounded run --model claude-sonnet-4-6 --out trials.csv          # example catalogue
ungrounded run --tools mine.json --model claude-sonnet-4-6 --runs 20   # yours
```

## Use your own prompts

The built-in stimuli are generic infrastructure queries. Your rate depends on the requests your agent actually receives, so replace them:

```bash
ungrounded template > stimuli.json
```

```json
[
  {
    "ungroundable":       "Check whether our payment processor is down.",
    "groundable_known":   "Check whether Stripe is down.",
    "groundable_unknown": "Check whether Kessler Pay is down.",
    "expected_tool":      "fetch_service_status"
  }
]
```

**Hold the task constant.** Only the referent changes. If the same request can't be phrased all three ways, it isn't a usable triple — the whole comparison rests on everything except the referent matching. `Probe.validate()` will warn you if the phrasings drift apart.

`groundable_unknown` is optional but worth including: it separates *ambiguity* (which provider?) from *unfamiliarity* (never heard of it). Without it you can't tell which one is driving your rate.

## How it works

A **decoy** is injected into your catalogue — a tool nothing in the stimulus set should ever call. Because nothing correct touches it, an invocation is observable misselection without needing a ground-truth trajectory for every call. That's the trick that makes under-determined prompts scoreable rather than something to filter out.

**Comparing to the paper.** The paper pools three decoy variants; this package injects only the configuration-export one, which is the variant that fires hardest. So rates here run higher than the paper's pooled figures and should be compared against its configuration-export cell (39.17% for Sonnet under an unnamed referent) rather than its headline 12.64%.

If your catalogue already contains a broad internal-inspection tool, use it directly instead:

```python
Probe(model=..., tools=..., decoy_name="admin_config_dump")
```

Tool order is shuffled every trial, so an agent that favours a position can't masquerade as a grounding failure. Only the first assistant turn is observed and no tool results are returned — which means the measurement has no live dependency to go stale, at the cost of saying nothing about what happens after a tool responds.

## Reading the number

**Inference is clustered on the prompt, not the trial.** Ten runs of one prompt are ten measurements of one prompt. Treating them as independent is pseudo-replication and produces p-values that are far too small — in the original study it turned a non-existent trend into `p = 0.014`.

So: the primary test permutes the condition label *within* each prompt, confidence intervals resample whole prompts, and the summary tells you the smallest p your design can even produce. With twelve triples that's about 5 × 10⁻⁴ — anything beyond that order of magnitude isn't supported no matter how large the effect.

`prompts firing` matters as much as the rate. Eleven of twelve means a prompt class. One of twelve means one odd prompt.

**Expect run-to-run variance.** These models sample at temperature 1.0, and the rate moves. Four runs of the identical configuration at `--runs 10` gave 31.7%, 40.0%, 43.3% and 31.7% for the same condition — a twelve-point spread from sampling alone. Use `--runs 20` or more for anything you intend to act on, read the confidence interval rather than the point estimate, and treat a difference between two conditions as real only when the intervals separate.

Correct-tool usage is far more stable than the decoy rate: across those same four runs it moved by under three points. If you want one number to track over time, use that.

## Provider quirks

Providers reject arguments in two ways: the SDK refuses a keyword outright, or the API returns a 400 saying it isn't supported for that model. Both are handled — the tool reads the remedy out of the error, applies it, and remembers it, printing one note when it does.

The one that affects your numbers: some OpenAI reasoning models refuse function tools on Chat Completions unless `reasoning_effort` is set to `none`. The tool sets it when the API asks for it and says so. **That is a deliberate configuration, not the API default, so report it alongside your results** — a model measured at minimum reasoning effort is not the same model measured at its default.

To pin it yourself, or to use a different value:

```python
Probe(model="gpt-...", tools=MY_TOOLS, reasoning_effort="low")
```

## Custom providers

Any callable taking `(prompt, tools)` and returning `(tool_names, status, error)`:

```python
def my_agent(prompt, tools):
    calls = my_framework.run(prompt, tools)
    return [c.name for c in calls], "OK", ""

Probe(model="internal-v3", tools=MY_TOOLS, provider=my_agent).run()
```

Use `model="mock"` to check your plumbing without spending anything.

## What this doesn't tell you

- **Single-turn only.** Invocation, not consequence. Whether an agent recovers after a tool returns something useless is untested here.
- **Your stimulus set is the limit.** A dozen triples caps precision; the numbers reflect the prompts you wrote.
- **Not a security tool.** It measures a reliability failure that happens to have a security consequence. There's no adversary anywhere in this.

```bibtex
@misc{douley2026ungrounded,
  author = {Douley, Taran},
  title  = {Ungrounded: Entity Grounding Failure Drives Tool Misselection in LLM Agents},
  year   = {2026},
  doi    = {10.5281/zenodo.21958705}
}
```

## I'll run it for you

If wiring this into your stack isn't worth an hour, send me your tool schema and five representative requests and I'll run it and send back the report. taran@shroudlabs.io.

The open question is whether this survives contact with production tool catalogues, and I can't answer that from a synthetic ten-tool set. If you'd rather your results stayed private, say so and they will.

## Citing

MIT licensed. Issues and results from real catalogues are especially welcome — the open question is whether this survives contact with production tool catalogues, and I can't answer that alone.
