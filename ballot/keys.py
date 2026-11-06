#!/usr/bin/env python3
"""Save an API key to .env: OpenRouter (the default), OpenAI or Gemini.

Usage: python3 -m ballot keys [openrouter|openai|gemini] [--terminal]
       python3 -m ballot keys --check    tests every saved key again, without asking for one

On a Mac, a native window asks for the key in a hidden field. With --terminal, or if that
window can't open, a hidden terminal prompt asks instead. Either way the key never appears
on screen, in shell history, in a process list or in a chat. This script checks the key
with its service through a request that costs nothing, writes it to a private .env file
and never prints it. For OpenAI and Gemini it also says whether the key can use the models
the experiment needs.
"""

import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ballot.paths import ENV_FILE


@dataclass(frozen=True)
class Service:
    name: str
    env: str  # the variable in .env
    url: str  # a free request that needs the key
    header: str  # how the key is sent: never in the URL
    needs: tuple[str, ...] = ()  # models the experiment uses through this key


SERVICES = {
    "openrouter": Service("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/key", "Authorization"),
    # Codex uses its own web tool only with a direct OpenAI key.
    "openai": Service("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1/models", "Authorization",
                      ("gpt-6-astra", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")),
    # Gemini CLI only talks to Google. Google accepts the key in this header instead of the URL.
    "gemini": Service("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                      "x-goog-api-key", ("gemini-4-argon", "gemini-3.8-flash")),
}

ASK_WINDOW = """
activate
set reply to display dialog "Paste your {name} key, then click Save. It stays hidden and is saved only to the .env file in this experiment." default answer "" with title "{name} key" with hidden answer buttons {{"Cancel", "Save"}} default button "Save" giving up after 600
if gave up of reply then error number -128
return text returned of reply
"""
RESULT_WINDOW = """
activate
display dialog "{message}" with title "{name} key" buttons {{"OK"}} default button "OK" giving up after 60
"""


def check_key(service: Service, key: str) -> tuple[bool | None, dict]:
    """True if the service accepts the key, False if it refuses, None if it can't tell."""
    value = key if service.header == "x-goog-api-key" else f"Bearer {key}"
    request = urllib.request.Request(service.url, headers={service.header: value, "User-Agent": "ca-ballot-experiment/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return True, json.load(response)
    except urllib.error.HTTPError as e:
        # Google answers a bad key with 400, the others with 401 or 403.
        return (False if e.code in (400, 401, 403) else None), {}
    except (OSError, ValueError):
        return None, {}


def model_names(body: dict) -> set[str]:
    """Model ids from OpenAI's list ("data") or Google's ("models", named "models/<id>")."""
    names = {m.get("id", "") for m in body.get("data") or [] if isinstance(m, dict)}
    names |= {m.get("name", "").removeprefix("models/") for m in body.get("models") or [] if isinstance(m, dict)}
    return names - {""}


def describe(service: Service, body: dict) -> str:
    """What the check found, without the key."""
    if not service.needs:
        remaining = (body.get("data") or {}).get("limit_remaining")
        return f" Spending limit left on this key: ${remaining:.2f}." if isinstance(remaining, (int, float)) else ""
    names = model_names(body)
    missing = [m for m in service.needs if m not in names]
    if not missing:
        return " It can use every model the experiment needs: " + ", ".join(service.needs) + "."
    return f" It can't see {', '.join(missing)}. The experiment needs {', '.join(service.needs)}."


def save_key(service: Service, key: str) -> None:
    """Replace .env in one step. mkstemp makes the new file readable only by you."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith(f"{service.env}=")]
    fd, partial = tempfile.mkstemp(dir=ENV_FILE.parent, prefix=".env.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join([f"{service.env}={key}", *lines]) + "\n")
        os.replace(partial, ENV_FILE)
    except BaseException:
        Path(partial).unlink(missing_ok=True)
        raise


def saved_keys() -> dict[str, str]:
    keys = {}
    for line in ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []:
        name, sep, value = line.partition("=")
        if sep and value.strip() and not name.startswith("#"):
            keys[name.strip()] = value.strip()
    return keys


def check_saved() -> None:
    """Test every saved key again. Prints only what each service said."""
    keys = saved_keys()
    for service in SERVICES.values():
        key = keys.get(service.env)
        if not key:
            print(f"{service.name}: no key saved.")
            continue
        accepted, body = check_key(service, key)
        verdict = {True: "accepted", False: "REJECTED", None: "couldn't be checked just now"}[accepted]
        print(f"{service.name}: key {verdict}." + (describe(service, body) if accepted else ""))


def ask_in_window(service: Service) -> str | None:
    """Ask in a native window. The key comes back over a pipe, never in a command line.

    Returns None if the window can't open, so the caller can use the terminal instead.
    """
    result = subprocess.run(["osascript", "-e", ASK_WINDOW.format(name=service.name)], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    if "-128" in result.stderr:  # the Cancel button, or the window timing out
        sys.exit("Cancelled. .env was not changed.")
    return None


def ask_in_terminal(service: Service) -> str:
    if not sys.stdin.isatty():
        sys.exit("Run this in a terminal, so the key can stay hidden.")
    return getpass.getpass(f"Paste your {service.name} key, then press Enter (it stays hidden): ")


def clean(key: str) -> str:
    """Drop the invisible markers some terminals wrap around pasted text."""
    return key.replace("\x1b[200~", "").replace("\x1b[201~", "").strip()


def main() -> None:
    if "--check" in sys.argv:
        check_saved()
        return
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    service = SERVICES.get(names[0] if names else "openrouter")
    if service is None:
        sys.exit(__doc__)
    in_window = sys.platform == "darwin" and "--terminal" not in sys.argv
    key = ask_in_window(service) if in_window else None
    if key is None:
        in_window = False
        key = ask_in_terminal(service)
    key = clean(key)

    def finish(message: str, failed: bool = False) -> None:
        if in_window:
            subprocess.run(["osascript", "-e", RESULT_WINDOW.format(message=message, name=service.name)], capture_output=True)
        if failed:
            sys.exit(message)
        print(message)

    if not key:
        finish("Nothing entered. .env was not changed.", failed=True)
    if not re.fullmatch(r"[\x21-\x7e]+", key):
        finish("That doesn't look like a single key. .env was not changed.", failed=True)

    accepted, body = check_key(service, key)
    if accepted is False:
        finish(f"{service.name} rejected that key. .env was not changed.", failed=True)

    save_key(service, key)
    if accepted is None:
        finish(f"Key saved, but {service.name} couldn't confirm it just now. Run python3 -m ballot keys --check to test it again.")
        return
    finish(f"Key saved. {service.name} accepted it.{describe(service, body)}")


if __name__ == "__main__":
    main()
