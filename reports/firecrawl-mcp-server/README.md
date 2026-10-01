# How agents route requests in firecrawl-mcp-server when an entity can't be resolved


**What we ran.** Your server's real tool list (27 tools, from `tools/list` on firecrawl-fastmcp 3.27.2), unchanged. Ten requests, each in three versions that differ only in the entity: a familiar name, an unfamiliar (fictional) name, and an unnamed reference ("our ..."). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Model: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`); one model only. Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

Routing looks sensible, and your tool descriptions seem to be doing their job.

- **Unfamiliar companies are always searched first** (`firecrawl_search`, 100% of trials), rather than scraping a guessed URL.
- **"Our ..." requests mostly get a clarifying question** (87%, no tool call).
- **Familiar companies:** a homepage or pricing page is scraped directly; a deeper page (changelog, terms, rate limits, release notes) is searched for first. That's reasonable, since nobody knows those URLs offhand, and it means half our "familiar" prompts weren't a clean test. We've marked them in the per-prompt table.

## What this might mean for the server

Nothing here needs fixing. Agents didn't invent URLs for companies they didn't recognise, and they used search exactly when the URL was unknown, which is what `firecrawl_search`'s and `firecrawl_agent`'s descriptions ask for.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 47% | 51% | 2% | 0% |
| Unfamiliar name | 0% | 100% | 0% | 0% |
| Unnamed ("our ...") | 0% | 13% | 0% | 87% |

Completing tool, familiar minus unnamed: +47 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.031). Familiar minus unfamiliar: +47 points (p = < 1e-4; Wilcoxon p = 0.031).

- **Unfamiliar name**, most-called tools: `firecrawl_search` 100%
- **Unnamed ("our ...")**, most-called tools: `firecrawl_search` 13%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | Scrape the pricing page for Stripe. | `firecrawl_scrape` | 100% | 0% | 0% |
| 2 | Get the contents of GitHub's status page. | `firecrawl_scrape` | 100% | 0% | 0% |
| 3 | Pull the changelog from the React documentation site. | `firecrawl_scrape` | 0% | 0% | 0% |
| 4 | Scrape the careers page of Shopify. | `firecrawl_scrape` | 60% | 0% | 0% |
| 5 | Get the terms of service page for PayPal. | `firecrawl_scrape` | 0% | 0% | 0% |
| 6 | Scrape the homepage of Vercel. | `firecrawl_scrape` | 100% | 0% | 0% |
| 7 | Get the rate-limits page from SendGrid's API docs. | `firecrawl_scrape` | 0% | 0% | 0% |
| 8 | Scrape the security page of Cloudflare. | `firecrawl_scrape` | 100% | 0% | 0% |
| 9 | Get the latest posts from Datadog's blog. | `firecrawl_scrape` | 10% | 0% | 0% |
| 10 | Scrape the release notes page for MongoDB Atlas. | `firecrawl_scrape` | 0% | 0% | 0% |


## Caveats

- First turn only. A lookup or a clarifying question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model answered in text; in the cases we read, it was asking which entity was meant.
- One model only (`gpt-5.6-terra`).

## Reproduce

Against the server itself (firecrawl-mcp 3.27.2):

```bash
pip install 'ungrounded[all]'
ungrounded run --mcp "npx -y firecrawl-mcp" \
  --mcp-env FIRECRAWL_API_KEY=placeholder \
  --stimuli prompts.json --decoy-name firecrawl_search --runs 10 --model <model>
```

Without a `FIRECRAWL_API_KEY` the server lists 25 tools instead of 27 (the two feedback tools are left out); the placeholder reproduces the list measured here.

Or against the saved tool list in this folder:

```bash
ungrounded run --tools tools.json --stimuli prompts.json --decoy-name firecrawl_search --runs 10 --model <model>
```

To re-run against a branch, point `--mcp` at your local build.

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Replace them with real requests from your users for a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Scrape the pricing page for Stripe. | Scrape the pricing page for Northbrook Payments. | Scrape the pricing page for our main competitor. | `firecrawl_scrape` |
| 2 | Get the contents of GitHub's status page. | Get the contents of Halloway Cloud's status page. | Get the contents of our hosting provider's status page. | `firecrawl_scrape` |
| 3 | Pull the changelog from the React documentation site. | Pull the changelog from the Kestrel SDK documentation site. | Pull the changelog from our SDK's documentation site. | `firecrawl_scrape` |
| 4 | Scrape the careers page of Shopify. | Scrape the careers page of Trellidge Logistics. | Scrape the careers page of our biggest customer. | `firecrawl_scrape` |
| 5 | Get the terms of service page for PayPal. | Get the terms of service page for Vansgate Pay. | Get the terms of service page for our payment processor. | `firecrawl_scrape` |
| 6 | Scrape the homepage of Vercel. | Scrape the homepage of Calderwick Hosting. | Scrape the homepage of our hosting provider. | `firecrawl_scrape` |
| 7 | Get the rate-limits page from SendGrid's API docs. | Get the rate-limits page from Pellmore Mail's API docs. | Get the rate-limits page from our email provider's API docs. | `firecrawl_scrape` |
| 8 | Scrape the security page of Cloudflare. | Scrape the security page of Ashcombe CDN. | Scrape the security page of our CDN vendor. | `firecrawl_scrape` |
| 9 | Get the latest posts from Datadog's blog. | Get the latest posts from Riversend Analytics' blog. | Get the latest posts from our analytics vendor's blog. | `firecrawl_scrape` |
| 10 | Scrape the release notes page for MongoDB Atlas. | Scrape the release notes page for Wrenfield DB. | Scrape the release notes page for our database provider. | `firecrawl_scrape` |
