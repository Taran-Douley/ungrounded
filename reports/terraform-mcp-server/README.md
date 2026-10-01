# How agents route requests in terraform-mcp-server when an entity can't be resolved


**What we ran.** Your server's real tool list (9 tools, from `tools/list` on terraform-mcp-server 1.3.0), unchanged. Ten requests, each in three versions that differ only in the entity: a familiar name, an unfamiliar (fictional) name, and an unnamed reference ("our ..."). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Models: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`) and `claude-sonnet-4-6` (served via OpenRouter). Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

- **Familiar providers and modules route well.** With a name like *AWS* or *terraform-aws-modules VPC*, both models called the right version tool in every trial.
- **For a provider the agent doesn't recognise, it guesses an identifier instead of looking it up.** Asked about *"the Terraform provider for Northbrook Cloud"* (fictional), `gpt-5.6-terra` called `get_latest_provider_version` in 50 of 50 trials and `claude-sonnet-4-6` in 27 of 50 (it asked the user in most of the rest), with made-up arguments such as `{"namespace": "northbrook-cloud", "name": "northbrook"}`. `search_providers` was used once in 100 trials.
- **For a module it doesn't recognise, it can look it up, and Claude mostly does:** `search_modules` in 39 of 50 trials (`gpt-5.6-terra`: 14 of 50; it guessed the rest).
- **"Our ... module" is often answered with the well-known public module.** For *"our standard VPC module"*, `gpt-5.6-terra` called the version tool for `terraform-aws-modules/vpc/aws` in most trials; Claude searched first in most trials. If a team's module is internal, the direct answer is about a different module. (Our wording, "standard", may encourage this.)
- **"Our cloud platform" (an unnamed provider) is handled well:** both models asked which provider was meant in every trial.

## What this might mean for the server

The contrast between modules and providers points at the catalogue. Modules have a name-based lookup (`search_modules`), and when one is available Claude uses it most of the time. Providers don't: `search_providers` needs the namespace already, so when the namespace is unknown the version tool is the only provider tool an agent can call, and it fills the namespace with a guess. Two options that might help, neither tested:

1. A provider lookup that takes just a name (or let `search_providers` work without a namespace).
2. A line in `get_latest_provider_version`'s description such as "if you don't know the exact namespace, ask the user or search first; don't guess".

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `claude-sonnet-4-6` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 100% | 0% | 0% | 0% |
| Unfamiliar name | 38% | 40% | 1% | 21% |
| Unnamed ("our ...") | 14% | 36% | 0% | 50% |

Completing tool, familiar minus unnamed: +86 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.002). Familiar minus unfamiliar: +62 points (p = < 1e-4; Wilcoxon p = 0.0039).

- **Unfamiliar name**, most-called tools: `search_modules` 39%, `get_latest_provider_version` 27%, `get_latest_module_version` 11%, `get_provider_capabilities` 1%, `search_providers` 1%
- **Unnamed ("our ...")**, most-called tools: `search_modules` 36%, `get_latest_module_version` 14%

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 100% | 0% | 0% | 0% |
| Unfamiliar name | 86% | 14% | 0% | 0% |
| Unnamed ("our ...") | 39% | 11% | 0% | 50% |

Completing tool, familiar minus unnamed: +61 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.002). Familiar minus unfamiliar: +14 points (p = 0.0001; Wilcoxon p = 0.062).

- **Unfamiliar name**, most-called tools: `get_latest_provider_version` 50%, `get_latest_module_version` 36%, `search_modules` 14%
- **Unnamed ("our ...")**, most-called tools: `get_latest_module_version` 39%, `search_modules` 11%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | What's the latest version of the Terraform provider for AWS? | `get_latest_provider_version` | 100% | 95% | 0% |
| 2 | What's the latest version of the Terraform provider for Cloudflare? | `get_latest_provider_version` | 100% | 50% | 0% |
| 3 | What's the latest version of the Terraform provider for Datadog? | `get_latest_provider_version` | 100% | 80% | 0% |
| 4 | What's the latest version of the Terraform provider for MongoDB Atlas? | `get_latest_provider_version` | 100% | 60% | 0% |
| 5 | What's the latest version of the Terraform provider for Okta? | `get_latest_provider_version` | 100% | 100% | 0% |
| 6 | What's the latest version of the terraform-aws-modules VPC module? | `get_latest_module_version` | 100% | 40% | 60% |
| 7 | What's the latest version of the terraform-aws-modules EKS module? | `get_latest_module_version` | 100% | 80% | 50% |
| 8 | What's the latest version of the terraform-aws-modules S3 bucket module? | `get_latest_module_version` | 100% | 25% | 55% |
| 9 | What's the latest version of the terraform-google-modules Kubernetes Engine module? | `get_latest_module_version` | 100% | 40% | 50% |
| 10 | What's the latest version of the terraform-aws-modules security group module? | `get_latest_module_version` | 100% | 50% | 50% |


## Caveats

- First turn only. A lookup or a clarifying question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model answered in text; in the cases we read, it was asking which entity was meant.
- Two models; `claude-sonnet-4-6` was served through OpenRouter rather than Anthropic's API.
- Identifiers quoted above come from a separate check that recorded call arguments (15 trials per condition on `gpt-5.6-terra`); the tables count tool names only.

## Reproduce

```bash
pip install 'ungrounded[all]'
ungrounded run --model gpt-5.6-terra --tools tools.json \
  --stimuli prompts.json --decoy-name search_modules --runs 10
```
The tool list, prompts and per-trial results are in this folder.

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Replace them with real requests from your users for a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | What's the latest version of the Terraform provider for AWS? | What's the latest version of the Terraform provider for Northbrook Cloud? | What's the latest version of the Terraform provider for our cloud platform? | `get_latest_provider_version` |
| 2 | What's the latest version of the Terraform provider for Cloudflare? | What's the latest version of the Terraform provider for Calderwick DNS? | What's the latest version of the Terraform provider for our DNS provider? | `get_latest_provider_version` |
| 3 | What's the latest version of the Terraform provider for Datadog? | What's the latest version of the Terraform provider for Vansgate Monitoring? | What's the latest version of the Terraform provider for our monitoring vendor? | `get_latest_provider_version` |
| 4 | What's the latest version of the Terraform provider for MongoDB Atlas? | What's the latest version of the Terraform provider for Wrenfield DB? | What's the latest version of the Terraform provider for our database host? | `get_latest_provider_version` |
| 5 | What's the latest version of the Terraform provider for Okta? | What's the latest version of the Terraform provider for Ashcombe Identity? | What's the latest version of the Terraform provider for our identity provider? | `get_latest_provider_version` |
| 6 | What's the latest version of the terraform-aws-modules VPC module? | What's the latest version of the Halloway VPC module? | What's the latest version of our standard VPC module? | `get_latest_module_version` |
| 7 | What's the latest version of the terraform-aws-modules EKS module? | What's the latest version of the Kestrel EKS module? | What's the latest version of our EKS cluster module? | `get_latest_module_version` |
| 8 | What's the latest version of the terraform-aws-modules S3 bucket module? | What's the latest version of the Pellmore S3 bucket module? | What's the latest version of our S3 bucket module? | `get_latest_module_version` |
| 9 | What's the latest version of the terraform-google-modules Kubernetes Engine module? | What's the latest version of the Riversend GKE module? | What's the latest version of our GKE module? | `get_latest_module_version` |
| 10 | What's the latest version of the terraform-aws-modules security group module? | What's the latest version of the Duncastle security group module? | What's the latest version of our security group module? | `get_latest_module_version` |
