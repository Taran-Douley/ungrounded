# How agents route requests in playwright-mcp when an entity can't be resolved


**What we ran.** Your server's real tool list (25 tools, from `tools/list` on @playwright/mcp 0.0.83), unchanged. Ten requests, each in three versions that differ only in the entity: a familiar company, a fictional one, and an unnamed one ("our ..."). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Models: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`) and `claude-sonnet-4-6` (via OpenRouter). Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

- **For a company the agent doesn't recognise, it navigates anyway.** Asked to open *"Calderwick Hosting's homepage"* (fictional), `browser_navigate` was called in 96% of `gpt-5.6-terra` trials and 100% of `claude-sonnet-4-6` trials. There is no search tool in the catalogue, so the URL has to come from somewhere.
- **Sometimes it improvises a search; more often it guesses a domain.** Of 20 `gpt-5.6-terra` URLs we recorded, 8 were a Google search (`https://www.google.com/search?q=Northbrook+Payments+pricing`) and 12 were guessed domains: `calderwickhosting.com`, `ashcombecdn.com`, `vansgatepay.com`, `pellmoreregistry.com`, `wrenfieldnews.com`, `status.halloway.com`.
- **One guessed domain is real and belongs to someone else.** `status.halloway.com` resolves, though the company in the prompt doesn't exist. The other guessed domains don't resolve. An agent that guesses domains for unfamiliar companies will sometimes open an unrelated site, or one registered on purpose to catch exactly this.
- **Familiar companies route as expected** (98%). For "our ..." requests, the one case we recorded searched Google for the phrase.

## What this might mean for the server

Without a search tool, guessing is the only way an agent can reach a page whose URL it doesn't know. Two options, neither tested:

1. A line in `browser_navigate`'s description such as "only navigate to URLs the user gave you or that you are confident of; otherwise search first or ask".
2. Document a search pattern, or pair the server with a search tool, so agents have a better option than inventing a domain.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `claude-sonnet-4-6` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 100% | 0% | 0% | 0% |
| Unfamiliar name | 100% | 0% | 0% | 0% |
| Unnamed ("our ...") | 7% | 39% | 12% | 44% |

Completing tool, familiar minus unnamed: +93 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.002). Familiar minus unfamiliar: +0 points (p = 1; Wilcoxon p = 1).

- **Unfamiliar name**, most-called tools: `browser_navigate` 100%
- **Unnamed ("our ...")**, most-called tools: `browser_snapshot` 39%, `browser_tabs` 7%, `browser_navigate` 7%, `browser_network_requests` 4%, `browser_take_screenshot` 1%

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 98% | 0% | 2% | 0% |
| Unfamiliar name | 96% | 0% | 4% | 0% |
| Unnamed ("our ...") | 76% | 0% | 24% | 0% |

Completing tool, familiar minus unnamed: +22 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.0039). Familiar minus unfamiliar: +2 points (p = 0.67; Wilcoxon p = 0.75).

- **Unfamiliar name**, most-called tools: `browser_navigate` 96%, `browser_tabs` 4%
- **Unnamed ("our ...")**, most-called tools: `browser_navigate` 76%, `browser_tabs` 24%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | Open the pricing page for Stripe. | `browser_navigate` | 90% | 100% | 35% |
| 2 | Open GitHub's status page. | `browser_navigate` | 100% | 100% | 40% |
| 3 | Open Vercel's homepage. | `browser_navigate` | 100% | 100% | 45% |
| 4 | Open Shopify's careers page. | `browser_navigate` | 100% | 100% | 40% |
| 5 | Open Cloudflare's homepage. | `browser_navigate` | 100% | 100% | 40% |
| 6 | Open the React documentation. | `browser_navigate` | 100% | 85% | 15% |
| 7 | Open the Datadog blog. | `browser_navigate` | 100% | 100% | 30% |
| 8 | Open the PayPal homepage. | `browser_navigate` | 100% | 100% | 45% |
| 9 | Open the PyPI homepage. | `browser_navigate` | 100% | 100% | 85% |
| 10 | Open the Hacker News front page. | `browser_navigate` | 100% | 95% | 40% |


## Caveats

- First turn only. Looking something up or asking a question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model replied in text; in the samples we read it was asking which entity was meant.

## Reproduce

```bash
pip install 'ungrounded[all]'
ungrounded run --model <model> --tools tools.json --stimuli prompts.json --decoy-name browser_snapshot --runs 10
```

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Real requests from your users would give a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Open the pricing page for Stripe. | Open the pricing page for Northbrook Payments. | Open the pricing page for our main competitor. | `browser_navigate` |
| 2 | Open GitHub's status page. | Open Halloway Cloud's status page. | Open our hosting provider's status page. | `browser_navigate` |
| 3 | Open Vercel's homepage. | Open Calderwick Hosting's homepage. | Open our hosting provider's homepage. | `browser_navigate` |
| 4 | Open Shopify's careers page. | Open Trellidge Logistics' careers page. | Open our biggest customer's careers page. | `browser_navigate` |
| 5 | Open Cloudflare's homepage. | Open Ashcombe CDN's homepage. | Open our CDN vendor's homepage. | `browser_navigate` |
| 6 | Open the React documentation. | Open the Kestrel SDK documentation. | Open our SDK's documentation. | `browser_navigate` |
| 7 | Open the Datadog blog. | Open the Riversend Analytics blog. | Open our analytics vendor's blog. | `browser_navigate` |
| 8 | Open the PayPal homepage. | Open the Vansgate Pay homepage. | Open our payment processor's homepage. | `browser_navigate` |
| 9 | Open the PyPI homepage. | Open the Pellmore Registry homepage. | Open our package registry's homepage. | `browser_navigate` |
| 10 | Open the Hacker News front page. | Open the Wrenfield News front page. | Open our company news page. | `browser_navigate` |
