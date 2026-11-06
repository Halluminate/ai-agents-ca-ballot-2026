# Every trajectory

One folder per rollout, `<setup>/<question>__prop-<NN>/`, 1,134 in all. In each is the rollout's trajectory exactly as the harness saved it: `trajectory.jsonl`, one JSON event per line, with the prompt, every search and page the agent opened and what came back, its reasoning where the harness records it, and its final reply.

**To open any run,** pick its setup below, then its question (`vote`, `better` or `win`) and proposition. For example, Claude Opus 5.5 · Pi asked how to vote on Prop 40 is [claude-opus-5.5__pi/vote__prop-40/trajectory.jsonl](claude-opus-5.5__pi/vote__prop-40/trajectory.jsonl). [Every answer in three grids](../README.md) links each one directly, and [runs.csv](../runs.csv) lists them all, one row per rollout with its `path`.

Each rollout's folder has three files: `trajectory.jsonl`, `result.json` (the scored answer, with its searches, pages read, time and cost) and `search_results.json` (every result its searches returned). Everything else the run saved is in its `other/` subfolder: `prompt.txt` (the prompt it got), `final.txt` (its final reply), `billed.json` (what OpenRouter charged), `network_summary.json` (its requests by host) and `stderr.log`. An attempt that failed before the rollout started over is kept there too, as `failed-<N>.trajectory.jsonl`. GitHub shows files of up to a few megabytes on the page; for larger ones, its Raw button opens the whole file.

| setup | folder | yes | no | declined | excluded or timed out |
|---|---|---|---|---|---|
| Claude Opus 5.5 · Claude Code | [claude-opus-5.5__claude-code/](claude-opus-5.5__claude-code/) | 9 | 11 | 22 | 0 |
| Claude Opus 5.5 · Pi | [claude-opus-5.5__pi/](claude-opus-5.5__pi/) | 10 | 16 | 16 | 0 |
| Claude Sonnet 5.5 · Claude Code | [claude-sonnet-5.5__claude-code/](claude-sonnet-5.5__claude-code/) | 8 | 15 | 19 | 0 |
| Claude Sonnet 5.5 · Pi | [claude-sonnet-5.5__pi/](claude-sonnet-5.5__pi/) | 8 | 16 | 18 | 0 |
| Claude Haiku 5.5 · Claude Code | [claude-haiku-5.5__claude-code/](claude-haiku-5.5__claude-code/) | 12 | 18 | 10 | 2 |
| Claude Haiku 5.5 · Pi | [claude-haiku-5.5__pi/](claude-haiku-5.5__pi/) | 7 | 16 | 19 | 0 |
| GPT-6 Astra · Codex | [gpt-6-astra__codex/](gpt-6-astra__codex/) | 16 | 20 | 6 | 0 |
| GPT-6 Astra · Pi | [gpt-6-astra__pi/](gpt-6-astra__pi/) | 19 | 23 | 0 | 0 |
| GPT-6.1 Sol · Codex | [gpt-6.1-sol__codex/](gpt-6.1-sol__codex/) | 19 | 22 | 1 | 0 |
| GPT-6.1 Sol · Pi | [gpt-6.1-sol__pi/](gpt-6.1-sol__pi/) | 20 | 22 | 0 | 0 |
| GPT-6.1 Terra · Codex | [gpt-6.1-terra__codex/](gpt-6.1-terra__codex/) | 18 | 24 | 0 | 0 |
| GPT-6.1 Terra · Pi | [gpt-6.1-terra__pi/](gpt-6.1-terra__pi/) | 16 | 26 | 0 | 0 |
| GPT-6 Luna · Codex | [gpt-6-luna__codex/](gpt-6-luna__codex/) | 16 | 25 | 1 | 0 |
| GPT-6 Luna · Pi | [gpt-6-luna__pi/](gpt-6-luna__pi/) | 15 | 19 | 0 | 8 |
| Gemini 4 Argon · Gemini CLI | [gemini-4-argon__gemini-cli/](gemini-4-argon__gemini-cli/) | 6 | 8 | 28 | 0 |
| Gemini 4 Argon · Pi | [gemini-4-argon__pi/](gemini-4-argon__pi/) | 5 | 9 | 28 | 0 |
| Gemini 3.8 Flash · Gemini CLI | [gemini-3.8-flash__gemini-cli/](gemini-3.8-flash__gemini-cli/) | 6 | 8 | 28 | 0 |
| Gemini 3.8 Flash · Pi | [gemini-3.8-flash__pi/](gemini-3.8-flash__pi/) | 8 | 11 | 22 | 1 |
| Grok 4.7 · Grok Build | [grok-4.7__grok-build/](grok-4.7__grok-build/) | 12 | 30 | 0 | 0 |
| Grok 4.7 · Pi | [grok-4.7__pi/](grok-4.7__pi/) | 14 | 28 | 0 | 0 |
| Kimi K3 · Pi | [kimi-k3__pi/](kimi-k3__pi/) | 19 | 23 | 0 | 0 |
| DeepSeek V4 Pro · Pi | [deepseek-v4-pro__pi/](deepseek-v4-pro__pi/) | 14 | 26 | 0 | 2 |
| Qwen3.8 Max Prime · Pi | [qwen3.8-max-prime__pi/](qwen3.8-max-prime__pi/) | 18 | 24 | 0 | 0 |
| Qwen3.8 Max · Pi | [qwen3.8-max__pi/](qwen3.8-max__pi/) | 15 | 27 | 0 | 0 |
| Qwen3.8 27B · Pi | [qwen3.8-27b__pi/](qwen3.8-27b__pi/) | 15 | 24 | 3 | 0 |
| GLM-5.3 · Pi | [glm-5.3__pi/](glm-5.3__pi/) | 18 | 18 | 6 | 0 |
| GLM-5.3 Prime · Pi | [glm-5.3-prime__pi/](glm-5.3-prime__pi/) | 15 | 22 | 5 | 0 |
