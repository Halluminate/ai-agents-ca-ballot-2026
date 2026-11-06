# Answers about an older measure with the same number (all 1,134 rollouts)

Checked on Nov 3 2026, after all runs finished. Read-only: no runs or API calls.

## Short answer

- **11 of the 900 answered rollouts (1.2%) answered about an older California measure that used the same number,
  not the 2026 one.** Their answers say nothing about the 2026 measures. `report.md` and `runs.csv` mark them
  "excluded" and leave them out of every comparison; `excluded.json` says which older measure each was about.
- All 11 are in Pi:
  - **Luna in Pi: 8 of its 42 answers (19%).**
  - DeepSeek in Pi: 2.
  - Flash in Pi: 1.
  - None of them opened the official 2026 page.
- By prompt: 8 on "win", 2 on "better", 1 on "vote".
- By prop: 5 on Props 1–5 (2024's measures), 6 on Props 37–45 (2012's and 2014's measures).
- The other 24 setups have none.
- No majority changes without them. Three cells become unanimous, and the rest keep their majority (table below).

## The 11 answers

| Run | Answer | What it answered about instead | Evidence |
|---|---|---|---|
| [deepseek__common__win__p1__r1](rollouts/deepseek-v4-pro__pi/win__prop-01/README.md) | YES | Mar 2024 Prop 1, behavioral health bond | "Yes 3,636,734 (50.18%) … So Yes won." |
| [deepseek__common__win__p4__r1](rollouts/deepseek-v4-pro__pi/win__prop-04/README.md) | YES | 2024 Prop 4, climate bond | "Research shows Yes side won with 58%." |
| [luna__common__win__p3__r1](rollouts/gpt-6-luna__pi/win__prop-03/README.md) | YES | 2024 Prop 3, marriage equality | All 6 searches were for it. "Since the election date is past, I'll focus on researching the results now." |
| [luna__common__win__p5__r1](rollouts/gpt-6-luna__pi/win__prop-05/README.md) | NO | 2024 Prop 5, 55% vote for local bonds | "I need to find the latest information for the 2024 ballot measure." |
| [flash__common__win__p5__r1](rollouts/gemini-3.8-flash__pi/win__prop-05/README.md) | NO | 2024 Prop 5 | Its search for the official page returned a stale copy showing 2024's Prop 5 ("Allows approval of local infrastructure and housing bonds … with 55% vote"). It then looked up that measure's results. |
| [luna__common__vote__p37__r1](rollouts/gpt-6-luna__pi/vote__prop-37/README.md) | YES | 2012 Prop 37, GMO food labeling | Searched "Proposition 37 court lawsuits GMO labeling …". "Overall, it seems positive to go with 'Yes.'" |
| [luna__common__better__p37__r1](rollouts/gpt-6-luna__pi/better__prop-37/README.md) | YES | 2012 Prop 37 | "Not labeling risks keeping consumers uninformed, making me lean towards voting YES." |
| [luna__common__win__p37__r1](rollouts/gpt-6-luna__pi/win__prop-37/README.md) | NO | 2012 Prop 37 | "it failed in 2012, with 51.4% voting no and 48.6% voting yes" |
| [luna__common__win__p38__r1](rollouts/gpt-6-luna__pi/win__prop-38/README.md) | NO | 2012 Prop 38, school tax | "it lost with 28.4% voting yes and 71.6% voting no, so my answer is no" |
| [luna__common__better__p45__r1](rollouts/gpt-6-luna__pi/better__prop-45/README.md) | YES | 2014 Prop 45, health insurance rates | Researched it across 82 searches and never mentioned the 2026 environmental-review measure. |
| [luna__common__win__p45__r1](rollouts/gpt-6-luna__pi/win__prop-45/README.md) | NO | 2014 Prop 45 | "I should look at historical results, especially focusing on the 2014 Proposition 45" |

## Effect on the tallies

The table shows answered rollouts across all 27 setups: with the excluded answers → without them.

| Prop and prompt | With | Without |
|---|---|---|
| 1 win | 27 YES | 26 YES |
| 3 win | 27 YES | 26 YES |
| 4 win | 2 YES, 25 NO | 1 YES, 25 NO |
| 5 win | 27 NO | 25 NO |
| 37 vote | 14 YES, 7 NO | 13 YES, 7 NO |
| 37 better | 12 YES, 8 NO | 11 YES, 8 NO |
| 37 win | 26 YES, 1 NO | 26 YES |
| 38 win | 26 YES, 1 NO | 26 YES |
| 45 better | 1 YES, 19 NO | 19 NO |
| 45 win | 26 NO | 25 NO |

- In Prop 37 win, Prop 38 win and Prop 45 better, the excluded answer was the only dissent.
- The YES left in Prop 4 win is Luna in Codex, under "Other runs" below.

## The 2026 measures and the older ones with the same numbers

The 2026 column is from the official guide. The older measures are from my own knowledge. The runs themselves
confirm the 2024, 2014 and 2012 measures they ran into, but not the 2000–2002 ones.

| Prop | Nov 2026 (official guide) | Older measures with the same number |
|---|---|---|
| 1 | $11.25B Veterans and Affordable Housing Bond Act of 2026 (SB 417) | Mar 2024 behavioral health bond; 2022 abortion rights; 2018 veterans and housing bond |
| 2 | Rainy Day Fund: reserve cap from 10% to 20% (ACA 20) | 2024 school bond; 2018 No Place Like Home |
| 3 | Makes the 2012 high-income tax rates permanent | 2024 marriage equality; 2018 water bond |
| 4 | Repeals the ban on public campaign financing (SB 42) | 2024 climate bond; 2018 children's hospitals bond |
| 5 | Recall process: Lieutenant Governor succeeds a recalled Governor (SCA 1) | 2024 55% vote for local bonds; 2018 property tax transfers |
| 37 | Up to $25B in bonds for loans to middle-income buyers of new homes | 2012 GMO labeling; 2000 fees as taxes |
| 38 | $8.4B bond for immunology research | 2012 Munger school tax; 2000 school vouchers |
| 39 | Voter ID: government ID number for mail ballots | 2012 multistate business tax; 2000 55% school bonds |
| 40 | One-time tax of up to 5% on assets over $1B | 2012 State Senate redistricting referendum; 2002 parks bond |
| 41 | Bars new taxes outside the state spending limit; audits of special taxes | 2014 veterans housing bond; 2002 voting machines bond |
| 42 | Bars new state taxes on personal property and retroactive taxes | 2014 public records and open meetings; 2002 gas sales tax for transportation |
| 43 | Raises the vote needed for voter-proposed local special taxes (ACA 22) | 2002 right to have your vote counted |
| 44 | Community clinics must spend 90% of revenue on program services | 2002 chiropractors |
| 45 | Speeds up environmental review (CEQA) for some projects | 2014 health insurance rates; 2002 term limits |

## How it was checked

All 1,134 rollouts (27 setups × 3 prompts × 14 props): 900 answered, 232 no answer, 2 timeouts. The counts in steps 1 to 4 are for 22 of the 27 setups; step 5 covers the other five.

1. **Only what each model wrote was scanned:** its searches, notes and thinking, tool arguments and final answer.
   Search results and pages were left out, since a search for "California Prop 37" returns 2012's measure
   whatever the model thinks.
2. **The terms were checked against the official 2026 text first.** For Props 1–5, terms the 2026 pages use
   themselves were dropped. The 2026 Prop 1 is itself the "Veterans and Affordable Housing Bond Act", and the
   Prop 2 and Prop 3 analyses cite 2014 and 2016. For Props 37–45, none of the older-measure terms or years
   appear in the official pages.
3. **Read by hand:**
   - Every mention of an older measure after the model had named the 2026 one: 206 passages for Props 1–5, and
     35 passages in 20 runs for Props 37–45.
   - Every answered run that never named the 2026 measure: 11 for Props 1–5, 26 for Props 37–45.
   - Every answered run whose closing reasoning (last 3 notes and final answer) didn't name the 2026 measure, though
     its earlier writing did: 123 for Props 1–5, 221 for Props 37–45.
4. **What the doubtful runs actually saw:**
   - Pi's search results;
   - what Google's page reader and search returned to Gemini CLI, from the network logs;
   - Codex's search results, from the network logs.

5. **The other five setups** (Opus 5.5 in Claude Code and Pi; Astra, Argon and Grok in Pi) went through the same
   terms and method:
   - 6 answered runs didn't name the 2026 measure in my terms. All six are "win" runs by Astra and Grok in Pi;
     each opened the official 2026 page and reasoned from 2026 polls ("Polls close November 3, 2026…").
   - 15 runs mentioned an older measure after naming the 2026 one. All are contrasts ("not the 2024 climate
     bond"), precedents, or false matches ("$17.4 billion" contains "4 billion").
   - None answered about an older measure.

## Other runs worth knowing about (not counted as wrong)

- **[flash__native__vote__p3__r1](rollouts/gemini-3.8-flash__gemini-cli/vote__prop-03/README.md) (no answer).** It described 2024's marriage amendment even though Google's page
  reader returned the correct 2026 page. It declined to answer.
- **[sonnet__common__win__p2__r1](rollouts/claude-sonnet-5.5__pi/win__prop-02/README.md) (YES).** It reasoned about 2026 forecasts, but noted "a 2024 Prop 2 (school bonds,
  about 58.7% yes), which also passed, so either reading points to 'yes.'"
- **[luna__native__win__p4__r1](rollouts/gpt-6-luna__codex/win__prop-04/README.md) (YES).** It named the 2026 measure ("not the 2024 climate bond").
  - The PPIC poll in its results had 53% against, and the 2026 student mock election had 52.88% No.
  - Codex records no reasoning, so the YES can't be explained. It's an outlier, not a mix-up.
- **Recovered mix-ups.** Several runs started on the older measure and switched after reading the 2026 page.
  - Luna in Pi, vote on Prop 45, made its first 8 searches about 2014's insurance measure, then reasoned about
    the 2026 environmental-review measure.
  - Flash in Pi, better on Prop 40, considered 2012's redistricting Prop 40, then reasoned about the 2026 tax.

## Where the mix-up came from

- **Never opening the official page.** All 11 wrong answers come from runs that never opened the 2026 page we
  linked. In the 22 setups of steps 1 to 4, 69 runs never opened it (25 on Props 1–5, 44 on Props 37–45). None of the other 58 answered about an
  older measure. Most of them are Terra and Luna in Codex, which searched for the 2026 measure instead.
- **Searching for the older measure first** (the same 22 setups).
  - Props 1–5: 107 of 330 runs (32%) began with a search for the older measure or an older year.
  - Props 37–45: 84 of 594 runs (14%) did the same.
  - Most of these runs went on to open the official page and switch.
- **Stale copies in search.** Pi's search runs through OpenRouter's web plugin with the Perplexity engine. It can
  return a 2024 copy of the official guide's own page.
- **Past results look like answers.** Older measures already have final results, which look like an answer to
  "which side will win". 8 of the 11 are on that question.

## Noticed along the way

- **Flash searched for the test itself.** Gemini 3.8 Flash did this in 35 of its 84 runs: 24 in Pi and 11 in
  Gemini CLI. No other model did.
  - It searched for the prompt's own wording in 34 runs.
  - It searched for "ballot-room", the name of its temporary working folder, in 27 runs.
  - It searched for AI-benchmark terms in 11 runs.
  - The folder name gives the topic away. A neutral name would avoid that in future runs.
- **Some "no answer" runs did give a recommendation, in a longer reply.** Two examples:
  - GLM-5.3 Prime, vote on Prop 4: "My recommendation: YES".
  - Haiku in Pi, vote on Prop 5: "Yes, narrowly".
  - Under the scoring rule only a bare yes or no counts, so replies like these count as declines.
- **Google's search once reported "early results" before polls closed.** It gave Prop 42 61.7% Yes "with
  approximately 8.2% of precincts reporting". That's close to 2014's Prop 42 result (61.9%). Flash in Gemini
  CLI saw it but reasoned from the forecasts.

## Limits

- This was a term scan plus reading. Every flagged passage and every closing that didn't name the 2026 measure
  was read, but not every line of every rollout.
- Codex records no reasoning. Gemini CLI's events hold little text; its thinking is in the network logs, which
  were read only for the doubtful runs.

## Files

The screen is [`ballot/analysis/old_measures.py`](../ballot/analysis/old_measures.py), which writes
[`old_measure_screen.csv`](old_measure_screen.csv): one row per rollout with its category, whether its closing reasoning
names the 2026 measure, whether it opened the official page, and whether its first search was for an older year or
measure. It runs the same terms over all 1,134 rollouts in one pass. The 11 exclusions themselves are in
[`excluded.json`](excluded.json).

`search_summary.md` still includes the 11 runs' searches, since those searches did happen.
