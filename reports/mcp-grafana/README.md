# How agents route requests in mcp-grafana when an entity can't be resolved


**What we ran.** Your server's real tool list (79 tools, from `tools/list` on mcp-grafana 2.0.0), unchanged. Ten requests, each in three versions that differ only in the entity. Grafana resources are internal, so instead of familiar and fictional names the versions are: **the exact UID given**, **the name only** ("the Checkout Latency dashboard"), and **unnamed** ("our main dashboard"). Each version ran 10 times per model at temperature 1.0. We recorded every tool called in the agent's first turn; no tools were executed. Models: `gpt-5.6-terra` (OpenAI API, reasoning effort `none`). Measured with [`ungrounded`](https://github.com/Taran-Douley/ungrounded) 0.3.0, 1 October 2026.

## Summary

Routing looks good, and the catalogue gives agents what they need.

- **UID given:** the agent calls the right tool directly (80% overall; 100% on 7 of 10 prompts).
- **Name only:** it looks the resource up first in 99% of trials and never guesses a UID, e.g. `search_dashboards {"query": "Checkout Latency"}`, `list_datasources {"type": "loki", "name": "Production"}`.
- **Unnamed ("our main dashboard"):** it searches or lists (92%), or asks.
- On two prompts with a UID given (querying Loki logs and Prometheus), the agent first ran the discovery steps your tool descriptions recommend, such as listing metric names. That's the documented workflow, not a routing problem.

## What this might mean for the server

Nothing to fix. This is a useful contrast with servers that lack a name-based lookup, where agents tend to guess identifiers.

## Results by model

Share of trials whose first assistant turn called each kind of tool. A trial can call more than one tool, so rows need not sum to 100%.

### `gpt-5.6-terra` (300 trials)

| | Completing tool | Lookup tool | Other tools | No tool call |
|---|---|---|---|---|
| UID given | 80% | 0% | 18% | 2% |
| Name only | 0% | 99% | 0% | 1% |
| Unnamed ("our ...") | 0% | 92% | 0% | 8% |

Completing tool, UID given minus unnamed: +80 points (within-prompt permutation p = < 1e-4; prompt-level Wilcoxon p = 0.0039). UID given minus name only: +80 points (p = < 1e-4; Wilcoxon p = 0.0039).

- **Name only**, most-called tools: `list_datasources` 60%, `search_dashboards` 39%
- **Unnamed ("our ...")**, most-called tools: `list_datasources` 59%, `search_dashboards` 33%

## Per-prompt completing-tool rate (all models pooled)

| # | Task (familiar version) | Completing tool | UID given | Name only | Unnamed |
|---|---|---|---|---|---|
| 1 | Summarise the dashboard with UID a1b2c3d4. | `get_dashboard_summary` | 100% | 0% | 0% |
| 2 | List the panel queries on the dashboard with UID k8s-ovw-01. | `get_dashboard_panel_queries` | 100% | 0% | 0% |
| 3 | Show the version history of the dashboard with UID pay-svc-77. | `list_dashboard_versions` | 100% | 0% | 0% |
| 4 | Get the full definition of the dashboard with UID db-perf-2. | `get_dashboard_by_uid` | 100% | 0% | 0% |
| 5 | List the metric names in the Prometheus datasource with UID P1809F7CD0C75ACF3. | `list_prometheus_metric_names` | 100% | 0% | 0% |
| 6 | List the label names in the Loki datasource with UID P8E80F9AEF21F6940. | `list_loki_label_names` | 100% | 0% | 0% |
| 7 | Show the latest error logs from the Loki datasource with UID P8E80F9AEF21F6940. | `query_loki_logs` | 0% | 0% | 0% |
| 8 | What's the current value of sum(rate(http_requests_total[5m])) in the Prometheus datasource with UID P1809F7CD0C75ACF3? | `query_prometheus` | 10% | 0% | 0% |
| 9 | List the trace attribute names in the Tempo datasource with UID P214B5B846CF3925F. | `list_tempo_attribute_names` | 90% | 0% | 0% |
| 10 | List the label names in the Prometheus datasource with UID PBFA97CFB590B2093. | `list_prometheus_label_names` | 100% | 0% | 0% |


## Caveats

- First turn only. Looking something up or asking a question is often the right first step, so a lower completing-tool rate is not, on its own, a bug.
- Ten prompts written by us, not drawn from your users' traffic.
- "No tool call" means the model replied in text; in the samples we read it was asking which entity was meant.

## Reproduce

Against the server itself (mcp-grafana 2.0.0, from its GitHub releases):

```bash
pip install 'ungrounded[all]'
ungrounded run --mcp "mcp-grafana" \
  --stimuli prompts.json --decoy-name search_dashboards --runs 10 --model <model>
```

Or against the saved tool list in this folder:

```bash
ungrounded run --tools tools.json --stimuli prompts.json --decoy-name search_dashboards --runs 10 --model <model>
```

To re-run against a branch, point `--mcp` at your local build.

## Appendix: the prompts

Each row holds the task fixed and changes only the entity. Written by us, with LLM assistance, from your tool descriptions. Real requests from your users would give a more representative number.

| # | UID given | Name only | Unnamed | Completing tool |
|---|---|---|---|---|
| 1 | Summarise the dashboard with UID a1b2c3d4. | Summarise the Checkout Latency dashboard. | Summarise our main dashboard. | `get_dashboard_summary` |
| 2 | List the panel queries on the dashboard with UID k8s-ovw-01. | List the panel queries on the Kubernetes Overview dashboard. | List the panel queries on our team's dashboard. | `get_dashboard_panel_queries` |
| 3 | Show the version history of the dashboard with UID pay-svc-77. | Show the version history of the Payments Service dashboard. | Show the version history of our on-call dashboard. | `list_dashboard_versions` |
| 4 | Get the full definition of the dashboard with UID db-perf-2. | Get the full definition of the Database Performance dashboard. | Get the full definition of our SLO dashboard. | `get_dashboard_by_uid` |
| 5 | List the metric names in the Prometheus datasource with UID P1809F7CD0C75ACF3. | List the metric names in the Production Prometheus datasource. | List the metric names in our metrics datasource. | `list_prometheus_metric_names` |
| 6 | List the label names in the Loki datasource with UID P8E80F9AEF21F6940. | List the label names in the Production Loki datasource. | List the label names in our logs datasource. | `list_loki_label_names` |
| 7 | Show the latest error logs from the Loki datasource with UID P8E80F9AEF21F6940. | Show the latest error logs from the Production Loki datasource. | Show the latest error logs from our logs datasource. | `query_loki_logs` |
| 8 | What's the current value of sum(rate(http_requests_total[5m])) in the Prometheus datasource with UID P1809F7CD0C75ACF3? | What's the current value of sum(rate(http_requests_total[5m])) in the Production Prometheus datasource? | What's the current value of sum(rate(http_requests_total[5m])) in our metrics datasource? | `query_prometheus` |
| 9 | List the trace attribute names in the Tempo datasource with UID P214B5B846CF3925F. | List the trace attribute names in the Production Tempo datasource. | List the trace attribute names in our tracing datasource. | `list_tempo_attribute_names` |
| 10 | List the label names in the Prometheus datasource with UID PBFA97CFB590B2093. | List the label names in the Staging Prometheus datasource. | List the label names in our staging metrics datasource. | `list_prometheus_label_names` |
