# Tags

Claude Opus 5.5 tagged every one of the 1,134 rollouts under one written protocol, [PROTOCOL.md](PROTOCOL.md):

- **The answer:** the final answer as the agent concluded it, and how firmly.
- **The case:** the reasons for a yes or no, the values it appeals to, the sources it relies on, and whether it answers
  the other side.
- **Declines and forecasts:** why a decline declined, and what a forecast rests on.
- **How it got there:** when it first stated its side and whether it switched, whether it cited party positions, and
  whether it looked for election results.

Every label comes with a quote found word for word in the agent's own text.

| File | What it is |
|---|---|
| [PROTOCOL.md](PROTOCOL.md) | The protocol every tagger followed: the fields, every category with its definition, the tie-breaks and the quote rules |
| [key.csv](key.csv) | Each blind id (R0001 to R1134) and its rollout: `run_id`, model, harness, question, proposition, scored outcome, and the shards that tagged it |
| [shards/](shards/) | The rollouts each of the 20 taggers tagged, in the order it tagged them |
| [records/](records/) | Every record each tagger logged, one JSON line per rollout, with the time it was logged |
| [tags.jsonl](tags.jsonl) | One record per rollout, from its first tagging, with its `run_id`, model, harness, question, proposition and scored outcome |
| [tags_second.jsonl](tags_second.jsonl) | The second tagging of 117 rollouts, done blind by a different tagger, to measure agreement |

## How the tagging ran

- **Taggers.** 20 Claude Code sessions, each running Claude Opus 5.5 (`claude-opus-5-5`) at maximum effort with a fresh
  context and the same brief, one per shard. Each shard holds about 60 rollouts, balanced by length and mixed across
  questions, harnesses and answers.
- **Blind.** Each rollout was shown under its blind id, with the proposition, the exact prompt and the agent's own text:
  its messages, its recorded reasoning and its research steps, in order. The pages it read were not shown, and no model
  or harness was named.
- **Checked.** Each tagger wrote one record per rollout and logged it through `add.py`, which accepts a record only if it
  follows every rule in the protocol: the fields that apply to the rollout's question and answer, the categories, and
  quotes found word for word in the agent's text, research steps excluded.
- **Agreement.** 117 rollouts, a tenth of each question and scored outcome, were given to a second shard as well,
  without either tagger knowing. Their second tagging is `tags_second.jsonl`.

## Rebuild and check

```bash
python3 -m ballot tags kit tagging
```

writes the kit the taggers worked in, byte for byte: every rollout as they read it (`rollouts/R0001.md` and so on), the
shards, the protocol, `add.py` and `status.py`.

```bash
python3 -m ballot tags check
```

checks every record in `records/` against its rollout, as `add.py` did, and `python3 -m ballot tags merge` rebuilds
`tags.jsonl` and `tags_second.jsonl` from the records.
