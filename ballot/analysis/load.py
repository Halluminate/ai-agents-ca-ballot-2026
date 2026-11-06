"""Read rollouts from a raw runs folder (runs/<name>/<run>/) or from the published results
(results/rollouts/<setup>/<rollout>/), with every answer read again by the current rules."""

import gzip
import json
import re
from pathlib import Path

from ballot.config import DIRECT_KEYS, extract_answer

COST = re.compile(r'"cost"\s*:\s*([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)')
# A published rollout's folder holds result.json, search_results.json and trajectory.jsonl; every other file is
# in its other/ folder. A raw run's folder holds everything at the top.
TOP_FILES = ("result.json", "search_results.json", "trajectory.jsonl")
OTHER = "other"


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def rollout_file(run_dir: Path, name: str) -> Path:
    """Where a rollout keeps a file: in other/ in the published results, at the top of a raw run's folder."""
    return run_dir / OTHER / name if name not in TOP_FILES and (run_dir / OTHER).is_dir() else run_dir / name


def rollout_dirs(folder: Path) -> list[Path]:
    """Every rollout folder: one level down in a runs folder, two levels down in results/rollouts."""
    base = folder / "rollouts" if (folder / "rollouts").is_dir() else folder
    found = sorted(p.parent for p in base.glob("*/result.json"))
    return found or sorted(p.parent for p in base.glob("*/*/result.json"))


def billed_cost(run_dir: Path) -> float | None:
    """What OpenRouter charged for a run, failed attempts included.

    Each OpenRouter response carries its own usage.cost, and a streamed one repeats it as
    it grows, so the last value in each response is its charge. This covers what the
    harnesses can't report themselves, such as Grok Build's separate search calls.
    The total is saved as billed.json, so it survives where the network logs aren't kept.
    A run that never called OpenRouter, such as Codex or Gemini CLI on its own key, has no
    bill here: None.
    """
    logs = sorted(run_dir.glob("network*.jsonl.gz"))
    saved = rollout_file(run_dir, "billed.json")
    if not logs:
        return json.loads(saved.read_text())["billed_usd"] if saved.exists() else None
    total, called = 0.0, False
    for log in logs:
        for line in gzip.decompress(log.read_bytes()).splitlines():
            record = json.loads(line)
            if record.get("type") != "http" or "openrouter.ai" not in ((record.get("request") or {}).get("url") or ""):
                continue
            called = True
            costs = COST.findall((record.get("response") or {}).get("body") or "")
            total += float(costs[-1]) if costs else 0.0
    if not called:
        saved.write_text(json.dumps({"billed_usd": None, "source": "no OpenRouter requests in the run's network logs"}))
        return None
    saved.write_text(json.dumps({"billed_usd": round(total, 4), "source": "usage.cost in the run's network logs"}))
    return total


def load_results(folder: Path) -> list[dict]:
    """Every result in the folder, with its answer read again from the saved reply.

    excluded.json, where present, maps a run id to why its answer can't count, such as an
    answer about an older measure with the same number: the run shows as "excluded" and its
    answer is left out of every comparison. Each result also gets "path", its folder relative
    to `folder`.
    """
    excluded = read_json(folder / "excluded.json", {})
    results = []
    for run_dir in rollout_dirs(folder):
        result = json.loads((run_dir / "result.json").read_text())
        result["billed_usd"] = billed_cost(run_dir)
        if result["billed_usd"] is None and result.get("harness") in DIRECT_KEYS:
            result["billed_usd"] = result["cost_usd"]  # billed by OpenAI or Google, estimated from tokens
        if result["status"] in ("answered", "no_answer"):
            final = rollout_file(run_dir, "final.txt")
            result["answer"], result["answer_form"] = extract_answer(final.read_text() if final.exists() else "")
            result["status"] = "answered" if result["answer"] else "no_answer"
        result["excluded"] = result["excluded_answer"] = ""
        if result["run_id"] in excluded:
            result["excluded"], result["excluded_answer"] = excluded[result["run_id"]], result["answer"]
            result["answer"], result["status"] = None, "excluded"
        result["path"] = run_dir.relative_to(folder).as_posix()
        results.append(result)
    return results
