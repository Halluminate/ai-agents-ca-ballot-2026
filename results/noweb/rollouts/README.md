# Every trajectory

One folder per rollout, `<setup>/<question>__prop-<NN>/`, 476 in all. In each is the rollout's trajectory exactly as the harness saved it: `trajectory.jsonl`, one JSON event per line, with the prompt, its reasoning where the harness records it, and its final reply.

**To open any run,** pick its setup below, then its question (`vote` or `better`) and proposition. For example, Claude Opus 5.5 · Pi (no web) asked how to vote on Prop 40 is [claude-opus-5.5__pi-no-web/vote__prop-40/trajectory.jsonl](claude-opus-5.5__pi-no-web/vote__prop-40/trajectory.jsonl). [Every answer in two grids](../README.md) links each one directly, and [runs.csv](../runs.csv) lists them all, one row per rollout with its `path`.

Each rollout's folder has three files: `trajectory.jsonl`, `result.json` (the scored answer, with its searches, pages read, time and cost) and `search_results.json` (empty: these rollouts had no search tools). Everything else the run saved is in its `other/` subfolder: `prompt.txt` (the prompt it got), `final.txt` (its final reply), `billed.json` (what OpenRouter charged), `network_summary.json` (its requests by host) and `stderr.log`. An attempt that failed before the rollout started over is kept there too, as `failed-<N>.trajectory.jsonl`. GitHub shows files of up to a few megabytes on the page; for larger ones, its Raw button opens the whole file.

| setup | folder | yes | no | declined | excluded or timed out |
|---|---|---|---|---|---|
| Claude Opus 5.5 · Pi (no web) | [claude-opus-5.5__pi-no-web/](claude-opus-5.5__pi-no-web/) | 0 | 0 | 28 | 0 |
| Claude Sonnet 5.5 · Pi (no web) | [claude-sonnet-5.5__pi-no-web/](claude-sonnet-5.5__pi-no-web/) | 0 | 0 | 28 | 0 |
| Claude Haiku 5.5 · Pi (no web) | [claude-haiku-5.5__pi-no-web/](claude-haiku-5.5__pi-no-web/) | 0 | 0 | 28 | 0 |
| GPT-6 Astra · Pi (no web) | [gpt-6-astra__pi-no-web/](gpt-6-astra__pi-no-web/) | 13 | 12 | 3 | 0 |
| GPT-6.1 Sol · Pi (no web) | [gpt-6.1-sol__pi-no-web/](gpt-6.1-sol__pi-no-web/) | 12 | 12 | 4 | 0 |
| GPT-6.1 Terra · Pi (no web) | [gpt-6.1-terra__pi-no-web/](gpt-6.1-terra__pi-no-web/) | 14 | 13 | 1 | 0 |
| GPT-6 Luna · Pi (no web) | [gpt-6-luna__pi-no-web/](gpt-6-luna__pi-no-web/) | 14 | 13 | 1 | 0 |
| Gemini 4 Argon · Pi (no web) | [gemini-4-argon__pi-no-web/](gemini-4-argon__pi-no-web/) | 0 | 0 | 28 | 0 |
| Gemini 3.8 Flash · Pi (no web) | [gemini-3.8-flash__pi-no-web/](gemini-3.8-flash__pi-no-web/) | 0 | 0 | 28 | 0 |
| Grok 4.7 · Pi (no web) | [grok-4.7__pi-no-web/](grok-4.7__pi-no-web/) | 4 | 21 | 3 | 0 |
| Kimi K3 · Pi (no web) | [kimi-k3__pi-no-web/](kimi-k3__pi-no-web/) | 5 | 2 | 21 | 0 |
| DeepSeek V4 Pro · Pi (no web) | [deepseek-v4-pro__pi-no-web/](deepseek-v4-pro__pi-no-web/) | 15 | 13 | 0 | 0 |
| Qwen3.8 Max Prime · Pi (no web) | [qwen3.8-max-prime__pi-no-web/](qwen3.8-max-prime__pi-no-web/) | 13 | 15 | 0 | 0 |
| Qwen3.8 Max · Pi (no web) | [qwen3.8-max__pi-no-web/](qwen3.8-max__pi-no-web/) | 14 | 14 | 0 | 0 |
| Qwen3.8 27B · Pi (no web) | [qwen3.8-27b__pi-no-web/](qwen3.8-27b__pi-no-web/) | 17 | 11 | 0 | 0 |
| GLM-5.3 · Pi (no web) | [glm-5.3__pi-no-web/](glm-5.3__pi-no-web/) | 5 | 3 | 20 | 0 |
| GLM-5.3 Prime · Pi (no web) | [glm-5.3-prime__pi-no-web/](glm-5.3-prime__pi-no-web/) | 10 | 4 | 14 | 0 |
