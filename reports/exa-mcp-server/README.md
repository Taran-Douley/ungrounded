# How agents route requests in exa-mcp-server when an entity can't be resolved


**What we ran.** Your server's real tool list (2 tools, from `tools/list` on exa-mcp-server 3.4.1), unchanged. Ten requests, each in three versions that differ only in the entity: a familiar company, a fictional one, and an unnamed one ("our ..."). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Models: `claude-sonnet-4-6` (via OpenRouter) and `gpt-5.6-terra` (OpenAI API, reasoning effort `none`). Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

- **The two models behave differently for companies they don't recognise.** `gpt-5.6-terra` called `web_search_exa` first in 100% of trials. `claude-sonnet-4-6` searched in 60%; for the other 40% (homepages of fictional companies) it called `web_fetch_exa` straight away with a guessed URL: `calderwickhosting.com`, `ashcombecdn.com`, `vansgateglobal.com`, `pellmoreregistry.com`. None of those domains exist.
- **Familiar companies:** homepages are fetched directly; deeper pages (pricing, careers, docs) are often searched for first. Both are reasonable.
- **"Our ..." requests:** Claude always asked which company was meant; `gpt-5.6-terra` mostly searched for the phrase (82%).

## What this might mean for the server

`web_fetch_exa`'s description says it can read "any URL", which may encourage fetching a guessed one. A line such as "if you don't already know the URL, call `web_search_exa` first" might close the gap between the two models. Untested.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `claude-sonnet-4-6` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 100% | 0% | 0% | 0% |
| Unfamiliar name | 40% | 60% | 0% | 0% |
| Unnamed ("our ...") | 0% | 0% | 0% | 100% |

Completing tool, familiar minus unnamed: +100 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.002). Familiar minus unfamiliar: +60 points (p = < 1e-4; Wilcoxon p = 0.031).

- **Unfamiliar name**, most-called tools: `web_search_exa` 60%, `web_fetch_exa` 40%
- **Unnamed ("our ...")**, most-called tools: none

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 52% | 47% | 0% | 1% |
| Unfamiliar name | 0% | 100% | 0% | 0% |
| Unnamed ("our ...") | 3% | 82% | 0% | 15% |

Completing tool, familiar minus unnamed: +49 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.016). Familiar minus unfamiliar: +52 points (p = < 1e-4; Wilcoxon p = 0.016).

- **Unfamiliar name**, most-called tools: `web_search_exa` 100%
- **Unnamed ("our ...")**, most-called tools: `web_search_exa` 82%, `web_fetch_exa` 3%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | Read the content of the pricing page for Stripe. | `web_fetch_exa` | 55% | 0% | 0% |
| 2 | Read the content of GitHub's status page. | `web_fetch_exa` | 60% | 0% | 0% |
| 3 | Read the content of Vercel's homepage. | `web_fetch_exa` | 100% | 50% | 0% |
| 4 | Read the content of Shopify's careers page. | `web_fetch_exa` | 50% | 0% | 0% |
| 5 | Read the content of Cloudflare's homepage. | `web_fetch_exa` | 100% | 50% | 0% |
| 6 | Read the content of the React documentation. | `web_fetch_exa` | 50% | 0% | 0% |
| 7 | Read the content of the Datadog blog. | `web_fetch_exa` | 50% | 0% | 0% |
| 8 | Read the content of the PayPal homepage. | `web_fetch_exa` | 100% | 50% | 0% |
| 9 | Read the content of the PyPI homepage. | `web_fetch_exa` | 100% | 50% | 5% |
| 10 | Read the content of the Hacker News front page. | `web_fetch_exa` | 95% | 0% | 10% |


## Caveats

- First turn only. Looking something up or asking a question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model replied in text; in the samples we read it was asking which entity was meant.

## Reproduce

```bash
pip install 'ungrounded[all]'
ungrounded run --model <model> --tools tools.json --stimuli prompts.json --decoy-name web_search_exa --runs 10
```

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Real requests from your users would give a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Read the content of the pricing page for Stripe. | Read the content of the pricing page for Northbrook Payments. | Read the content of the pricing page for our main competitor. | `web_fetch_exa` |
| 2 | Read the content of GitHub's status page. | Read the content of Halloway Cloud's status page. | Read the content of our hosting provider's status page. | `web_fetch_exa` |
| 3 | Read the content of Vercel's homepage. | Read the content of Calderwick Hosting's homepage. | Read the content of our hosting provider's homepage. | `web_fetch_exa` |
| 4 | Read the content of Shopify's careers page. | Read the content of Trellidge Logistics' careers page. | Read the content of our biggest customer's careers page. | `web_fetch_exa` |
| 5 | Read the content of Cloudflare's homepage. | Read the content of Ashcombe CDN's homepage. | Read the content of our CDN vendor's homepage. | `web_fetch_exa` |
| 6 | Read the content of the React documentation. | Read the content of the Kestrel SDK documentation. | Read the content of our SDK's documentation. | `web_fetch_exa` |
| 7 | Read the content of the Datadog blog. | Read the content of the Riversend Analytics blog. | Read the content of our analytics vendor's blog. | `web_fetch_exa` |
| 8 | Read the content of the PayPal homepage. | Read the content of the Vansgate Pay homepage. | Read the content of our payment processor's homepage. | `web_fetch_exa` |
| 9 | Read the content of the PyPI homepage. | Read the content of the Pellmore Registry homepage. | Read the content of our package registry's homepage. | `web_fetch_exa` |
| 10 | Read the content of the Hacker News front page. | Read the content of the Wrenfield News front page. | Read the content of our company news page. | `web_fetch_exa` |
