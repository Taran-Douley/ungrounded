# How agents route requests in the AWS Documentation MCP server when an entity can't be resolved


**What we ran.** Your server's real tool list (5 tools, from `tools/list` on awslabs.aws-documentation-mcp-server (latest on 1 October 2026)), unchanged. Ten requests, each in three versions that differ only in the entity: a real AWS feature, a fictional AWS service, and an unnamed one ("our storage service"). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Models: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`) and `claude-sonnet-4-6` (via OpenRouter). Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

Routing looks good in every condition.

- **Both models searched the documentation before reading a page.** `gpt-5.6-terra` searched first in 96–100% of trials in every condition. `claude-sonnet-4-6` searched first for real features (95%) and "our ..." requests (90%); for fictional services it searched (72%) or asked which service was meant (28%).
- **Neither model guessed a documentation URL for a fictional service.**
- **Fictional services were searched by name** (e.g. `search_documentation {"search_phrase": "Amazon Kestrel Streams retention"}`) rather than mapped to a made-up page.

## What this might mean for the server

Nothing to fix. The tool descriptions steer agents to search before reading, and they do.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `claude-sonnet-4-6` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 6% | 95% | 0% | 0% |
| Unfamiliar name | 0% | 72% | 0% | 28% |
| Unnamed ("our ...") | 0% | 90% | 0% | 10% |

Completing tool, familiar minus unnamed: +6 points (within-prompt permutation p = 0.018; prompt-level Wilcoxon p = 0.5). Familiar minus unfamiliar: +6 points (p = 0.015; Wilcoxon p = 0.5).

- **Unfamiliar name**, most-called tools: `search_documentation` 72%
- **Unnamed ("our ...")**, most-called tools: `search_documentation` 90%

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| Familiar name | 0% | 100% | 0% | 0% |
| Unfamiliar name | 0% | 99% | 0% | 1% |
| Unnamed ("our ...") | 0% | 96% | 0% | 4% |

Completing tool, familiar minus unnamed: +0 points (within-prompt permutation p = 1; prompt-level Wilcoxon p = 1). Familiar minus unfamiliar: +0 points (p = 1; Wilcoxon p = 1).

- **Unfamiliar name**, most-called tools: `search_documentation` 99%
- **Unnamed ("our ...")**, most-called tools: `search_documentation` 96%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | Familiar | Unfamiliar | Unnamed |
|---|---|---|---|---|---|
| 1 | Read the AWS documentation page on S3 lifecycle configuration. | `read_documentation` | 0% | 0% | 0% |
| 2 | Read the AWS documentation page on Lambda function timeouts. | `read_documentation` | 0% | 0% | 0% |
| 3 | Read the AWS documentation page on DynamoDB time to live. | `read_documentation` | 0% | 0% | 0% |
| 4 | Read the AWS documentation page on CloudFront cache behaviours. | `read_documentation` | 0% | 0% | 0% |
| 5 | Read the AWS documentation page on SQS visibility timeout. | `read_documentation` | 0% | 0% | 0% |
| 6 | Read the AWS documentation page on IAM policy evaluation logic. | `read_documentation` | 0% | 0% | 0% |
| 7 | Read the AWS documentation page on EC2 instance metadata (IMDSv2). | `read_documentation` | 0% | 0% | 0% |
| 8 | Read the AWS documentation page on RDS automated backups. | `read_documentation` | 0% | 0% | 0% |
| 9 | Read the AWS documentation page on Route 53 health checks. | `read_documentation` | 5% | 0% | 0% |
| 10 | Read the AWS documentation page on ECS task definitions. | `read_documentation` | 25% | 0% | 0% |


## Caveats

- First turn only. Looking something up or asking a question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model replied in text; in the samples we read it was asking which entity was meant.

## Reproduce

```bash
pip install 'ungrounded[all]'
ungrounded run --model <model> --tools tools.json --stimuli prompts.json --decoy-name search_documentation --runs 10
```

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Real requests from your users would give a more representative number.

| # | Familiar | Unfamiliar (fictional) | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Read the AWS documentation page on S3 lifecycle configuration. | Read the AWS documentation page on Amazon Kestrel Streams retention. | Read the AWS documentation page for our storage service's lifecycle rules. | `read_documentation` |
| 2 | Read the AWS documentation page on Lambda function timeouts. | Read the AWS documentation page on AWS Northbrook Functions timeouts. | Read the AWS documentation page on timeouts for the compute service we use. | `read_documentation` |
| 3 | Read the AWS documentation page on DynamoDB time to live. | Read the AWS documentation page on Amazon Halloway DB time to live. | Read the AWS documentation page on time to live for our database. | `read_documentation` |
| 4 | Read the AWS documentation page on CloudFront cache behaviours. | Read the AWS documentation page on Amazon Ashcombe Edge cache behaviours. | Read the AWS documentation page on cache behaviours for our CDN setup. | `read_documentation` |
| 5 | Read the AWS documentation page on SQS visibility timeout. | Read the AWS documentation page on Amazon Wrenfield Queue visibility timeout. | Read the AWS documentation page on visibility timeout for our queue service. | `read_documentation` |
| 6 | Read the AWS documentation page on IAM policy evaluation logic. | Read the AWS documentation page on AWS Calderwick Identity policy evaluation. | Read the AWS documentation page on policy evaluation for our access setup. | `read_documentation` |
| 7 | Read the AWS documentation page on EC2 instance metadata (IMDSv2). | Read the AWS documentation page on Amazon Trellidge Compute instance metadata. | Read the AWS documentation page on instance metadata for our servers. | `read_documentation` |
| 8 | Read the AWS documentation page on RDS automated backups. | Read the AWS documentation page on Amazon Pellmore RDS automated backups. | Read the AWS documentation page on automated backups for our database host. | `read_documentation` |
| 9 | Read the AWS documentation page on Route 53 health checks. | Read the AWS documentation page on Amazon Riversend DNS health checks. | Read the AWS documentation page on health checks for our DNS service. | `read_documentation` |
| 10 | Read the AWS documentation page on ECS task definitions. | Read the AWS documentation page on Amazon Duncastle Containers task definitions. | Read the AWS documentation page on task definitions for our container service. | `read_documentation` |
