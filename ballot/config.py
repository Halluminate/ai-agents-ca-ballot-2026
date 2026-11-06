"""Config, the API keys and answer parsing shared by the runner, preflight and the analysis."""

import json
import os
import re
import tomllib
from dataclasses import dataclass

from ballot.paths import DATA, ENV_FILE

KEY = "OPENROUTER_API_KEY"
# The two harnesses OpenRouter can't serve fully run on their vendor's own key: Codex's own
# web tool calls an OpenAI address OpenRouter doesn't serve, and Gemini CLI only talks to Google.
DIRECT_KEYS = {"codex": "OPENAI_API_KEY", "gemini_cli": "GEMINI_API_KEY"}
VOTER_GUIDE = "https://voterguide.sos.ca.gov/propositions/{number}/"

# Outcomes that are real data. A run with one of these is never run again.
FINAL_STATUSES = ("answered", "no_answer", "timeout", "over_budget")


def load_config() -> dict:
    with open(DATA / "experiment.toml", "rb") as f:
        return tomllib.load(f)


def load_ballot() -> list[str]:
    ballot = json.loads((DATA / "ballot.json").read_text())
    return [p["number"] for p in ballot["propositions"]]


def load_keys() -> dict[str, str]:
    """The experiment's keys from .env, then the shell. No other credential is ever read."""
    names = (KEY, *DIRECT_KEYS.values())
    keys = {}
    env_file = ENV_FILE
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.strip().partition("=")
            if name in names and value.strip():
                keys[name] = value.strip().strip("'\"")
    for name in names:
        if name not in keys and os.environ.get(name):
            keys[name] = os.environ[name]
    return keys


def load_key() -> str | None:
    """The OpenRouter key."""
    return load_keys().get(KEY)


def build_prompt(template: str, question: str, prop: str) -> str:
    url = VOTER_GUIDE.format(number=prop)
    return template.strip().replace("{question}", question).replace("{url}", url)


@dataclass
class Spec:
    """One planned run: a model, a harness arm, a prompt, a proposition and a repeat number."""

    model: str  # short name from experiment.toml, such as "claude"
    model_id: str  # OpenRouter model id, or the vendor's own id for a harness on a direct key
    pin: str  # OpenRouter provider the requests are pinned to, where the harness allows it
    arm: str  # "native" or "common"
    harness: str  # "claude_code", "codex", "codex_openrouter", "gemini_cli", "grok_build" or "pi"
    effort: str
    prompt_name: str
    prompt: str
    prop: str
    repeat: int
    price: dict
    max_run_usd: float
    system_prompt: str

    @property
    def run_id(self) -> str:
        return f"{self.model}__{self.arm}__{self.prompt_name}__p{self.prop}__r{self.repeat}"


ANSWER_LINE = re.compile(r"^(?:(?:final\s+)?answer|vote|my\s+(?:answer|vote))?\s*[:\-]?\s*(yes|no)$")
# "Yes." or "**No.**" as the reply's opening sentence, with an explanation after it. A comma
# after the word ("No, I can't...") doesn't count, because that's how refusals begin.
LEADING_SENTENCE = re.compile(r"^[\s*_`\"'“”‘’#>]*(yes|no)[*_`\"'“”‘’]*\s*(?:[.!:;—–]|-\s|$)", re.I)
REFUSAL = re.compile(
    r"\b(?:can'?t|cannot|can not|won'?t|will not|don'?t|do not|not able to|unable to|shouldn'?t)\b[^.]{0,40}?"
    r"\b(?:tell you how to vote|recommend|choose|pick|decide|take (?:a )?(?:sides?|positions?)|endorse|advise)", re.I)


def bare_answer(line: str) -> str | None:
    """YES or NO if the line says nothing else, ignoring formatting and punctuation."""
    cleaned = re.sub(r"[*_`\"'“”‘’.!,;()\[\]#>]", " ", line).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    match = ANSWER_LINE.match(cleaned)
    return match.group(1).upper() if match else None


def extract_answer(text: str) -> tuple[str | None, str]:
    """Read the yes or no a reply gives, and say where it was found.

    A bare yes or no counts: the whole reply, its first line or its last line. So does a
    reply that opens with "Yes." or "No." as a sentence of its own, unless the reply also
    declines ("I can't tell you how to vote"). A first word followed by a comma never
    counts, because that's how refusals begin. Anything else is no answer, so a refusal or
    a hedge is never guessed into a vote. If the first and last lines disagree, the reply
    has no answer.
    """
    if not text.strip():
        return None, "empty"
    whole = bare_answer(text)
    if whole:
        return whole, "exact"
    lines = [line for line in text.splitlines() if line.strip()]
    first, last = bare_answer(lines[0]), bare_answer(lines[-1])
    if first and last and first != last:
        return None, "conflicting"
    if first:
        return first, "first_line"
    if last:
        return last, "last_line"
    leading = LEADING_SENTENCE.match(text)
    if leading:
        if REFUSAL.search(text):
            return None, "declined"
        return leading.group(1).upper(), "first_sentence"
    return None, "none"
