#!/usr/bin/env python3
"""Check the keys, the models, Pi's settings and the harnesses. Spends nothing."""

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from ballot.config import DIRECT_KEYS, KEY, load_config, load_keys
from ballot.harnesses import PI_MODEL_OVERRIDES
from ballot.keys import SERVICES, check_key, describe, model_names
from ballot.paths import BIN, DATA, ROOT

USER_AGENT = "ca-ballot-experiment/1.0"


def get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (OSError, ValueError):
        return 0, {}


def codex_bundled_models() -> set[str] | None:
    """The models Codex has its own settings for, read from its program file."""
    binary = next(ROOT.glob("node_modules/@openai/codex-*/vendor/*/bin/codex"), None)
    if binary is None:
        return None
    data = binary.read_bytes()
    start = data.find(b'{\n  "models": [')
    catalog, _ = json.JSONDecoder().raw_decode(data[start:start + 5_000_000].decode("utf-8", "replace"))
    return {m["slug"] for m in catalog["models"]}


def catalog_models(name: str) -> set[str]:
    return {m["slug"] for m in json.loads((DATA / name).read_text())["models"]}


def main() -> None:
    cfg = load_config()
    failures = 0

    def report(ok: bool, label: str, note: str) -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {label}: {note}")

    # Each key is checked with a request that costs nothing.
    keys = load_keys()
    natives = {m["native"] for m in cfg["models"]}
    for name, service in SERVICES.items():
        harness = next((h for h, env in DIRECT_KEYS.items() if env == service.env), None)
        if service.env not in keys:
            if service.env == KEY or harness in natives:
                report(False, f"{name} key", f"{service.env} is not set. Run python3 -m ballot keys {name}")
            continue
        accepted, body = check_key(service, keys[service.env])
        verdict = {True: "accepted.", False: "rejected.", None: "couldn't be checked just now."}[accepted]
        report(accepted is True, f"{name} key", verdict + (describe(service, body) if accepted and not service.needs else ""))
        if accepted and harness:
            # The models this harness runs, by the vendor's own ids.
            wanted = {m[k] for m in cfg["models"] if m["native"] == harness for k in ("native_model", "native_cheap_model") if m.get(k)}
            missing = sorted(wanted - model_names(body))
            report(not missing, f"{name} models", f"the key can use {', '.join(sorted(wanted))}" if not missing
                   else f"the key can't see {', '.join(missing)}")

    status, listing = get("https://openrouter.ai/api/v1/models")
    available = {m["id"] for m in listing.get("data") or []}
    wanted = [m["model"] for m in cfg["models"]] + [m["cheap_model"] for m in cfg["models"]]
    wanted += [cfg["search"]["helper_model"], "x-ai/grok-4.6", "anthropic/claude-haiku-5.5"]
    for model_id in dict.fromkeys(wanted):
        report(model_id in available, model_id, "listed on OpenRouter" if model_id in available else "not listed")

    # pi -p ignores a broken models.json without a word, so load it the way a run does.
    with tempfile.TemporaryDirectory() as home:
        agent_dir = Path(home) / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "models.json").write_text(json.dumps({"providers": {"openrouter": {"modelOverrides": PI_MODEL_OVERRIDES}}}))
        env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": home, "PI_CODING_AGENT_DIR": str(agent_dir),
               "PI_OFFLINE": "1", "OPENROUTER_API_KEY": "not-a-real-key"}
        result = subprocess.run([str(BIN / "pi"), "--list-models", "openrouter"], capture_output=True, text=True, env=env, timeout=120)
        output = result.stdout + result.stderr
        broken = "error" in output.lower() and "models.json" in output
        missing = [m["model"] for m in cfg["models"] if m["model"] not in output]
        report(not broken and not missing, "pi models.json",
               "loads, and every model is in Pi's catalog" if not broken and not missing else f"broken or missing: {missing or output[-200:]}")

    if "codex" in natives:
        slugs = codex_bundled_models()
        wanted = {m[k] for m in cfg["models"] if m["native"] == "codex" for k in ("native_model", "native_cheap_model") if m.get(k)}
        missing = sorted(wanted - (slugs or set()))
        report(slugs is not None and not missing, "codex models",
               f"Codex has its own settings for {', '.join(sorted(wanted))}" if slugs is not None and not missing
               else f"Codex has no settings for {', '.join(missing) or 'anything: program not found'}")
        missing = sorted(wanted - catalog_models("codex_openai_catalog.json"))
        report(not missing, "codex catalog", "codex_openai_catalog.json has every model" if not missing
               else f"codex_openai_catalog.json is missing {', '.join(missing)}. Run python3 -m ballot codex-catalog")
    if "codex_openrouter" in natives:
        slugs = catalog_models("codex_openrouter_catalog.json")
        ids = {m[k] for m in cfg["models"] if m["native"] == "codex_openrouter" for k in ("model", "cheap_model")}
        report(ids <= slugs, "codex openrouter catalog", f"has {sorted(slugs)}")

    for tool in ("claude", "codex", "gemini", "grok", "pi"):
        path = BIN / tool
        if not path.exists():
            report(False, tool, "not installed. Run npm install, then npm rebuild @anthropic-ai/claude-code")
            continue
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=120)
        output = (result.stdout or result.stderr).strip()
        report(result.returncode == 0, tool, output.splitlines()[0] if output else "no output")

    print("\nAll checks passed." if not failures else f"\n{failures} checks failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
