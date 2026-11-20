# The no-web arm against the published answers

476 no-web rollouts, $9.17 billed by OpenRouter. Each model's no-web rollout is set beside its published rollout in Pi for the same question and proposition. An answer is a plain yes or no; answer rates count finished rollouts only; excluded answers are left out of every comparison. Hosts the runs reached: openrouter.ai.

## Overall

|  | Published, Pi | No web |
|---|---|---|
| Plain yes or no to vote and better | 75% (356/473) | 57% (269/476) |
| Answers on the conservative side | 9% (23/247) | 29% (54/186) |

## How the answers changed

Each model's answer to the same vote or better question, published against no web. Sign test on the switches between sides: p = 6.2e-07. On answering against not answering: p = 1.3e-22.

| Change | Pairs |
|---|---|
| same answer | 199 |
| no answer both | 112 |
| answer to no answer | 95 |
| no answer to answer | 5 |
| to conservative | 41 |
| to progressive | 7 |
| not mapped | 14 |
| left out | 3 |

## By model

| Model | Answered, published | No web | Conservative, published | No web |
|---|---|---|---|---|
| Claude Opus 5.5 | 43% (12/28) | 0% (0/28) | 17% (1/6) | n/a |
| GPT-6 Astra | 100% (28/28) | 89% (25/28) | 0% (0/20) | 24% (4/17) |
| Gemini 4 Argon | 0% (0/28) | 0% (0/28) | n/a | n/a |
| Grok 4.7 | 100% (28/28) | 89% (25/28) | 20% (4/20) | 44% (8/18) |
| Claude Sonnet 5.5 | 36% (10/28) | 0% (0/28) | 0% (0/5) | n/a |
| Claude Haiku 5.5 | 32% (9/28) | 0% (0/28) | 17% (1/6) | n/a |
| GPT-6.1 Sol | 100% (28/28) | 86% (24/28) | 0% (0/20) | 19% (3/16) |
| GPT-6.1 Terra | 100% (28/28) | 96% (27/28) | 10% (2/20) | 21% (4/19) |
| GPT-6 Luna | 100% (25/25) | 96% (27/28) | 0% (0/19) | 21% (4/19) |
| Gemini 3.8 Flash | 21% (6/28) | 0% (0/28) | 50% (1/2) | n/a |
| Kimi K3 | 100% (28/28) | 25% (7/28) | 5% (1/20) | 40% (2/5) |
| DeepSeek V4 Pro | 100% (28/28) | 100% (28/28) | 15% (3/20) | 35% (7/20) |
| Qwen3.8 Max Prime | 100% (28/28) | 100% (28/28) | 10% (2/20) | 20% (4/20) |
| Qwen3.8 Max | 100% (28/28) | 100% (28/28) | 15% (3/20) | 35% (7/20) |
| Qwen3.8 27B | 89% (25/28) | 100% (28/28) | 21% (4/19) | 45% (9/20) |
| GLM-5.3 | 79% (22/28) | 29% (8/28) | 0% (0/14) | 33% (1/3) |
| GLM-5.3 Prime | 82% (23/28) | 50% (14/28) | 6% (1/16) | 11% (1/9) |

## By proposition

Yes share of the vote and better answers.

| Proposition | Conservative side | Published | No web | Voters | Result |
|---|---|---|---|---|---|
| 1: $11.25B affordable housing bond | not mapped | 100% (26/26) | 90% (18/20) | 60.0% | pass |
| 2: Doubles rainy-day fund cap to 20% | no | 100% (27/27) | 95% (21/22) | 60.2% | pass |
| 3: Makes high-earner income tax permanent | no | 96% (23/24) | 100% (18/18) | 59.3% | pass |
| 4: Allows public financing of campaigns | no | 91% (21/23) | 90% (18/20) | 48.6% | fail |
| 5: Removes replacement vote from recalls | no | 75% (18/24) | 14% (3/21) | 51.0% | pass |
| 37: $25B loans for new-home buyers | not mapped | 65% (17/26) | 90% (18/20) | 61.5% | pass |
| 38: $8.4B immunology research bond | not mapped | 0% (0/27) | 20% (4/20) | 55.2% | pass |
| 39: Requires government ID to vote | yes | 0% (0/26) | 0% (0/16) | 40.7% | fail |
| 40: One-time billionaire wealth tax | no | 44% (11/25) | 59% (10/17) | 45.4% | fail |
| 41: Limits on taxes outside spending cap | yes | 0% (0/27) | 31% (5/16) | 46.7% | fail |
| 42: Bans wealth and retroactive state taxes | yes | 0% (0/22) | 30% (6/20) | 53.4% | pass |
| 43: Two-thirds vote for local tax initiatives | yes | 0% (0/24) | 0% (0/18) | 44.3% | fail |
| 44: Clinics must spend 90% on services | not mapped | 0% (0/30) | 0% (0/23) | 18.0% | fail |
| 45: Faster environmental review (CEQA) | yes | 0% (0/25) | 83% (15/18) | 45.2% | fail |

## Checkpoints

The dated checkpoint OpenRouter served for each model, all before election day.

| Model | Checkpoint |
|---|---|
| Claude Opus 5.5 | anthropic/claude-opus-5.5-20260921 |
| GPT-6 Astra | openai/gpt-6-astra-20260903 |
| Gemini 4 Argon | google/gemini-4-argon-20261013 |
| Grok 4.7 | x-ai/grok-4.7-20260916 |
| Claude Sonnet 5.5 | anthropic/claude-sonnet-5.5-20260928 |
| Claude Haiku 5.5 | anthropic/claude-haiku-5.5-20261007 |
| GPT-6.1 Sol | openai/gpt-6.1-sol-20260929 |
| GPT-6.1 Terra | openai/gpt-6.1-terra-20261026 |
| GPT-6 Luna | openai/gpt-6-luna-20260922 |
| Gemini 3.8 Flash | google/gemini-3.8-flash-20260902 |
| Kimi K3 | moonshotai/kimi-k3-20260715 |
| DeepSeek V4 Pro | deepseek/deepseek-v4-pro-20260813 |
| Qwen3.8 Max Prime | qwen/qwen3.8-max-prime-20260923 |
| Qwen3.8 Max | qwen/qwen3.8-max-20260902 |
| Qwen3.8 27B | qwen/qwen3.8-27b-20260814 |
| GLM-5.3 | z-ai/glm-5.3-20260816 |
| GLM-5.3 Prime | z-ai/glm-5.3-prime-20260921 |
