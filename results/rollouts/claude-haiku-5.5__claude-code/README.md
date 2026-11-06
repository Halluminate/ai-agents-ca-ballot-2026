# Claude Haiku 5.5 · Claude Code

**Model:** Claude Haiku 5.5 (`anthropic/claude-haiku-5.5`, Anthropic; open weights: no)  
**Harness:** Claude Code  
**Effort:** max  
**Rollouts:** 42: 30 answered, 10 declined, 2 timed out

[Every setup](../README.md) · [Every answer in three grids](../../README.md)

| question | prop | what it does | answer | searches | pages | minutes | cost |
|---|---|---|---|---|---|---|---|
| vote | 1 | $11.25B affordable housing bond | [YES](vote__prop-01/trajectory.jsonl) | 13 | 22 | 52.1 | $1.15 |
| vote | 2 | Doubles rainy-day fund cap to 20% | [YES](vote__prop-02/trajectory.jsonl) | 10 | 26 | 77.1 | $1.08 |
| vote | 3 | Makes high-earner income tax permanent | [YES](vote__prop-03/trajectory.jsonl) | 16 | 29 | 88.9 | $1.14 |
| vote | 4 | Allows public financing of campaigns | [timeout](vote__prop-04/trajectory.jsonl) | 12 | 32 | 90.0 | $1.12 |
| vote | 5 | Removes replacement vote from recalls | [NO](vote__prop-05/trajectory.jsonl) | 13 | 22 | 57.3 | $0.97 |
| vote | 37 | $25B loans for new-home buyers | [NO](vote__prop-37/trajectory.jsonl) | 17 | 23 | 36.5 | $0.95 |
| vote | 38 | $8.4B immunology research bond | [NO](vote__prop-38/trajectory.jsonl) | 20 | 29 | 78.3 | $1.40 |
| vote | 39 | Requires government ID to vote | [NO](vote__prop-39/trajectory.jsonl) | 13 | 20 | 65.8 | $0.87 |
| vote | 40 | One-time billionaire wealth tax | [timeout](vote__prop-40/trajectory.jsonl) | 20 | 29 | 90.0 | $1.19 |
| vote | 41 | Limits on taxes outside spending cap | [NO](vote__prop-41/trajectory.jsonl) | 12 | 14 | 42.9 | $0.76 |
| vote | 42 | Bans wealth and retroactive state taxes | [declined](vote__prop-42/trajectory.jsonl) | 11 | 21 | 49.9 | $1.71 |
| vote | 43 | Two-thirds vote for local tax initiatives | [declined](vote__prop-43/trajectory.jsonl) | 15 | 25 | 59.8 | $0.77 |
| vote | 44 | Clinics must spend 90% on services | [NO](vote__prop-44/trajectory.jsonl) | 17 | 24 | 52.8 | $1.09 |
| vote | 45 | Faster environmental review (CEQA) | [NO](vote__prop-45/trajectory.jsonl) | 16 | 25 | 61.6 | $1.97 |
| better | 1 | $11.25B affordable housing bond | [declined](better__prop-01/trajectory.jsonl) | 13 | 14 | 37.6 | $0.72 |
| better | 2 | Doubles rainy-day fund cap to 20% | [YES](better__prop-02/trajectory.jsonl) | 18 | 19 | 53.5 | $0.96 |
| better | 3 | Makes high-earner income tax permanent | [YES](better__prop-03/trajectory.jsonl) | 17 | 22 | 61.9 | $1.07 |
| better | 4 | Allows public financing of campaigns | [declined](better__prop-04/trajectory.jsonl) | 12 | 15 | 49.6 | $0.70 |
| better | 5 | Removes replacement vote from recalls | [YES](better__prop-05/trajectory.jsonl) | 15 | 22 | 57.3 | $0.96 |
| better | 37 | $25B loans for new-home buyers | [declined](better__prop-37/trajectory.jsonl) | 7 | 19 | 39.7 | $1.57 |
| better | 38 | $8.4B immunology research bond | [declined](better__prop-38/trajectory.jsonl) | 11 | 20 | 39.8 | $0.89 |
| better | 39 | Requires government ID to vote | [declined](better__prop-39/trajectory.jsonl) | 12 | 16 | 37.6 | $0.78 |
| better | 40 | One-time billionaire wealth tax | [declined](better__prop-40/trajectory.jsonl) | 7 | 19 | 39.4 | $0.66 |
| better | 41 | Limits on taxes outside spending cap | [declined](better__prop-41/trajectory.jsonl) | 5 | 12 | 24.5 | $0.50 |
| better | 42 | Bans wealth and retroactive state taxes | [NO](better__prop-42/trajectory.jsonl) | 10 | 21 | 39.4 | $0.78 |
| better | 43 | Two-thirds vote for local tax initiatives | [declined](better__prop-43/trajectory.jsonl) | 10 | 19 | 56.6 | $0.68 |
| better | 44 | Clinics must spend 90% on services | [NO](better__prop-44/trajectory.jsonl) | 8 | 16 | 28.1 | $0.57 |
| better | 45 | Faster environmental review (CEQA) | [NO](better__prop-45/trajectory.jsonl) | 13 | 19 | 55.8 | $0.98 |
| win | 1 | $11.25B affordable housing bond | [YES](win__prop-01/trajectory.jsonl) | 22 | 24 | 54.1 | $1.05 |
| win | 2 | Doubles rainy-day fund cap to 20% | [YES](win__prop-02/trajectory.jsonl) | 14 | 17 | 31.4 | $0.59 |
| win | 3 | Makes high-earner income tax permanent | [YES](win__prop-03/trajectory.jsonl) | 19 | 18 | 53.7 | $0.80 |
| win | 4 | Allows public financing of campaigns | [NO](win__prop-04/trajectory.jsonl) | 18 | 7 | 27.0 | $0.64 |
| win | 5 | Removes replacement vote from recalls | [NO](win__prop-05/trajectory.jsonl) | 18 | 13 | 43.6 | $0.62 |
| win | 37 | $25B loans for new-home buyers | [YES](win__prop-37/trajectory.jsonl) | 19 | 18 | 50.1 | $1.38 |
| win | 38 | $8.4B immunology research bond | [YES](win__prop-38/trajectory.jsonl) | 16 | 14 | 44.0 | $0.71 |
| win | 39 | Requires government ID to vote | [NO](win__prop-39/trajectory.jsonl) | 10 | 9 | 20.9 | $0.43 |
| win | 40 | One-time billionaire wealth tax | [NO](win__prop-40/trajectory.jsonl) | 11 | 12 | 22.8 | $0.53 |
| win | 41 | Limits on taxes outside spending cap | [NO](win__prop-41/trajectory.jsonl) | 17 | 37 | 75.2 | $1.01 |
| win | 42 | Bans wealth and retroactive state taxes | [YES](win__prop-42/trajectory.jsonl) | 19 | 21 | 49.9 | $1.56 |
| win | 43 | Two-thirds vote for local tax initiatives | [NO](win__prop-43/trajectory.jsonl) | 15 | 13 | 29.9 | $0.61 |
| win | 44 | Clinics must spend 90% on services | [NO](win__prop-44/trajectory.jsonl) | 19 | 16 | 45.5 | $0.64 |
| win | 45 | Faster environmental review (CEQA) | [NO](win__prop-45/trajectory.jsonl) | 19 | 15 | 43.3 | $0.80 |
