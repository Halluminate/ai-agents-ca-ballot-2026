"""Indexes of the trajectories, and the pages each rollout opened.

Every rollout's trajectory is the harness's own event log, exactly as it was saved (with any piece of
a key, this machine's addresses and private paths replaced): trajectory.jsonl, one JSON event per line.
This module writes the indexes that link straight to those files:

  results/README.md                    every answer, each linked to its trajectory
  results/rollouts/README.md           where every trajectory is, and each setup's folder
  results/rollouts/<setup>/README.md   that setup's 42 rollouts, with their research and cost

Every harness writes its own event format, so each is first turned into the same list of steps
(the model's messages and reasoning, its tool calls and what they returned). Those steps give
visits.csv: every page each rollout opened, with where in the run it happened.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ballot.harnesses import FETCH_TOOLS, iter_events
from ballot.meta import HARNESSES, model_name, models, propositions, questions, setup_name
from ballot.analysis.sites import domain

URL = re.compile(r"https?://[^\s\"'<>\\)\]]+")
OPEN_TOOLS = FETCH_TOOLS | {"open_page"}
SETUP_ORDER = ("claude_code", "codex", "gemini_cli", "grok_build", "pi")


@dataclass
class Step:
    kind: str  # "system", "reasoning", "message", "tool_call", "tool_result" or "note"
    text: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    call_id: str = ""
    error: bool = False


def text_of(content) -> str:
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def messages_stream_steps(path: Path) -> list[Step]:
    """Claude Code's stream-json; Grok Build writes the same format."""
    steps, names = [], {}
    for event in iter_events(path):
        message = event.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            kind = block.get("type")
            if event.get("type") == "assistant":
                if kind == "text" and block.get("text", "").strip():
                    steps.append(Step("message", block["text"]))
                elif kind == "thinking" and block.get("thinking", "").strip():
                    steps.append(Step("reasoning", block["thinking"]))
                elif kind in ("tool_use", "server_tool_use"):
                    names[block.get("id", "")] = block.get("name", "")
                    steps.append(Step("tool_call", tool=block.get("name", ""), args=block.get("input") or {},
                                      call_id=block.get("id", "")))
                elif kind == "web_search_tool_result":
                    steps.append(Step("tool_result", text_of(block.get("content")), tool="web_search",
                                      call_id=block.get("tool_use_id", "")))
            elif event.get("type") == "user" and kind == "tool_result":
                call = block.get("tool_use_id", "")
                steps.append(Step("tool_result", text_of(block.get("content")), tool=names.get(call, ""), call_id=call,
                                  error=bool(block.get("is_error"))))
    return steps


def codex_steps(path: Path) -> list[Step]:
    steps, seen = [], set()
    for event in iter_events(path):
        item = event.get("item") or {}
        if event.get("type") in ("turn.failed", "error"):
            steps.append(Step("note", str((event.get("error") or {}).get("message") or event.get("message") or event["type"])))
        if event.get("type") != "item.completed" or item.get("id") in seen:
            continue
        seen.add(item.get("id"))
        if item.get("type") == "agent_message" and item.get("text", "").strip():
            steps.append(Step("message", item["text"]))
        elif item.get("type") == "reasoning" and (item.get("text") or "").strip():
            steps.append(Step("reasoning", item["text"]))
        elif item.get("type") == "web_search":
            # One web tool, three actions. An "other" action with no query is a call that never ran.
            action = item.get("action") or {}
            query = item.get("query") or action.get("query") or ""
            if action.get("type") == "open_page" and action.get("url"):
                steps.append(Step("tool_call", tool="open_page", args={"url": action["url"]}))
            elif action.get("type") == "find_in_page":
                steps.append(Step("tool_call", tool="find_in_page", args={"pattern": action.get("pattern", ""),
                                                                           "url": action.get("url", "")}))
            elif query:
                steps.append(Step("tool_call", tool="web_search", args={"query": query}))
    return steps


def gemini_steps(path: Path) -> list[Step]:
    steps, names = [], {}
    for event in iter_events(path):
        kind = event.get("type")
        if kind == "message" and event.get("role") == "assistant":
            if steps and steps[-1].kind == "message":
                steps[-1].text += event.get("content", "")
            else:
                steps.append(Step("message", event.get("content", "")))
        elif kind == "tool_use":
            names[event.get("tool_id", "")] = event.get("tool_name", "")
            steps.append(Step("tool_call", tool=event.get("tool_name", ""), args=event.get("parameters") or {},
                              call_id=event.get("tool_id", "")))
        elif kind == "tool_result":
            call = event.get("tool_id", "")
            steps.append(Step("tool_result", str(event.get("output") or event.get("error") or ""), tool=names.get(call, ""),
                              call_id=call, error=event.get("status") != "success"))
        elif kind == "error":
            steps.append(Step("note", str(event.get("message") or event.get("error") or "error")))
    return [s for s in steps if s.kind != "message" or s.text.strip()]


def pi_steps(path: Path) -> list[Step]:
    steps = []
    for event in iter_events(path):
        if event.get("type") == "auto_retry_start":
            steps.append(Step("note", f"{event.get('errorMessage') or 'Error'} Pi retried "
                                      f"(attempt {event.get('attempt')} of {event.get('maxAttempts')})."))
        if event.get("type") != "message_end":
            continue
        message = event.get("message") or {}
        role = message.get("role")
        if role == "system":
            sections = message.get("sections") or {}
            steps.append(Step("system", "\n\n".join(str(v) for v in sections.values()) or text_of(message.get("content"))))
        elif role == "assistant":
            for block in message.get("content") or []:
                if block.get("type") == "thinking" and block.get("thinking", "").strip():
                    steps.append(Step("reasoning", block["thinking"]))
                elif block.get("type") == "text" and block.get("text", "").strip():
                    steps.append(Step("message", block["text"]))
                elif block.get("type") == "toolCall":
                    steps.append(Step("tool_call", tool=block.get("name", ""), args=block.get("arguments") or {},
                                      call_id=block.get("id", "")))
            if message.get("stopReason") in ("error", "aborted", "length"):
                steps.append(Step("note", f"The model's turn ended with {message.get('stopReason')}: "
                                          f"{message.get('errorMessage') or ''}".strip()))
        elif role == "toolResult":
            steps.append(Step("tool_result", text_of(message.get("content")), tool=message.get("toolName", ""),
                              call_id=message.get("toolCallId", ""), error=bool(message.get("isError"))))
    return steps


PARSERS = {"claude_code": messages_stream_steps, "grok_build": messages_stream_steps, "codex": codex_steps,
           "codex_openrouter": codex_steps, "gemini_cli": gemini_steps, "pi": pi_steps}


def steps_of(events: Path, harness: str) -> list[Step]:
    return PARSERS[harness](events) if events.exists() else []


def opened_urls(step: Step) -> list[str]:
    """The pages a tool call opened. Gemini CLI's page reader takes its URLs inside a prompt."""
    if step.kind != "tool_call" or step.tool not in OPEN_TOOLS:
        return []
    return list(dict.fromkeys(u.rstrip(".,;") for u in URL.findall(json.dumps(step.args))))


def setup_key(r: dict) -> tuple:
    order = list(models())
    return (order.index(r["model"]) if r["model"] in order else 99, SETUP_ORDER.index(r["harness"])
            if r["harness"] in SETUP_ORDER else 9)


CELL = {"answered": None, "no_answer": "D", "excluded": "X", "timeout": "T"}


def grid(results: list[dict], question: str, link_prefix: str) -> str:
    props = list(propositions())
    setups = sorted({(r["model"], r["harness"]) for r in results}, key=lambda s: setup_key({"model": s[0], "harness": s[1]}))
    by_key = {(r["model"], r["harness"], r["prompt"], str(r["prop"])): r for r in results}
    lines = ["| setup | " + " | ".join(props) + " |", "|---|" + "---|" * len(props)]
    for model, harness in setups:
        cells = []
        for prop in props:
            r = by_key.get((model, harness, question, prop))
            if r is None:
                cells.append("-")
                continue
            letter = (r["answer"] or "")[:1] if r["status"] == "answered" else CELL.get(r["status"], "?")
            cells.append(f"[{letter}]({link_prefix}{r['path']}/trajectory.jsonl)")
        lines.append(f"| {setup_name(model, harness)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def setup_page(group: list[dict]) -> str:
    r0 = group[0]
    info = models().get(r0["model"], {})
    statuses = {s: sum(1 for r in group if r["status"] == s) for s in ("answered", "no_answer", "excluded", "timeout")}
    rows = ["| question | prop | what it does | answer | searches | pages | minutes | cost |", "|---|---|---|---|---|---|---|---|"]
    order = list(questions())
    for r in sorted(group, key=lambda r: (order.index(r["prompt"]), list(propositions()).index(str(r["prop"])))):
        leaf = r["path"].split("/")[-1]
        answer = r["answer"] if r["status"] == "answered" else {"no_answer": "declined"}.get(r["status"], r["status"])
        cost = f"${r['billed_usd']:.2f}" if r.get("billed_usd") is not None else "n/a"
        rows.append(f"| {r['prompt']} | {r['prop']} | {propositions()[str(r['prop'])].get('short', '')} | [{answer}]({leaf}/trajectory.jsonl) | "
                    f"{len(r['searches'])} | {len(r['fetches'])} | {r['seconds'] / 60:.1f} | {cost} |")
    return "\n\n".join([
        f"# {setup_name(r0['model'], r0['harness'])}",
        f"**Model:** {model_name(r0['model'])} (`{r0['model_id']}`, {info.get('vendor', '')}; "
        f"open weights: {info.get('open_weights', 'n/a')})  \n**Harness:** {HARNESSES.get(r0['harness'], r0['harness'])}  \n"
        f"**Effort:** {r0['effort']}  \n**Rollouts:** {len(group)}: {statuses['answered']} answered, {statuses['no_answer']} declined"
        + (f", {statuses['excluded']} excluded" if statuses["excluded"] else "")
        + (f", {statuses['timeout']} timed out" if statuses["timeout"] else ""),
        "[Every setup](../README.md) · [Every answer in three grids](../../README.md)",
        "\n".join(rows),
    ]) + "\n"


def index_page(results: list[dict]) -> str:
    parts = [
        "# Every rollout",
        f"{len(results):,} rollouts: {len({(r['model'], r['harness']) for r in results})} setups (model × harness) × "
        f"{len(questions())} questions × {len(propositions())} propositions. Each cell opens that rollout's trajectory exactly as "
        "the harness saved it (trajectory.jsonl, one JSON event per line): the prompt, every search and page the model opened "
        "with what came back, its reasoning where the harness records it, and its final reply. Next to it in the same "
        "folder: result.json (the scored answer) and search_results.json (what its searches returned); everything else "
        "the run saved is in the folder's other/ subfolder.",
        "**Y** = answered yes, **N** = answered no, **D** = declined (gave no plain yes or no), **X** = excluded (answered "
        "about an older measure with the same number; see [OLD_MEASURE_CHECK.md](OLD_MEASURE_CHECK.md)), **T** = timed out.",
        "[rollouts/](rollouts/) explains how the folders are named, and each setup's folder lists its rollouts with their "
        "research and cost.",
    ]
    for question, wording in questions().items():
        parts.append(f"## `{question}`: \"{wording.split('?')[0]}?\"\n\n" + grid(results, question, ""))
    prop_rows = ["| prop | title | what it does |", "|---|---|---|"]
    prop_rows += [f"| {p['prop']} | {p['title']} | {p.get('short', '')} |" for p in propositions().values()]
    parts.append("## The propositions\n\n" + "\n".join(prop_rows))
    return "\n\n".join(parts) + "\n"


def rollouts_page(results: list[dict]) -> str:
    """The landing page of results/rollouts/: how a rollout's folder is named, an example, and every setup's folder."""
    groups = {}
    for r in results:
        groups.setdefault(r["path"].split("/")[1], []).append(r)
    rows = ["| setup | folder | yes | no | declined | excluded or timed out |", "|---|---|---|---|---|---|"]
    for folder, group in sorted(groups.items(), key=lambda kv: setup_key(kv[1][0])):
        r0 = group[0]
        n = lambda status, answer=None: sum(1 for r in group if r["status"] == status and (answer is None or r["answer"] == answer))
        rows.append(f"| {setup_name(r0['model'], r0['harness'])} | [{folder}/]({folder}/) | {n('answered', 'YES')} | "
                    f"{n('answered', 'NO')} | {n('no_answer')} | {n('excluded') + n('timeout')} |")
    example = next(r for r in results if r["model"] == "claude" and r["harness"] == "pi" and r["prompt"] == "vote" and str(r["prop"]) == "40")
    leaf = "/".join(example["path"].split("/")[1:])
    return "\n\n".join([
        "# Every trajectory",
        f"One folder per rollout, `<setup>/<question>__prop-<NN>/`, {len(results):,} in all. In each is the rollout's trajectory "
        "exactly as the harness saved it: `trajectory.jsonl`, one JSON event per line, with the prompt, every search and page "
        "the agent opened and what came back, its reasoning where the harness records it, and its final reply.",
        "**To open any run,** pick its setup below, then its question (`vote`, `better` or `win`) and proposition. For "
        f"example, {setup_name(example['model'], example['harness'])} asked how to vote on Prop 40 is "
        f"[{leaf}/trajectory.jsonl]({leaf}/trajectory.jsonl). [Every answer in three grids](../README.md) links each one "
        "directly, and [runs.csv](../runs.csv) lists them all, one row per rollout with its `path`.",
        "Each rollout's folder has three files: `trajectory.jsonl`, `result.json` (the scored answer, with its searches, "
        "pages read, time and cost) and `search_results.json` (every result its searches returned). Everything else the "
        "run saved is in its `other/` subfolder: `prompt.txt` (the prompt it got), `final.txt` (its final reply), "
        "`billed.json` (what OpenRouter charged), `network_summary.json` (its requests by host) and `stderr.log`. An "
        "attempt that failed before the rollout started over is kept there too, as `failed-<N>.trajectory.jsonl`. GitHub "
        "shows files of up to a few megabytes on the page; for larger ones, its Raw button opens the whole file.",
        "\n".join(rows),
    ]) + "\n"


def write_all(results_dir: Path, results: list[dict]) -> list[dict]:
    """Every setup index and the grid; returns one row per opened page for visits.csv."""
    visits, groups = [], {}
    for r in results:
        steps = steps_of(results_dir / r["path"] / "trajectory.jsonl", r["harness"])
        groups.setdefault(r["path"].split("/")[1], []).append(r)
        calls = [s for s in steps if s.kind == "tool_call"]
        for i, step in enumerate(calls):
            for url in opened_urls(step):
                visits.append({"run_id": r["run_id"], "path": r["path"], "model": r["model"], "harness": r["harness"],
                               "question": r["prompt"], "prop": r["prop"], "status": r["status"], "answer": r["answer"] or "",
                               "step": i + 1, "tool_calls": len(calls), "position": round((i + 0.5) / len(calls), 4),
                               "url": url, "domain": domain(url)})
    for setup, group in groups.items():
        (results_dir / "rollouts" / setup / "README.md").write_text(setup_page(group))
    (results_dir / "README.md").write_text(index_page(results))
    (results_dir / "rollouts" / "README.md").write_text(rollouts_page(results))
    with open(results_dir / "visits.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(visits[0]) if visits else ["run_id"])
        writer.writeheader()
        writer.writerows(visits)
    return visits
