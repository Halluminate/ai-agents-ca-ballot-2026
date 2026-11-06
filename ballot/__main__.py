"""Usage: python3 -m ballot <command> [options]

Running the experiment
  keys [openrouter|openai|gemini] [--check]  save an API key to .env through a hidden window
  preflight                                  check the keys, models and harnesses; spends nothing
  codex-catalog <codex binary>               rebuild Codex's model catalogs in data/
  run [options]                              run models on the ballot; `run --help` lists the options
  report <runs folder>                       report.md and runs.csv for one runs folder

Publishing the results
  export [runs folder] [--logs <tar>]        cleaned copy of the runs into results/, heavy logs into a tar
  tags kit <folder> | check | merge          the tagging kit, a check of every tag record, and the merged tags
  results                                    every page and table in results/, built from the rollouts
"""

import importlib
import sys

COMMANDS = {
    "keys": "ballot.keys",
    "preflight": "ballot.preflight",
    "codex-catalog": "ballot.codex_catalog",
    "run": "ballot.runner",
    "report": "ballot.analysis.report",
    "export": "ballot.export",
    "tags": "ballot.tagging",
    "results": "ballot.analysis.pipeline",
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    command = sys.argv.pop(1)
    sys.argv[0] = f"python3 -m ballot {command}"
    importlib.import_module(COMMANDS[command]).main()


if __name__ == "__main__":
    main()
