"""Runs the real harness binaries through run.py's real run path, against a fake model server
shaped like OpenRouter, OpenAI and Google. No API key is needed and nothing is spent.

These tests check the success path of each adapter, and they check what each harness sends:
only web tools offered to the model, the right effort, the provider pin, and which key.
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ballot import runner as run
from ballot.config import Spec, build_prompt, load_config
from ballot.harnesses import ClaudeCode, Codex, CodexOpenRouter, GeminiCli, GrokBuild, Pi, Room
from fake_provider import FakeProvider, offered_tools

CFG = load_config()
KEY = "sk-or-v1-fake-key-for-tests"
OPENAI_KEY = "sk-proj-fake-openai-key-for-tests"
GEMINI_KEY = "AIza-fake-gemini-key-for-tests"
KEYS = {"OPENROUTER_API_KEY": KEY, "OPENAI_API_KEY": OPENAI_KEY, "GEMINI_API_KEY": GEMINI_KEY}
PRICE = {"input": 1.0, "output": 1.0, "cached": 0.1}
SEARCH = {"engine": "perplexity", "helper_model": "mistralai/mistral-nemo"}
# Tools that would let a model run commands or touch files. No harness may offer one.
SHELL_TOOLS = {"shell", "shell_command", "exec_command", "local_shell", "write_stdin", "apply_patch",
               "run_shell_command", "write_file", "replace", "Bash", "Write", "Edit"}
# Sub-agents, which no harness gets here: Codex's own settings would offer these.
AGENT_TOOLS = {"spawn_agent", "send_message", "followup_task", "wait_agent", "list_agents", "interrupt_agent", "Task", "Agent"}


def make_spec(model_id: str, pin: str, arm: str, harness: str, effort: str = "low") -> Spec:
    return Spec(
        model="test", model_id=model_id, pin=pin, arm=arm, harness=harness, effort=effort, prompt_name="vote",
        prompt=build_prompt(CFG["templates"]["full"], CFG["prompts"]["vote"], "1"),
        prop="1", repeat=1, price=PRICE, max_run_usd=1, system_prompt=CFG["pi"]["system_prompt"],
    )


class ViaFake:
    """A real adapter, pointed at the fake server instead of the real APIs."""

    def __init__(self, harness, env: dict | None = None, pi_base_url: str | None = None, extra_args: list | None = None):
        self.harness = harness
        self.needs_dns = getattr(harness, "needs_dns", False)
        self.extra_env = env or {}
        self.pi_base_url = pi_base_url
        self.extra_args = extra_args or []

    def setup(self, spec: Spec, room: Room) -> None:
        self.harness.setup(spec, room)
        if self.pi_base_url:
            models = room.home / ".pi" / "agent" / "models.json"
            config = json.loads(models.read_text())
            config["providers"]["openrouter"]["baseUrl"] = self.pi_base_url
            models.write_text(json.dumps(config))

    def command(self, spec: Spec, room: Room):
        cmd, stdin = self.harness.command(spec, room)
        return cmd[:-1] + self.extra_args + cmd[-1:], stdin  # Codex's final "-" stays last

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        return self.harness.env(spec, room, keys) | self.extra_env

    def parse(self, path: Path):
        return self.harness.parse(path)


class Pipeline(unittest.TestCase):
    def setUp(self):
        run.CAPTURE_NETWORK = False  # tests/test_netlog.py covers the capture itself
        self.fake = FakeProvider()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.fake.stop)

    def run_spec(self, spec: Spec, harness) -> dict:
        run_dir = Path(self.folder.name) / spec.run_id / spec.model_id.replace("/", "_")
        run_dir.mkdir(parents=True)
        self.last_dir = run_dir
        result = asyncio.run(run.attempt(spec, harness, KEYS, run_dir, timeout=120))
        print(f"\n{spec.harness}/{spec.model_id}: {result['status']} {result['answer']}, {len(result['searches'])} searches, "
              f"{len(result['fetches'])} pages, {result['search_errors']} failed, tools {sorted(self.fake.tools_seen())}, "
              f"reasoning {sorted(self.fake.reasoning_settings())}, error: {result['error'][:200]}")
        self.assertTrue(self.fake.main_requests(), "no request carried the prompt")
        return result

    def first_event(self) -> dict:
        return json.loads((self.last_dir / "events.jsonl").read_text().splitlines()[0])

    def assert_answered(self, result: dict) -> None:
        self.assertEqual(result["status"], "answered", result["error"])
        self.assertEqual(result["answer"], "YES")
        self.assertGreaterEqual(len(result["searches"]), 1)

    def assert_keys_only_in_headers(self) -> None:
        for request in self.fake.requests:
            for key in KEYS.values():
                self.assertNotIn(key, json.dumps(request["body"]))
                self.assertNotIn(key, request["path"])
            headers = request["headers"]
            if "x-api-key" in headers:
                self.assertIn(headers["x-api-key"], (KEY, ""))

    def test_pi_with_each_model_pinned_with_matched_effort(self):
        for model in CFG["models"]:
            with self.subTest(model=model["model"]):
                self.fake.requests.clear()
                spec = make_spec(model["model"], model["pin"], "common", "pi", effort=model["pi_thinking"])
                pi = Pi(SEARCH, Path(self.folder.name) / "cache" / model["name"])
                result = self.run_spec(spec, ViaFake(pi, env={"OPENROUTER_CHAT_URL": f"{self.fake.url}/api/v1/chat/completions"},
                                                     pi_base_url=f"{self.fake.url}/api/v1"))
                self.assert_answered(result)
                self.assertEqual(result["search_errors"], 0)
                self.assertEqual(self.fake.tools_seen(), {"web_search", "web_fetch"})
                for request in self.fake.main_requests():
                    self.assertEqual(request["body"].get("provider"), {"only": [model["pin"]], "allow_fallbacks": False})
                settings = self.fake.reasoning_settings()
                maker = model["model"].split("/")[0]
                if maker in ("anthropic", "openai"):
                    self.assertEqual(settings, {"max"})
                elif maker == "google":
                    self.assertEqual(settings, {"high"})
                elif maker == "x-ai":
                    self.assertEqual(settings, {"xhigh"})
                else:  # each model's own highest level, whatever Pi calls it
                    self.assertEqual(len(settings), 1)
                    self.assertNotIn("None", settings)
                helper = [r for r in self.fake.requests if r["body"].get("plugins")]
                self.assertTrue(helper, "the search helper never ran")
                self.assertEqual(helper[0]["body"]["plugins"], [{"id": "web", "engine": "perplexity", "max_results": 10}])
                self.assert_keys_only_in_headers()
                for request in self.fake.requests:  # Claude requests carry it as x-api-key
                    headers = request["headers"]
                    self.assertTrue(headers.get("authorization") == f"Bearer {KEY}" or headers.get("x-api-key") == KEY)

    def test_claude_code(self):
        spec = make_spec("anthropic/claude-opus-5.5", "anthropic", "native", "claude_code", effort="max")
        result = self.run_spec(spec, ViaFake(ClaudeCode(), env={"ANTHROPIC_BASE_URL": self.fake.url}))
        self.assert_answered(result)
        self.assertLessEqual({"WebSearch", "WebFetch"}, self.fake.tools_seen())
        self.assertLessEqual(self.fake.tools_seen(), {"WebSearch", "WebFetch", "web_search"})
        self.assertEqual(self.fake.reasoning_settings(), {"max"})
        main = self.fake.main_requests()[0]
        self.assertEqual(main["body"].get("provider"), {"only": ["anthropic"], "allow_fallbacks": False})
        self.assertEqual(main["headers"].get("authorization"), f"Bearer {KEY}")
        # The run used the OpenRouter token and no login from this machine.
        self.assertEqual(self.first_event()["apiKeySource"], "none")
        self.assert_keys_only_in_headers()

    def test_codex_on_its_own_key_runs_with_no_shell_and_no_sub_agents(self):
        spec = make_spec("gpt-6-astra", "openai", "native", "codex", effort="max")
        # Codex's built-in OpenAI address can't be changed, so a stand-in provider that reads the
        # same key variable points it at the fake. Codex adds its own web tool only for OpenAI
        # itself; test_codex_offers_openai_its_own_web_tool checks that against the real address.
        stand_in = ["-c", 'model_provider="fake"', "-c", 'model_providers.fake.name="Fake"',
                    "-c", f'model_providers.fake.base_url="{self.fake.url}/v1"',
                    "-c", 'model_providers.fake.env_key="OPENAI_API_KEY"', "-c", 'model_providers.fake.wire_api="responses"']
        result = self.run_spec(spec, ViaFake(Codex(), extra_args=stand_in))
        self.assertEqual(result["status"], "answered", result["error"])
        seen = self.fake.tools_seen()
        self.assertIn("exec", seen)  # code mode, where Codex's own web tool lives
        self.assertFalse(seen & (SHELL_TOOLS | AGENT_TOOLS), f"a shell, file or sub-agent tool was offered: {seen}")
        self.assertEqual(self.fake.reasoning_settings(), {"max"})
        for request in self.fake.requests:
            self.assertEqual(request["headers"].get("authorization"), f"Bearer {OPENAI_KEY}")
        self.assert_keys_only_in_headers()

    def test_codex_offers_openai_its_own_web_tool(self):
        """Through the network log, against OpenAI's real address with a fake key: OpenAI refuses
        the key, so nothing is spent, and the recorded request shows every tool Codex offered."""
        run.CAPTURE_NETWORK = True
        try:
            spec = make_spec("gpt-6-luna", "openai", "native", "codex", effort="max")
            run_dir = Path(self.folder.name) / "codex-probe"
            run_dir.mkdir()
            asyncio.run(run.attempt(spec, Codex(), KEYS, run_dir, timeout=120))
        finally:
            run.CAPTURE_NETWORK = False
        import gzip

        posts = [json.loads(line) for line in gzip.decompress((run_dir / "network.jsonl.gz").read_bytes()).splitlines()]
        posts = [r for r in posts if r.get("type") == "http" and (r.get("request") or {}).get("method") == "POST"
                 and "api.openai.com/v1/responses" in r["request"].get("url", "")]
        if not posts:
            self.skipTest("OpenAI couldn't be reached")
        self.assertEqual(str(posts[0]["response"]["status"]), "401")
        tools = set(offered_tools(json.loads(posts[0]["request"]["body"])))
        self.assertIn("web__run", tools)  # Codex's own web tool: search, open a page, find in it
        self.assertFalse(tools & (SHELL_TOOLS | AGENT_TOOLS | {"clock__curr_time", "sleep"}), tools)
        self.assertNotIn(OPENAI_KEY, gzip.decompress((run_dir / "network.jsonl.gz").read_bytes()).decode())

    def test_codex_on_openrouter_has_hosted_search_and_no_shell(self):
        spec = make_spec("openai/gpt-6-astra", "openai", "native", "codex_openrouter", effort="max")
        harness = ViaFake(CodexOpenRouter(), extra_args=["-c", f'model_providers.openrouter.base_url="{self.fake.url}/v1"'])
        result = self.run_spec(spec, harness)
        self.assertEqual(result["status"], "answered", result["error"])
        seen = self.fake.tools_seen()
        self.assertIn("web_search", seen)
        self.assertLessEqual(seen, {"web_search", "request_user_input"})
        self.assertEqual(self.fake.reasoning_settings(), {"max"})
        self.assertEqual(self.fake.requests[0]["headers"].get("authorization"), f"Bearer {KEY}")

    def test_gemini_cli_on_its_own_key_has_web_tools_only(self):
        spec = make_spec("gemini-3.8-flash", "google-ai-studio", "native", "gemini_cli", effort="high")
        result = self.run_spec(spec, ViaFake(GeminiCli(), env={"GOOGLE_GEMINI_BASE_URL": self.fake.url}))
        self.assert_answered(result)
        main = self.fake.main_requests()
        tools = {name for r in main for name in offered_tools(r["body"])}
        self.assertEqual(tools, {"google_web_search", "web_fetch"})
        self.assertTrue(any(":streamGenerateContent" in r["path"] or ":generateContent" in r["path"] for r in main))
        for request in self.fake.requests:
            self.assertEqual(request["headers"].get("x-goog-api-key"), GEMINI_KEY)
        self.assert_keys_only_in_headers()

    def test_grok_build_offers_search_and_the_page_reader(self):
        spec = make_spec("x-ai/grok-4.7", "xai", "native", "grok_build", effort="xhigh")
        harness = ViaFake(GrokBuild(), env={"GROK_MODELS_BASE_URL": f"{self.fake.url}/v1",
                                            "GROK_XAI_API_BASE_URL": f"{self.fake.url}/v1"})
        result = self.run_spec(spec, harness)
        self.assert_answered(result)
        self.assertEqual(result["search_errors"], 0)
        # Only the main model's requests count: Grok also names the session with a separate call.
        main = [r for r in self.fake.main_requests() if r["body"].get("model") == "x-ai/grok-4.7"]
        tools = {name for r in main for name in offered_tools(r["body"])}
        self.assertIn("web_fetch", tools)  # the page reader, which the runner turns on
        self.assertLessEqual(tools, {"web_search", "web_fetch", "search_tool", "use_tool"})
        self.assertEqual({r["body"].get("reasoning_effort") for r in main}, {"xhigh"})
        searches = [r for r in self.fake.requests if "/responses" in r["path"]]
        self.assertTrue(searches and searches[0]["body"]["model"] == "x-ai/grok-4.6", "the search call didn't use grok-4.6")
        init = self.first_event()
        self.assertEqual(init["mcp_servers"], [])  # search_tool and use_tool only reach MCP servers


if __name__ == "__main__":
    unittest.main(verbosity=1)
