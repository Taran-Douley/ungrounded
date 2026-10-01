# Reports on real MCP servers

`ungrounded` run against the published tool lists of open-source MCP servers, to see how agents
route a request when the entity in it can't be resolved: a name they don't recognise, or an
unnamed reference like "our CDN provider".

**The pattern across all seven:** agents behave well when the catalogue lets them look a name up,
and guess an identifier when it doesn't.

| Server | Models | What we found |
|---|---|---|
| [playwright-mcp](playwright-mcp/) | gpt-5.6-terra, claude-sonnet-4-6 | No search tool, so for an unfamiliar company the agent navigates to a guessed domain or improvises a Google search. One guessed domain is a real, unrelated site. |
| [terraform-mcp-server](terraform-mcp-server/) | gpt-5.6-terra, claude-sonnet-4-6 | No name-based provider lookup, so agents guess provider namespaces. Modules, which have one, are mostly looked up. |
| [exa-mcp-server](exa-mcp-server/) | gpt-5.6-terra, claude-sonnet-4-6 | Depends on the model: one always searches first; the other fetches guessed homepage URLs 40% of the time. |
| [mcp-grafana](mcp-grafana/) | gpt-5.6-terra | Healthy: names are always looked up, never a guessed UID. |
| [aws-documentation-mcp-server](aws-documentation-mcp-server/) | gpt-5.6-terra, claude-sonnet-4-6 | Healthy: both models search before reading; no guessed URLs. |
| [github-mcp-server](github-mcp-server/) | gpt-5.6-terra | Healthy: unfamiliar repos are searched, "our repo" gets a clarifying question. |
| [firecrawl-mcp-server](firecrawl-mcp-server/) | gpt-5.6-terra | Healthy: unfamiliar companies are searched, never guessed. |

## What's in each folder

- `README.md`: the report.
- `tools.json`: the server's tool list, from `tools/list`, unchanged.
- `prompts.json`: the ten request triples (familiar, unfamiliar, unnamed). Written by us, with LLM
  assistance, from each server's tool descriptions.
- `trials__<model>.csv`: one row per trial: the prompt, its condition, and every tool called in the
  first turn.
- `call_arguments*.jsonl`: a small separate sample on `gpt-5.6-terra` recording the arguments of
  those calls (the trial files record tool names only).

## Method

Each prompt version ran 10 times per model at temperature 1.0, first assistant turn only, with no
tools executed. `gpt-5.6-terra` ran on the OpenAI API at reasoning effort `none`;
`claude-sonnet-4-6` was served through OpenRouter. Measured on 1 October 2026 with `ungrounded`
0.3.0. Reproduce any report with:

```bash
pip install 'ungrounded[all]'
ungrounded run --model <model> --tools tools.json --stimuli prompts.json --runs 10
```

A lower completing-tool rate is not, on its own, a bug: when an entity can't be resolved, looking
it up or asking the user is often the right first step. The reports flag guessing, not caution.

If you maintain one of these servers and want a different prompt set, or a re-run against a branch,
open an issue.
