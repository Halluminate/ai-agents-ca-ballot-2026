#!/usr/bin/env python3
"""Write Codex's own model settings, adjusted for this experiment, as two catalogs.

codex_openai_catalog.json, for the OpenAI key: Codex's own entries for the GPT models, with
everything but its web tool taken out, as in every other harness: no apply_patch, no
sub-agents, no clock tools, no shell. Code mode stays, because Codex's own web tool,
web__run, is called from inside it.

codex_openrouter_catalog.json, for the OpenRouter key: the bundled entries
renamed to the OpenRouter slugs and switched from code mode (nested web__run -> POST
/v1/alpha/search, which OpenRouter does not serve) to the classic tool list with the hosted
Responses `web_search` tool.

Usage: python3 -m ballot codex-catalog <path to codex native binary>
The binary is node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex.
"""
import copy
import json
import sys
from pathlib import Path

from ballot.paths import DATA

OPENAI_MODELS = ("gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
# Bundled Codex slug -> OpenRouter slug. gpt-6-luna is the --cheap model.
OPENROUTER_MODELS = {"gpt-6-astra": "openai/gpt-6-astra", "gpt-6-luna": "openai/gpt-6-luna"}

# Shared by both: web tools only.
WEB_ONLY = {
    "shell_type": "disabled",            # second lock: no shell even if a --disable flag is lost
    "apply_patch_tool_type": None,       # no apply_patch tool
    "multi_agent_version": None,         # no collaboration/spawn_agent namespace
    "experimental_supported_tools": [],  # no clock / send_user_message_async
    "supports_search_tool": False,       # no client tool_search
}

OPENROUTER_OVERRIDES = WEB_ONLY | {
    "use_responses_lite": False,         # lite mode drops hosted web_search and uses additional_tools items
    "tool_mode": None,                   # leave code_mode_only, so no exec tool and no nested web__run
    "web_search_tool_type": "text",      # plain {"type":"web_search"} (no search_content_types)
    "prefer_websockets": False,          # OpenRouter has no Responses WebSocket (upgrade -> 404)
}

def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = Path(sys.argv[1]).read_bytes()
    start = data.find(b'{\n  "models": [')
    catalog, _ = json.JSONDecoder().raw_decode(data[start:start + 5_000_000].decode("utf-8", "replace"))
    bundled = {m["slug"]: m for m in catalog["models"]}

    openai = [copy.deepcopy(bundled[slug]) | WEB_ONLY for slug in OPENAI_MODELS]
    openrouter = [copy.deepcopy(bundled[slug]) | OPENROUTER_OVERRIDES | {"slug": OPENROUTER_MODELS[slug]}
                  for slug in OPENROUTER_MODELS]
    for name, entries in (("codex_openai_catalog.json", openai), ("codex_openrouter_catalog.json", openrouter)):
        with open(DATA / name, "w") as f:
            json.dump({"models": entries}, f, indent=1)
        print("wrote", name, [e["slug"] for e in entries])


if __name__ == "__main__":
    main()
