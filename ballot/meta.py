"""Names for everything: models, harnesses, questions and propositions.

Model names, vendors and licenses come from data/models.csv; proposition notes (title,
description, party positions, results) from data/propositions.csv; the question wording
from data/experiment.toml.
"""

import csv
import json
from functools import cache

from ballot.config import load_config
from ballot.paths import DATA

HARNESSES = {
    "claude_code": "Claude Code",
    "codex": "Codex",
    "codex_openrouter": "Codex (OpenRouter)",
    "gemini_cli": "Gemini CLI",
    "grok_build": "Grok Build",
    "pi": "Pi",
}
QUESTION_ORDER = ("vote", "better", "win")


@cache
def models() -> dict[str, dict]:
    with open(DATA / "models.csv", newline="") as f:
        return {row["short_name"]: row for row in csv.DictReader(f)}


@cache
def propositions() -> dict[str, dict]:
    """Keyed by number as a string ("1", "37"), in ballot order."""
    numbers = [p["number"] for p in json.loads((DATA / "ballot.json").read_text())["propositions"]]
    notes = {}
    path = DATA / "propositions.csv"
    if path.exists():
        with open(path, newline="") as f:
            notes = {row["prop"]: row for row in csv.DictReader(f)}
    titles = {p["number"]: p["title"] for p in json.loads((DATA / "ballot.json").read_text())["propositions"]}
    return {n: {"prop": n, "title": titles[n], **notes.get(n, {})} for n in numbers}


@cache
def questions() -> dict[str, str]:
    """Each question's name and wording, in the order the analysis uses."""
    prompts = load_config()["prompts"]
    return {name: prompts[name] for name in QUESTION_ORDER if name in prompts}


def model_name(model: str) -> str:
    return models()[model]["display_name"] if model in models() else model


def setup_name(model: str, harness: str) -> str:
    return f"{model_name(model)} · {HARNESSES.get(harness, harness)}"


def setup_slug(model: str, harness: str) -> str:
    """The setup's folder under results/rollouts, such as claude-opus-5.5__claude-code."""
    slug = models()[model]["slug"] if model in models() else model
    return f"{slug}__{HARNESSES.get(harness, harness).lower().replace(' ', '-').replace('(', '').replace(')', '')}"


def rollout_slug(question: str, prop: str, repeat: int = 1, repeats: int = 1) -> str:
    """The rollout's folder inside its setup's, such as vote__prop-01."""
    return f"{question}__prop-{int(prop):02d}" + (f"__r{repeat}" if repeats > 1 else "")
