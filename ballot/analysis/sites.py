"""Where each model searched: the sites in its search results, the pages it opened and its queries.

Writes search_summary.md into the folder: python3 -m ballot analyze does it for results/.
"""

import base64
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from ballot.harnesses import SEARCH_TOOLS, iter_events
from ballot.meta import setup_name

URL = re.compile(r"https?://[^\s\"'<>\\)\]]+")
# Old voter guides reuse proposition numbers: 2024 also had Props 2 to 6 and 32 to 36.
OLD_ELECTION = re.compile(r"vigarchive\.sos\.ca\.gov|/(?:2016|2018|2020|2022|2024)/|year=(?:2016|2018|2020|2022|2024)\b")


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def text_of(content) -> str:
    if isinstance(content, list):
        return " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content or "")


def events_file(run_dir: Path) -> Path | None:
    """The run's event log: events.jsonl in a raw run folder, trajectory.jsonl in the published results."""
    return next((p for p in (run_dir / "events.jsonl", run_dir / "trajectory.jsonl") if p.exists()), None)


def result_urls(run_dir: Path, harness: str) -> list[str]:
    """URLs that came back in this run's search results, whichever harness ran it.

    The published results keep these in search_results.json, because for Codex they can
    only be read from the full network log, which is in the logs release instead.
    """
    saved = run_dir / "search_results.json"
    if saved.exists():
        return json.loads(saved.read_text())
    urls: list[str] = []
    events = events_file(run_dir)
    if events is None:
        return urls
    if harness == "pi":
        searches: set[str] = set()
        for event in iter_events(events):
            if event.get("type") == "tool_execution_start" and event.get("toolName") == "web_search":
                searches.add(event.get("toolCallId", ""))
            elif event.get("type") == "tool_execution_end" and event.get("toolCallId") in searches:
                urls += URL.findall(text_of((event.get("result") or {}).get("content")))
    elif harness in ("claude_code", "grok_build"):
        search_ids: set[str] = set()
        for event in iter_events(events):
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") in ("tool_use", "server_tool_use") and block.get("name") in SEARCH_TOOLS:
                    search_ids.add(block.get("id", ""))
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in search_ids:
                    details = event.get("tool_use_result")
                    urls += URL.findall(json.dumps(details) if details else text_of(block.get("content")))
    elif harness in ("codex", "codex_openrouter"):
        # Codex's events don't carry search results, but its recorded responses do: on the OpenAI
        # key its web tool calls /v1/alpha/search, and on OpenRouter search results come back in /responses.
        for record in network_records(run_dir):
            if any(path in (record.get("request") or {}).get("url", "") for path in ("/v1/alpha/search", "/responses")):
                body = (record.get("response") or {}).get("body") or ""
                urls += [u for u in URL.findall(body) if not domain(u).endswith(VENDOR_HOSTS)]
    elif harness == "gemini_cli":
        # Gemini CLI's search helper answers with grounding sources, each titled with its site's domain.
        for record in network_records(run_dir):
            request = record.get("request") or {}
            if "generativelanguage.googleapis.com" in request.get("url", "") and '"googleSearch"' in request_body(request):
                for chunk in grounding_chunks((record.get("response") or {}).get("body") or ""):
                    title = str((chunk.get("web") or {}).get("title") or "").lower()
                    if DOMAIN.fullmatch(title):
                        urls.append(f"https://{title}/")
    return list(dict.fromkeys(u.rstrip(".,;") for u in urls))


VENDOR_HOSTS = ("openai.com", "chatgpt.com", "openrouter.ai")
DOMAIN = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}")


def network_records(run_dir: Path):
    """The HTTP records of the attempt that produced the run's result, from a raw run folder's full network log."""
    log = run_dir / "network.jsonl.gz"
    for line in gzip.decompress(log.read_bytes()).splitlines() if log.exists() else []:
        record = json.loads(line)
        if record.get("type") == "http":
            yield record


def request_body(request: dict) -> str:
    body = request.get("body") or ""
    return base64.b64decode(body).decode("utf-8", "replace") if request.get("body_base64") else body


def grounding_chunks(body: str) -> list[dict]:
    """Every groundingChunks entry in a Gemini response, plain JSON or streamed as server-sent events."""
    found: list[dict] = []

    def walk(value) -> None:
        if isinstance(value, dict):
            found.extend(c for c in value.get("groundingChunks") or [] if isinstance(c, dict))
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for part in [body] + [line[5:] for line in body.splitlines() if line.startswith("data:")]:
        try:
            walk(json.loads(part))
        except ValueError:
            continue
    return found


def top(counts: Counter, n: int) -> list[tuple[str, int]]:
    """The n most common, ties in name order, so the summary comes out the same every time."""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:n]


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def write_summary(folder: Path, results: list[dict]) -> None:
    """search_summary.md for the finished rollouts in `results` (as load_results returns them)."""
    runs = []
    for r in results:
        if r["status"] in ("answered", "no_answer", "excluded"):
            r["result_urls"] = result_urls(folder / r["path"], r["harness"])
            runs.append(r)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        groups[(r["model"], r["harness"])].append(r)

    overview, top_rows, query_parts = [], [], []
    for (model, harness), group in groups.items():
        n = len(group)
        seen = Counter(d for r in group for d in {domain(u) for u in r["result_urls"] + r["fetches"]})
        opened = Counter(d for r in group for d in {domain(u) for u in r["fetches"]})
        official = sum(1 for r in group if any("voterguide.sos.ca.gov" in u for u in r["fetches"]))
        lao = sum(1 for r in group if any("lao.ca.gov" in domain(u) for u in r["result_urls"] + r["fetches"]))
        old = sum(1 for r in group if any(OLD_ELECTION.search(u) for u in r["result_urls"] + r["fetches"]))
        searches = [len(r["searches"]) for r in group]
        overview.append([setup_name(model, harness), n, f"{sum(searches) / n:.1f}", sum(1 for s in searches if not s),
                         f"{sum(len(r['fetches']) for r in group) / n:.1f}", len(seen),
                         f"{100 * official / n:.0f}%", f"{100 * lao / n:.0f}%", f"{100 * old / n:.0f}%"])
        top_rows.append([setup_name(model, harness), ", ".join(f"{d} ({c})" for d, c in top(seen, 10)),
                         ", ".join(f"{d} ({c})" for d, c in top(opened, 6)) or "not reported"])
        examples = [r["searches"][0] for r in sorted(group, key=lambda r: (r["prompt"], int(r["prop"]))) if r["searches"]][:4]
        query_parts.append(f"- **{setup_name(model, harness)}**: " + "; ".join(f"`{q[:110]}`" for q in examples))

    every = Counter(d for r in runs for d in {domain(u) for u in r["result_urls"] + r["fetches"]})
    sections = [
        f"# Where the models searched\n\n{len(runs)} finished rollouts. Timeouts are left out.",
        "## Overview\n\n" + table(
            ["setup", "rollouts", "searches per rollout", "rollouts with no search", "pages opened per rollout",
             "sites seen", "read the official guide", "saw LAO", "saw an older election"], overview),
        "\"Sites seen\" counts every site in search results or opened pages. \"Read the official guide\" means the rollout "
        "opened a voterguide.sos.ca.gov page. \"Saw an older election\" means a result or page came from a past voter "
        "guide, such as 2024's, which reused Props 2 to 5. Codex, Gemini CLI and Grok Build search on their providers' "
        "servers, so the sites in their search results are the ones those servers sent back. For Gemini CLI they are the "
        "sources its search helper cited.",
        "## Top sites per setup\n\nEach number is how many rollouts saw that site.\n\n"
        + table(["setup", "sites in results or pages", "pages opened"], top_rows),
        "## Most-seen sites overall\n\n" + table(["site", "rollouts"], [[d, c] for d, c in top(every, 25)]),
        "## Example first queries\n\n" + "\n".join(query_parts),
    ]
    (folder / "search_summary.md").write_text("\n\n".join(sections) + "\n")
