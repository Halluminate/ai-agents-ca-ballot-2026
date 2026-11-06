"""The overnight behavior of run.py and analyze.py, using a stub harness. No model, no spend."""

import asyncio
import json
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballot import runner as run
from ballot.config import Spec, load_config
from ballot.harnesses import Parsed, Room
from ballot.paths import ROOT


def make_spec(repeat: int = 1, prompt: str = "vote", model: str = "claude", arm: str = "native", prop: str = "1") -> Spec:
    return Spec(model=model, model_id="m", pin="anthropic", arm=arm, harness="stub", effort="max", prompt_name=prompt,
                prompt="p", prop=prop, repeat=repeat, price={"input": 1, "output": 1, "cached": 1}, max_run_usd=1,
                system_prompt="s")


class Stub:
    """A harness whose process prints a scripted reply, one per attempt."""

    def __init__(self, replies: list[str], seconds: float = 0, cost: float = 1.0):
        self.replies = list(replies)
        self.seconds = seconds
        self.cost = cost
        self.calls = 0

    def setup(self, spec: Spec, room: Room) -> None:
        (room.home / "session.jsonl").write_text("a session file the harness wrote")

    def command(self, spec: Spec, room: Room):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        script = f"import sys,time; time.sleep({self.seconds}); sys.stdout.write({reply!r})"
        return [sys.executable, "-c", script], None

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        return {}

    def parse(self, path: Path) -> Parsed:
        text = path.read_text()
        if text.startswith("INFRA"):
            return Parsed(error="503 overloaded", cost_usd=0.0)
        if text.startswith("NOSEARCH"):
            return Parsed(final_text="Yes", searches=["a", "b"], search_errors=2, search_error="HTTP 432", cost_usd=0.5)
        if text.startswith("ONEFAILED"):
            return Parsed(final_text="Yes", searches=["a", "b"], search_errors=1, search_error="HTTP 500", cost_usd=0.5)
        return Parsed(final_text=text, searches=["q"], cost_usd=self.cost)


class Runner(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.out = Path(self.folder.name)
        self.cfg = load_config()
        self.cfg["run"].update(concurrency=4, per_model=4, retries=2, max_total_usd=1000, timeout_minutes=1)
        run.RETRY_BACKOFF_SECONDS = 0
        run.CAPTURE_NETWORK = False  # tests/test_netlog.py covers the capture itself

    def go(self, plan: list[Spec], harnesses: dict) -> list[dict]:
        return asyncio.run(run.run_all(plan, harnesses, {"OPENROUTER_API_KEY": "test-key"}, self.out, self.cfg))

    def test_an_answered_run(self):
        spec = make_spec()
        result = self.go([spec], {spec.run_id: Stub(["No"])})[0]
        self.assertEqual((result["status"], result["answer"], result["answer_form"]), ("answered", "NO", "exact"))
        self.assertEqual(result["attempts"], 1)
        self.assertTrue((self.out / spec.run_id / "final.txt").exists())

    def test_every_file_the_harness_wrote_is_kept(self):
        spec = make_spec()
        self.go([spec], {spec.run_id: Stub(["Yes"])})
        with tarfile.open(self.out / spec.run_id / "room.tar.gz") as tar:
            self.assertIn("home/session.jsonl", tar.getnames())

    def test_a_refusal_is_data_and_is_never_retried(self):
        spec = make_spec()
        stub = Stub(["I won't tell you how to vote."])
        result = self.go([spec], {spec.run_id: stub})[0]
        self.assertEqual((result["status"], result["answer"]), ("no_answer", None))
        self.assertEqual(stub.calls, 1)

    def test_an_infrastructure_failure_is_retried_and_its_files_are_kept(self):
        spec = make_spec()
        stub = Stub(["INFRA", "INFRA", "Yes"])
        result = self.go([spec], {spec.run_id: stub})[0]
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["attempts"], 3)
        for name in ("failed-1.events.jsonl", "failed-1.room.tar.gz", "failed-2.stderr.log"):  # network files: netlog
            self.assertTrue((self.out / spec.run_id / name).exists(), name)

    def test_retries_stop_at_the_limit(self):
        spec = make_spec()
        stub = Stub(["INFRA"])
        result = self.go([spec], {spec.run_id: stub})[0]
        self.assertEqual(result["status"], "error")
        self.assertEqual(stub.calls, 3)  # the first try plus two retries

    def test_a_run_that_lost_all_search_is_not_a_result(self):
        spec = make_spec()
        result = self.go([spec], {spec.run_id: Stub(["NOSEARCH"])})[0]
        self.assertEqual(result["status"], "error")
        self.assertIn("all 2 web searches failed: HTTP 432", result["error"])

    def test_one_failed_search_does_not_void_a_run(self):
        spec = make_spec()
        result = self.go([spec], {spec.run_id: Stub(["ONEFAILED"])})[0]
        self.assertEqual(result["status"], "answered")

    def test_resume_skips_finished_runs_and_reruns_errors(self):
        done, failed = make_spec(1), make_spec(2)
        harnesses = {done.run_id: Stub(["Yes"]), failed.run_id: Stub(["INFRA"])}
        self.go([done, failed], harnesses)
        harnesses[failed.run_id] = Stub(["Yes"])
        results = self.go([done, failed], harnesses)
        self.assertEqual([r["run_id"] for r in results], [failed.run_id])
        self.assertEqual(harnesses[done.run_id].calls, 1)

    def test_a_refusal_is_not_rerun_on_resume(self):
        spec = make_spec()
        stub = Stub(["I won't say."])
        self.go([spec], {spec.run_id: stub})
        self.assertEqual(self.go([spec], {spec.run_id: stub}), [])
        self.assertEqual(stub.calls, 1)

    def test_a_slow_run_is_killed_and_not_retried(self):
        spec = make_spec()
        self.cfg["run"]["timeout_minutes"] = 0.02
        stub = Stub(["Yes"], seconds=60)
        started = time.time()
        result = self.go([spec], {spec.run_id: stub})[0]
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(stub.calls, 1)
        self.assertLess(time.time() - started, 10)

    def test_the_spending_cap_stops_new_runs(self):
        self.cfg["run"].update(concurrency=1, per_model=1, max_total_usd=2)
        plan = [make_spec(i) for i in range(1, 6)]
        results = self.go(plan, {s.run_id: Stub(["Yes"], cost=1.0) for s in plan})
        self.assertEqual(len(results), 2)

    def test_spend_from_earlier_sessions_counts_toward_the_cap(self):
        self.cfg["run"].update(concurrency=1, per_model=1, max_total_usd=2)
        plan = [make_spec(i) for i in range(1, 6)]
        harnesses = {s.run_id: Stub(["Yes"], cost=1.0) for s in plan}
        self.go(plan, harnesses)
        self.assertEqual(self.go(plan, harnesses), [])

    def test_per_model_limit_is_respected(self):
        self.cfg["run"].update(concurrency=8, per_model=2)
        plan = [make_spec(i) for i in range(1, 5)]
        started = time.time()
        self.go(plan, {s.run_id: Stub(["Yes"], seconds=0.4) for s in plan})
        self.assertGreater(time.time() - started, 0.75)  # four runs of one model, two at a time

    def test_changed_prompts_cannot_join_an_old_folder(self):
        spec = make_spec()
        run.write_manifest(self.out, [spec], self.cfg)
        run.write_manifest(self.out, [spec], self.cfg)
        spec.prompt = "a different prompt"
        with self.assertRaises(SystemExit):
            run.write_manifest(self.out, [spec], self.cfg)

    def plan(self, *argv: str) -> list[Spec]:
        sys_argv, sys.argv = sys.argv, ["run.py", *argv]
        try:
            return run.build_plan(run.parse_args(), self.cfg)
        finally:
            sys.argv = sys_argv

    def test_the_plan_covers_every_model_in_every_harness_it_has(self):
        plan = self.plan()
        pairs = {(s.model, s.arm) for s in plan}
        expected = {(m["name"], arm) for m in self.cfg["models"] for arm in ("native", "common") if arm == "common" or m["native"]}
        self.assertEqual(pairs, expected)
        self.assertIn(("gemini", "native"), pairs)  # Gemini CLI, on its own key
        self.assertNotIn(("kimi", "native"), pairs)
        self.assertEqual(len(plan), len(expected) * 3 * 14)
        self.assertEqual(len({s.run_id for s in plan}), len(plan))

    def test_harnesses_on_their_own_key_get_the_vendors_model_ids(self):
        ids = {(s.model, s.arm): (s.harness, s.model_id) for s in self.plan()}
        self.assertEqual(ids[("gpt", "native")], ("codex", "gpt-6-astra"))
        self.assertEqual(ids[("gpt", "common")], ("pi", "openai/gpt-6-astra"))
        self.assertEqual(ids[("gemini", "native")], ("gemini_cli", "gemini-4-argon"))
        self.assertEqual(ids[("flash", "native")], ("gemini_cli", "gemini-3.8-flash"))
        self.assertEqual(ids[("grok", "native")], ("grok_build", "x-ai/grok-4.7"))
        cheap = {(s.model, s.arm): s.model_id for s in self.plan("--cheap", "--models", "gpt,gemini")}
        self.assertEqual(cheap[("gpt", "native")], "gpt-6-luna")
        self.assertEqual(cheap[("gemini", "native")], "gemini-3.8-flash")
        self.assertEqual(cheap[("gpt", "common")], "openai/gpt-6-luna")

    def test_a_model_can_be_picked_with_one_harness(self):
        plan = self.plan("--models", "grok:native,sonnet,gpt:native,gpt:common")
        self.assertEqual({(s.model, s.arm) for s in plan},
                         {("grok", "native"), ("sonnet", "native"), ("sonnet", "common"), ("gpt", "native"), ("gpt", "common")})
        with self.assertRaises(SystemExit):
            self.plan("--models", "grok:sideways")

    def test_the_spend_cap_counts_openrouters_bill_where_there_is_one(self):
        self.assertEqual(run.charge({"cost_usd": 0.1, "billed_usd": 2.5}), 2.5)  # Grok Build's search calls
        self.assertEqual(run.charge({"cost_usd": 0.4, "billed_usd": None}), 0.4)  # a direct key, estimated
        self.assertEqual(run.charge({"cost_usd": 0.4}), 0.4)


class Report(unittest.TestCase):
    def test_report_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / "manifest.json").write_text(json.dumps({"config": {"prompts": {"vote": "Q1", "better": "Q2"}}}))

            def write(model, arm, prompt, prop, answer, status="answered"):
                run_id = f"{model}__{arm}__{prompt}__p{prop}__r1"
                (out / run_id).mkdir()
                # The report reads each answer again from the saved reply.
                (out / run_id / "final.txt").write_text(answer.capitalize() if answer else "I won't pick a side.")
                (out / run_id / "result.json").write_text(json.dumps({
                    "run_id": run_id, "model": model, "model_id": model, "arm": arm, "harness": "h", "effort": "max",
                    "prompt": prompt, "prop": prop, "repeat": 1, "status": status, "answer": answer,
                    "answer_form": "exact" if answer else "none", "error": "", "seconds": 60, "input_tokens": 1,
                    "output_tokens": 1, "cached_tokens": 0, "cost_usd": 2.0, "cost_source": "reported",
                    "searches": ["q"], "search_errors": 0, "fetches": ["https://lao.ca.gov/a"], "tool_errors": 0,
                    "warnings": [], "attempts": 1, "network": {"requests": 5, "requests_per_host": {"openrouter.ai": 4, "lao.ca.gov": 1}},
                }))

            write("a", "native", "vote", "1", "YES")
            write("a", "native", "vote", "2", "NO")
            write("a", "native", "better", "1", "NO")   # flips prop 1 between prompts
            write("a", "native", "better", "2", "NO")
            write("a", "common", "vote", "1", "YES")
            write("a", "common", "vote", "2", "YES")    # flips prop 2 between harnesses
            write("a", "common", "better", "1", None, "no_answer")
            write("a", "common", "better", "2", "NO")
            write("b", "common", "vote", "1", "YES")
            write("b", "common", "vote", "2", None, "no_answer")

            subprocess.run([sys.executable, "-m", "ballot", "report", str(out)], check=True, capture_output=True, cwd=ROOT)
            report = (out / "report.md").read_text()
            self.assertIn("10 runs, $20.00", report)
            # Worked out by hand from the answers above.
            self.assertIn("| a | common | 100% (2/2) | 50% (1/2) |", report)
            self.assertIn("| b | common | 50% (1/2) | n/a |", report)
            self.assertIn("| a | native | 50% (1/2) |", report)                 # prompt flips, native
            self.assertIn("| a | 50% (1/2) | 0% (0/1) |", report)              # harness flips per prompt
            self.assertIn("| 1 | YES | YES | YES |", report)                   # the vote table's first row
            self.assertIn("declined", report)
            self.assertIn("openrouter.ai (16)", report)
            self.assertIn("lao.ca.gov", report)
            self.assertIn("runs.csv", [p.name for p in out.iterdir()])


if __name__ == "__main__":
    unittest.main()
