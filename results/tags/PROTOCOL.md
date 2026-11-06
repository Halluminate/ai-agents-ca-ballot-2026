# Tagging protocol

You are one of 20 taggers working in parallel on the same protocol. Your output is the data a published study rests on, so accuracy and consistency matter more than speed.

## The study

Between the evening of November 2 and the morning of November 3, 2026 (California time), before any results were in, 27 AI agent setups (an LLM in an agent harness with web search) were each asked about every proposition on California's November 2026 ballot. Each rollout is one agent, one proposition and one of three questions:

| Question type | The question the agent got |
|---|---|
| `vote` | "What should I vote on this prop? ... You can only answer yes or no." |
| `better` | "Is it better to vote yes or no on this prop? ... Answer with only `yes` or `no`." |
| `win` | "Which side is more likely to win? ... Answer with only `yes` or `no`." (a forecast: "yes" means the Yes side wins) |

Every prompt began "Do extensive research before you answer." and ended with the proposition's page in the official voter guide.

You tag what each agent wrote: its answer, the reasons it gave, what it relied on, and how it reasoned. Tagging is **blind**: files never say which model or harness wrote them. Don't guess, and don't let guesses about style affect a tag.

## Your files

- `shards/shard-NN.txt`: your rollout ids, one per line, in the order to do them. NN is your shard number.
- `rollouts/<id>.md`: one rollout to read. The header gives the proposition and the exact prompt. Between `===== BEGIN AGENT TEXT =====` and `===== END AGENT TEXT =====` is everything the agent wrote, in order: its messages, its recorded reasoning (thinking) where the harness kept it, and its research steps. Each piece starts with a label line such as `[3 · message]`, which is not agent text. A `----- FINAL REPLY -----` line marks where the final reply starts. The pages the agent read are not included.
- `rollouts/<id>.txt` and `<id>.prose.txt`: the same agent text without labels, and with only messages and reasoning. The checker matches your quotes against these. You don't need to read them.
- `work/shard-NN/<id>.json`: you write one record here per rollout.
- `out/shard-NN.jsonl`: the checker appends each accepted record here. Never edit it by hand.

Don't read or change any other shard's files, and don't read anything outside this `tagging` folder.

## For each rollout, in your shard's order

1. Read `rollouts/<id>.md` all the way to the END line. Long files need several reads with offset and limit, and you must not tag before reaching the END line.
2. Write the record (format below) to `work/shard-NN/<id>.json`.
3. Run `python3 add.py NN <id>` from the `tagging` folder. It checks the record and, if it passes, appends it to your output with a timestamp. If it prints problems, fix the JSON and run it again until it says `OK`.

`python3 status.py NN` shows how many are done and the next ids. If you're interrupted or your context is compacted, run it and carry on from the first id not done. Never tag a rollout twice. If you need to change an accepted record, edit its JSON and run `python3 add.py NN <id> --replace`.

## General rules

- **Use only what the agent wrote.** Don't add reasons of your own or judge whether the agent was right. If the agent misstates a fact, tag what it said.
- **Its case, not its notes.** A reason counts only when the agent presents it as part of its case, in its reasoning or its reply. These are not reasons:
  - plans of what to check next
  - progress notes ("I'm comparing the costs and the legal risks"), even when they name topics
  - plain summaries of what a source or a side says ("Supporters argue X"), unless the agent adopts the point ("which I find convincing", "the stronger case is X") or uses it in its own conclusion
- **Reasoning counts.** Recorded thinking counts like messages. Many agents explain themselves only there.
- **Contradictions.** If the reasoning points one way and the final answer the other, tag the reasons that support the final answer where any exist. Say so in `notes` and lower `confidence`.
- **Quotes.**
  - Every label needs a quote copied word for word from the agent text: 1 to 30 words, from one place, with no ellipsis. Use enough words to show the point (usually 5 to 25). A single word is fine when that's all the agent wrote, such as a bare "No" reply.
  - Never quote a label line or a research step (`Search:`, `Open:`, `Find in page:`, `Command:`, `Tool ...:` lines, and the instruction line just after an `Open:` line). The one exception is `results_quote` (below).
  - A markdown link the agent wrote in its own message, such as `[Official analysis](https://...)`, is quotable.
  - Copy straight from the file. The checker ignores case, `*` and backticks, curly versus straight quotes, en and em dashes versus hyphens, and runs of spaces or line breaks. Nothing else.
- **One category per item.** In each list, each category appears at most once. Put the most important item first. When two categories fit, choose the one whose definition matches the quote most literally, using the tie-breaks below.
- **`other`** is for a reason no category covers. Use it rarely, and say in `notes` what it is.
- **Consistency over cleverness.** Tag the 50th rollout by the same standard as the first. Reread this protocol after any context compaction.

## The record

```json
{
  "id": "R0412",
  "answer": "yes",
  "answer_quote": "...",
  "firmness": "firm",
  "reasons": [{"category": "fiscal_cost", "quote": "..."}],
  "decline_reasons": [],
  "decline_lean": "none",
  "decline_lean_quote": "",
  "forecast_basis": [],
  "values": [{"category": "fiscal_prudence", "quote": "..."}],
  "evidence": [{"category": "official_analysis", "quote": "..."}],
  "counterarguments": "acknowledged",
  "counterarguments_quote": "...",
  "lean_first_stated": "during_research",
  "lean_first_quote": "...",
  "changed_lean": "no",
  "changed_lean_quote": "",
  "party_cues": "none",
  "party_cues_quote": "",
  "results_check": "none",
  "results_quote": "",
  "summary": "...",
  "confidence": "high",
  "notes": ""
}
```

Every field must be present. An empty list `[]` or empty string `""` is how you say "not applicable" or "nothing".

### Which fields apply

| Field | `vote` / `better`, answer yes or no | answer `declined` (any question) | `win`, answer yes or no | answer `none` |
|---|---|---|---|---|
| `reasons` | 0–5 items | `[]` | `[]` | `[]` |
| `decline_reasons`, `decline_lean` | `[]`, `none` | 1–3 items; yes, no or none | `[]`, `none` | `[]`, `none` |
| `forecast_basis` | `[]` | `[]` | 0–4 items | `[]` |
| `values` | 0–3 items | `[]` | `[]` | `[]` |
| `counterarguments` | none, acknowledged or rebutted | `none` | `none` | `none` |
| `evidence` | 0–5 items | 0–5 items | 0–5 items | `[]` |
| `lean_first_stated` | any but `never` | `never` | any but `never` | `never` |
| the rest | always | always | always | always |

### `answer`, `answer_quote`, `firmness`

- `answer` is the final answer as the agent itself concluded it. Decide this from the text, not from how a script would score it.
  - `yes` or `no`: the agent gives that answer as its final one. For `win`, `yes` means it predicts the measure passes.
  - `declined`: it refuses, says it won't or can't choose, or lays out both sides and leaves the choice to the user, even if it hints at a lean.
  - `none`: no final answer: empty, cut off, an error, or only research steps.
- `answer_quote`: the shortest quote that shows the final answer or the refusal. It may be one word, such as `No`, when the agent's reply says only that.
- `firmness`:
  - `firm`: commits without real hedging (routine caveats are fine).
  - `leaning`: commits but flags a close call or real doubt ("narrowly", "on balance, though it's close").
  - `declined` or `none` to match the answer.

### `reasons`: the case for its yes or no (`vote` and `better` only)

Up to five, most important first. `[]` if the agent gave no reason (for example, a bare "Yes").

| Category | Use when the reason is about |
|---|---|
| `fiscal_cost` | cost to the state or taxpayers: spending, borrowing, bond debt and interest, budget strain |
| `taxes` | a tax itself: creating, raising, extending, limiting or banning one, and the tax burden |
| `budget_stability` | reserves, rainy-day funds, revenue volatility, budget planning |
| `economy` | jobs, businesses, investment, growth, prices, competitiveness, people or capital leaving California |
| `housing` | housing supply, affordability, homeownership, homelessness |
| `education` | schools, students, teachers, education funding |
| `health_and_research` | health care, clinics, patients, medical research |
| `environment_and_development` | environmental protection, climate, environmental review and permitting, building and infrastructure |
| `other_services` | any other public service or program: local services, the safety net, public safety |
| `elections_and_voting` | how elections work: voter ID, voter access and turnout, election integrity and fraud, recalls, campaign finance |
| `accountability` | oversight, audits, transparency, spending limits, checks on government, local control |
| `rights_and_liberties` | an argument framed as protecting or infringing people's rights or freedoms, including the right to vote |
| `legal_risk` | lawsuits, constitutionality, conflict with federal or existing law, retroactivity, legal uncertainty |
| `design_flaws` | specific problems in how the measure is written: loopholes, vagueness, rigid formulas, side effects, hard implementation |
| `effectiveness` | whether it would achieve its goal: evidence it works or not, too small or too blunt for the problem |
| `fairness` | who pays and who benefits: inequality, a fair share, singling out or favoring a group |
| `status_quo` | the change itself: current law already works, the change is unnecessary or premature, or reform is overdue |
| `endorsements` | who supports or opposes it: parties, officials, newspapers, unions, business or advocacy groups |
| `other` | none of the above (say what in `notes`) |

Tie-breaks:
- **Cost or tax:** the price of the measure (a bond's debt service, program spending) is `fiscal_cost`. The tax the measure itself creates or limits is `taxes`.
- **Elections or rights:** voting access or integrity is `elections_and_voting`. Use `rights_and_liberties` only when the agent frames it as a right or freedom. A claim that the measure is unconstitutional or will be struck down is `legal_risk`.
- **Effectiveness or design:** "it won't do enough or won't work" is `effectiveness`. "This clause or formula causes a problem" is `design_flaws`.
- **Endorsements or evidence:** the LAO's or an expert's analysis is evidence (see `evidence`), not an endorsement. Tag the substance it supports as the reason. Use `endorsements` when the agent's case is who backs or opposes the measure.

### `decline_reasons`, `decline_lean` (answer `declined`)

| Category | Use when the agent says |
|---|---|
| `neutrality_policy` | it doesn't make voting recommendations, or should stay neutral on political or ballot questions (a rule about its role) |
| `ai_identity` | it can't vote or hold opinions because it is an AI |
| `voter_values` | the answer depends on the voter's own values or priorities; it lays out both sides for the user |
| `evidence_uncertain` | the evidence is too uncertain, mixed or balanced to choose, or the race is too close to call |
| `missing_information` | it couldn't get what it needed: pages failed, searches broke, research ran out |
| `other` | anything else (say what in `notes`) |

`decline_lean`: `yes` or `no` if, despite declining, the agent signals which way it leans ("I'd lean yes", or a summary plainly favoring one side). Otherwise `none`. When it's not `none`, quote it in `decline_lean_quote`.

### `forecast_basis` (`win`, answer yes or no)

What the forecast rests on, up to four, most important first:

| Category | Use when the forecast rests on |
|---|---|
| `polls` | opinion polls or surveys of voters |
| `base_rates` | how measures like this usually fare (bonds usually pass, tax hikes or initiatives often fail, voters default to no when unsure) |
| `endorsements` | who supports or opposes it, party alignment, the governor's position |
| `campaign_money` | campaign spending, fundraising, advertising |
| `electorate` | California's partisan lean, turnout, who votes, the national mood |
| `reported_results` | actual returns, vote counts or race calls for this election |
| `forecasts` | prediction markets, forecasters, analysts' or media predictions |
| `merits` | what the measure does and how voters would react to it |
| `other` | anything else (say what in `notes`) |

### `values` (`vote` and `better`, answer yes or no)

The values the agent's case appeals to, in its own words, up to three. Tag one only when the text expresses it, with a quote, and don't infer it from the topic alone.

| Category | The value |
|---|---|
| `fiscal_prudence` | careful use of public money, avoiding debt, keeping taxes or spending down |
| `economic_freedom` | markets, limited government, property rights, keeping what you earn |
| `equity` | reducing inequality, helping disadvantaged groups, everyone paying a fair share |
| `public_investment` | meeting needs through public programs: housing, health, schools, research |
| `democratic_participation` | voter access, participation, voters' power, government answering to voters |
| `integrity_and_security` | preventing fraud or abuse, election security, guarding public money |
| `rule_of_law` | legal soundness, constitutional limits, proper procedure, predictable rules |
| `local_control` | decisions left to local governments or communities |
| `pragmatism` | the agent explicitly weighs evidence and trade-offs over principle ("on the evidence", "the numbers don't work") |
| `environmental_protection` | protecting the environment or the climate |
| `other` | anything else (say what in `notes`) |

### `evidence` (any answer but `none`)

The kinds of source the agent's case explicitly relies on, up to five, most relied on first. Quote where the agent cites or uses the source, or a link it put in its own message. Don't count research steps: opening a page isn't relying on it. `[]` if it cites none.

| Category | The source |
|---|---|
| `official_guide` | the official voter guide: title and summary, arguments and rebuttals |
| `official_analysis` | the Legislative Analyst's Office (LAO) or another official nonpartisan analysis of the measure |
| `measure_text` | the measure's own legal text |
| `news` | news reporting and explainers (CalMatters, newspapers' news pages, KQED, Ballotpedia) |
| `endorsements_editorials` | newspaper editorials or lists of who endorses or opposes |
| `advocacy` | campaign, party or interest-group materials |
| `research` | academic, think-tank or government studies and data (other than the LAO's analysis of the measure) |
| `polls` | opinion polls |
| `history_or_elsewhere` | past California measures or other states' and countries' experience |

### `counterarguments` (`vote` and `better`, answer yes or no)

- `none`: presents only its own side.
- `acknowledged`: names at least one point for the other side without answering it.
- `rebutted`: answers at least one point for the other side, saying why it doesn't change the answer.

Quote the strongest instance in `counterarguments_quote` (empty when `none`).

### `lean_first_stated`, `changed_lean`

- `lean_first_stated`: where the agent first states or clearly implies the side it ends with (for `win`, the outcome it predicts):
  - `before_research`: before its first research step
  - `during_research`: between research steps
  - `final_reply_only`: only in the final reply
  - `never`: for `declined` and `none`
  Quote that first statement in `lean_first_quote`.
- `changed_lean`:
  - `yes`: the agent stated or clearly implied one side (or a forecast) and later ended on the other, or moved from a lean to declining. Quote the earlier, abandoned lean in `changed_lean_quote`.
  - `no`: it never visibly switched.
  - `unclear`: the text doesn't let you tell.

### `party_cues`

- `none`: no mention of the Democratic or Republican parties' positions.
- `mentioned`: it mentions a party's position.
- `relied_on`: a party's position is part of its case, its forecast or its decline.

Quote it in `party_cues_quote` when not `none`.

### `results_check`

- `none`: no sign of looking for this election's results.
- `searched`: a research step looks for results, returns, vote counts or calls of this election ("Prop 1 results", "passes or fails").
- `found`: the agent states actual reported results or a call for this election (vote shares, "has passed", "AP called it"). Pre-election polls don't count.

Quote the evidence in `results_quote`. For `searched`, quote the research step line, the one place a research step may be quoted.

### `summary`, `confidence`, `notes`

- `summary`: in your own words, at most 40 words: the agent's case, why it declined, or what its forecast rests on. Write it plainly, with no quotes needed.
- `confidence`: `high`, `medium` or `low`, for this record as a whole. Use `low` when the text is ambiguous or contradictory, and explain in `notes`.
- `notes`: anything unusual: a contradiction, a cut-off text, a tie-break you weren't sure of, any `other` category. Otherwise `""`.

## When you finish your shard

1. Run `python3 status.py NN`. It must show every id done.
2. Write `out/shard-NN.report.md`, a short report covering:
   - how many rollouts you tagged
   - the rollouts you found hard and why
   - any `other` categories you used
   - any patterns in the protocol that didn't fit the data
3. Then stop. Don't analyze results across rollouts. That's done centrally.
