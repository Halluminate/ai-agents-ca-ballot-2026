"""The tags on every rollout: rebuild the kit the taggers worked in, check every record, merge the shards.

Claude Opus 5.5, in 20 Claude Code sessions at maximum effort, one per shard, tagged every rollout under
results/tags/PROTOCOL.md: its answer, the reasons and values it argued from, what it relied on, how it reached its
answer, and more. Each session read its rollouts blind, as R0001 to R1134 with no model or harness named, and logged
one record per rollout through add.py, which checks every rule in the protocol, every quote included. About a tenth of
the rollouts were tagged again by a second session, blind, to measure agreement.

Usage: python3 -m ballot tags <command>
  kit <folder>   write the kit the taggers worked in: every rollout as they read it, the shards, the protocol, add.py
                 and status.py. Nothing is sent anywhere.
  check          check every published record (results/tags/records/) against its rollout, as add.py did
  merge          results/tags/tags.jsonl, one record per rollout from its first tagging, and tags_second.jsonl, the
                 second tagging of the overlap rollouts, each with the rollout's run_id, setup, question and answer
"""

import csv
import json
import shutil
import sys
from pathlib import Path

from ballot.analysis.load import load_results
from ballot.analysis.trajectories import steps_of
from ballot.meta import propositions, questions
from ballot.paths import RESULTS
from ballot.tagging import add

TAGS = RESULTS / "tags"
HERE = Path(__file__).resolve().parent
LABEL = {"message": "message", "reasoning": "reasoning (the model's recorded thinking)", "tool_call": "research step"}
SEARCH_TOOLS = {"WebSearch", "web_search", "google_web_search", "search_tool"}
OPEN_TOOLS = {"WebFetch", "web_fetch", "open_page", "fetch"}
FIND_TOOLS = {"find_in_page"}
SHELL_TOOLS = {"run_shell_command", "Bash"}


def call_text(tool: str, args: dict) -> str:
    """A research step as one short line, with the same labels in every harness, so no label gives a harness away."""
    def s(key: str) -> str:
        value = args.get(key)
        return value.strip() if isinstance(value, str) else ""

    domains = [str(d) for d in args.get("allowed_domains") or [] if d] if isinstance(args.get("allowed_domains"), list) else []
    if tool in SEARCH_TOOLS:
        line = "Search: " + s("query")
        if domains:
            line += " (sites: " + ", ".join(domains) + ")"
        if s("url"):
            line += " " + s("url")
        return line
    if tool in OPEN_TOOLS:
        if s("url"):
            return "Open: " + s("url") + ("\n" + s("prompt") if s("prompt") else "")
        return "Open: " + s("prompt")  # Gemini CLI's page reader takes its URL inside the prompt
    if tool in FIND_TOOLS:
        return "Find in page: " + s("pattern") + (f" ({s('url')})" if s("url") else "")
    if tool in SHELL_TOOLS:
        return "Command: " + s("command") + ("\n" + s("description") if s("description") else "")
    values = [v.strip() for v in args.values() if isinstance(v, str) and v.strip()]
    values += [", ".join(map(str, v)) for v in args.values() if isinstance(v, list) and v]
    return f"Tool {tool}: " + " ".join(values) if values else f"Tool {tool}"


def pieces_of(result: dict) -> list[tuple[str, str]]:
    """The agent's own text, in order: its messages, its recorded reasoning and its research steps (not what came back)."""
    out = []
    for step in steps_of(RESULTS / result["path"] / "trajectory.jsonl", result["harness"]):
        if step.kind in ("message", "reasoning") and step.text.strip():
            out.append((step.kind, step.text.strip()))
        elif step.kind == "tool_call":
            out.append(("tool_call", call_text(step.tool, step.args or {})))
    return out


def render(rid: str, result: dict) -> tuple[str, str, str]:
    """One rollout as the taggers read it (the .md file), its whole agent text, and its messages and reasoning only."""
    pieces = pieces_of(result)
    last_call = max((i for i, (k, _) in enumerate(pieces) if k == "tool_call"), default=-1)
    final_start = next((i for i, (k, _) in enumerate(pieces) if k == "message" and i > last_call), None)
    prop, q = propositions()[str(result["prop"])], result["prompt"]
    page = f"https://voterguide.sos.ca.gov/propositions/{result['prop']}/"
    lines = [
        f"# Rollout {rid}",
        "",
        f"- **Proposition:** {result['prop']}, {prop['title'].strip()} ({prop['short']})",
        f"- **Official voter guide page:** {page}",
        f"- **Question type:** `{q}`",
        f"- **The prompt the agent got:** \"Do extensive research before you answer. {questions()[q]} {page}\"",
        f"- **Pieces of agent text below:** {len(pieces)}" + ("" if pieces else " (the agent wrote nothing)"),
        "",
        "Everything between the BEGIN and END lines is the agent's own text, in order. Each piece is introduced",
        "by a line like `[3 · message]` that is NOT part of the agent's text: never quote those lines.",
        "",
        "===== BEGIN AGENT TEXT =====",
    ]
    for i, (kind, text) in enumerate(pieces):
        if i == final_start:
            lines += ["", "----- FINAL REPLY (every message after the last research step) -----"]
        lines += ["", f"[{i + 1} · {LABEL[kind]}]", text]
    if final_start is None and pieces:
        lines += ["", "----- (no message after the last research step: the agent's final reply is empty) -----"]
    lines += ["", "===== END AGENT TEXT =====", ""]
    full = "\n\n".join(t for _, t in pieces)
    prose = "\n\n".join(t for k, t in pieces if k != "tool_call")
    return "\n".join(lines), full, prose


def key() -> list[dict]:
    with open(TAGS / "key.csv", newline="") as f:
        return list(csv.DictReader(f))


def by_run_id() -> dict[str, dict]:
    return {r["run_id"]: r for r in load_results(RESULTS)}


def records() -> list[dict]:
    rows = []
    for path in sorted((TAGS / "records").glob("shard-*.jsonl")):
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return rows


def kit(folder: Path) -> None:
    results, rows = by_run_id(), key()
    (folder / "rollouts").mkdir(parents=True, exist_ok=True)
    for row in rows:
        md, full, prose = render(row["id"], results[row["run_id"]])
        (folder / "rollouts" / f"{row['id']}.md").write_text(md, encoding="utf-8")
        (folder / "rollouts" / f"{row['id']}.txt").write_text(full, encoding="utf-8")
        (folder / "rollouts" / f"{row['id']}.prose.txt").write_text(prose, encoding="utf-8")
    shutil.copytree(TAGS / "shards", folder / "shards", dirs_exist_ok=True)
    shutil.copy(TAGS / "PROTOCOL.md", folder / "PROTOCOL.md")
    for name in ("add.py", "status.py"):
        shutil.copy(HERE / name, folder / name)
    print(f"Wrote the kit for {len(rows)} rollouts and {len(list((TAGS / 'shards').glob('*.txt')))} shards to {folder}.")


def check() -> None:
    results, ids = by_run_id(), {r["id"]: r for r in key()}
    problems, rows = 0, records()
    texts = {}
    for rec in rows:
        rid = rec["id"]
        if rid not in texts:
            _, full, prose = render(rid, results[ids[rid]["run_id"]])
            texts[rid] = (full, prose)
        errors = add.check({k: rec[k] for k in add.FIELDS if k in rec}, rid, rec["question"], *texts[rid])
        if errors:
            problems += 1
            print(f"{rid} (shard {rec['shard']}): " + "; ".join(errors))
    print(f"{len(rows)} records, {problems} with problems.")
    if problems:
        sys.exit(1)


def merge() -> None:
    ids = {r["id"]: r for r in key()}
    first, second = [], []
    for rec in records():
        row = ids[rec["id"]]
        shard = int(rec["shard"])
        out = {"run_id": row["run_id"], "model": row["model"], "harness": row["harness"], "question": row["question"],
               "prop": row["prop"], "outcome": row["outcome"], **rec}
        if shard == int(row["primary_shard"]):
            first.append(out)
        elif row["second_shard"] and shard == int(row["second_shard"]):
            second.append(out)
        else:
            sys.exit(f"{rec['id']} is in shard {shard}, which the key doesn't give it")
    missing = set(ids) - {r["id"] for r in first}
    if missing:
        sys.exit(f"{len(missing)} rollouts have no first tagging yet, such as {sorted(missing)[:5]}")
    for name, rows in (("tags.jsonl", first), ("tags_second.jsonl", second)):
        with open(TAGS / name, "w", encoding="utf-8") as f:
            for r in sorted(rows, key=lambda r: r["run_id"]):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {TAGS / name} ({len(rows)} records)")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["kit"] and len(args) == 2:
        kit(Path(args[1]))
    elif args == ["check"]:
        check()
    elif args == ["merge"]:
        merge()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
