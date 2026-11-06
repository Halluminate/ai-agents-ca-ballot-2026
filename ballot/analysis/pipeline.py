"""Every page and table in results/ that's built from the rollouts, in one command.

Usage: python3 -m ballot results [--skip <step>,...]
Steps, in order:
  report        report.md and runs.csv: every answer and refusal, by setup, question and proposition
  sites         search_summary.md: where each setup searched and what it read
  trajectories  the answer grid and each setup's index, linking every trajectory (trajectory.jsonl), and visits.csv
  old-measures  old_measure_screen.csv: the screen behind OLD_MEASURE_CHECK.md
Reads only what's in results/, so anyone with the repository can rerun it. Needs no keys and spends nothing.
"""

import argparse
import sys
import time

from ballot.analysis import old_measures, report, sites, trajectories
from ballot.paths import RESULTS

STEPS = ("report", "sites", "trajectories", "old-measures")


def main() -> None:
    parser = argparse.ArgumentParser(prog=sys.argv[0], description=__doc__.splitlines()[0])
    parser.add_argument("--skip", default="", help=f"comma-separated steps to leave out: {', '.join(STEPS)}")
    skip = set(filter(None, parser.parse_args().skip.split(",")))
    if not (RESULTS / "rollouts").is_dir():
        sys.exit(f"No rollouts in {RESULTS}. Run python3 -m ballot export first.")

    def step(name: str, action) -> object:
        if name in skip:
            print(f"- {name}: skipped")
            return None
        started = time.time()
        out = action()
        print(f"- {name}: done in {time.time() - started:.0f}s")
        return out

    results = report.write_report(RESULTS)
    step("sites", lambda: sites.write_summary(RESULTS, results))
    step("trajectories", lambda: trajectories.write_all(RESULTS, results))
    step("old-measures", lambda: old_measures.write(RESULTS, results))


if __name__ == "__main__":
    main()
