# Where the models searched

1132 finished rollouts. Timeouts are left out.

## Overview

| setup | rollouts | searches per rollout | rollouts with no search | pages opened per rollout | sites seen | read the official guide | saw LAO | saw an older election |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 · Claude Code | 42 | 16.1 | 0 | 25.0 | 759 | 100% | 88% | 69% |
| Claude Opus 5.5 · Pi | 42 | 14.4 | 0 | 28.5 | 744 | 100% | 100% | 40% |
| GPT-6 Astra · Codex | 42 | 7.5 | 0 | 7.2 | 1104 | 100% | 86% | 79% |
| GPT-6 Astra · Pi | 42 | 8.5 | 0 | 25.8 | 682 | 100% | 95% | 55% |
| Gemini 4 Argon · Gemini CLI | 42 | 1.7 | 22 | 2.3 | 103 | 100% | 0% | 0% |
| Gemini 4 Argon · Pi | 42 | 2.5 | 16 | 7.7 | 186 | 100% | 38% | 48% |
| Grok 4.7 · Grok Build | 42 | 10.3 | 6 | 14.6 | 314 | 100% | 90% | 19% |
| Grok 4.7 · Pi | 42 | 6.9 | 0 | 8.7 | 426 | 100% | 98% | 55% |
| Claude Sonnet 5.5 · Claude Code | 42 | 16.4 | 0 | 27.9 | 644 | 100% | 88% | 71% |
| Claude Sonnet 5.5 · Pi | 42 | 14.5 | 0 | 24.7 | 618 | 100% | 100% | 90% |
| Claude Haiku 5.5 · Claude Code | 40 | 14.2 | 0 | 19.2 | 568 | 100% | 92% | 60% |
| Claude Haiku 5.5 · Pi | 42 | 12.8 | 0 | 20.8 | 622 | 100% | 100% | 43% |
| GPT-6.1 Sol · Codex | 42 | 7.9 | 0 | 6.4 | 1383 | 98% | 93% | 76% |
| GPT-6.1 Sol · Pi | 42 | 7.8 | 0 | 24.4 | 603 | 100% | 98% | 52% |
| GPT-6.1 Terra · Codex | 42 | 7.4 | 0 | 0.1 | 1002 | 5% | 95% | 93% |
| GPT-6.1 Terra · Pi | 42 | 17.4 | 0 | 24.3 | 742 | 100% | 100% | 86% |
| GPT-6 Luna · Codex | 42 | 8.0 | 0 | 0.7 | 1050 | 64% | 93% | 90% |
| GPT-6 Luna · Pi | 42 | 39.7 | 0 | 24.0 | 1240 | 81% | 93% | 95% |
| Gemini 3.8 Flash · Gemini CLI | 42 | 4.1 | 3 | 1.6 | 174 | 100% | 0% | 0% |
| Gemini 3.8 Flash · Pi | 42 | 8.7 | 0 | 3.3 | 579 | 98% | 83% | 71% |
| Kimi K3 · Pi | 42 | 4.5 | 0 | 4.2 | 292 | 100% | 93% | 83% |
| DeepSeek V4 Pro · Pi | 42 | 4.2 | 0 | 5.0 | 227 | 95% | 90% | 64% |
| Qwen3.8 Max Prime · Pi | 42 | 9.5 | 0 | 11.4 | 512 | 100% | 100% | 79% |
| Qwen3.8 Max · Pi | 42 | 10.2 | 0 | 11.0 | 540 | 100% | 98% | 71% |
| Qwen3.8 27B · Pi | 42 | 4.2 | 0 | 5.6 | 338 | 100% | 100% | 48% |
| GLM-5.3 · Pi | 42 | 5.9 | 0 | 6.2 | 375 | 100% | 93% | 67% |
| GLM-5.3 Prime · Pi | 42 | 5.2 | 0 | 6.3 | 340 | 100% | 95% | 67% |

"Sites seen" counts every site in search results or opened pages. "Read the official guide" means the rollout opened a voterguide.sos.ca.gov page. "Saw an older election" means a result or page came from a past voter guide, such as 2024's, which reused Props 2 to 5. Codex, Gemini CLI and Grok Build search on their providers' servers, so the sites in their search results are the ones those servers sent back. For Gemini CLI they are the sources its search helper cited.

## Top sites per setup

Each number is how many rollouts saw that site.

| setup | sites in results or pages | pages opened |
|---|---|---|
| Claude Opus 5.5 · Claude Code | calmatters.org (42), en.wikipedia.org (42), voterguide.sos.ca.gov (42), sfchronicle.com (41), igs.berkeley.edu (39), laist.com (39), lao.ca.gov (37), californiatoday.com (36), kqed.org (36), vig.cdn.sos.ca.gov (33) | voterguide.sos.ca.gov (42), calmatters.org (41), sfchronicle.com (31), kqed.org (28), laist.com (27), lao.ca.gov (24) |
| Claude Opus 5.5 · Pi | lao.ca.gov (42), latimes.com (42), quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), calmatters.org (41), sacbee.com (41), sfchronicle.com (41), mercurynews.com (39), igs.berkeley.edu (37), yahoo.com (35) | voterguide.sos.ca.gov (42), calmatters.org (33), latimes.com (30), sfchronicle.com (28), vig.cdn.sos.ca.gov (28), sacbee.com (26) |
| GPT-6 Astra · Codex | calmatters.org (42), en.wikipedia.org (42), reddit.com (42), voterguide.sos.ca.gov (42), apnews.com (39), igs.berkeley.edu (39), ballotpedia.org (38), kqed.org (38), lao.ca.gov (36), vig.cdn.sos.ca.gov (35) | voterguide.sos.ca.gov (42), calmatters.org (20), lao.ca.gov (11), ppic.org (10), ballotpedia.org (8), leginfo.legislature.ca.gov (8) |
| GPT-6 Astra · Pi | voterguide.sos.ca.gov (42), calmatters.org (41), quickguidetoprops.sos.ca.gov (41), lao.ca.gov (40), latimes.com (37), igs.berkeley.edu (36), sos.ca.gov (35), sacbee.com (32), vig.cdn.sos.ca.gov (29), sfchronicle.com (28) | voterguide.sos.ca.gov (42), calmatters.org (39), vig.cdn.sos.ca.gov (28), igs.berkeley.edu (27), ppic.org (20), sfchronicle.com (20) |
| Gemini 4 Argon · Gemini CLI | voterguide.sos.ca.gov (42), ca.gov (19), ballotpedia.org (18), calmatters.org (18), berkeley.edu (17), kqed.org (13), spur.org (13), multistate.us (11), latimes.com (10), youtube.com (10) | voterguide.sos.ca.gov (42), ballotpedia.org (5), vertexaisearch.cloud.google.com (3), en.wikipedia.org (1), fppc.ca.gov (1), sos.ca.gov (1) |
| Gemini 4 Argon · Pi | voterguide.sos.ca.gov (42), quickguidetoprops.sos.ca.gov (25), sos.ca.gov (20), vigarchive.sos.ca.gov (19), lao.ca.gov (16), igs.berkeley.edu (15), vig.cdn.sos.ca.gov (14), calmatters.org (13), californiatoday.com (12), latimes.com (12) | voterguide.sos.ca.gov (42), vig.cdn.sos.ca.gov (14), igs.berkeley.edu (10), calmatters.org (8), californiatoday.com (7), escholarship.org (6) |
| Grok 4.7 · Grok Build | voterguide.sos.ca.gov (42), ballotpedia.org (41), lao.ca.gov (38), calmatters.org (34), vig.cdn.sos.ca.gov (27), latimes.com (26), sfchronicle.com (26), hoover.org (25), ppic.org (25), igs.berkeley.edu (21) | voterguide.sos.ca.gov (42), ballotpedia.org (37), lao.ca.gov (26), vig.cdn.sos.ca.gov (25), calmatters.org (21), ppic.org (20) |
| Grok 4.7 · Pi | voterguide.sos.ca.gov (42), lao.ca.gov (41), quickguidetoprops.sos.ca.gov (41), latimes.com (40), calmatters.org (38), igs.berkeley.edu (36), sfchronicle.com (35), sacbee.com (34), sos.ca.gov (32), vig.cdn.sos.ca.gov (26) | voterguide.sos.ca.gov (42), vig.cdn.sos.ca.gov (23), calmatters.org (16), lao.ca.gov (15), sfchronicle.com (15), calbudgetcenter.org (11) |
| Claude Sonnet 5.5 · Claude Code | calmatters.org (42), en.wikipedia.org (42), voterguide.sos.ca.gov (42), igs.berkeley.edu (41), laist.com (41), sfchronicle.com (40), kqed.org (39), lao.ca.gov (37), ppic.org (36), vig.cdn.sos.ca.gov (36) | calmatters.org (42), voterguide.sos.ca.gov (42), igs.berkeley.edu (34), sfchronicle.com (33), kqed.org (31), lao.ca.gov (29) |
| Claude Sonnet 5.5 · Pi | calmatters.org (42), lao.ca.gov (42), latimes.com (42), quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), igs.berkeley.edu (41), ppic.org (38), sacbee.com (38), sfchronicle.com (38), vigarchive.sos.ca.gov (37) | voterguide.sos.ca.gov (42), calmatters.org (39), latimes.com (35), ppic.org (28), vig.cdn.sos.ca.gov (27), sfchronicle.com (26) |
| Claude Haiku 5.5 · Claude Code | calmatters.org (40), en.wikipedia.org (40), voterguide.sos.ca.gov (40), igs.berkeley.edu (39), laist.com (38), lao.ca.gov (37), sfchronicle.com (37), ppic.org (35), kqed.org (34), cavotes.org (31) | calmatters.org (40), voterguide.sos.ca.gov (40), ppic.org (33), igs.berkeley.edu (32), lao.ca.gov (29), sfchronicle.com (23) |
| Claude Haiku 5.5 · Pi | calmatters.org (42), lao.ca.gov (42), voterguide.sos.ca.gov (42), quickguidetoprops.sos.ca.gov (41), latimes.com (40), ppic.org (40), sacbee.com (40), sfchronicle.com (38), sos.ca.gov (38), igs.berkeley.edu (36) | voterguide.sos.ca.gov (42), calmatters.org (40), vig.cdn.sos.ca.gov (25), lao.ca.gov (24), ppic.org (24), igs.berkeley.edu (22) |
| GPT-6.1 Sol · Codex | calmatters.org (42), en.wikipedia.org (42), igs.berkeley.edu (42), reddit.com (42), voterguide.sos.ca.gov (42), kqed.org (39), lao.ca.gov (39), ballotpedia.org (37), sos.ca.gov (36), apnews.com (35) | voterguide.sos.ca.gov (41), calmatters.org (13), lao.ca.gov (11), ballotpedia.org (10), ppic.org (10), igs.berkeley.edu (8) |
| GPT-6.1 Sol · Pi | quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), lao.ca.gov (41), calmatters.org (40), latimes.com (40), sos.ca.gov (35), igs.berkeley.edu (34), vig.cdn.sos.ca.gov (31), sacbee.com (30), sfchronicle.com (30) | voterguide.sos.ca.gov (42), calmatters.org (39), vig.cdn.sos.ca.gov (28), igs.berkeley.edu (27), latimes.com (22), sfchronicle.com (22) |
| GPT-6.1 Terra · Codex | calmatters.org (42), en.wikipedia.org (42), igs.berkeley.edu (42), reddit.com (42), voterguide.sos.ca.gov (42), apnews.com (41), axios.com (40), kiplinger.com (40), kqed.org (40), lao.ca.gov (39) | voterguide.sos.ca.gov (2), calbudgetcenter.org (1), leginfo.legislature.ca.gov (1), probolskyresearch.com (1) |
| GPT-6.1 Terra · Pi | lao.ca.gov (42), quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), igs.berkeley.edu (41), latimes.com (41), sos.ca.gov (41), calmatters.org (39), sacbee.com (39), mercurynews.com (35), sfchronicle.com (33) | voterguide.sos.ca.gov (42), igs.berkeley.edu (31), calmatters.org (29), vig.cdn.sos.ca.gov (28), sfchronicle.com (26), lao.ca.gov (25) |
| GPT-6 Luna · Codex | en.wikipedia.org (42), kqed.org (42), reddit.com (42), voterguide.sos.ca.gov (42), apnews.com (41), calmatters.org (41), axios.com (40), igs.berkeley.edu (40), latimes.com (40), theatlantic.com (40) | voterguide.sos.ca.gov (27), electionresults.sos.ca.gov (1), lao.ca.gov (1), probolskyresearch.com (1) |
| GPT-6 Luna · Pi | igs.berkeley.edu (40), latimes.com (40), lao.ca.gov (39), sos.ca.gov (39), quickguidetoprops.sos.ca.gov (37), sacbee.com (37), calmatters.org (36), en.wikipedia.org (36), mercurynews.com (34), sfchronicle.com (34) | lao.ca.gov (35), voterguide.sos.ca.gov (34), igs.berkeley.edu (24), calmatters.org (22), latimes.com (22), ppic.org (22) |
| Gemini 3.8 Flash · Gemini CLI | voterguide.sos.ca.gov (42), ca.gov (36), ballotpedia.org (27), calmatters.org (26), berkeley.edu (21), youtube.com (20), spur.org (18), latimes.com (16), kqed.org (15), ppic.org (12) | voterguide.sos.ca.gov (42), ballotpedia.org (1), vertexaisearch.cloud.google.com (1) |
| Gemini 3.8 Flash · Pi | voterguide.sos.ca.gov (42), quickguidetoprops.sos.ca.gov (41), sos.ca.gov (39), lao.ca.gov (35), latimes.com (30), igs.berkeley.edu (25), vigarchive.sos.ca.gov (24), sfchronicle.com (23), kpbs.org (22), mercurynews.com (22) | voterguide.sos.ca.gov (41), vig.cdn.sos.ca.gov (4), igs.berkeley.edu (3), sfchronicle.com (3), anthropic.com (2), en.wikipedia.org (2) |
| Kimi K3 · Pi | quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), lao.ca.gov (39), latimes.com (36), sacbee.com (35), calmatters.org (32), vigarchive.sos.ca.gov (32), sos.ca.gov (30), mercurynews.com (25), sfchronicle.com (25) | voterguide.sos.ca.gov (42), calmatters.org (14), lao.ca.gov (9), hoover.org (6), latimes.com (6), vig.cdn.sos.ca.gov (6) |
| DeepSeek V4 Pro · Pi | voterguide.sos.ca.gov (40), lao.ca.gov (38), quickguidetoprops.sos.ca.gov (38), sacbee.com (35), latimes.com (32), calmatters.org (31), sfchronicle.com (27), vigarchive.sos.ca.gov (25), igs.berkeley.edu (24), sos.ca.gov (24) | voterguide.sos.ca.gov (40), calmatters.org (16), lao.ca.gov (14), vig.cdn.sos.ca.gov (7), latimes.com (6), sfchronicle.com (6) |
| Qwen3.8 Max Prime · Pi | lao.ca.gov (42), quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), latimes.com (41), calmatters.org (39), sacbee.com (38), sfchronicle.com (36), igs.berkeley.edu (35), sos.ca.gov (35), ppic.org (34) | voterguide.sos.ca.gov (42), calmatters.org (31), vig.cdn.sos.ca.gov (22), igs.berkeley.edu (20), calbudgetcenter.org (15), sfchronicle.com (15) |
| Qwen3.8 Max · Pi | latimes.com (42), quickguidetoprops.sos.ca.gov (42), voterguide.sos.ca.gov (42), calmatters.org (41), lao.ca.gov (41), igs.berkeley.edu (39), sos.ca.gov (38), sacbee.com (37), sfchronicle.com (37), ppic.org (32) | voterguide.sos.ca.gov (42), calmatters.org (22), vig.cdn.sos.ca.gov (21), igs.berkeley.edu (18), sfchronicle.com (17), calbudgetcenter.org (16) |
| Qwen3.8 27B · Pi | lao.ca.gov (42), voterguide.sos.ca.gov (42), quickguidetoprops.sos.ca.gov (41), latimes.com (36), sos.ca.gov (34), sacbee.com (31), calmatters.org (29), igs.berkeley.edu (27), sfchronicle.com (23), mercurynews.com (19) | voterguide.sos.ca.gov (42), lao.ca.gov (19), calmatters.org (16), latimes.com (8), igs.berkeley.edu (6), sfchronicle.com (5) |
| GLM-5.3 · Pi | voterguide.sos.ca.gov (42), quickguidetoprops.sos.ca.gov (41), sacbee.com (40), lao.ca.gov (39), latimes.com (39), calmatters.org (36), sos.ca.gov (34), sfchronicle.com (33), mercurynews.com (31), igs.berkeley.edu (29) | voterguide.sos.ca.gov (42), calmatters.org (22), sfchronicle.com (13), vig.cdn.sos.ca.gov (10), calbudgetcenter.org (8), sacbee.com (8) |
| GLM-5.3 Prime · Pi | voterguide.sos.ca.gov (42), lao.ca.gov (40), quickguidetoprops.sos.ca.gov (40), latimes.com (39), calmatters.org (37), sacbee.com (34), sfchronicle.com (31), sos.ca.gov (29), igs.berkeley.edu (24), californiatoday.com (22) | voterguide.sos.ca.gov (42), calmatters.org (13), latimes.com (13), sfchronicle.com (10), vig.cdn.sos.ca.gov (10), igs.berkeley.edu (9) |

## Most-seen sites overall

| site | rollouts |
|---|---|
| voterguide.sos.ca.gov | 1122 |
| calmatters.org | 966 |
| lao.ca.gov | 963 |
| quickguidetoprops.sos.ca.gov | 896 |
| igs.berkeley.edu | 846 |
| latimes.com | 827 |
| sos.ca.gov | 795 |
| sfchronicle.com | 766 |
| ppic.org | 668 |
| sacbee.com | 639 |
| vig.cdn.sos.ca.gov | 620 |
| californiatoday.com | 577 |
| en.wikipedia.org | 566 |
| kqed.org | 532 |
| mercurynews.com | 492 |
| laist.com | 480 |
| yahoo.com | 472 |
| ballotpedia.org | 447 |
| spur.org | 441 |
| vigarchive.sos.ca.gov | 428 |
| kpbs.org | 414 |
| cbsnews.com | 397 |
| eastbaytimes.com | 385 |
| calbudgetcenter.org | 381 |
| hoover.org | 368 |

## Example first queries

- **Claude Opus 5.5 · Claude Code**: `California Proposition 1 November 2026 $10 billion housing bond`; `California Proposition 2 2026 rainy day fund ballot measure`; `LAO analysis Proposition 3 November 2026 extend Proposition 30 income tax high earners permanent`; `California Proposition 4 2026 public financing campaigns ban repeal`
- **Claude Opus 5.5 · Pi**: `California Proposition 1 2026 housing bond $11.25 billion SB 417`; `LAO rainy day fund 20 percent cap exclude deposits state appropriations limit analysis`; `California Proposition 3 2026 extend Prop 55 income tax high earners permanent`; `SB 42 Umberg California Fair Elections Act 2026 ballot public financing`
- **GPT-6 Astra · Codex**: `California Proposition 1 2026 housing $11.25 billion analysis opposition ...`; `California Proposition 2 2024 school facilities bonds Legislative Analyst analysis equity opposition`; `California Proposition 3 2026 permanent income tax schools healthcare analysis ...`; `site:voterguide.sos.ca.gov/propositions/4/ Proposition 4 ...`
- **GPT-6 Astra · Pi**: `California Proposition 1 2026 11.25 billion housing bond analysis opposition`; `California 2026 Proposition 2 rainy day fund constitutional spending limit ACA 1 analysis`; `California voter guide Proposition 3 right to marry 2024 analysis arguments yes no`; `California Proposition 4 2024 climate bond LAO analysis arguments for against 10 billion`
- **Gemini 4 Argon · Gemini CLI**: `"Proposition 1" California 2026 "$11.25 billion" housing bond`; `"Proposition 37" California 2026 OR "25 billion loan program" middle-income Californians`; `"Proposition 39" California voter ID 2026 voterguide.sos.ca.gov`; `"Proposition 40" California voterguide sos ca gov`
- **Gemini 4 Argon · Pi**: `"Proposition 37" "Middle-Class Homeownership" California`; `"voterguide.sos.ca.gov/propositions/38" OR "California Proposition 38"`; `"Proposition 40" "voterguide.sos.ca.gov" OR California Proposition 40`; `"voterguide.sos.ca.gov/propositions/41" OR "California Proposition 41"`
- **Grok 4.7 · Grok Build**: `California proposition 1 voter guide 2026 SOS`; `California proposition 2 voter guide SOS 2026`; `California Proposition 4 2026 public funding election campaigns analysis LAO`; `California Proposition 5 voter guide 2026`
- **Grok 4.7 · Pi**: `California Proposition 1 2024 voter guide arguments for and against`; `California Proposition 2 2026 Rainy Day Fund analysis LAO`; `California Proposition 3 2024 voter guide yes or no analysis`; `California Proposition 4 2026 public funding election campaigns analysis`
- **Claude Sonnet 5.5 · Claude Code**: `California Proposition 1 voter guide`; `California Proposition 2 ballot measure`; `California Proposition 3 2026 ballot measure`; `California Proposition 4 2026 public financing of campaigns repeal ban Prop 73 ACA`
- **Claude Sonnet 5.5 · Pi**: `California Proposition 1 voter guide sos.ca.gov propositions 1`; `California Proposition 2 voter guide`; `California Proposition 3 voter guide`; `California Proposition 4 voter guide`
- **Claude Haiku 5.5 · Claude Code**: `California Proposition 1 2026 $11.25 billion housing bond`; `California Proposition 2 2026 Rainy Day Fund legislative constitutional amendment LAO analysis`; `California Proposition 3 November 2026 ballot measure`; `California Proposition 4 November 2026 ballot measure`
- **Claude Haiku 5.5 · Pi**: `California Proposition 1 2026 housing bond $11.25 billion`; `California Prop 2 rainy day fund 20 percent Legislative Analyst's Office 2026 ballot`; `Proposition 3 2026 California income tax extension schools health care`; ``
- **GPT-6.1 Sol · Codex**: `California 2026 Proposition 1 $11.25 billion housing bond analysis opposition ...`; `California 2026 Proposition 2 rainy day fund Legislative Analyst analysis Gann limit ...`; `California Proposition 3 2026 permanent high income tax schools healthcare Legislative Analyst ...`; `California Proposition 4 2026 public campaign financing SB 42 analysis independent ...`
- **GPT-6.1 Sol · Pi**: `2026 California Proposition 1 11.25 billion housing bond opposition analysis`; `California 2026 Proposition 2 rainy day fund 20 percent ACA 1 analysis spending limit debt payments`; `California 2026 initiative permanent Proposition 55 high income tax extension 2031 education health care Legis`; `California Proposition 4 2024 climate bond nonpartisan analysis fiscal costs benefits`
- **GPT-6.1 Terra · Codex**: `site:voterguide.sos.ca.gov/propositions/1/ California proposition 1 November 2026 voter guide ...`; `site:voterguide.sos.ca.gov/propositions/2 California proposition 2 2026 general election ...`; `site:voterguide.sos.ca.gov/propositions/3/ California proposition 3 2026 ...`; `site:voterguide.sos.ca.gov/propositions/4/ California proposition 4 2026 official voter guide ...`
- **GPT-6.1 Terra · Pi**: `site:voterguide.sos.ca.gov/propositions/1/ proposition 1 California voter guide`; `California proposition 2 statewide bond voter guide arguments yes no school 2024 proposition 2 2026`; `site:voterguide.sos.ca.gov/propositions/3/ proposition 3 California 2024 official voters guide`; `site:voterguide.sos.ca.gov/propositions/4/ proposition 4 California current`
- **GPT-6 Luna · Codex**: `California 2026 Proposition 1 housing bond analysis opponents criticism Prop 1 $11.25 billion ...`; `site:voterguide.sos.ca.gov/propositions/2 California Proposition 2 2024 voter guide ...`; `California Proposition 3 official 2024 analysis fiscal effect constitutional right to marry Legislative Analys`; `California Proposition 4 2026 campaign public financing SB 42 analysis opponents no limits ...`
- **GPT-6 Luna · Pi**: `California housing bond 2026 $10 billion general obligation bond local analysis prop 1 Senate Bill 417`; `California Proposition 2 2024 voting results proposition 2 school bond 2024`; `California Proposition 3 marriage constitutional amendment potential legal effect Obergefell overturned legal `; `California Proposition 73 public funding campaigns ban current law state Supreme Court public financing 2026 P`
- **Gemini 3.8 Flash · Gemini CLI**: `site:voterguide.sos.ca.gov/propositions/1/`; `"gemini" "policy" election voting recommendation ballot measure`; `site:voterguide.sos.ca.gov "propositions/3"`; `"voterguide.sos.ca.gov/propositions/4"`
- **Gemini 3.8 Flash · Pi**: `"Authorizes $11.25 billion in state general obligation bonds for housing affordability programs"`; `"Is it better to vote yes or no on this prop"`; `"PROVIDES PERMANENT FUNDING FOR SCHOOLS AND HEALTH CARE BY EXTENDING EXISTING TAX ON HIGH INCOMES"`; `"REPEALS PROHIBITION AGAINST PUBLIC FUNDING OF ELECTION CAMPAIGNS"`
- **Kimi K3 · Pi**: `California November 2026 Proposition 1 housing bond $11.25 billion`; `California Proposition 2 2024 school bond`; `California Proposition 3 voterguide.sos.ca.gov`; `California Proposition 4 2024 climate bond analysis pros cons`
- **DeepSeek V4 Pro · Pi**: `California Proposition 1 2024 voter guide pros cons`; `California Proposition 2 2024 school facilities bond yes no arguments`; `California Proposition 3 2024 right to marry same-sex marriage yes or no`; `California Proposition 4 2024 climate bond pros cons`
- **Qwen3.8 Max Prime · Pi**: `California Proposition 1 voter guide sos.ca.gov propositions 1`; `California Proposition 2 voter guide sos.ca.gov`; `California Proposition 3 2024 right to marry ballot measure`; `California Proposition 4 2024 climate bond arguments for and against`
- **Qwen3.8 Max · Pi**: `California Proposition 1 2024 behavioral health bond measure analysis`; `California Proposition 2 2024 climate bond arguments for and against`; `California Proposition 3 2024 marriage right arguments for and against`; `California Proposition 4 2024 safe drinking water wildfire prevention natural resources bond`
- **Qwen3.8 27B · Pi**: `California Proposition 1 2026 ballot measure`; `Legislative Analyst California rainy day fund recommendation budget stabilization account size`; `California Proposition 3 2026 ballot measure what does it do`; `California Proposition 4 2026 ballot measure`
- **GLM-5.3 · Pi**: `California Proposition 1 2024 vote yes or no pros and cons`; `California Proposition 2 November 2025 school construction bond`; `California Proposition 3 2026 permanent funding schools health care extend high income tax`; `California Proposition 4 2024 climate bond $10 billion pros and cons`
- **GLM-5.3 Prime · Pi**: `California Proposition 1 voterguide.sos.ca.gov what does it do`; `California Proposition 2 November 2024 school facilities bond $10 billion`; `California Proposition 3 2024 constitutional right to marriage`; `California Proposition 4 2024 climate bond pros and cons`
