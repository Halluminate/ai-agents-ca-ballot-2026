"""Record all network traffic of one experiment run.

Each run gets its own mitmproxy on a free 127.0.0.1 port, and the harness runs
under a macOS sandbox that only lets it connect to that port. The proxy writes
every request and response, with full bodies, to network.jsonl.gz in the run
folder. Anything that ignores the proxy settings fails instead of reaching the
internet unrecorded. API keys are redacted before anything is written.

How run.py uses it, in attempt(), once per attempt:

    capture = NetworkCapture(run_dir, secrets=list(keys.values()))
    await capture.start()  # raises if the capture cannot run: no run goes unrecorded
    try:
        env = base_env(room) | harness.env(spec, room, keys) | capture.env()  # capture.env() last
        returncode, timed_out = await run_process(capture.wrap(cmd), stdin, env, room, run_dir, timeout)
    finally:
        network = await capture.stop()  # after the harness exited or was killed
    warnings += problems(network)  # anything that makes the record less than complete

Each run folder then holds network.jsonl.gz (every record), network_summary.json
(what stop() returned) and proxy.log (mitmproxy's own warnings). A retry moves the
earlier attempt's files to network.failed-1.jsonl.gz and so on, as run.py does
with events.jsonl. read_log() loads a network.jsonl.gz.

DNS: the sandbox also refuses the system resolver (block_dns, on by default).
A lookup sends the hostname to DNS servers outside the record, and a hostname can
carry data. Nothing that uses the proxy needs DNS, because the proxy resolves names;
all four harnesses were checked to run unchanged without it. A refused lookup is
reported like any refused connection.

What is not in the record: the exact address of a refused connection (macOS hides
it, and rate-limits its reports, so blocked_by_sandbox is best-effort; the refusal
itself is not), and with block_dns=False, DNS lookups.

The sandbox also stops the harness from writing to the capture's own files (this
folder's .mitmproxy, .venv-netlog and netlog files) and to the run folder, so a
run cannot change its own record or turn the capture off for later runs.

The proxy, its CA and its trust bundle live in this folder (.venv-netlog and
.mitmproxy), never in the home folder. Set them up once with:

    uv venv .venv-netlog
    uv pip install --python .venv-netlog/bin/python mitmproxy
"""

from __future__ import annotations

import asyncio
import atexit
import fcntl
import gzip
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from ballot.paths import PACKAGE, ROOT

VENV = ROOT / ".venv-netlog"
MITMDUMP = VENV / "bin" / "mitmdump"
VENV_PYTHON = VENV / "bin" / "python"
CONFDIR = ROOT / ".mitmproxy"
CA_CERT = CONFDIR / "mitmproxy-ca-cert.pem"
CA_BUNDLE = CONFDIR / "ca-bundle.pem"
ADDON = PACKAGE / "netlog_addon.py"
PROFILE = PACKAGE / "netlog.sb"
MODULE = Path(__file__).resolve()
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
LOG_TOOL = "/usr/bin/log"
MDNS_SOCKET = "/private/var/run/mDNSResponder"
# mitmproxy reads options from these, and an option such as ignore_hosts would let
# traffic through unrecorded, so the capture refuses to start while one exists.
MITMPROXY_CONFIGS = (CONFDIR / "config.yaml", CONFDIR / "config.yml",
                     CONFDIR / ".mitmproxy" / "config.yaml", CONFDIR / ".mitmproxy" / "config.yml")

LOG_NAME = "network.jsonl"  # written live during the run, removed once gzipped
GZ_NAME = "network.jsonl.gz"
PROXY_LOG_NAME = "proxy.log"
SUMMARY_NAME = "network_summary.json"

REDACTED = "<redacted>"
MIN_SECRET_LENGTH = 8
START_TIMEOUT = 30.0
STOP_TIMEOUT = 20.0
SETTLE_SECONDS = 3.0  # how long stop() waits for connections the harness left open
DENIAL_LAG_SECONDS = 1.5  # the kernel's sandbox reports reach `log stream` with a short delay
DENIAL = re.compile(r"^(?:(\d+) duplicate reports? for )?Sandbox: (.+)\((\d+)\) deny\(\d+\) (\S+)\s*(.*?)\s*$")

_LIVE: set[int] = set()  # mitmdump and log pids to interrupt if the runner exits without stop()


def _interrupt_live() -> None:
    for pid in list(_LIVE):
        try:
            os.kill(pid, signal.SIGINT)  # mitmdump flushes its log on SIGINT
        except ProcessLookupError:
            pass


atexit.register(_interrupt_live)


class NetlogError(RuntimeError):
    pass


def check_install() -> None:
    missing = [p for p in (MITMDUMP, ADDON, PROFILE) if not p.exists()]
    if missing:
        raise NetlogError(
            "Network capture is not set up. Missing: " + ", ".join(str(p) for p in missing)
            + ". Run: uv venv .venv-netlog && uv pip install --python .venv-netlog/bin/python mitmproxy"
        )
    if not os.access(SANDBOX_EXEC, os.X_OK):
        raise NetlogError(f"{SANDBOX_EXEC} is missing; the capture needs the macOS sandbox.")
    found = [str(p) for p in MITMPROXY_CONFIGS if p.exists()]
    if found:
        raise NetlogError("mitmproxy would load options from " + ", ".join(found)
                          + "; options there (such as ignore_hosts) can exempt traffic from the record. Remove it.")


def ensure_ca() -> None:
    """Create the proxy CA once, plus a bundle of the public roots and that CA."""
    CONFDIR.mkdir(mode=0o700, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(CONFDIR)}
    with open(CONFDIR / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # concurrent runs must not create two CAs
        if not CA_CERT.exists():
            subprocess.run(
                [str(VENV_PYTHON), "-I", "-c",
                 "import sys; from mitmproxy.certs import CertStore; CertStore.from_store(sys.argv[1], 'mitmproxy', 2048)",
                 str(CONFDIR)],
                check=True, env=env, capture_output=True,
            )
        if not CA_BUNDLE.exists() or CA_BUNDLE.stat().st_mtime < CA_CERT.stat().st_mtime:
            roots = subprocess.run(
                [str(VENV_PYTHON), "-I", "-c", "import certifi; print(certifi.where())"],
                check=True, env=env, capture_output=True, text=True,
            ).stdout.strip()
            bundle = Path(roots).read_bytes().rstrip() + b"\n\n# Experiment capture proxy CA\n" + CA_CERT.read_bytes()
            tmp = CA_BUNDLE.with_name(CA_BUNDLE.name + ".tmp")
            tmp.write_bytes(bundle)
            os.replace(tmp, CA_BUNDLE)


def clean_secrets(secrets) -> list[str]:
    out = []
    for secret in secrets or []:
        secret = (secret or "").strip()
        if not secret:
            continue
        if len(secret) < MIN_SECRET_LENGTH:
            # Redacting a very short string would shred the whole log; real keys are long.
            print(f"netlog: ignoring a secret shorter than {MIN_SECRET_LENGTH} characters", file=sys.stderr)
            continue
        out.append(secret)
    return sorted(set(out), key=len, reverse=True)


def secret_variants(secret: str) -> set[str]:
    """Every form of a secret the log could hold. Identical to the copy in netlog_addon.py (a test checks)."""
    import base64
    from urllib.parse import quote, quote_plus

    variants = {secret, secret.replace("/", "\\/")}
    for safe in ("", "/"):
        for encoded in (quote(secret, safe=safe), quote_plus(secret, safe=safe)):
            variants.add(encoded)
            variants.add(re.sub("%[0-9A-F]{2}", lambda m: m.group(0).lower(), encoded))
    raw = secret.encode()
    for offset in range(3):
        encoded = base64.b64encode(b"\0" * offset + raw).decode()
        core = encoded[(8 * offset + 5) // 6:(8 * offset + 8 * len(raw)) // 6]
        if len(core) >= 8:
            variants |= {core, core.replace("+", "-").replace("/", "_")}
    return {v for v in variants if v}


def redact_bytes(data: bytes, secrets: list[str]) -> tuple[bytes, int]:
    """Last line of defence: the addon already redacts, so a hit here is a bug."""
    hits = 0
    variants = set()
    for secret in secrets:
        variants |= secret_variants(secret)
    for variant in sorted(variants, key=len, reverse=True):
        raw = variant.encode()
        count = data.count(raw)
        if count:
            hits += count
            data = data.replace(raw, REDACTED.encode())
    return data, hits


class NetworkCapture:
    """One proxy and one sandbox for one run. See the module docstring."""

    def __init__(self, run_dir: Path, secrets: list[str], *, block_dns: bool = True, idle_timeout: int = 7200,
                 upstream_ca: Path | None = None):
        self.run_dir = Path(run_dir)
        self.secrets = clean_secrets(secrets)
        self.block_dns = block_dns
        # Tests only: a CA the proxy trusts for upstream servers instead of the public
        # roots, so local TLS servers can stand in for real ones.
        self.upstream_ca = upstream_ca
        # The proxy closes a connection after this long with no bytes at all. It
        # is far above any run's timeout, so the proxy never cuts a slow request.
        self.idle_timeout = idle_timeout
        self.port: int | None = None
        self.proc: asyncio.subprocess.Process | None = None
        self.summary: dict | None = None
        self.log_path = self.run_dir / LOG_NAME
        # Every connection the sandbox refuses is reported by the kernel with this tag.
        self.tag = f"netlog-{uuid.uuid4().hex}"
        self.denials: list[dict] = []
        self.denial_log_error: str | None = None
        self._private: Path | None = None
        self._pump: asyncio.Task | None = None
        self._watch: asyncio.subprocess.Process | None = None
        self._watch_task: asyncio.Task | None = None
        self._offset = 0
        self._open: set[str] = set()

    async def __aenter__(self) -> "NetworkCapture":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    # ---- start --------------------------------------------------------------

    async def start(self) -> None:
        if self.proc is not None:
            raise NetlogError("this capture was already started; use one NetworkCapture per run")
        check_install()
        ensure_ca()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        archive_previous(self.run_dir)
        self._private = Path(tempfile.mkdtemp(prefix="netlog-"))
        ready = self._private / "ready.json"
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(CONFDIR),
            "LANG": "en_US.UTF-8",
            "NETLOG_FILE": str(self.log_path),
            "NETLOG_READY": str(ready),
            "NETLOG_SECRETS": "\n".join(self.secrets),
        }
        args = [
            str(MITMDUMP),
            "--listen-host", "127.0.0.1", "--listen-port", "0",
            "--set", f"confdir={CONFDIR}",
            "-s", str(ADDON),
            "--set", "flow_detail=0",
            "--set", "termlog_verbosity=warn",
            "--set", "onboarding=false",
            "--set", "ssl_insecure=false",
            "--set", f"tcp_timeout={self.idle_timeout}",
        ]
        if self.upstream_ca is not None:
            args += ["--set", f"ssl_verify_upstream_trusted_ca={self.upstream_ca}"]
        await self._watch_denials()
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, env=env, cwd=str(CONFDIR),
            )
            _LIVE.add(self.proc.pid)
            self._pump = asyncio.create_task(self._pump_proxy_log())
            deadline = time.monotonic() + START_TIMEOUT
            while not ready.exists():
                if self.proc.returncode is not None:
                    await self._pump
                    raise NetlogError(f"mitmdump exited with {self.proc.returncode}: {self._proxy_log_tail()}")
                if time.monotonic() > deadline:
                    raise NetlogError(f"mitmdump did not start within {START_TIMEOUT:.0f}s: {self._proxy_log_tail()}")
                await asyncio.sleep(0.05)
            info = json.loads(ready.read_text())
            ports = [addr[1] for addr in info["listen"] if addr and addr[0] == "127.0.0.1"]
            if not ports:
                raise NetlogError(f"mitmdump is not listening on 127.0.0.1: {info['listen']}")
            self.port = int(ports[0])
            # It listens; check it accepts too. This empty connection shows up in the
            # log with zero bytes and is counted as "empty", not as traffic.
            reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", self.port), 5)
            writer.close()
            await writer.wait_closed()
        except BaseException:
            # Never leave a proxy or a log follower running for a run that will not happen.
            await self._kill()
            await self._stop_watch()
            if self.proc is not None:
                _LIVE.discard(self.proc.pid)
            raise

    async def _watch_denials(self) -> None:
        """Follow the kernel's reports of connections this run's sandbox refused."""
        predicate = f'sender == "Sandbox" AND eventMessage CONTAINS "{self.tag}"'
        try:
            self._watch = await asyncio.create_subprocess_exec(
                LOG_TOOL, "stream", "--style", "ndjson", "--predicate", predicate,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _LIVE.add(self._watch.pid)
            # `log stream` prints one header line once it is following the log.
            header = await asyncio.wait_for(self._watch.stdout.readline(), 10)
            if not header.startswith(b"Filtering the log data"):
                raise OSError(header.decode(errors="replace").strip()[:200] or "log stream exited")
        except (OSError, asyncio.TimeoutError) as e:
            self.denial_log_error = f"log stream unavailable: {type(e).__name__}: {e}"
            if self._watch is not None:
                if self._watch.returncode is None:
                    self._watch.kill()
                await self._watch.wait()
                _LIVE.discard(self._watch.pid)
            self._watch = None
            return
        self._watch_task = asyncio.create_task(self._read_denials())

    async def _read_denials(self) -> None:
        assert self._watch is not None and self._watch.stdout is not None
        async for line in self._watch.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            message = str(event.get("eventMessage", "")).split("\n")[0]
            match = DENIAL.match(message)
            when = time.time()
            try:
                when = datetime.strptime(event.get("timestamp", ""), "%Y-%m-%d %H:%M:%S.%f%z").timestamp()
            except ValueError:
                pass
            record = {"type": "sandbox_denied", "time": when, "message": message}
            if match:
                record.update({"count": int(match.group(1) or 1), "process": match.group(2),
                               "pid": int(match.group(3)), "operation": match.group(4),
                               "target": match.group(5) or None})
            self.denials.append(record)

    async def _stop_watch(self) -> None:
        if self._watch is None:
            return
        if self._watch.returncode is None:
            self._watch.terminate()
        try:
            await asyncio.wait_for(self._watch.wait(), 5)
        except asyncio.TimeoutError:
            self._watch.kill()
            await self._watch.wait()
        if self._watch_task is not None:
            try:
                await asyncio.wait_for(self._watch_task, 5)
            except asyncio.TimeoutError:
                self._watch_task.cancel()
        _LIVE.discard(self._watch.pid)

    async def _pump_proxy_log(self) -> None:
        """Copy mitmdump's own output to proxy.log, redacted on the way.

        It reads in blocks, not lines: a line longer than asyncio's 64 KiB line limit
        would end a line reader, and mitmdump would then block on a full pipe and stall
        every connection of the run. It never stops reading before mitmdump exits.
        """
        assert self.proc is not None and self.proc.stdout is not None
        pending = b""
        with open(self.run_dir / PROXY_LOG_NAME, "ab") as out:
            while True:
                try:
                    block = await self.proc.stdout.read(65536)
                except Exception as e:  # noqa: BLE001
                    out.write(f"\nnetlog: reading mitmdump output failed: {type(e).__name__}\n".encode())
                    break
                if not block:
                    break
                pending += block
                end = pending.rfind(b"\n") + 1
                if end:
                    out.write(redact_bytes(pending[:end], self.secrets)[0])
                    out.flush()
                    pending = pending[end:]
                elif len(pending) > 1 << 20:
                    # One very long line: write it in pieces. After redaction no whole secret
                    # crosses the cut, and the last 4 KiB can still finish a secret.
                    pending = redact_bytes(pending, self.secrets)[0]
                    out.write(pending[:-4096])
                    out.flush()
                    pending = pending[-4096:]
            if pending:
                out.write(redact_bytes(pending, self.secrets)[0])

    def _proxy_log_tail(self) -> str:
        path = self.run_dir / PROXY_LOG_NAME
        return path.read_text(errors="replace")[-1500:] if path.exists() else ""

    # ---- what the harness gets ----------------------------------------------

    def env(self) -> dict:
        """Variables that send the four CLIs through the proxy and make them trust its CA."""
        if self.port is None:
            raise NetlogError("start() the capture before asking for its env")
        proxy = f"http://127.0.0.1:{self.port}"
        return {
            "HTTPS_PROXY": proxy, "https_proxy": proxy,
            "HTTP_PROXY": proxy, "http_proxy": proxy,
            "ALL_PROXY": proxy, "all_proxy": proxy,
            "NO_PROXY": "", "no_proxy": "",  # nothing bypasses the proxy
            "NODE_USE_ENV_PROXY": "1",  # Node's fetch and http ignore the variables above without it
            "NODE_EXTRA_CA_CERTS": str(CA_CERT),  # Node (Pi) and Bun (Claude Code)
            "SSL_CERT_FILE": str(CA_BUNDLE),  # Rust clients (Codex, Grok Build)
            "CODEX_CA_CERTIFICATE": str(CA_BUNDLE),  # Codex reads this before SSL_CERT_FILE
            "GROK_EXTRA_CA_BUNDLE": str(CA_CERT),  # Grok Build adds this to its roots
            "GIT_SSL_CAINFO": str(CA_BUNDLE),  # Codex runs git to sync its plugin repo from github.com
            "REQUESTS_CA_BUNDLE": str(CA_BUNDLE),
            "CURL_CA_BUNDLE": str(CA_BUNDLE),
        }

    def wrap(self, cmd: list[str]) -> list[str]:
        """Run cmd in a sandbox that can only connect to this proxy (and unix sockets).

        It also cannot write to the capture's own files or to the run folder (run.py
        opens events.jsonl and stderr.log before the harness starts, so those work).
        """
        if self.port is None:
            raise NetlogError("start() the capture before wrapping a command")
        args = [SANDBOX_EXEC, "-f", str(PROFILE), "-D", f"PROXY_PORT={self.port}", "-D", f"RUN_TAG={self.tag}"]
        protected = {"CONFDIR": CONFDIR, "VENV": VENV, "ADDON": ADDON, "PROFILE": PROFILE, "MODULE": MODULE,
                     "RUN_DIR": self.run_dir}
        for name, path in protected.items():
            args += ["-D", f"{name}={os.path.realpath(path)}"]
        if self.block_dns:
            args += ["-D", "BLOCK_DNS=1"]
        return args + [str(c) for c in cmd]

    # ---- stop ---------------------------------------------------------------

    async def stop(self) -> dict:
        """Stop the proxy cleanly, gzip the log and return a summary. Safe to call twice."""
        if self.summary is not None:
            return self.summary
        if self.proc is None:
            await self._stop_watch()
            return {}
        settle_started = time.monotonic()
        await self._settle()
        clean = False
        if self.proc.returncode is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(self.proc.wait(), STOP_TIMEOUT)
                clean = True
            except asyncio.TimeoutError:
                await self._kill()
        else:
            await self.proc.wait()
        if self._pump is not None:
            try:
                await asyncio.wait_for(self._pump, 5)
            except asyncio.TimeoutError:
                self._pump.cancel()
            except Exception:  # noqa: BLE001 - proxy.log is secondary; the record must still be finished
                pass
        _LIVE.discard(self.proc.pid)
        if self._private is not None:
            shutil.rmtree(self._private, ignore_errors=True)
        lag = DENIAL_LAG_SECONDS - (time.monotonic() - settle_started)
        if self._watch is not None and lag > 0:
            await asyncio.sleep(lag)
        await self._stop_watch()
        dns = "blocked" if self.block_dns else "allowed, not recorded"
        try:
            self.summary = finish(self.run_dir, self.secrets, exit_code=self.proc.returncode, stopped_cleanly=clean,
                                  denials=self.denials, denial_log_error=self.denial_log_error, dns=dns)
        except Exception as e:  # noqa: BLE001
            # Never lose the run over this: network.jsonl stays on disk as the addon wrote
            # it (already redacted), and problems() reports the failure.
            error = redact_bytes(f"finishing the record failed: {type(e).__name__}: {e}"[:500].encode(), self.secrets)[0]
            self.summary = {"capture_error": error.decode(errors="replace"),
                            "log": LOG_NAME, "proxy_exit_code": self.proc.returncode,
                            "proxy_stopped_cleanly": clean, "sandbox_log": self.denial_log_error or "ok", "dns": dns}
        return self.summary

    async def _settle(self) -> None:
        """Give the proxy a moment to finish flows whose client just exited."""
        deadline = time.monotonic() + SETTLE_SECONDS
        while True:
            self._read_new_records()
            if not self._open or time.monotonic() > deadline or self.proc.returncode is not None:
                return
            await asyncio.sleep(0.05)

    def _read_new_records(self) -> None:
        if not self.log_path.exists():
            return
        with open(self.log_path, "rb") as f:
            f.seek(self._offset)
            data = f.read()
        end = data.rfind(b"\n") + 1
        self._offset += end
        for line in data[:end].splitlines():
            # Only connection records matter here; skip parsing bodies, which can be large.
            if not line.startswith((b'{"type": "client_connect"', b'{"type": "client_disconnect"')):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "client_connect":
                self._open.add(record.get("conn"))
            elif record.get("type") == "client_disconnect":
                self._open.discard(record.get("conn"))

    async def _kill(self) -> None:
        if self.proc is None or self.proc.returncode is not None:
            return
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), 5)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()


CAPTURE_FILES = (GZ_NAME, LOG_NAME, SUMMARY_NAME, PROXY_LOG_NAME)


def archive_previous(run_dir: Path) -> None:
    """A retry reuses the run folder, so keep the earlier attempt's capture, as run.py keeps its events.

    network.jsonl.gz becomes network.failed-1.jsonl.gz, and so on. A network.jsonl
    without a .gz is from an attempt that never reached stop(); it is kept as is.
    """
    present = [name for name in CAPTURE_FILES if (run_dir / name).exists()]
    if not present:
        return
    number = 1
    while any((run_dir / _numbered(name, number)).exists() for name in CAPTURE_FILES):
        number += 1
    for name in present:
        (run_dir / name).rename(run_dir / _numbered(name, number))


def _numbered(name: str, number: int) -> str:
    stem, dot, rest = name.partition(".")
    return f"{stem}.failed-{number}{dot}{rest}"


def problems(summary: dict) -> list[str]:
    """Plain warnings for anything that makes this run's record less than complete."""
    out = []
    if not summary:
        return ["no network capture for this run"]
    if summary.get("capture_error"):
        out.append(f"{summary['capture_error']}; the raw record is in {LOG_NAME}")
    blocked = summary.get("blocked_by_sandbox", [])
    groups = {
        "DNS lookups were refused (the proxy resolves names; something tried the system resolver)":
            [b for b in blocked if b["target"] == MDNS_SOCKET],
        "connection attempts that ignored the proxy were blocked":
            [b for b in blocked if str(b["operation"]).startswith("network") and b["target"] != MDNS_SOCKET],
        "writes to the capture's files or the run folder were refused":
            [b for b in blocked if str(b["operation"]).startswith("file")],
    }
    other = [b for b in blocked if not any(b in g for g in groups.values())]
    groups["other operations were refused by the sandbox"] = other
    for label, group in groups.items():
        if group:
            who = ", ".join(f"{b['process']} {b['target'] or b['operation']} x{b['attempts']}" for b in group[:3])
            out.append(f"{sum(b['attempts'] for b in group)} {label} ({who})")
    if summary.get("not_intercepted"):
        hosts = ", ".join(sorted({f"{c['host']}:{c['port']}" for c in summary["not_intercepted"]}))
        out.append(f"{len(summary['not_intercepted'])} connections were not readable by the proxy ({hosts})")
    if summary.get("sandbox_log") != "ok":
        out.append(f"blocked attempts were not recorded: {summary.get('sandbox_log')}")
    if not summary.get("proxy_stopped_cleanly"):
        out.append(f"capture proxy did not stop cleanly (exit {summary.get('proxy_exit_code')}); "
                   "flows in progress at that moment may be missing")
    if summary.get("addon_errors"):
        out.append(f"capture addon failed {summary['addon_errors']} times; see error_details")
    if summary.get("proxy_log_errors"):
        out.append(f"mitmproxy reported {summary['proxy_log_errors']} errors; see {PROXY_LOG_NAME}")
    if summary.get("secrets_redacted_at_stop"):
        out.append(f"{summary['secrets_redacted_at_stop']} secrets reached the raw log and were redacted at stop")
    if "byte_counter" in summary and not summary["byte_counter"]:
        out.append("the proxy could not count socket bytes, so an unreadable connection may be missing "
                   "from not_intercepted")
    if summary.get("incomplete_flows"):
        out.append(f"{summary['incomplete_flows']} requests were still open when the capture stopped; "
                   "their records end at that point")
    if summary.get("tcp_flows"):
        out.append(f"{summary['tcp_flows']} connections carried raw TCP rather than HTTP; their bytes are recorded "
                   "but may not be readable")
    if summary.get("dns") == "allowed, not recorded":
        out.append("DNS lookups were allowed and are not in the record (block_dns=False)")
    return out


def finish(run_dir: Path, secrets: list[str], exit_code: int | None = None, stopped_cleanly: bool = False,
           denials: list[dict] | None = None, denial_log_error: str | None = None, dns: str | None = None) -> dict:
    """Redact once more, add the sandbox's refusals, gzip network.jsonl, write the summary and return it."""
    raw_path = run_dir / LOG_NAME
    data = raw_path.read_bytes() if raw_path.exists() else b""
    if data and not data.endswith(b"\n"):
        data += b"\n"
    for record in denials or []:
        data += json.dumps(record, ensure_ascii=True).encode() + b"\n"
    data, hits = redact_bytes(data, secrets)
    proxy_log = run_dir / PROXY_LOG_NAME
    proxy_log_errors = 0
    if proxy_log.exists():
        text, proxy_hits = redact_bytes(proxy_log.read_bytes(), secrets)
        if proxy_hits:
            proxy_log.write_bytes(text)
        hits += proxy_hits
        # mitmproxy logs an addon that raised (for example a failed write) and its own crashes here.
        proxy_log_errors = sum(1 for line in text.splitlines()
                               if b"Addon error" in line or b"Traceback (most recent call last)" in line)
    records = []
    for line in data.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    summary = summarize(records)
    summary.update({
        "log": GZ_NAME,
        "sandbox_log": denial_log_error or "ok",
        "proxy_exit_code": exit_code,
        "proxy_stopped_cleanly": stopped_cleanly and any(r.get("type") == "proxy_stop" for r in records),
        "proxy_log_errors": proxy_log_errors,
        "secrets_redacted_at_stop": hits,  # should always be 0: the addon redacts first
        "dns": dns,
    })
    gz_path = run_dir / GZ_NAME
    tmp = run_dir / (GZ_NAME + ".tmp")
    with gzip.open(tmp, "wb", compresslevel=6) as f:
        f.write(data)
    os.replace(tmp, gz_path)
    raw_path.unlink(missing_ok=True)
    (run_dir / SUMMARY_NAME).write_text(json.dumps(summary, indent=2))
    return summary


def _header_bytes(headers) -> int:
    return sum(len(str(k)) + len(str(v)) + 4 for k, v in headers or [])


def summarize(records: list[dict]) -> dict:
    """Totals for one run, read back from its records."""
    per_host: Counter = Counter()
    statuses: Counter = Counter()
    errors: list[dict] = []
    not_intercepted: list[dict] = []
    wire = Counter()
    up = down = websocket_messages = tcp_flows = incomplete = connections = empty = addon_errors = 0
    blocked: Counter = Counter()
    proxy_start = None
    for r in records:
        kind = r.get("type")
        if kind == "http":
            host = (r.get("server") or {}).get("host") or "?"
            per_host[host] += 1
            request, response = r.get("request") or {}, r.get("response")
            up += _header_bytes(request.get("headers")) + int(request.get("body_size") or 0)
            if response:
                statuses[str(response.get("status"))] += 1
                down += _header_bytes(response.get("headers")) + int(response.get("body_size") or 0)
            if r.get("incomplete"):
                incomplete += 1
            if r.get("error"):
                errors.append({"kind": "http", "host": host, "url": request.get("url"), "error": r["error"]})
        elif kind == "websocket_message":
            websocket_messages += 1
            if r.get("from_client"):
                up += int(r.get("size") or 0)
            else:
                down += int(r.get("size") or 0)
        elif kind == "tcp_start":
            tcp_flows += 1
        elif kind == "tcp_message":
            if r.get("from_client"):
                up += int(r.get("size") or 0)
            else:
                down += int(r.get("size") or 0)
        elif kind == "client_disconnect":
            connections += 1
            counts = r.get("bytes") or {}
            wire.update({k: int(v) for k, v in counts.items()})
            if not r.get("flows") and not counts.get("from_client") and not r.get("tls_error"):
                empty += 1
        elif kind == "not_intercepted":
            not_intercepted.append({k: r.get(k) for k in
                                    ("host", "port", "sni", "bytes_up", "bytes_down", "duration", "reason")})
        elif kind == "tls_failed":
            errors.append({"kind": f"tls_failed_{r.get('side')}", "host": (r.get("server") or [None])[0],
                           "sni": r.get("sni"), "error": r.get("error")})
        elif kind == "connect_error":
            errors.append({"kind": "connect_error", "host": r.get("host"), "error": r.get("error")})
        elif kind == "addon_error":
            addon_errors += 1
            errors.append({"kind": "addon_error", "hook": r.get("hook"), "error": r.get("error")})
        elif kind == "sandbox_denied":
            key = (r.get("process") or r.get("message"), r.get("operation"), r.get("target"))
            blocked[key] += int(r.get("count") or 1)
        elif kind == "proxy_start":
            proxy_start = r
    return {
        "requests": sum(per_host.values()),
        "requests_per_host": dict(per_host.most_common()),
        "hosts": sorted(per_host),
        "status_counts": dict(sorted(statuses.items())),
        "bytes_up": up,
        "bytes_down": down,
        "wire_bytes": {
            "harness_to_proxy": wire.get("from_client", 0), "proxy_to_harness": wire.get("to_client", 0),
            "proxy_to_internet": wire.get("to_server", 0), "internet_to_proxy": wire.get("from_server", 0),
        },
        "byte_counter": bool(proxy_start and proxy_start.get("byte_counter")),
        "errors": len(errors),
        "error_details": errors[:100],
        "not_intercepted": not_intercepted,
        # Connections the sandbox refused: something tried to go around the proxy.
        # The kernel hides the address, so only the process and port are known.
        "blocked_by_sandbox": [
            {"process": process, "operation": operation, "target": target, "attempts": attempts}
            for (process, operation, target), attempts in blocked.most_common()
        ],
        "blocked_attempts": sum(blocked.values()),
        "websocket_messages": websocket_messages,
        "tcp_flows": tcp_flows,
        "incomplete_flows": incomplete,
        "connections": connections,
        "empty_connections": empty,
        "addon_errors": addon_errors,
    }


def read_log(path: Path) -> list[dict]:
    """All records from a network.jsonl.gz, for analysis and tests."""
    with gzip.open(path, "rb") as f:
        return [json.loads(line) for line in f if line.strip()]
