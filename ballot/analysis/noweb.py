"""The no-web arm: every page for its rollouts, and how its answers compare with the published ones.

Usage: python3 -m ballot.analysis.noweb [folder]   (also the noweb step of python3 -m ballot results)
The folder defaults to results/noweb, the cleaned export of the no-web runs. Into it go report.md and
runs.csv, the trajectory pages, old_measure_screen.csv, and comparison.md and comparison.json.

The comparison sets each model's no-web rollout beside its published rollout in Pi, the shared harness,
for the same question and proposition. It uses report.md's definitions: an answer is a plain yes or no;
an answer rate counts finished rollouts only, leaving out timeouts, errors and excluded answers; excluded
answers are left out of every comparison. The lean is the share of answers to the vote and better
questions on the conservative side, on the 10 propositions where the parties disagreed. The arm's
published rollouts are its vote and better questions only.
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

from ballot.analysis import old_measures, report, trajectories
from ballot.config import load_config
from ballot.meta import models, propositions
from ballot.paths import RESULTS

ADVICE = ("vote", "better")
FINISHED = ("answered", "no_answer")
PROPS = propositions()
SPLIT = [p for p, row in PROPS.items() if row["conservative_side"]]


def conservative(prop: str, answer: str) -> bool:
    return answer.lower() == PROPS[prop]["conservative_side"]


def published_rollouts() -> dict[tuple, tuple]:
    """The published Pi rollouts, as (model, question, prop) -> (status, answer)."""
    with open(RESULTS / "runs.csv", newline="") as f:
        return {(r["model"], r["prompt"], r["prop"]): (r["status"], r["answer"] or None)
                for r in csv.DictReader(f) if r["arm"] == "common"}


def summary(rollouts: dict, model: str | None = None) -> dict:
    """Answer rate and lean, for every model or for one."""
    mine = {k: v for k, v in rollouts.items() if model in (None, k[0])}
    advice = [(k, a) for k, (status, a) in mine.items() if k[1] in ADVICE and status in FINISHED]
    answers = [(k, a) for k, a in advice if a]
    lean = [(k, a) for k, a in answers if k[2] in SPLIT]
    return {"advice_finished": len(advice), "advice_answered": len(answers),
            "lean_answers": len(lean), "conservative": sum(conservative(k[2], a) for k, a in lean)}


def advice_answers(rollouts: dict, prop: str) -> list[str]:
    """A proposition's plain answers to the vote and better questions."""
    return [a for (_, q, p), (status, a) in rollouts.items() if p == prop and q in ADVICE and status == "answered"]


def by_prop(rollouts: dict) -> dict[str, dict]:
    """Each proposition's advice answers."""
    out = {}
    for prop in PROPS:
        answers = advice_answers(rollouts, prop)
        out[prop] = {"answers": len(answers), "yes": answers.count("YES")}
    return out


def majority_conservative(rollouts: dict) -> list[str]:
    """The propositions where most advice answers took the conservative side."""
    out = []
    for prop in SPLIT:
        answers = advice_answers(rollouts, prop)
        if answers and sum(conservative(prop, a) for a in answers) > len(answers) / 2:
            out.append(prop)
    return out


def sign_test(hits: int, misses: int) -> float | None:
    """Exact two-sided sign test: how likely a split at least this lopsided is if each change were a coin flip."""
    n = hits + misses
    if not n:
        return None
    tail = sum(math.comb(n, i) for i in range(min(hits, misses) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def changes(published: dict, noweb: dict) -> dict:
    """How each answer to a vote or better question changed without research. A pair is left out when
    either rollout didn't finish or its answer was excluded."""
    count = Counter()
    switches = []
    for key in sorted(published.keys() & noweb.keys()):
        (before_status, before), (after_status, after) = published[key], noweb[key]
        if key[1] not in ADVICE:
            continue
        if before_status not in FINISHED or after_status not in FINISHED:
            count["left_out"] += 1
        elif before == after:
            count["same_answer" if before else "no_answer_both"] += 1
        elif not after:
            count["answer_to_no_answer"] += 1
        elif not before:
            count["no_answer_to_answer"] += 1
        else:
            side = ("not_mapped" if key[2] not in SPLIT
                    else "to_conservative" if conservative(key[2], after) else "to_progressive")
            count[side] += 1
            switches.append({"model": key[0], "question": key[1], "prop": key[2], "from": before, "to": after, "side": side})
    return {"counts": dict(count), "switches": switches,
            "lean_sign_test_p": sign_test(count["to_conservative"], count["to_progressive"]),
            "answering_sign_test_p": sign_test(count["answer_to_no_answer"], count["no_answer_to_answer"])}


def compare(folder: Path, results: list[dict]) -> dict:
    noweb = {(r["model"], r["prompt"], r["prop"]): (r["status"], r["answer"]) for r in results}
    published = {k: v for k, v in published_rollouts().items() if k in noweb}
    configured = load_config()["models"]
    names = models()
    manifest = json.loads((folder / "manifest.json").read_text())
    voters = [p for p in SPLIT if conservative(p, "YES" if PROPS[p]["result"] == "pass" else "NO")]
    return {
        "rollouts": len(results), "statuses": dict(Counter(r["status"] for r in results)),
        "billed_usd": round(sum(r["billed_usd"] or 0 for r in results), 2),
        "hosts": sorted({h for r in results for h in (r.get("network") or {}).get("hosts", [])}),
        "published": summary(published), "noweb": summary(noweb),
        "models": [{"model": m, "name": names[m]["display_name"], "vendor": names[m]["vendor"],
                    "open_weights": names[m]["open_weights"], "published": summary(published, m), "noweb": summary(noweb, m)}
                   for m in (c["name"] for c in configured)],
        "props": [{"prop": p, "short": PROPS[p]["short"], "title": PROPS[p]["title"],
                   "conservative_side": PROPS[p]["conservative_side"], "result": PROPS[p]["result"],
                   "voters_yes_pct": float(PROPS[p]["yes_pct"]), "called": PROPS[p]["called"],
                   "published": before, "noweb": after}
                  for (p, before), after in zip(by_prop(published).items(), by_prop(noweb).values())],
        "majority_conservative": {"published": majority_conservative(published), "noweb": majority_conservative(noweb),
                                  "voters": voters},
        "changes": changes(published, noweb),
        "checkpoints": {names[m["name"]]["display_name"]: manifest["openrouter_snapshots"][m["model"]]
                        for m in configured},
    }


def page(c: dict) -> str:
    """comparison.md: the comparison as tables."""
    pub, now = c["published"], c["noweb"]
    rows = [["Plain yes or no to vote and better", report.percent(pub["advice_answered"], pub["advice_finished"]),
             report.percent(now["advice_answered"], now["advice_finished"])],
            ["Answers on the conservative side", report.percent(pub["conservative"], pub["lean_answers"]),
             report.percent(now["conservative"], now["lean_answers"])]]
    counts = c["changes"]["counts"]
    change_rows = [[name.replace("_", " "), counts.get(name, 0)] for name in
                   ("same_answer", "no_answer_both", "answer_to_no_answer", "no_answer_to_answer",
                    "to_conservative", "to_progressive", "not_mapped", "left_out")]
    model_rows = [[m["name"], report.percent(m["published"]["advice_answered"], m["published"]["advice_finished"]),
                   report.percent(m["noweb"]["advice_answered"], m["noweb"]["advice_finished"]),
                   report.percent(m["published"]["conservative"], m["published"]["lean_answers"]),
                   report.percent(m["noweb"]["conservative"], m["noweb"]["lean_answers"])] for m in c["models"]]
    prop_rows = [[f"{p['prop']}: {p['short']}", p["conservative_side"] or "not mapped",
                  report.percent(p["published"]["yes"], p["published"]["answers"]),
                  report.percent(p["noweb"]["yes"], p["noweb"]["answers"]), f"{p['voters_yes_pct']:.1f}%", p["result"]]
                 for p in c["props"]]
    p_lean, p_answering = (f"{p:.2g}" if p is not None else "n/a"
                           for p in (c["changes"]["lean_sign_test_p"], c["changes"]["answering_sign_test_p"]))
    return "\n\n".join([
        "# The no-web arm against the published answers",
        f"{c['rollouts']} no-web rollouts, ${c['billed_usd']:.2f} billed by OpenRouter. Each model's no-web rollout "
        "is set beside its published rollout in Pi for the same question and proposition. An answer is a plain yes "
        "or no; answer rates count finished rollouts only; excluded answers are left out of every comparison. "
        f"Hosts the runs reached: {', '.join(c['hosts'])}.",
        "## Overall\n\n" + report.table(["", "Published, Pi", "No web"], rows),
        "## How the answers changed\n\nEach model's answer to the same vote or better question, published against "
        f"no web. Sign test on the switches between sides: p = {p_lean}. On answering against not answering: "
        f"p = {p_answering}.\n\n" + report.table(["Change", "Pairs"], change_rows),
        "## By model\n\n" + report.table(["Model", "Answered, published", "No web", "Conservative, published", "No web"], model_rows),
        "## By proposition\n\nYes share of the vote and better answers.\n\n"
        + report.table(["Proposition", "Conservative side", "Published", "No web", "Voters", "Result"], prop_rows),
        "## Checkpoints\n\nThe dated checkpoint OpenRouter served for each model, all before election day.\n\n"
        + report.table(["Model", "Checkpoint"], [[m, slug] for m, slug in c["checkpoints"].items()]),
    ]) + "\n"


def write(folder: Path) -> None:
    results = report.write_report(folder)
    trajectories.write_all(folder, results)
    old_measures.write(folder, results)
    comparison = compare(folder, results)
    (folder / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    (folder / "comparison.md").write_text(page(comparison))
    print(f"Wrote {folder / 'comparison.md'} and comparison.json")


def main() -> None:
    parser = argparse.ArgumentParser(prog=sys.argv[0], description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", type=Path, default=RESULTS / "noweb")
    folder = parser.parse_args().folder
    if not (folder / "rollouts").is_dir():
        sys.exit(f"No rollouts in {folder}. Export the no-web runs there first: "
                 f"python3 -m ballot export runs/noweb --out {folder}")
    write(folder)


if __name__ == "__main__":
    main()
