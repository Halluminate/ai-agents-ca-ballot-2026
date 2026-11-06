"""report.md and runs.csv for a folder of rollouts: a raw runs folder, or the published results."""

import csv
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

from ballot.analysis.load import load_results
from ballot.config import DIRECT_KEYS, load_ballot
from ballot.paths import RUNS

STATUSES = ("answered", "no_answer", "excluded", "error", "timeout", "over_budget")
def sort_results(results: list[dict], config: dict) -> list[dict]:
    """Put results in the order of the config and the ballot, so every table reads the same way."""
    prompts = list(config.get("prompts") or {})
    models = [m["name"] for m in config.get("models") or []]
    ballot = load_ballot()

    def position(items: list, value) -> tuple:
        return (items.index(value), "") if value in items else (len(items), str(value))

    return sorted(results, key=lambda r: (position(models, r["model"]), position(["native", "common"], r["arm"]),
                                          position(prompts, r["prompt"]), position(ballot, r["prop"])))


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def percent(hits: int, total: int) -> str:
    return f"{100 * hits / total:.0f}% ({hits}/{total})" if total else "n/a"


def order(results: list[dict], field: str) -> list:
    return list(dict.fromkeys(r[field] for r in results))


def pairs(results: list[dict]) -> list[tuple[str, str]]:
    return list(dict.fromkeys((r["model"], r["arm"]) for r in results))


def write_csvs(folder: Path, results: list[dict]) -> None:
    fields = ["run_id", "path", "model", "model_id", "arm", "harness", "effort", "prompt", "prop", "repeat", "status",
              "answer", "excluded_answer", "excluded", "answer_form", "attempts", "seconds", "input_tokens", "output_tokens",
              "cached_tokens", "cost_usd", "cost_source", "billed_usd", "search_errors", "tool_errors", "error"]
    with open(folder / "runs.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields + ["searches", "pages", "requests_logged"], extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow({**r, "searches": len(r["searches"]), "pages": len(r["fetches"]),
                             "requests_logged": (r.get("network") or {}).get("requests", "")})


def outcome_section(results: list[dict]) -> str:
    rows = []
    for model, arm in pairs(results):
        group = [r for r in results if (r["model"], r["arm"]) == (model, arm)]
        counts = Counter(r["status"] for r in group)
        n = len(group)
        billed = [r["billed_usd"] for r in group if r.get("billed_usd") is not None]
        rows.append([model, arm, group[0]["harness"], n, *[counts[s] for s in STATUSES],
                     f"{sum(r['seconds'] for r in group) / n / 60:.1f}",
                     f"${sum(r['cost_usd'] for r in group):.2f}",
                     f"${sum(billed):.2f}" if billed else "n/a",
                     f"${sum(billed) / len(billed):.2f}" if billed else "n/a",
                     f"{sum(len(r['searches']) for r in group) / n:.1f}",
                     sum(1 for r in group if not r["searches"]),
                     sum(r["search_errors"] for r in group)])
    headers = ["model", "arm", "harness", "runs", *STATUSES,
               "mean min", "recorded cost", "billed cost", "billed per run", "mean searches", "runs with no search",
               "failed searches"]
    note = ("Recorded cost is what each harness reported, or an estimate from its tokens for Codex, Grok Build and "
            "Gemini CLI. Billed cost is what OpenRouter charged, from every response in the run's network log, and it "
            "is the real figure. The two differ most for Grok Build, whose searches run as separate model calls. "
            "Codex and Gemini CLI on their own keys are billed by OpenAI and Google, so their billed cost is the "
            "estimate from tokens and search fees.")
    return "## Run outcomes\n\n" + table(headers, rows) + "\n\n" + note


def answer_rate_section(results: list[dict]) -> str:
    prompts = order(results, "prompt")
    rows = []
    for model, arm in pairs(results):
        row = [model, arm]
        for prompt in prompts:
            group = [r for r in results if (r["model"], r["arm"], r["prompt"]) == (model, arm, prompt)
                     and r["status"] in ("answered", "no_answer")]
            row.append(percent(sum(1 for r in group if r["answer"]), len(group)))
        rows.append(row)
    forms = Counter(r["answer_form"] for r in results if r["status"] in ("answered", "no_answer"))
    intro = ("Share of finished runs that gave a plain yes or no. Anything else counts as declining, and those "
             "runs are never retried, so this measures refusals and hedging directly. Errors, timeouts and excluded "
             "answers are left out.")
    form_note = "How answers were read: " + ", ".join(f"{form} {n}" for form, n in forms.most_common()) + "."
    return f"## Did they answer?\n\n{intro}\n\n" + table(["model", "arm", *prompts], rows) + f"\n\n{form_note}"


def cell(result: dict | None) -> str:
    if result is None:
        return "-"
    if result["status"] == "answered":
        return result["answer"]
    return "declined" if result["status"] == "no_answer" else result["status"]


def answers_section(results: list[dict], prompts: dict, props: list[str]) -> str:
    by_key = {(r["model"], r["arm"], r["prompt"], r["prop"]): r for r in results}
    columns = pairs(results)
    parts = ["## Answers\n\n\"declined\" means the run finished without a plain yes or no. \"excluded\" means its "
             "answer can't count; excluded.json says why. \"-\" means that run hasn't been done yet."]
    for prompt in order(results, "prompt"):
        rows = [[prop, *[cell(by_key.get((m, a, prompt, prop))) for m, a in columns]] for prop in props]
        parts.append(f"### {prompt}: {prompts.get(prompt, '')}\n\n" + table(["prop", *[f"{m} / {a}" for m, a in columns]], rows))
    return "\n\n".join(parts)


def compare(results: list[dict], left, right) -> tuple[int, int]:
    """Matching and total answers across propositions where both sides answered."""
    answers = {(r["model"], r["arm"], r["prompt"], r["prop"]): r["answer"] for r in results if r["answer"]}
    same = total = 0
    for prop in order(results, "prop"):
        a, b = answers.get(left + (prop,)), answers.get(right + (prop,))
        if a and b:
            total += 1
            same += a == b
    return same, total


def effects_section(results: list[dict]) -> str:
    prompts = order(results, "prompt")
    rows = []
    for model, arm in pairs(results):
        row = [model, arm]
        for a, b in combinations(prompts, 2):
            same, total = compare(results, (model, arm, a), (model, arm, b))
            row.append(percent(total - same, total))
        rows.append(row)
    headers = ["model", "arm", *[f"{a} vs {b}" for a, b in combinations(prompts, 2)]]
    prompt_part = ("### Between prompts\n\nShare of propositions where the same model and harness gave different "
                   "answers to two prompts. \"win\" asks for a prediction, so it can differ for good reason.\n\n"
                   + table(headers, rows))

    rows = []
    for model in order(results, "model"):
        arms = [arm for m, arm in pairs(results) if m == model]
        if len(arms) < 2:
            continue
        row = [model]
        for prompt in prompts:
            same, total = compare(results, (model, "native", prompt), (model, "common", prompt))
            row.append(percent(total - same, total))
        rows.append(row)
    harness_part = ("### Between harnesses\n\nShare of propositions where a model's native harness and the shared "
                    "harness gave different answers to the same prompt.\n\n" + table(["model", *prompts], rows))
    note = "With one run per condition, a difference here can be noise. Repeats would separate the two."
    return f"## Prompt and harness effects\n\n{note}\n\n{prompt_part}\n\n{harness_part}"


def agreement_section(results: list[dict]) -> str:
    parts = ["## Agreement between models\n\nShare of propositions where two models gave the same answer, "
             "when both answered."]
    for arm in order(results, "arm"):
        models = [m for m, a in pairs(results) if a == arm]
        rows = []
        for a, b in combinations(models, 2):
            row = [a, b]
            for prompt in order(results, "prompt"):
                same, total = compare(results, (a, arm, prompt), (b, arm, prompt))
                row.append(percent(same, total))
            rows.append(row)
        if rows:
            parts.append(f"### {arm}\n\n" + table(["model", "model", *order(results, "prompt")], rows))
    return "\n\n".join(parts)


def network_section(results: list[dict]) -> str:
    rows = []
    for model, arm in pairs(results):
        group = [r for r in results if (r["model"], r["arm"]) == (model, arm) and r.get("network")]
        hosts: Counter = Counter()
        for r in group:
            hosts.update(r["network"].get("requests_per_host") or {})
        requests = sum(r["network"].get("requests", 0) for r in group)
        top = ", ".join(f"{h} ({n})" for h, n in hosts.most_common(8))
        rows.append([model, arm, len(group), requests, top or "-"])
    intro = ("Every request each run made, from its network log (summarized in each rollout's other/network_summary.json). "
             "This includes model calls, searches, page fetches and any telemetry.")
    return f"## What each harness contacted\n\n{intro}\n\n" + table(["model", "arm", "runs logged", "requests", "hosts"], rows)


def sources_section(results: list[dict]) -> str:
    parts = ["## Most-read sites\n\nBased on the pages each harness reports opening."]
    for arm in order(results, "arm"):
        domains = Counter(urlparse(url).netloc.removeprefix("www.") for r in results if r["arm"] == arm for url in r["fetches"])
        parts.append(f"### {arm}\n\n" + table(["site", "reads"], [[d, n] for d, n in domains.most_common(15)]))
    return "\n\n".join(parts)


def write_report(folder: Path) -> list[dict]:
    """Write report.md and runs.csv into the folder and return its results, sorted."""
    results = load_results(folder)
    if not results:
        sys.exit(f"No results in {folder}.")

    manifest = json.loads((folder / "manifest.json").read_text()) if (folder / "manifest.json").exists() else {}
    config = manifest.get("config") or {}
    prompts = config.get("prompts") or {}
    results = sort_results(results, config)
    write_csvs(folder, results)
    ran = set(order(results, "prop"))
    props = [p for p in load_ballot() if p in ran]
    billed = [r["billed_usd"] for r in results if r.get("billed_usd") is not None]
    direct = any(r.get("harness") in DIRECT_KEYS for r in results)
    spend = (f"${sum(billed):.2f} billed" + (" (OpenRouter's bill, plus estimates for Codex and Gemini CLI on their own keys)"
                                              if direct else " by OpenRouter")
             if billed else f"${sum(r['cost_usd'] for r in results):.2f} recorded")
    excluded = sum(1 for r in results if r["status"] == "excluded")
    sections = [
        f"# Results: {folder.name}\n\n{len(results)} runs, {spend}."
        + (f" {excluded} answers are excluded and left out of every comparison; excluded.json says why." if excluded else ""),
        outcome_section(results),
        answer_rate_section(results),
        answers_section(results, prompts, props),
        effects_section(results),
        agreement_section(results),
        network_section(results),
        sources_section(results),
    ]
    (folder / "report.md").write_text("\n\n".join(sections) + "\n")
    print(f"Wrote {folder / 'report.md'} and runs.csv")
    return results


def main() -> None:
    if len(sys.argv) > 1:
        folder = Path(sys.argv[1])
    else:
        folders = [p for p in RUNS.glob("*") if (p / "manifest.json").exists()]
        if not folders:
            sys.exit("No runs yet.")
        folder = max(folders, key=lambda p: p.stat().st_mtime)
    write_report(folder)


if __name__ == "__main__":
    main()
