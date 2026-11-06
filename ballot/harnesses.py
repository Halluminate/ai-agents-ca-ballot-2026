"""One adapter per agent harness, all but two running on one OpenRouter key.

Codex and Gemini CLI run on their vendor's own key, because OpenRouter can't serve them
fully: Codex's own web tool calls an OpenAI address OpenRouter doesn't serve, and Gemini
CLI only talks to Google.

Every run happens in a throwaway home folder and an empty working folder, with a
minimal environment that holds only the key its harness needs. That keeps local logins,
memories, instructions and MCP servers out of every run.

Each adapter also restricts its harness to web tools, so an unattended agent that
reads a hostile page has no shell and no file tools to misuse. Requests are pinned to
the model's own company on OpenRouter wherever the harness can send that setting.
"""

import gzip
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ballot.config import DIRECT_KEYS, KEY, Spec
from ballot.paths import BIN, DATA, PACKAGE

OPENROUTER_API = "https://openrouter.ai/api"
SEARCH_TOOLS = {"WebSearch", "web_search", "google_web_search"}
FETCH_TOOLS = {"WebFetch", "web_fetch"}
CLAUDE_SEARCH_PREFIX = "Web search results for query:"


@dataclass
class Room:
    """The throwaway folders for one run."""

    home: Path
    cwd: Path
    tmp: Path


@dataclass
class Parsed:
    """What a harness produced, in the same shape for every harness."""

    final_text: str = ""
    input_tokens: int = 0  # uncached input
    output_tokens: int = 0  # includes reasoning
    cached_tokens: int = 0
    cache_write_tokens: int = 0  # only where a harness reports them apart from input
    cost_usd: float | None = None  # set when the harness reports a cost, or the adapter works it out
    cost_estimated: bool = False  # the adapter worked cost_usd out from tokens
    searches: list[str] = field(default_factory=list)
    fetches: list[str] = field(default_factory=list)
    tool_errors: int = 0
    search_errors: int = 0
    search_error: str = ""
    web_search_requests: int | None = None  # the harness's own count, where it reports one
    error: str = ""
    over_budget: bool = False

    def note_tool(self, name: str, args: dict) -> None:
        if name in SEARCH_TOOLS:
            self.searches.append(str(args.get("query", "")))
        elif name in FETCH_TOOLS:
            urls = re.findall(r"https?://[^\s\"'\\)]+", json.dumps(args))
            self.fetches.extend(dict.fromkeys(urls))

    def note_search_error(self, message: str) -> None:
        self.search_errors += 1
        self.search_error = message[:300]


def estimate_cost(parsed: Parsed, price: dict) -> float:
    """Token prices are per million. A vendor's search fee, where it bills one, is per search."""
    return (
        parsed.input_tokens * price["input"]
        + parsed.output_tokens * price["output"]
        + parsed.cached_tokens * price["cached"]
        + parsed.cache_write_tokens * price.get("cache_write", price["input"])
    ) / 1_000_000 + len(parsed.searches) * price.get("search", 0.0)


def iter_events(path: Path) -> Iterator[dict]:
    """Yield JSON objects from a JSONL file, gzipped or not, skipping any non-JSON log lines."""
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    for line in data.split(b"\n"):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def search_links(block: dict, details) -> int | None:
    """How many links one Claude Code WebSearch result holds. None if it isn't that format."""
    if isinstance(details, dict) and "searchCount" in details:
        return sum(len(r.get("content") or []) for r in details.get("results") or [] if isinstance(r, dict))
    text = block.get("content")
    if isinstance(text, list):
        text = "".join(c.get("text", "") for c in text if isinstance(c, dict))
    if isinstance(text, str) and text.startswith(CLAUDE_SEARCH_PREFIX):
        return text.count('{"title":')
    return None


def parse_messages_stream(path: Path) -> Parsed:
    """Claude Code stream-json. Grok's streaming-messages-json is the same format.

    A search tool call alone doesn't prove a search happened: the harness reports the
    call even when its search request failed. So each search result is checked too, and
    an error or an empty result counts as a failed search.
    """
    out = Parsed()
    last_text = ""
    search_ids: set[str] = set()
    for event in iter_events(path):
        kind = event.get("type")
        content = (event.get("message") or {}).get("content")
        if kind == "assistant" and isinstance(content, list):
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            last_text = text or last_text
            for block in content:
                if block.get("type") in ("tool_use", "server_tool_use"):
                    out.note_tool(block.get("name", ""), block.get("input") or {})
                    if block.get("name") in SEARCH_TOOLS:
                        search_ids.add(block.get("id", ""))
                elif block.get("type") == "web_search_tool_result" and isinstance(block.get("content"), dict):
                    out.note_search_error(f"search failed: {block['content']}")
        elif kind == "user" and isinstance(content, list):
            results = [b for b in content if b.get("type") == "tool_result"]
            out.tool_errors += sum(1 for b in results if b.get("is_error"))
            searched = [b for b in results if b.get("tool_use_id") in search_ids]
            for block in searched:
                details = event.get("tool_use_result") if len(searched) == 1 else None
                if block.get("is_error"):
                    out.note_search_error(str(block.get("content")))
                elif search_links(block, details) == 0:
                    out.note_search_error(f"search returned no results: {block.get('content')}")
        elif kind == "result":
            usage = event.get("usage") or {}
            out.input_tokens = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
            out.output_tokens = usage.get("output_tokens", 0)
            out.cached_tokens = usage.get("cache_read_input_tokens", 0)
            out.cost_usd = event.get("total_cost_usd")
            models = event.get("modelUsage") or {}
            if models:
                out.web_search_requests = sum(m.get("webSearchRequests", 0) for m in models.values())
            subtype = str(event.get("subtype", ""))
            out.over_budget = "budget" in subtype
            if event.get("is_error") or subtype.startswith("error"):
                out.error = str(event.get("result") or " ".join(event.get("errors") or []) or subtype)
            else:
                out.final_text = event.get("result") or last_text
        elif kind == "error":
            out.error = str(event.get("message", "error"))
    return out


class ClaudeCode:
    def setup(self, spec: Spec, room: Room) -> None:
        pass

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        # --bare would be simpler, but it removes WebSearch and WebFetch. The empty
        # home folder gives the same isolation.
        tools = "WebSearch,WebFetch"
        return [
            str(BIN / "claude"), "-p",
            "--model", spec.model_id,
            "--effort", spec.effort,
            "--tools", tools,
            "--allowedTools", tools,
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--output-format", "stream-json", "--verbose",
            "--no-session-persistence",
            "--max-budget-usd", str(spec.max_run_usd),
        ], spec.prompt

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        return {
            "ANTHROPIC_BASE_URL": OPENROUTER_API,
            "ANTHROPIC_AUTH_TOKEN": keys[KEY],
            "ANTHROPIC_API_KEY": "",
            # WebFetch summarizes pages with the small model, as it does on a direct key.
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anthropic/claude-haiku-5.5",
            "ANTHROPIC_SMALL_FAST_MODEL": "anthropic/claude-haiku-5.5",
            # Other hosts of Claude on OpenRouter have no native web search.
            "CLAUDE_CODE_EXTRA_BODY": json.dumps({"provider": {"only": [spec.pin], "allow_fallbacks": False}}),
            # A config folder of its own means no keychain login on this machine can match.
            "CLAUDE_CONFIG_DIR": str(room.home / ".claude"),
            "DISABLE_AUTOUPDATER": "1",
        }

    def parse(self, path: Path) -> Parsed:
        return parse_messages_stream(path)


# The plugin features download a 25 MB plugin repository from GitHub on every run.
CODEX_OFF = ("shell_tool", "unified_exec", "multi_agent", "image_generation", "view_image", "goals",
             "plugins", "remote_plugin", "plugin_discovery_prefetch")


class Codex:
    """Codex on a direct OpenAI key, with Codex's own setup for the model.

    That setup reaches the web through Codex's own web tool, web__run, which can search,
    open any page and search within it. The tool calls an OpenAI address that OpenRouter
    doesn't serve. The catalog is Codex's own entry for each model with everything else
    taken out: Codex's settings would also offer sub-agents, apply_patch and clock tools,
    which no other harness gets and --disable doesn't reach.
    """

    def setup(self, spec: Spec, room: Room) -> None:
        (room.home / ".codex").mkdir()

    def base_command(self, spec: Spec) -> list[str]:
        return [
            str(BIN / "codex"), "exec", "--json",
            "--skip-git-repo-check", "--ephemeral",
            "--ignore-user-config", "--ignore-rules",
            "--sandbox", "read-only",
            "-m", spec.model_id,
            "-c", f'model_reasoning_effort="{spec.effort}"',
            "-c", 'web_search="live"',
        ]

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        cmd = self.base_command(spec) + ["-c", f'model_catalog_json="{DATA / "codex_openai_catalog.json"}"']
        for feature in CODEX_OFF:
            cmd += ["--disable", feature]
        return cmd + ["-"], spec.prompt

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        key = keys[DIRECT_KEYS["codex"]]
        return {"OPENAI_API_KEY": key, "CODEX_API_KEY": key, "CODEX_HOME": str(room.home / ".codex")}

    def parse(self, path: Path) -> Parsed:
        out = Parsed()
        finished = False
        # Keyed by item id: an item can arrive twice, and a search can start and never complete.
        searches: dict[str, str] = {}
        pages: dict[str, str] = {}
        for event in iter_events(path):
            kind = event.get("type")
            item = event.get("item") or {}
            if kind in ("item.started", "item.completed") and item.get("type") == "web_search":
                action = item.get("action") or {}
                if action.get("url"):
                    pages[item.get("id", "")] = action["url"]
                else:
                    searches[item.get("id", "")] = item.get("query") or action.get("query") or ""
            elif kind == "item.completed" and item.get("type") == "agent_message":
                out.final_text = item.get("text", "")
            elif kind == "turn.completed":
                finished = True
                usage = event.get("usage") or {}
                # Cached reads and cache writes are both counted inside input_tokens.
                cached = usage.get("cached_input_tokens", 0)
                written = usage.get("cache_write_input_tokens", 0)
                out.input_tokens += usage.get("input_tokens", 0) - cached - written
                out.cached_tokens += cached
                out.cache_write_tokens += written
                out.output_tokens += usage.get("output_tokens", 0)
            elif kind in ("turn.failed", "error"):
                error = event.get("error") or {}
                out.error = str(error.get("message") or event.get("message") or kind)
        # A search item with no query is a page open, or a search that never ran.
        out.searches = [query for item_id, query in searches.items() if query and item_id not in pages]
        out.fetches = list(dict.fromkeys(pages.values()))
        if finished:
            out.error = ""  # earlier error events were reconnects that recovered
        return out


class CodexOpenRouter(Codex):
    """Codex on the OpenRouter key. Not part of the published results: its own web tool is out
    of reach there, so the catalog swaps in OpenAI's standard search tool, and with that tool
    Codex never opened a page.
    """

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        # The catalog is Codex's own entry for this model under its OpenRouter id, with
        # code mode off. Code mode's search calls an endpoint OpenRouter doesn't serve;
        # without it Codex uses the hosted web_search tool. It also locks the shell off.
        provider = "model_providers.openrouter"
        cmd = self.base_command(spec) + [
            "-c", 'model_provider="openrouter"',
            "-c", f'{provider}.name="OpenRouter"',
            "-c", f'{provider}.base_url="{OPENROUTER_API}/v1"',
            "-c", f'{provider}.env_key="OPENROUTER_API_KEY"',
            "-c", f'{provider}.wire_api="responses"',
            # OpenRouter's keep-alive comments don't reset Codex's 300-second idle timer.
            "-c", f"{provider}.stream_idle_timeout_ms=3600000",
            "-c", f'model_catalog_json="{DATA / "codex_openrouter_catalog.json"}"',
        ]
        for feature in CODEX_OFF:
            cmd += ["--disable", feature]
        return cmd + ["-"], spec.prompt

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        return {"OPENROUTER_API_KEY": keys[KEY], "CODEX_HOME": str(room.home / ".codex")}


GROK_CONFIG = """
[models]
# The web_search tool runs a separate call on this model with xAI's hosted search.
# grok-4.6 is Grok Build's own default for it, here under its OpenRouter id.
web_search = "x-ai/grok-4.6"
session_summary = "x-ai/grok-4.6"

[model."{model_id}"]
model = "{model_id}"
name = "Grok 4.7"
system_prompt_label = "Grok 4.7"
context_window = 500000
# OpenRouter's model list has no effort levels for Grok, so without these it sends none.
[[model."{model_id}".reasoning_efforts]]
value = "xhigh"
label = "Extra High Effort"
[[model."{model_id}".reasoning_efforts]]
value = "high"
label = "High Effort"
default = true
"""


class GrokBuild:
    # Its page reader looks up a site's address itself, to refuse private networks, before
    # fetching through the proxy. With lookups blocked, every page read fails.
    needs_dns = True

    def setup(self, spec: Spec, room: Room) -> None:
        (room.tmp / "prompt.txt").write_text(spec.prompt)
        (room.home / ".grok").mkdir()
        (room.home / ".grok" / "config.toml").write_text(GROK_CONFIG.replace("{model_id}", spec.model_id))

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        return [
            str(BIN / "grok"),
            "--prompt-file", str(room.tmp / "prompt.txt"),
            "--output-format", "streaming-messages-json",
            "-m", spec.model_id,
            "--reasoning-effort", spec.effort,
            "--tools", "web_search,web_fetch",
            "--always-approve",
            "--no-subagents", "--no-plan",
            "--cwd", str(room.cwd),
        ], None

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        # Both base URLs are needed. With only one, searches go to xAI's own servers.
        return {
            "XAI_API_KEY": keys[KEY],
            "GROK_MODELS_BASE_URL": f"{OPENROUTER_API}/v1",
            "GROK_XAI_API_BASE_URL": f"{OPENROUTER_API}/v1",
            # Grok Build's page reader is off unless this is set. --always-approve lets it
            # open any site, not just its built-in list of documentation sites.
            "GROK_WEB_FETCH": "1",
        }

    def parse(self, path: Path) -> Parsed:
        out = parse_messages_stream(path)
        if out.cost_usd == 0:
            out.cost_usd = None  # Grok reports 0 for OpenRouter models, so estimate instead
        return out


# Pi's defaults send Claude's effort as per-message markers on a "low" baseline, compact
# GPT past OpenRouter's higher price tier, and retry Gemini silently at its output limit.
PI_MODEL_OVERRIDES = {
    "anthropic/claude-opus-5.5": {"compat": {"supportsMidConvoEffort": False}},
    "anthropic/claude-fable-5.1": {"compat": {"supportsMidConvoEffort": False}},
    "anthropic/claude-sonnet-5.5": {"compat": {"supportsMidConvoEffort": False}},
    "anthropic/claude-haiku-5.5": {"compat": {"supportsMidConvoEffort": False}},
    "openai/gpt-6-astra": {"contextWindow": 272000},
    "openai/gpt-6.1-sol": {"contextWindow": 272000},
    "openai/gpt-6.1-terra": {"contextWindow": 272000},
    "openai/gpt-6-luna": {"contextWindow": 272000},
    "google/gemini-4-argon": {"maxTokens": 65536},
    "google/gemini-3.8-flash": {"maxTokens": 65536},
}


class Pi:
    """The shared harness: same loop, system prompt and web tools for every model."""

    def __init__(self, search: dict, cache_dir: Path):
        self.search = search
        self.cache_dir = cache_dir

    def setup(self, spec: Spec, room: Room) -> None:
        agent_dir = room.home / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        overrides = {"providers": {"openrouter": {"modelOverrides": PI_MODEL_OVERRIDES}}}
        (agent_dir / "models.json").write_text(json.dumps(overrides))

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        return [
            str(BIN / "pi"), "-p", "--mode", "json", "--no-session",
            "--provider", "openrouter",
            "--model", spec.model_id,
            "--thinking", spec.effort,
            "--system-prompt", spec.system_prompt,
            "--no-builtin-tools", "--no-mcp", "--no-extensions", "--no-skills",
            "--no-prompt-templates", "--no-themes", "--no-context-files",
            "-e", str(PACKAGE / "pi_ext" / "web_tools.ts"),
            "-e", str(PACKAGE / "pi_ext" / "openrouter_route.ts"),
            "--", spec.prompt,
        ], None

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        key = keys[KEY]
        return {
            "OPENROUTER_API_KEY": key,
            "OPENROUTER_ONLY": spec.pin,
            "PI_CODING_AGENT_DIR": str(room.home / ".pi" / "agent"),
            "PI_OFFLINE": "1",  # keeps the pinned model catalog for the whole run
            "PI_TELEMETRY": "0",
            "SEARCH_PROVIDER": "openrouter",
            "SEARCH_API_KEY": key,
            "SEARCH_ENGINE": self.search["engine"],
            "SEARCH_HELPER_MODEL": self.search["helper_model"],
            "WEB_CACHE_DIR": str(self.cache_dir),
        }

    def parse(self, path: Path) -> Parsed:
        out = Parsed()
        cost = 0.0
        tool_args: dict[str, dict] = {}
        for event in iter_events(path):
            kind = event.get("type")
            if kind == "message_end" and (event.get("message") or {}).get("role") == "assistant":
                message = event["message"]
                text = "".join(b.get("text", "") for b in message.get("content", []) if b.get("type") == "text")
                out.final_text = text or out.final_text
                usage = message.get("usage") or {}
                out.input_tokens += usage.get("input", 0) + usage.get("cacheWrite", 0)
                out.output_tokens += usage.get("output", 0)
                out.cached_tokens += usage.get("cacheRead", 0)
                cost += (usage.get("cost") or {}).get("total", 0)
                # A failed turn that Pi retries successfully is followed by a clean
                # message, so only the last assistant message decides the outcome.
                # Hitting the output limit would otherwise look like a refusal.
                stop = message.get("stopReason")
                failed = stop in ("error", "aborted", "length")
                out.error = str(message.get("errorMessage") or f"pi run ended with {stop}") if failed else ""
            elif kind == "tool_execution_start":
                tool_args[event.get("toolCallId", "")] = event.get("args") or {}
            elif kind == "tool_execution_end":
                out.note_tool(event.get("toolName", ""), tool_args.get(event.get("toolCallId", ""), {}))
                result = event.get("result") or {}
                # The search helper's fee is not part of the model's usage.
                cost += (result.get("details") or {}).get("searchCostUsd", 0) or 0
                if event.get("isError"):
                    out.tool_errors += 1
                    if event.get("toolName") == "web_search":
                        content = result.get("content") or [{}]
                        out.note_search_error(str(content[0].get("text", "")))
        out.cost_usd = cost
        return out


GEMINI_SETTINGS = {
    "security": {"auth": {"selectedType": "gemini-api-key"}},
    "tools": {"core": ["google_web_search", "web_fetch"]},  # web tools only: no shell, no file tools
    "privacy": {"usageStatisticsEnabled": False},
    "telemetry": {"enabled": False},
    "general": {"disableAutoUpdate": True, "disableUpdateNag": True},
}
# USD per million tokens on Google's own API: input, output, cached. Gemini CLI also has a
# smaller model read pages and search results, so a run is priced model by model.
GOOGLE_PRICES = {
    "gemini-4-argon": (2.0, 10.0, 0.10),
    "gemini-3.8-flash": (0.825, 4.125, 0.0825),
    "gemini-3-flash-preview": (0.5, 3.0, 0.05),
}
GOOGLE_SEARCH_FEE = 0.014  # per search past Google's free allowance, so an upper bound


class GeminiCli:
    """Gemini CLI on a direct Google key, with only its web search and page reader."""

    # Its page reader treats a site it can't look up as private and skips it.
    needs_dns = True

    def setup(self, spec: Spec, room: Room) -> None:
        (room.home / ".gemini").mkdir()
        (room.home / ".gemini" / "settings.json").write_text(json.dumps(GEMINI_SETTINGS))

    def command(self, spec: Spec, room: Room) -> tuple[list[str], str | None]:
        # Gemini CLI has no effort setting: it always thinks at Gemini's highest level. The
        # empty room would fail its folder trust check, and nothing in it needs trusting.
        return [
            str(BIN / "gemini"), "-p", spec.prompt,
            "-m", spec.model_id,
            "-o", "stream-json",
            "--approval-mode", "yolo",
            "--skip-trust",
        ], None

    def env(self, spec: Spec, room: Room, keys: dict) -> dict:
        return {"GEMINI_API_KEY": keys[DIRECT_KEYS["gemini_cli"]]}

    def parse(self, path: Path) -> Parsed:
        out = Parsed()
        text = ""
        names: dict[str, str] = {}
        for event in iter_events(path):
            kind = event.get("type")
            if kind == "message" and event.get("role") == "assistant":
                text += event.get("content", "")
            elif kind == "tool_use":
                text = ""  # the answer is the text after the last tool call
                names[event.get("tool_id", "")] = event.get("tool_name", "")
                out.note_tool(event.get("tool_name", ""), event.get("parameters") or {})
            elif kind == "tool_result" and event.get("status") != "success":
                out.tool_errors += 1
                if names.get(event.get("tool_id", "")) in SEARCH_TOOLS:
                    out.note_search_error(str(event.get("output") or event.get("error")))
            elif kind == "result":
                cost = 0.0
                for name, used in ((event.get("stats") or {}).get("models") or {}).items():
                    uncached, cached = used.get("input", 0), used.get("cached", 0)
                    # Thinking is billed as output, and only the total includes it.
                    output = used.get("total_tokens", 0) - used.get("input_tokens", 0)
                    out.input_tokens += uncached
                    out.cached_tokens += cached
                    out.output_tokens += output
                    price_in, price_out, price_cached = GOOGLE_PRICES.get(name, GOOGLE_PRICES["gemini-4-argon"])
                    cost += (uncached * price_in + cached * price_cached + output * price_out) / 1_000_000
                out.cost_usd = cost + len(out.searches) * GOOGLE_SEARCH_FEE
                out.cost_estimated = True
                if event.get("status") != "success":
                    out.error = out.error or str(event.get("error") or f"gemini run ended with {event.get('status')}")
            elif kind == "error":
                out.error = str(event.get("message") or event.get("error") or "error")
        out.final_text = text
        return out


NATIVE = {
    "claude_code": ClaudeCode,
    "codex": Codex,
    "codex_openrouter": CodexOpenRouter,
    "gemini_cli": GeminiCli,
    "grok_build": GrokBuild,
}


def base_env(room: Room) -> dict:
    node = Path(shutil.which("node") or "/usr/local/bin/node").parent
    return {
        "PATH": f"{node}:/usr/bin:/bin",
        "HOME": str(room.home),
        "TMPDIR": str(room.tmp),
        "LANG": "en_US.UTF-8",
        "NO_COLOR": "1",
    }
