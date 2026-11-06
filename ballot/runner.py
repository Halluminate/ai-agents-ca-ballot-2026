#!/usr/bin/env python3
"""Run the ballot experiment on the OpenRouter key, plus OpenAI's and Google's for Codex and Gemini CLI. See README.md."""

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import random
import re
import shutil
import signal
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from ballot.analysis.load import billed_cost
from ballot.config import (
    DIRECT_KEYS,
    FINAL_STATUSES,
    KEY,
    Spec,
    build_prompt,
    extract_answer,
    load_ballot,
    load_config,
    load_keys,
)
from ballot.harnesses import NATIVE, Pi, Room, base_env, estimate_cost
from ballot.paths import DATA, ROOT, RUNS

ACTIVE: set[int] = set()  # process groups to kill if the runner is interrupted
RETRY_BACKOFF_SECONDS = 30
RATE_LIMIT_BACKOFF_SECONDS = 180  # an upstream rate limit takes minutes, not seconds, to clear
RATE_LIMITED = re.compile(r"\b429\b|rate.?limit", re.I)
CAPTURE_NETWORK = True  # every run records all its traffic, see netlog.py
ARCHIVE_SKIP = ("home/.grok/bin",)  # Grok's unpacked binary, 130 MB per run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", help="a separate folder under runs/, such as for a test. Default: runs/ itself. Run the same command again to resume")
    parser.add_argument("--smoke", action="store_true", help="Proposition 1 and the first prompt only, to test the plumbing")
    parser.add_argument("--cheap", action="store_true", help="use each model's cheap stand-in at low effort")
    parser.add_argument("--models", help="comma-separated names from experiment.toml. name:native or name:common runs one harness of that model")
    parser.add_argument("--arms", help="native, common, or both. Default: both")
    parser.add_argument("--prompts", help="comma-separated prompt names from experiment.toml")
    parser.add_argument("--props", help="comma-separated proposition numbers. Default: all 14")
    parser.add_argument("--repeats", type=int, help="overrides repeats in experiment.toml")
    parser.add_argument("--retry-errors", action="store_true",
                        help="only the runs that already ended in an error. Safe beside a runner still going on the folder")
    parser.add_argument("--slow-first", action="store_true",
                        help="start the slowest model and harness pairs first, by their measured time, so they don't trail at the end")
    parser.add_argument("--first", help="pairs to run first, in this order, so they finish whole: model names, or name:native / name:common")
    parser.add_argument("--skip-running-in", help="another runner's log on this folder: leave it the runs it has started and not finished")
    parser.add_argument("--control", help="the file in the run folder that sets runs at once mid-run. Default: concurrency.txt")
    parser.add_argument("--concurrency", type=int, help="runs at once in total. Overrides experiment.toml")
    parser.add_argument("--per-model", type=int, help="runs at once for one model. Overrides experiment.toml")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    return parser.parse_args()


def pick(names: str | None, available: list[str], label: str) -> list[str]:
    if not names:
        return available
    chosen = names.split(",")
    unknown = sorted(set(chosen) - set(available))
    if unknown:
        sys.exit(f"Unknown {label}: {', '.join(unknown)}. Choose from: {', '.join(available)}")
    return chosen


def pick_models(names: str | None, cfg: dict, arms: list[str]) -> dict[str, list[str]]:
    """The arms to run for each chosen model. A name can carry one arm, as in grok:native."""
    available = [m["name"] for m in cfg["models"]]
    chosen: dict[str, list[str]] = {}
    for item in names.split(",") if names else available:
        name, _, arm = item.partition(":")
        pick(name, available, "models")
        wanted = pick(arm, ["native", "common"], "arms") if arm else arms
        chosen[name] = [a for a in ("native", "common") if a in wanted or a in chosen.get(name, [])]
    return chosen


def build_plan(args: argparse.Namespace, cfg: dict) -> list[Spec]:
    ballot = load_ballot()
    props = ["1"] if args.smoke and not args.props else pick(args.props, ballot, "propositions")
    all_prompts = list(cfg["prompts"])
    prompt_names = all_prompts[:1] if args.smoke and not args.prompts else pick(args.prompts, all_prompts, "prompts")
    arms = pick(args.arms, ["native", "common"], "arms")
    chosen = pick_models(args.models, cfg, arms)
    repeats = args.repeats or cfg["run"]["repeats"]

    plan = []
    for model in cfg["models"]:
        for arm in chosen.get(model["name"], []):
            if arm == "native" and not model["native"]:
                continue  # Kimi, DeepSeek, Qwen and GLM have no native harness here
            model_id = model["cheap_model"] if args.cheap else model["model"]
            if arm == "native":
                # A harness on a direct key takes the vendor's own model id.
                model_id = model.get("native_cheap_model" if args.cheap else "native_model") or model_id
            for prompt_name in prompt_names:
                for prop in props:
                    for repeat in range(1, repeats + 1):
                        effort = model["native_effort"] if arm == "native" else model["pi_thinking"]
                        plan.append(Spec(
                            model=model["name"],
                            model_id=model_id,
                            pin=model["pin"],
                            arm=arm,
                            harness=model["native"] if arm == "native" else "pi",
                            effort="low" if args.cheap else effort,
                            prompt_name=prompt_name,
                            prompt=build_prompt(cfg["templates"]["full"], cfg["prompts"][prompt_name], prop),
                            prop=prop,
                            repeat=repeat,
                            price=model["price"],
                            max_run_usd=cfg["run"]["max_run_usd"],
                            system_prompt=cfg["pi"]["system_prompt"],
                        ))
    # A shuffled order stops time drift from lining up with any one condition.
    random.Random(cfg["run"]["seed"]).shuffle(plan)
    return plan


def write_manifest(out: Path, plan: list[Spec], cfg: dict) -> None:
    """Record exactly what ran. Refuse to mix different prompts into one folder."""
    prompts = {f"{s.prompt_name}/p{s.prop}": hashlib.sha256(s.prompt.encode()).hexdigest() for s in plan}
    path = out / "manifest.json"
    if path.exists():
        old = json.loads(path.read_text())["prompt_sha256"]
        if any(old.get(name, digest) != digest for name, digest in prompts.items()):
            sys.exit(f"Prompts changed since {out.name} started. Use a new --name to keep results comparable.")
        prompts = {**old, **prompts}
    catalog = DATA / "codex_openrouter_catalog.json"
    openai_catalog = DATA / "codex_openai_catalog.json"
    path.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv[1:],
        "prompt_sha256": prompts,
        "search": cfg["search"],
        "harness_versions": json.loads((ROOT / "package.json").read_text())["dependencies"],
        "codex_catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "codex_openai_catalog_sha256": hashlib.sha256(openai_catalog.read_bytes()).hexdigest(),
        "config": {k: v for k, v in cfg.items() if k != "templates"},
        "templates": cfg["templates"],
    }, indent=2))


def kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # macOS refuses (EPERM) a group whose members have all exited but aren't reaped yet.
        pass


async def run_process(cmd: list[str], stdin: str | None, env: dict, room: Room, run_dir: Path, timeout: float) -> tuple[int | None, bool]:
    with open(run_dir / "events.jsonl", "wb") as stdout, open(run_dir / "stderr.log", "wb") as stderr:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            cwd=room.cwd,
            env=env,
            start_new_session=True,
        )
    ACTIVE.add(proc.pid)
    try:
        if stdin:
            proc.stdin.write(stdin.encode())
            await proc.stdin.drain()
            proc.stdin.close()
        await asyncio.wait_for(proc.wait(), timeout)
        return proc.returncode, False
    except asyncio.TimeoutError:
        kill_group(proc.pid)
        await proc.wait()
        return None, True
    finally:
        kill_group(proc.pid)  # helpers the harness left running, such as git
        ACTIVE.discard(proc.pid)


def archive_room(base: Path, run_dir: Path) -> None:
    """Keep every file the harness wrote: sessions, logs, caches and settings."""
    def keep(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        return None if any(info.name == p or info.name.startswith(p + "/") for p in ARCHIVE_SKIP) else info

    with tarfile.open(run_dir / "room.tar.gz", "w:gz") as tar:
        for part in ("home", "cwd", "tmp"):
            tar.add(base / part, arcname=part, filter=keep)


async def attempt(spec: Spec, harness, keys: dict, run_dir: Path, timeout: float) -> dict:
    started_at = datetime.now(timezone.utc)
    # Rooms live in the system temp folder, away from any AGENTS.md or CLAUDE.md
    # that a harness would otherwise find by walking up from its working folder.
    base = Path(tempfile.mkdtemp(prefix="ballot-room-"))
    room = Room(home=base / "home", cwd=base / "cwd", tmp=base / "tmp")
    for folder in (room.home, room.cwd, room.tmp):
        folder.mkdir()
    capture = None
    network = None
    try:
        harness.setup(spec, room)
        cmd, stdin = harness.command(spec, room)
        env = base_env(room) | harness.env(spec, room, keys)
        if CAPTURE_NETWORK:
            from ballot.netlog import NetworkCapture

            # start() raises if the capture can't run, so no run ever goes unrecorded.
            # Every key is redacted, not just the one this harness was given. Address
            # lookups stay blocked unless the harness's page reader can't work without them;
            # its connections still all go through the proxy.
            capture = NetworkCapture(run_dir, secrets=list(keys.values()),
                                     block_dns=not getattr(harness, "needs_dns", False))
            await capture.start()
            env |= capture.env()  # last, so nothing overrides the proxy settings
            cmd = capture.wrap(cmd)
        started = time.time()
        returncode, timed_out = await run_process(cmd, stdin, env, room, run_dir, timeout)
        seconds = time.time() - started
    finally:
        if capture:
            network = await capture.stop()
        archive_room(base, run_dir)
        shutil.rmtree(base, ignore_errors=True)

    parsed = harness.parse(run_dir / "events.jsonl")
    answer, answer_form = extract_answer(parsed.final_text)
    error = parsed.error
    if timed_out:
        status = "timeout"
    elif parsed.over_budget:
        status = "over_budget"
    elif parsed.error or returncode != 0:
        status = "error"
        tail = (run_dir / "stderr.log").read_text(errors="replace").strip()[-500:]
        error = parsed.error or f"exit code {returncode}: {tail}"
    elif parsed.searches and parsed.search_errors == len(parsed.searches):
        # A model that lost search still answers from memory, which would pass for
        # a real result.
        status = "error"
        error = f"all {len(parsed.searches)} web searches failed: {parsed.search_error}"
    else:
        status = "answered" if answer else "no_answer"

    if parsed.final_text:
        (run_dir / "final.txt").write_text(parsed.final_text)
    log = (run_dir / "stderr.log").read_text(errors="replace")
    warnings = [line.strip() for line in log.splitlines() if line.lower().startswith("warning")]
    if network is not None:
        from ballot.netlog import problems

        warnings += [f"capture: {problem}" for problem in problems(network)]
    return {
        "run_id": spec.run_id,
        "model": spec.model,
        "model_id": spec.model_id,
        "pin": spec.pin,
        "arm": spec.arm,
        "harness": spec.harness,
        "effort": spec.effort,
        "prompt": spec.prompt_name,
        "prop": spec.prop,
        "repeat": spec.repeat,
        "status": status,
        "answer": answer,
        "answer_form": answer_form,
        "error": error,
        # UTC, to the microsecond: the whole attempt, from setting up its room to archiving it.
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "seconds": round(seconds, 1),  # the harness process alone
        "input_tokens": parsed.input_tokens,
        "output_tokens": parsed.output_tokens,
        "cached_tokens": parsed.cached_tokens,
        "cost_usd": round(estimate_cost(parsed, spec.price) if parsed.cost_usd is None else parsed.cost_usd, 4),
        "cost_source": "estimated" if parsed.cost_usd is None or parsed.cost_estimated else "reported",
        # What OpenRouter charged, from the network log. None for a run on a direct key.
        "billed_usd": billed_cost(run_dir) if network is not None else None,
        "searches": parsed.searches,
        "search_errors": parsed.search_errors,
        "web_search_requests": parsed.web_search_requests,
        "fetches": parsed.fetches,
        "tool_errors": parsed.tool_errors,
        "warnings": warnings,
        "network": network,
    }


async def execute(spec: Spec, harness, keys: dict, out: Path, timeout: float, retries: int) -> dict:
    """Run one spec. Only infrastructure errors are retried, never a model's answer."""
    run_dir = out / spec.run_id
    run_dir.mkdir(exist_ok=True)
    (run_dir / "prompt.txt").write_text(spec.prompt)
    history = []  # every attempt's start, end and outcome
    for number in range(retries + 1):
        result = await attempt(spec, harness, keys, run_dir, timeout)
        history.append({"attempt": number + 1, "started_at": result["started_at"], "finished_at": result["finished_at"],
                        "status": result["status"], "error": result["error"][:300]})
        result["attempts"] = number + 1
        result["run_started_at"] = history[0]["started_at"]
        result["attempt_history"] = history
        (run_dir / "result.json").write_text(json.dumps(result, indent=2))
        if result["status"] != "error" or number == retries:
            return result
        # Keep everything from the failed attempt, under its attempt number.
        for name in ("events.jsonl", "stderr.log", "room.tar.gz"):
            if (run_dir / name).exists():
                (run_dir / name).rename(run_dir / f"failed-{number + 1}.{name}")
        backoff = RATE_LIMIT_BACKOFF_SECONDS if RATE_LIMITED.search(result["error"]) else RETRY_BACKOFF_SECONDS
        await asyncio.sleep(backoff * (number + 1))
    return result


def line(done: int, total: int, r: dict, spent: float) -> str:
    answer = r["answer"] or "no answer"
    detail = f"{r['seconds'] / 60:.1f}m ${r['cost_usd']:.2f} {len(r['searches'])} searches {len(r['fetches'])} pages"
    suffix = f" | {r['error'][:140]}" if r["error"] else ""
    if r["status"] in ("answered", "no_answer") and not r["searches"]:
        suffix += " | NO WEB SEARCH"
    if r["search_errors"]:
        suffix += f" | {r['search_errors']} failed searches"
    if r["tool_errors"]:
        suffix += f" | {r['tool_errors']} tool errors"
    if r["network"]:
        suffix += f" | {r['network'].get('requests', 0)} requests logged"
    for warning in r["warnings"][:3]:
        suffix += f" | {warning[:120]}"
    span = f"{r['run_started_at'][11:19]} to {r['finished_at'][11:19]} UTC"
    return f"[{done}/{total}] {r['run_id']}: {r['status']}, {answer}, {detail}, {span}, total ${spent:.2f}{suffix}"


class Slots:
    """How many runs go at once in total, as a limit that can change mid-run.

    Writing a number to the folder's concurrency.txt changes it. A lower number stops new
    runs from starting until enough have finished; nothing running is stopped.
    """

    def __init__(self, control: Path, default: int):
        self.control = control
        self.default = default
        self.active = 0

    def limit(self) -> int:
        try:
            return max(1, int(self.control.read_text().strip()))
        except (OSError, ValueError):
            return self.default

    async def __aenter__(self) -> None:
        while self.active >= self.limit():
            await asyncio.sleep(2)
        self.active += 1

    async def __aexit__(self, *exc) -> None:
        self.active -= 1


def slowest_first(plan: list[Spec]) -> list[Spec]:
    """The plan with the slowest model and harness pairs first, by the median time of their
    finished runs in any folder. Pairs with no finished run go in the middle. The sort is
    stable, so the shuffled order holds within each pair."""
    seconds: dict[tuple[str, str], list[float]] = {}
    for path in [*RUNS.glob("*/result.json"), *RUNS.glob("*/*/result.json")]:
        r = json.loads(path.read_text())
        if r.get("status") in FINAL_STATUSES:
            seconds.setdefault((r["model"], r["arm"]), []).append(r["seconds"])
    typical = {pair: sorted(v)[len(v) // 2] for pair, v in seconds.items()}
    middle = sorted(typical.values())[len(typical) // 2] if typical else 0
    return sorted(plan, key=lambda s: -typical.get((s.model, s.arm), middle))


def charge(result: dict) -> float:
    """What a run cost: OpenRouter's bill where there is one, else the recorded cost.

    The bill matters for the cap: Grok Build's own count leaves out its search calls.
    """
    return result["billed_usd"] if result.get("billed_usd") is not None else result["cost_usd"]


async def run_all(plan: list[Spec], harnesses: dict, keys: dict, out: Path, cfg: dict,
                  control: Path | None = None) -> list[dict]:
    limits = cfg["run"]
    timeout = limits["timeout_minutes"] * 60
    total_slots = Slots(control or out / "concurrency.txt", limits["concurrency"])
    model_slots = {s.model: asyncio.Semaphore(limits["per_model"]) for s in plan}
    # A provider that rate-limits gets a cap of its own, across all the models it hosts.
    provider_slots = {pin: asyncio.Semaphore(n) for pin, n in limits.get("per_provider", {}).items()}
    results: list[dict] = []

    # Spend from earlier sessions of this folder counts toward the cap.
    finished = {p.parent.name: json.loads(p.read_text()) for p in out.glob("*/result.json")}
    spent = sum(charge(r) for r in finished.values())
    todo = [s for s in plan if finished.get(s.run_id, {}).get("status") not in FINAL_STATUSES]
    if len(todo) < len(plan):
        print(f"Resuming: {len(plan) - len(todo)} runs already finished, ${spent:.2f} spent.")

    async def worker(spec: Spec) -> None:
        nonlocal spent
        async with model_slots[spec.model], provider_slots.get(spec.pin) or contextlib.nullcontext(), total_slots:
            if spent >= limits["max_total_usd"]:
                print(f"Skipped {spec.run_id}: spend reached the ${limits['max_total_usd']} cap.")
                return
            print(f"[start] {spec.run_id} at {datetime.now(timezone.utc).isoformat()}, "
                  f"{total_slots.active} running of {total_slots.limit()}", flush=True)
            result = await execute(spec, harnesses[spec.run_id], keys, out, timeout, limits["retries"])
        spent += charge(result)
        results.append(result)
        print(line(len(results), len(todo), result, spent), flush=True)

    tasks = [asyncio.create_task(worker(spec)) for spec in todo]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for pid in list(ACTIVE):
            kill_group(pid)
    return results


def main() -> None:
    args = parse_args()
    cfg = load_config()
    cfg["run"]["concurrency"] = args.concurrency or cfg["run"]["concurrency"]
    cfg["run"]["per_model"] = args.per_model or cfg["run"]["per_model"]
    plan = build_plan(args, cfg)
    if not plan:
        sys.exit("Nothing to run.")
    keys = load_keys()
    needed = sorted({DIRECT_KEYS.get(s.harness, KEY) for s in plan})
    missing = [name for name in needed if name not in keys]
    if missing and not args.dry_run:
        sys.exit(f"Missing {', '.join(missing)}. Run python3 -m ballot keys, adding openai or gemini for those keys.")

    name = args.name or (datetime.now().strftime("smoke-%Y%m%d-%H%M%S") if args.smoke else "")
    out = RUNS / name if name else RUNS
    limits = cfg["run"]
    if args.retry_errors:
        # Only runs that used up every attempt and still ended in an error: a runner still going
        # on this folder never goes back to those, so the two can't start the same run twice.
        # An error with attempts left is a retry that runner may be making right now.
        def errored(spec: Spec) -> bool:
            path = out / spec.run_id / "result.json"
            if not path.exists():
                return False
            result = json.loads(path.read_text())
            return result.get("status") == "error" and result.get("attempts", 1) > limits["retries"]

        plan = [s for s in plan if errored(s)]
        if not plan:
            sys.exit("No runs ended in an error.")
    if args.slow_first:
        plan = slowest_first(plan)
    if args.first:
        # Whole pairs first, in the order given; the sort is stable, so the rest keep their order.
        order = []
        for item in args.first.split(","):
            model, _, arm = item.partition(":")
            order += [(model, a) for a in ((arm,) if arm else ("native", "common"))]
        rank = {pair: i for i, pair in enumerate(order)}
        plan = sorted(plan, key=lambda s: rank.get((s.model, s.arm), len(order)))
    if args.skip_running_in:
        # The other runner keeps going until its runs finish, and starts none while this one runs.
        text = Path(args.skip_running_in).read_text(errors="replace")
        busy = set(re.findall(r"(?m)^\[start\] (\S+) ", text)) - set(re.findall(r"(?m)^\[\d+/\d+\] (\S+):", text))
        plan = [s for s in plan if s.run_id not in busy]
        print(f"Leaving {len(busy)} runs to the runner that started them.")
    print(f"{len(plan)} runs into runs/{name}: {len({s.model for s in plan})} models, "
          f"{len({(s.model, s.arm) for s in plan})} model and harness pairs, {len({s.prompt_name for s in plan})} prompts, "
          f"{len({s.prop for s in plan})} propositions, {len({s.repeat for s in plan})} repeats. "
          f"Stops starting runs after ${limits['max_total_usd']}. Keys: {', '.join(needed)}"
          + (f" (missing: {', '.join(missing)})." if missing else "."))
    if args.dry_run:
        for spec in plan:
            print(f"  {spec.run_id}: {spec.harness}, {spec.model_id}, effort {spec.effort}")
        return
    if not args.smoke and not args.yes and input("Start? This spends real money. [y/N] ").strip().lower() != "y":
        sys.exit("Cancelled.")

    out.mkdir(parents=True, exist_ok=True)
    write_manifest(out, plan, cfg)
    # A second runner gets its own control file, so it never changes the first runner's limit.
    control = out / (args.control or ("concurrency-retry.txt" if args.retry_errors else "concurrency.txt"))
    control.write_text(f"{limits['concurrency']}\n")
    print(f"{limits['concurrency']} runs at once. To change that mid-run, write a number to {control}.", flush=True)
    cache = RUNS / cfg["search"].get("cache", "web_cache_openrouter")
    harnesses = {
        s.run_id: Pi(cfg["search"], cache) if s.arm == "common" else NATIVE[s.harness]()
        for s in plan
    }
    try:
        results = asyncio.run(run_all(plan, harnesses, keys, out, cfg, control))
    except KeyboardInterrupt:
        sys.exit("Interrupted. Run the same command again to resume.")

    counts: dict[str, int] = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    print("Finished:", ", ".join(f"{count} {status}" for status, count in sorted(counts.items())) or "nothing new")
    print(f"Next: python3 -m ballot report runs/{name}")


if __name__ == "__main__":
    main()
