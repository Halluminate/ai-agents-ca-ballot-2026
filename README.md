# How AI agents vote

17 LLMs, in their developers' own agent harnesses and in one shared harness, researched the web and answered three
questions about each of the 14 propositions on California's November 3, 2026 ballot: how to vote, whether it is better
to vote yes or no, and which side will win. That is 1,134 rollouts, each recorded in full, run on the evening before
and the morning of election day, before any results were reported.

**[Every trajectory](results/rollouts/)** · [Every answer](results/README.md) · [The tags](results/tags/) ·
[The blog post](https://www.halluminate.ai/blog/how-ai-agents-vote) ·
[Full logs](https://github.com/Halluminate/ai-agents-ca-ballot-2026/releases/tag/logs-v1) · [Methodology](docs/methodology.md)

## Browse the trajectories

[results/rollouts/](results/rollouts/) has every trajectory: one folder per setup, and in it one folder per rollout,
`<question>__prop-<NN>/`. Its page lists the 27 setups, each linked to its folder. [results/README.md](results/README.md)
has every answer in three grids, one per question: rows are the 27 setups, columns the 14 propositions, and each cell
opens that rollout's trajectory.

Each rollout's folder holds three files:

- `trajectory.jsonl`: the harness's own log, exactly as it was saved, one JSON event per line: the prompt, every search
  and page the model opened and what came back, its reasoning where the harness records it, and its final reply.
- `result.json`: the scored answer, with the rollout's searches, pages read, time and cost.
- `search_results.json`: every result its searches returned.

Everything else the run saved, such as `prompt.txt` and `final.txt` (the final reply), is in the folder's `other/`
subfolder. For example: [Kimi K3 in Pi, asked how to vote on Prop 1](results/rollouts/kimi-k3__pi/vote__prop-01/trajectory.jsonl).
GitHub shows files of up to a few megabytes on the page; for larger ones, its Raw button opens the whole file.

## What's in the repository

| Path | What it is |
|---|---|
| [results/README.md](results/README.md) | Every answer, each linked to its trajectory |
| [results/rollouts/](results/rollouts/) | One folder per rollout, under its setup's folder: its trajectory, result and search results, with everything else the run saved in `other/` |
| [results/tags/](results/tags/) | Claude Opus 5.5's tags of every rollout: the protocol, every record with its quotes, the merged tags, and a second, blind tagging of 117 rollouts |
| [results/report.md](results/report.md) | Every answer and refusal, by setup, question and proposition, and what each harness contacted |
| [results/search_summary.md](results/search_summary.md) | Where each setup searched and what it read |
| [results/OLD_MEASURE_CHECK.md](results/OLD_MEASURE_CHECK.md) | The 11 answers about an older measure with the same number, and how every rollout was checked |
| `results/runs.csv`, `visits.csv`, `old_measure_screen.csv` | One row per rollout; every page opened, with its position in the run; the older-measure screen, one row per rollout |
| `results/excluded.json`, `manifest.json` | The excluded answers, and the configuration behind every rollout |
| [docs/methodology.md](docs/methodology.md) | Prompts, setups, harness settings, what each rollout records, and what we learned about the harnesses |
| `data/` | What the code reads: the config and prompts, the ballot, Codex's model catalogs, model notes (vendor, open weights) and proposition notes (party positions, results) |
| `ballot/` | The code: one Python package, run with `python3 -m ballot <command>` |
| `tests/` | Tests for the runner, the harness adapters, the network capture and the key handling; none spends anything |

Every network request and response (keys redacted), the recording proxy's logs and every file each harness wrote are in
the [logs release](https://github.com/Halluminate/ai-agents-ca-ballot-2026/releases/tag/logs-v1), under the same
`rollouts/<setup>/<rollout>/` paths. Download both parts and unpack them into one folder.

## Rerun the experiment

Running needs macOS (each run is sandboxed with `sandbox-exec`), Node 25, Python 3.12 and [uv](https://docs.astral.sh/uv/).
The code itself uses only Python's standard library.

**Harnesses and network capture.** The pinned harness binaries come from `package.json`; mitmproxy records every run's
traffic.

```bash
npm ci
```

```bash
uv venv .venv-netlog && uv pip install --python .venv-netlog/bin/python mitmproxy==12.3.1
```

**Keys.** The first command opens a hidden window for the OpenRouter key and saves it to `.env`. The next two do the same
for the OpenAI and Gemini keys, check each with a free request and say whether it can use the models the experiment needs.

```bash
python3 -m ballot keys
```

```bash
python3 -m ballot keys openai
```

```bash
python3 -m ballot keys gemini
```

**Preflight.** Checks the keys, the models, Pi's settings and the harnesses. It spends nothing.

```bash
python3 -m ballot preflight
```

**Runs.** The first command runs every setup on Proposition 1 only (81 runs), as a check. The second runs all 1,134 and
skips what's done. Both write into `runs/`.

```bash
caffeinate -i python3 -m ballot run --props 1 --yes
```

```bash
caffeinate -i python3 -m ballot run --yes
```

**Publish.** `export` writes the cleaned copy of `runs/` into `results/` and the heavy logs into `runs/logs-part*.tar`;
`results` builds the pages and tables in `results/` from the rollouts.

```bash
python3 -m ballot export
```

```bash
python3 -m ballot results
```

- If a run stops for any reason, run the same command again and it picks up where it left off.
- `--models` takes model names from `data/experiment.toml`, or `name:native` or `name:common` to run one harness of a model.
- `python3 -m ballot keys --check` tests every saved key again.
- `caffeinate -i` keeps the Mac from sleeping while a command runs.
- `python3 -m ballot report runs` writes `report.md` and `runs.csv` for the runs folder.

## Rerun the tagging

Claude Opus 5.5 tagged every rollout under [results/tags/PROTOCOL.md](results/tags/PROTOCOL.md), in 20 Claude Code
sessions, one per shard. [results/tags/README.md](results/tags/README.md) explains the records.

```bash
python3 -m ballot tags kit tagging
```

writes the kit the taggers worked in: every rollout as they read it, blind (`rollouts/R0001.md` to `R1134.md`), the 20
shards, the protocol, and `add.py` and `status.py`, which check and log each record. Each tagger reads `PROTOCOL.md` and
tags its shard.

```bash
python3 -m ballot tags check
```

checks every published record against its rollout, as `add.py` did, and `python3 -m ballot tags merge` rebuilds
`tags.jsonl` and `tags_second.jsonl` from the records.

## The code

| Module | What it does |
|---|---|
| `ballot/paths.py` | Where everything lives |
| `ballot/config.py` | The config, the API keys, the prompts and how a reply's yes or no is read |
| `ballot/harnesses.py` | One adapter per harness: how to launch it, its clean room, and how to read its events |
| `ballot/runner.py` | Runs the plan: concurrency, retries, timeouts, the spending cap and resuming |
| `ballot/netlog.py`, `netlog_addon.py`, `netlog.sb` | The sandbox and the recording proxy, with secrets redacted in the logs |
| `ballot/keys.py`, `preflight.py`, `codex_catalog.py` | Saving keys, checking everything before a run, and Codex's model catalogs |
| `ballot/export.py` | Copies the runs into `results/`, cleaned, and the heavy logs into the release archive |
| `ballot/meta.py` | Names for models, harnesses, questions and propositions |
| `ballot/analysis/` | `load` reads rollouts; `report`, `sites`, `old_measures` and `trajectories` write the pages and tables in `results/`; `pipeline` runs them all |
| `ballot/tagging/` | The tagging kit, its record checker (`add.py`) and the merge of the tag records |

## Tests

None of these spend anything.

| Test | What it checks |
|---|---|
| `tests/test_offline.py` | The prompts and ballot, how a yes or no is read (and refusals aren't), each harness's event parser and cost estimate, and each harness's settings, with no model calls |
| `tests/test_runner.py` | The runner with a stub harness: refusals are data and never retried, infrastructure failures are, timeouts, resuming, the spending cap and per-model limits |
| `tests/test_pipeline.py` | Runs the real harness binaries against a local fake server shaped like OpenRouter, OpenAI and Google. It checks that each harness completes a run, offers only web tools, sends the right effort, pins its provider and uses only its own key. |
| `tests/test_add_keys.py` | That the keys command keeps every key off the screen and writes a private `.env` |
| `tests/test_netlog.py` | The network capture, with local servers and the real harness binaries |

```bash
python3 tests/test_offline.py && python3 tests/test_runner.py && python3 tests/test_pipeline.py && python3 tests/test_add_keys.py && python3 tests/test_netlog.py
```

## Citation

```bibtex
@misc{halluminate2026agentsvote,
  title  = {How AI agents vote: California's November 2026 ballot},
  author = {Alina Hyk and Wyatt Marshall},
  year   = {2026},
  month  = {November},
  url    = {https://github.com/Halluminate/ai-agents-ca-ballot-2026}
}
```
