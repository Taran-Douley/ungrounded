# How agents route requests in github-mcp-server when an entity can't be resolved


**What we ran.** Your server's real tool list (45 tools, from `tools/list` on github-mcp-server 1.12.2), unchanged. Ten requests, each in three versions that differ only in the entity: a familiar name, an unfamiliar (fictional) name, and an unnamed reference ("our ..."). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Model: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`); one model only. Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

Routing looks sensible across the board.

- **Familiar repos route straight to the right tool** (88% of trials), e.g. `get_latest_release` for *"the React repo"*.
- **Unfamiliar repos are looked up first:** `search_repositories` in 73% of trials, and a clarifying answer in most of the rest. Almost no guessed `owner/repo` calls.
- **"Our ... repo" mostly gets a clarifying question** (86% of trials, no tool call). In a few trials the agent called `get_me` or `get_teams` to work out whose repos "our" means.

## What this might mean for the server

Nothing here looks broken. One possible improvement: for "our"/"my" repos the agent usually asks rather than using `get_me` and then a scoped `search_repositories` (`user:` or `org:`). A hint in `search_repositories`' description could make that path more common, if that's the behaviour you want.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 88% | 11% | 1% | 0% |
| Unfamiliar name | 3% | 73% | 1% | 23% |
| Unnamed ("our ...") | 0% | 8% | 6% | 86% |

Completing tool, familiar minus unnamed: +88 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.002). Familiar minus unfamiliar: +85 points (p = < 1e-4; Wilcoxon p = 0.002).

- **Unfamiliar name**, most-called tools: `search_repositories` 73%, `list_tags` 2%, `get_me` 1%, `list_issues` 1%
- **Unnamed ("our ...")**, most-called tools: `search_repositories` 8%, `get_me` 4%, `get_teams` 2%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | Show me the latest release of the React repo. | `get_latest_release` | 90% | 0% | 0% |
| 2 | List the open pull requests on the Next.js repo. | `list_pull_requests` | 100% | 0% | 0% |
| 3 | Show me the recent commits to the Kubernetes repo. | `list_commits` | 90% | 0% | 0% |
| 4 | Get the README from the ripgrep repo. | `get_file_contents` | 100% | 0% | 0% |
| 5 | List the open issues in the TypeScript repo. | `list_issues` | 60% | 10% | 0% |
| 6 | What branches does the Flutter repo have? | `list_branches` | 100% | 0% | 0% |
| 7 | List the tags on the Terraform repo. | `list_tags` | 100% | 20% | 0% |
| 8 | Show me the releases for the Tailwind CSS repo. | `list_releases` | 60% | 0% | 0% |
| 9 | Show me what's in the src directory of the PostHog repo. | `get_file_contents` | 90% | 0% | 0% |
| 10 | Get the latest release of the Prisma repo. | `get_latest_release` | 90% | 0% | 0% |


## Caveats

- First turn only. A lookup or a clarifying question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model answered in text; in the cases we read, it was asking which entity was meant.
- One model only (`gpt-5.6-terra`).

## Reproduce

Against the server itself (github-mcp-server 1.12.2, from its GitHub releases):

```bash
pip install 'ungrounded[all]'
ungrounded run --mcp "github-mcp-server stdio" \
  --stimuli prompts.json --decoy-name search_repositories --runs 10 --model <model>
```

Or against the saved tool list in this folder:

```bash
ungrounded run --tools tools.json --stimuli prompts.json --decoy-name search_repositories --runs 10 --model <model>
```

To re-run against a branch, point `--mcp` at your local build.

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Replace them with real requests from your users for a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Show me the latest release of the React repo. | Show me the latest release of the Kestrel SDK repo. | Show me the latest release of our main SDK repo. | `get_latest_release` |
| 2 | List the open pull requests on the Next.js repo. | List the open pull requests on the Halloway UI repo. | List the open pull requests on our frontend repo. | `list_pull_requests` |
| 3 | Show me the recent commits to the Kubernetes repo. | Show me the recent commits to the Trellidge API repo. | Show me the recent commits to our API server repo. | `list_commits` |
| 4 | Get the README from the ripgrep repo. | Get the README from the Vansgate CLI repo. | Get the README from our CLI tool's repo. | `get_file_contents` |
| 5 | List the open issues in the TypeScript repo. | List the open issues in the Calderwick Docs repo. | List the open issues in our docs repo. | `list_issues` |
| 6 | What branches does the Flutter repo have? | What branches does the Pellmore Mobile repo have? | What branches does our mobile app repo have? | `list_branches` |
| 7 | List the tags on the Terraform repo. | List the tags on the Ashcombe Infra repo. | List the tags on our infrastructure repo. | `list_tags` |
| 8 | Show me the releases for the Tailwind CSS repo. | Show me the releases for the Riversend Design repo. | Show me the releases for our design system repo. | `list_releases` |
| 9 | Show me what's in the src directory of the PostHog repo. | Show me what's in the src directory of the Wrenfield Analytics repo. | Show me what's in the src directory of our analytics repo. | `get_file_contents` |
| 10 | Get the latest release of the Prisma repo. | Get the latest release of the Duncastle DB driver repo. | Get the latest release of our database driver repo. | `get_latest_release` |
