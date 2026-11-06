"""Old-measure screen: did a rollout answer about an older proposition with the same number?

California reuses proposition numbers, and search engines happily return 2024's Prop 4 or
2012's Prop 37. This screen flags rollouts to read; the 11 exclusions in data/excluded.json
were decided by reading what it flagged (OLD_MEASURE_CHECK.md has the details).

Only what the model wrote is scanned: its messages, reasoning, tool arguments and final
reply, never search results or pages, since a search for "California Prop 37" returns
2012's measure whatever the model thinks. For each rollout it records:
- category: where mentions of an older measure fall relative to the first time the model
  named the 2026 one (clean, weak only, old before 2026 only, old at or after 2026, never
  named 2026, no topic words);
- end_new: whether the closing reasoning (last 3 text or reasoning segments, plus the final
  reply) names the 2026 measure in strict terms;
- opened_official and first_query_old: whether it opened the 2026 page we linked, and
  whether its first search was for an older year or measure.
Writes old_measure_screen.csv.
"""

import csv
import json
import re
from pathlib import Path

from ballot.analysis.load import rollout_file
from ballot.harnesses import iter_events

# Older measures with the same number: Mar 2024 Prop 1 ($6.38B behavioral health bond), Nov 2022 Prop 1
# (abortion), 2018 Prop 1 ($4B housing bond); Nov 2024 Props 2 ($10B school bond), 3 (marriage), 4 ($10B
# climate bond), 5 (55% local bonds); 2018 Props 2 to 5. 2012: 37 GMO labeling, 38 Munger school tax,
# 39 multistate business tax, 40 Senate redistricting referendum. 2014: 41 veterans housing bond, 42 public
# records, 45 health insurance rates. 2000-2002: 37 fees as taxes, 38 school vouchers, 39 55% school bonds,
# 40 parks bond, 41 voting modernization, 42 gas sales tax, 43 right to have your vote counted,
# 44 chiropractors, 45 term limits. Terms the official 2026 pages use themselves are left out.
OLD = {
    "1": r"6\.38|behavioral[- ]health|\bMHSA\b|mental health services act|abortion|reproductive|\$4 billion|\b4 billion",
    "2": r"school (?:bond|facilit|construction|moderni[sz]|repair)|public education facilit|no place like home",
    "3": r"marriage|same[- ]sex|\bprop(?:osition)?\.? ?8\b|water bond",
    "4": r"climate (?:bond|resilien)|wildfire|drinking water|children'?s hospital",
    "5": r"\b55 ?%|55 percent|fifty-five percent|local (?:housing |infrastructure )?bonds?\b|property tax (?:base )?transfer|portability",
    "37": r"genetically engineered|\bGMOs?\b|genetically modified|label(?:ing|s)? (?:of )?(?:genetically|GMO|food)|regulatory fee",
    "38": r"munger|our children,? our future|school vouchers?|\bvouchers?\b",
    "39": r"multistate|single[- ]sales[- ]factor|clean energy|school (?:facilit|bond)",
    "40": r"redistricting|state senate (?:map|district)|parks? (?:and|&) water bond|safe neighborhood parks",
    "41": r"veterans? (?:housing|and homeless)|homeless prevention|\$600 million|voting modernization",
    "42": r"public records|brown act|open meetings|congestion|gas(?:oline)? (?:sales )?tax",
    "43": r"vote counted|water bond",
    "44": r"chiropract|rainy[- ]day",
    "45": r"insurance rate|insurance commissioner|health insurance|term limits",
}
WEAK_OLD = {"1": r"mental[- ]health"}  # the 2026 Prop 1 analysis cites 2024's mental-health bond itself
# The 2026 measures, from their official summaries.
NEW = {
    "1": r"11\.25|\bSB 417\b|housing affordab|act of 2026|down ?payment|multifamily|affordable housing|housing bond|homeownership",
    "2": r"rainy[- ]day|budget stabilization|reserve cap|\bACA 20\b|10 ?% to 20 ?%|20 ?% of (?:general fund|revenue)",
    "3": r"high[- ]income|high earners|top earners|income tax|\bprop(?:osition)?\.? ?(?:55|30)\b|permanent|\bextend",
    "4": r"public (?:financ|fund)|campaign (?:financ|fund)|matching funds|publicly fund|clean elections|\bSB 42\b",
    "5": r"\brecall|\bSCA 1\b",
    "37": r"qualified new home|17 ?%|25 billion|middle[- ]income|loan program|fixed[- ]rate mortgage|new[- ]home|home ?buyer|mortgage",
    "38": r"immunolog|immunotherap|8\.4 billion|medical research",
    "39": r"voter (?:ID|identification)|government[- ]issued|photo ID|identification number|last four digits",
    "40": r"one[- ]time tax|billionaire|wealth tax|covered assets|minimum asset tax",
    "41": r"spending limit|gann|appropriations limit|pre-election audit",
    "42": r"personal property tax|retroactiv|tax(?:es)? on (?:personal property|financial assets|business interests)",
    "43": r"special tax|two[- ]thirds|\bACA 22\b|voter[- ]proposed|citizens? initiative",
    "44": r"community (?:health )?clinic|\bFQHCs?\b|federally qualified|health cent(?:er|re)s?|program services",
    "45": r"\bCEQA\b|environmental (?:review|quality)",
}
# Stricter terms for the closing check on Props 1-5: no "recall" as in "let me recall", no generic "housing bond".
STRICT_NEW = {**NEW,
    "1": r"11\.25|\bSB 417\b|act of 2026|housing affordab",
    "2": r"rainy[- ]day|budget stabilization|\bBSA\b|\bACA 20\b|reserve cap|budget reserve",
    "3": r"high[- ]income|high earners|top earners|millionaire|income tax|\bprop(?:osition)?\.? ?(?:55|30)\b",
    "4": r"public (?:financ|fund)|campaign (?:financ|fund)|publicly fund|\bSB 42\b|matching funds|clean elections|fair elections",
    "5": r"recall (?:election|process|measure|rules|system|of\b|an? |the (?:governor|officer|official|election|process))"
         r"|recalled|recalls\b|\bSCA 1\b|lieutenant governor|replacement (?:question|candidate|election)",
}
# Years of older measures that reused these numbers, for "did the first search look for an older one?"
OLD_YEAR = {"low": re.compile(r"\b(?:2024|2022|2018|2014|2012|2002|2000)\b"),
            "high": re.compile(r"\b(?:2024|2014|2012|2002|2000)\b")}


def official_url(prop: str) -> str:
    return rf"voterguide\.sos\.ca\.gov/propositions/{prop}/|vig\.cdn\.sos\.ca\.gov/2026/general/pdf/prop{prop}[.-]"


def segments(folder: Path, harness: str) -> list[tuple[str, str]]:
    """What the model wrote, in order, as (kind, text): its text, thinking and tool arguments, then the final reply."""
    out: list[tuple[str, str]] = []
    for event in iter_events(folder / "trajectory.jsonl") if (folder / "trajectory.jsonl").exists() else []:
        kind = event.get("type")
        if harness in ("claude_code", "grok_build") and kind == "assistant":
            for b in (event.get("message") or {}).get("content") or []:
                if b.get("type") == "text":
                    out.append(("text", b.get("text", "")))
                elif b.get("type") == "thinking":
                    out.append(("thinking", b.get("thinking", "")))
                elif b.get("type") in ("tool_use", "server_tool_use"):
                    out.append(("tool", json.dumps(b.get("input") or {})))
        elif harness == "pi" and kind == "message_end" and (event.get("message") or {}).get("role") == "assistant":
            for b in event["message"].get("content") or []:
                if b.get("type") == "text":
                    out.append(("text", b.get("text", "")))
                elif b.get("type") == "thinking":
                    out.append(("thinking", b.get("thinking", "")))
                elif b.get("type") == "toolCall":
                    out.append(("tool", json.dumps(b.get("arguments") or {})))
        elif harness == "codex" and kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                out.append(("text", item.get("text", "")))
            elif item.get("type") == "reasoning":
                out.append(("thinking", item.get("text", "")))
            elif item.get("type") == "web_search":
                out.append(("tool", json.dumps({"query": item.get("query"), "action": item.get("action")})))
        elif harness == "gemini_cli":
            if kind == "message" and event.get("role") == "assistant":
                if out and out[-1][0] == "text":
                    out[-1] = ("text", out[-1][1] + event.get("content", ""))
                else:
                    out.append(("text", event.get("content", "")))
            elif kind == "tool_use":
                out.append(("tool", json.dumps(event.get("parameters") or {})))
    final_file = rollout_file(folder, "final.txt")
    final = final_file.read_text() if final_file.exists() else ""
    return [(k, t) for k, t in out if t and t.strip()] + ([("final", final)] if final.strip() else [])


def first(pattern: str, segs: list[tuple[str, str]]) -> int | None:
    return next((i for i, (_, t) in enumerate(segs) if re.search(pattern, t, re.I)), None)


def late_mentions(prop: str, segs: list[tuple[str, str]], first_new: int | None) -> int:
    """Mentions of an older measure in or after the segment where the model first named the 2026 one."""
    if first_new is None:
        return 0
    return sum(len(re.findall(OLD[prop], text, re.I)) for i, (_, text) in enumerate(segs) if i >= first_new)


def screen(folder: Path, r: dict) -> dict:
    """One rollout's screen. Two definitions of "named the 2026 measure" are kept, because both were used:
    broad terms decide the category and the late mentions, strict terms decide the closing check."""
    prop = str(r["prop"])
    segs = segments(folder, r["harness"])
    first_new, first_strict = first(NEW[prop], segs), first(STRICT_NEW[prop], segs)
    strong = sum(len(re.findall(OLD[prop], t, re.I)) for _, t in segs)
    weak = sum(len(re.findall(WEAK_OLD[prop], t, re.I)) for _, t in segs) if prop in WEAK_OLD else 0
    late = late_mentions(prop, segs, first_new)
    if first_new is None:
        category = "never named 2026" if strong or weak else "no topic words"
    elif not strong:
        category = "clean" if not weak else "weak only"
    elif not late:
        category = "old before 2026 only"
    else:
        category = "old at or after 2026"
    prose = [s for s in segs if s[0] in ("text", "thinking")]
    end = "\n".join(t for _, t in prose[-3:] + [s for s in segs if s[0] == "final"])
    queries = [str(q) for q in r["searches"]]
    years = OLD_YEAR["low" if int(prop) <= 5 else "high"]
    recorded = json.loads((folder / "result.json").read_text())["status"]
    return {
        "run_id": r["run_id"], "path": r["path"], "model": r["model"], "harness": r["harness"], "question": r["prompt"],
        "prop": prop, "status": r["status"], "recorded_status": recorded, "answer": r["answer"] or r.get("excluded_answer") or "",
        "category": category, "old_mentions": strong, "late_old_mentions": late,
        "late_old_mentions_strict": late_mentions(prop, segs, first_strict),
        "named_2026": first_new is not None, "named_2026_strict": first_strict is not None,
        "closing_names_2026": bool(re.search(STRICT_NEW[prop], end, re.I)), "closing_mentions_old": bool(re.search(OLD[prop], end, re.I)),
        "opened_official": any(re.search(official_url(prop), u) for u in r["fetches"]),
        "first_search_old": bool(queries) and bool((years.search(queries[0]) and "2026" not in queries[0])
                                                   or re.search(OLD[prop], queries[0], re.I)),
        "excluded": r["status"] == "excluded",
    }


def write(results_dir: Path, results: list[dict]) -> list[dict]:
    rows = [screen(results_dir / r["path"], r) for r in results]
    with open(results_dir / "old_measure_screen.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows
