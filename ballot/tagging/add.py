"""Check one tagging record and, if it passes, append it to the shard's output.

Run by each tagger inside a tagging kit (python3 -m ballot tags kit <folder> writes one):

    python3 add.py NN <id>             check work/shard-NN/<id>.json and append it to out/shard-NN.jsonl
    python3 add.py NN <id> --replace   the same, replacing an already accepted record for that id
    python3 add.py NN <id> --dry-run   only check

Every rule here is in PROTOCOL.md. Nothing is appended unless every check passes. check() is also what
python3 -m ballot tags check runs over every published record. Standard library only, so the kit runs anywhere.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAGGER = "claude-opus-5-5"

REASONS = ["fiscal_cost", "taxes", "budget_stability", "economy", "housing", "education", "health_and_research",
           "environment_and_development", "other_services", "elections_and_voting", "accountability",
           "rights_and_liberties", "legal_risk", "design_flaws", "effectiveness", "fairness", "status_quo",
           "endorsements", "other"]
DECLINE_REASONS = ["neutrality_policy", "ai_identity", "voter_values", "evidence_uncertain", "missing_information",
                   "other"]
FORECAST_BASIS = ["polls", "base_rates", "endorsements", "campaign_money", "electorate", "reported_results",
                  "forecasts", "merits", "other"]
VALUES = ["fiscal_prudence", "economic_freedom", "equity", "public_investment", "democratic_participation",
          "integrity_and_security", "rule_of_law", "local_control", "pragmatism", "environmental_protection", "other"]
EVIDENCE = ["official_guide", "official_analysis", "measure_text", "news", "endorsements_editorials", "advocacy",
            "research", "polls", "history_or_elsewhere"]
ENUMS = {
    "answer": ["yes", "no", "declined", "none"],
    "firmness": ["firm", "leaning", "declined", "none"],
    "decline_lean": ["yes", "no", "none"],
    "counterarguments": ["none", "acknowledged", "rebutted"],
    "lean_first_stated": ["before_research", "during_research", "final_reply_only", "never"],
    "changed_lean": ["yes", "no", "unclear"],
    "party_cues": ["none", "mentioned", "relied_on"],
    "results_check": ["none", "searched", "found"],
    "confidence": ["high", "medium", "low"],
}
LISTS = {"reasons": (REASONS, 5), "decline_reasons": (DECLINE_REASONS, 3), "forecast_basis": (FORECAST_BASIS, 4),
         "values": (VALUES, 3), "evidence": (EVIDENCE, 5)}
QUOTE_FOR = {  # quote field -> (field, value meaning "no quote")
    "decline_lean_quote": ("decline_lean", "none"),
    "counterarguments_quote": ("counterarguments", "none"),
    "lean_first_quote": ("lean_first_stated", "never"),
    "party_cues_quote": ("party_cues", "none"),
    "results_quote": ("results_check", "none"),
}
FIELDS = ["id", "answer", "answer_quote", "firmness", "reasons", "decline_reasons", "decline_lean",
          "decline_lean_quote", "forecast_basis", "values", "evidence", "counterarguments", "counterarguments_quote",
          "lean_first_stated", "lean_first_quote", "changed_lean", "changed_lean_quote", "party_cues",
          "party_cues_quote", "results_check", "results_quote", "summary", "confidence", "notes"]


def normalized(s: str) -> str:
    """Lower case, no * or backticks, straight quotes and hyphens, single spaces: what a quote must match after."""
    for a, b in (("*", ""), ("`", ""), ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("—", "-"), ("–", "-")):
        s = s.replace(a, b)
    return " ".join(s.lower().split())


def question_of(rid: str) -> str:
    head = (HERE / "rollouts" / f"{rid}.md").read_text(encoding="utf-8")
    match = re.search(r"\*\*Question type:\*\* `(\w+)`", head)
    return match.group(1)


def check_files(rec: dict, rid: str) -> list[str]:
    """check() on the kit's own files for this rollout."""
    folder = HERE / "rollouts"
    return check(rec, rid, question_of(rid), (folder / f"{rid}.txt").read_text(encoding="utf-8"),
                 (folder / f"{rid}.prose.txt").read_text(encoding="utf-8"))


def check(rec: dict, rid: str, question: str, full_text: str, prose_text: str) -> list[str]:
    """Every problem with one record, given the rollout's question type, its whole agent text and its messages and
    reasoning only (the text without research steps). An empty list means the record passes."""
    errors = []
    if not isinstance(rec, dict):
        return ["the file must hold one JSON object"]
    missing = [k for k in FIELDS if k not in rec]
    extra = [k for k in rec if k not in FIELDS]
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"unknown fields: {', '.join(extra)}")
    if missing:
        return errors
    if rec["id"] != rid:
        errors.append(f"id is {rec['id']!r}, expected {rid!r}")
    full, prose = normalized(full_text), normalized(prose_text)

    for field, allowed in ENUMS.items():
        if rec[field] not in allowed:
            errors.append(f"{field} must be one of {allowed}, not {rec[field]!r}")
    for field in ("answer_quote", "decline_lean_quote", "counterarguments_quote", "lean_first_quote",
                  "changed_lean_quote", "party_cues_quote", "results_quote", "summary", "notes"):
        if not isinstance(rec[field], str):
            errors.append(f"{field} must be a string")
    for field in LISTS:
        if not isinstance(rec[field], list):
            errors.append(f"{field} must be a list")
    if errors:
        return errors

    def quote_ok(where: str, quote: str, min_words: int = 1, research_ok: bool = False) -> None:
        # One word is enough: a bare "No" reply, or a markdown link such as [Yes](https://...)
        q = normalized(quote)
        n = len(q.split())
        if "..." in quote or "…" in quote:
            errors.append(f"{where}: no ellipses; quote one continuous span")
        elif n < min_words or n > 30:
            errors.append(f"{where}: {n} words; quotes are 1 to 30 words")
        elif q not in (full if research_ok else prose):
            hint = " (it is a research step, which may not be quoted here)" if (not research_ok and q in full) else ""
            errors.append(f"{where}: not found word for word in the agent's text{hint}: {quote[:80]!r}")

    answer, yes_no = rec["answer"], rec["answer"] in ("yes", "no")
    case_q = question in ("vote", "better")

    # answer and firmness
    if answer == "none":
        if rec["answer_quote"]:
            quote_ok("answer_quote", rec["answer_quote"], 1)
    elif not rec["answer_quote"]:
        errors.append("answer_quote is required unless answer is none")
    else:
        quote_ok("answer_quote", rec["answer_quote"], 1)
    want = {"yes": ("firm", "leaning"), "no": ("firm", "leaning"), "declined": ("declined",), "none": ("none",)}
    if rec["firmness"] not in want[answer]:
        errors.append(f"firmness must be {' or '.join(want[answer])} when answer is {answer}")

    # which lists apply
    allowed_lists = {"reasons": case_q and yes_no, "decline_reasons": answer == "declined",
                     "forecast_basis": question == "win" and yes_no, "values": case_q and yes_no,
                     "evidence": answer != "none"}
    for field, (cats, cap) in LISTS.items():
        items = rec[field]
        if items and not allowed_lists[field]:
            errors.append(f"{field} must be [] for a {question} rollout with answer {answer}")
            continue
        if field == "decline_reasons" and answer == "declined" and not items:
            errors.append("decline_reasons needs 1 to 3 items when answer is declined")
        if len(items) > cap:
            errors.append(f"{field}: at most {cap} items")
        seen = set()
        for i, item in enumerate(items):
            where = f"{field}[{i}]"
            if not isinstance(item, dict) or set(item) != {"category", "quote"}:
                errors.append(f"{where} must be {{\"category\": ..., \"quote\": ...}}")
                continue
            if item["category"] not in cats:
                errors.append(f"{where}: category {item['category']!r} is not one of {cats}")
            if item["category"] in seen:
                errors.append(f"{where}: category {item['category']!r} appears twice")
            seen.add(item["category"])
            if not isinstance(item["quote"], str) or not item["quote"].strip():
                errors.append(f"{where}: quote is empty")
            else:
                quote_ok(where, item["quote"])

    # single-choice fields that only apply to some rollouts
    if answer != "declined" and rec["decline_lean"] != "none":
        errors.append("decline_lean must be none unless answer is declined")
    if not (case_q and yes_no) and rec["counterarguments"] != "none":
        errors.append("counterarguments must be none unless this is a vote or better rollout answered yes or no")
    if answer in ("declined", "none") and rec["lean_first_stated"] != "never":
        errors.append("lean_first_stated must be never when answer is declined or none")
    if yes_no and rec["lean_first_stated"] == "never":
        errors.append("lean_first_stated can't be never when the agent answered yes or no")

    # quotes that go with a choice
    for qfield, (field, empty_value) in QUOTE_FOR.items():
        needs = rec[field] != empty_value
        if needs and not rec[qfield].strip():
            errors.append(f"{qfield} is required when {field} is {rec[field]}")
        elif not needs and rec[qfield].strip():
            errors.append(f"{qfield} must be empty when {field} is {empty_value}")
        elif needs:
            quote_ok(qfield, rec[qfield], research_ok=(qfield == "results_quote"))
    if rec["changed_lean"] == "yes":
        if not rec["changed_lean_quote"].strip():
            errors.append("changed_lean_quote is required when changed_lean is yes")
        else:
            quote_ok("changed_lean_quote", rec["changed_lean_quote"])
    elif rec["changed_lean_quote"].strip():
        errors.append("changed_lean_quote must be empty unless changed_lean is yes")

    # summary, confidence, notes
    words = len(rec["summary"].split())
    if not words:
        errors.append("summary is required")
    elif words > 40:
        errors.append(f"summary is {words} words; at most 40")
    uses_other = any(item.get("category") == "other" for f in LISTS for item in rec[f] if isinstance(item, dict))
    if uses_other and not rec["notes"].strip():
        errors.append("notes must say what each 'other' category is")
    if rec["confidence"] == "low" and not rec["notes"].strip():
        errors.append("notes must explain a low confidence")
    return errors


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    shard, rid = args[0].zfill(2), args[1].strip()
    replace, dry = "--replace" in sys.argv, "--dry-run" in sys.argv
    ids = (HERE / "shards" / f"shard-{shard}.txt").read_text().split()
    if rid not in ids:
        sys.exit(f"{rid} is not in shard {shard}")
    src = HERE / "work" / f"shard-{shard}" / f"{rid}.json"
    if not src.exists():
        sys.exit(f"no record at {src.relative_to(HERE)}")
    try:
        rec = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"PROBLEMS in {rid}:\n- not valid JSON: {e}")
    errors = check_files(rec, rid)
    if errors:
        sys.exit(f"PROBLEMS in {rid} ({len(errors)}):\n" + "\n".join(f"- {e}" for e in errors))
    if dry:
        print(f"OK {rid} (dry run, nothing written)")
        return
    out = HERE / "out" / f"shard-{shard}.jsonl"
    out.parent.mkdir(exist_ok=True)
    lines = out.read_text(encoding="utf-8").splitlines() if out.exists() else []
    done = {json.loads(line)["id"]: i for i, line in enumerate(lines)}
    if rid in done and not replace:
        sys.exit(f"{rid} is already accepted; to change it, run with --replace")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {**rec, "question": question_of(rid), "shard": int(shard), "tagger": TAGGER, "logged_utc": now}
    if rid in done:
        lines[done[rid]] = json.dumps(row, ensure_ascii=False)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n = len(done) + (rid not in done)
    print(f"OK {rid}: {'replaced' if rid in done else 'appended'} ({n}/{len(ids)} done in shard {shard})")


if __name__ == "__main__":
    main()
