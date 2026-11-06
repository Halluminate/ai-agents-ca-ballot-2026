"""Where everything lives. Every other module takes its paths from here."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the repository
PACKAGE = ROOT / "ballot"
DATA = ROOT / "data"  # what the experiment and the analysis read: config, ballot, catalogs, notes on props and models
BIN = ROOT / "node_modules" / ".bin"  # the pinned harness binaries from package.json
ENV_FILE = ROOT / ".env"  # the API keys, saved by `python3 -m ballot keys`
RUNS = ROOT / "runs"  # raw run folders, with full network logs; never committed
RESULTS = ROOT / "results"  # the published results, cleaned by `python3 -m ballot export`
ROLLOUTS = RESULTS / "rollouts"  # one folder per rollout: results/rollouts/<setup>/<question>__prop-<NN>/
