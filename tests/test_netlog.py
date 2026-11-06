"""The network capture in netlog.py, checked with local servers and the real harness binaries.

Fake keys only, so nothing is spent. Run from the project folder:

    python3 tests/test_netlog.py -v

LocalCapture runs the proxy against servers on 127.0.0.1: streaming, redaction,
WebSocket, a client killed mid-stream, a flow still open at stop(), and the
sandbox refusing anything that is not the proxy.

Hardening tries the other ways around the record (UDP, ICMP, IPv6, DNS, relay
sockets such as Docker's, writing to the run folder or the capture's files) and
the other ways a key could reach it (a cut-off compressed body, raw TCP with the
key split across messages, HTTP/2 frames), and checks HTTP/2 streaming. Pure
holds the checks that need no proxy at all.

Internet, RealClis and WebToolsThroughCapture need the internet. RealClis runs
Claude Code, Codex, Grok Build and Pi against the real https://openrouter.ai with
a fake key, where a 401 is the expected answer: once through the capture, and once
in the sandbox without the proxy settings, which must reach nothing. The hosts each
CLI contacted are printed and written to netlog_hosts.json in the temp folder.
WebToolsThroughCapture runs run.py's attempt() with the capture on against the
local fake model server, so each harness's web search and page reads run for real.

NETLOG_SKIP_NETWORK=1 skips the internet classes. NETLOG_SKIP_CLIS=1 skips the two CLI classes.
"""

import asyncio
import base64
import gzip
import http.server
import json
import os
import shutil
import signal
import socket
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ballot import netlog
from ballot.paths import BIN

NODE = shutil.which("node", path="/opt/homebrew/bin:/usr/local/bin:/usr/bin") or "node"
FAKE_KEY = "sk-or-v1-fake-key-for-capture-test"
# A second secret with characters that URL encoding changes.
ODD_SECRET = "sk-test/abc+def=ghi-0123456789"
SECRETS = [FAKE_KEY, ODD_SECRET]
KEY_FRAGMENTS = [FAKE_KEY, "fake-key-for-capture-test", ODD_SECRET, "sk-test%2Fabc%2Bdef%3Dghi-0123456789",
                 "sk-test%2Fabc%2Bdef%3Dghi"]
CA_VARIABLES = ("NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "CODEX_CA_CERTIFICATE", "GROK_EXTRA_CA_BUNDLE",
                "GIT_SSL_CAINFO", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
SKIP_NETWORK = os.environ.get("NETLOG_SKIP_NETWORK") == "1"
SKIP_CLIS = SKIP_NETWORK or os.environ.get("NETLOG_SKIP_CLIS") == "1"


# ---- helpers ----------------------------------------------------------------


class Outcome:
    def __init__(self, run_dir: Path, summary: dict, returncode, timed_out: bool, stdout: str, stderr: str,
                 seconds: float, port: int):
        self.run_dir = run_dir
        self.summary = summary
        self.returncode = returncode
        self.timed_out = timed_out
        self.stdout = stdout
        self.stderr = stderr
        self.seconds = seconds
        self.port = port
        gz = run_dir / netlog.GZ_NAME
        self.records = netlog.read_log(gz) if gz.exists() else []

    def http(self, host: str | None = None) -> list[dict]:
        return [r for r in self.records if r["type"] == "http" and (host is None or r["server"]["host"] == host)]

    def all_written_text(self) -> str:
        """Everything the capture wrote into the run folder, decompressed."""
        parts = []
        for path in sorted(self.run_dir.iterdir()):
            if path.name in ("stdout.txt", "stderr.txt"):
                continue
            data = path.read_bytes()
            if path.suffix == ".gz":
                data = gzip.decompress(data)
            parts.append(data.decode("utf-8", "replace"))
        return "\n".join(parts)


async def run_captured(base: Path, name: str, cmd: list[str], *, extra_env: dict | None = None, stdin: str | None = None,
                       timeout: float = 30, proxy_env: bool = True, drop_env: tuple = (), during=None,
                       capture_kwargs: dict | None = None) -> Outcome:
    """Run cmd in a clean env, in the sandbox, through a fresh capture. Mirrors run.py."""
    run_dir = base / name / "run"
    room = base / name / "room"
    home, cwd, tmp = room / "home", room / "cwd", room / "tmp"
    for folder in (run_dir, home, cwd, tmp):
        folder.mkdir(parents=True, exist_ok=True)
    capture = netlog.NetworkCapture(run_dir, secrets=SECRETS, **(capture_kwargs or {}))
    await capture.start()
    cmd = [c.replace("{run_dir}", str(run_dir)).replace("{proxy_port}", str(capture.port)) for c in cmd]
    env = {"PATH": f"{Path(NODE).parent}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(tmp),
           "LANG": "en_US.UTF-8", "NO_COLOR": "1"}
    for key, value in (extra_env or {}).items():
        env[key] = value.replace("{home}", str(home))
    if proxy_env:
        env |= capture.env()
    for key in drop_env:
        env.pop(key, None)
    started = time.time()
    try:
        with open(run_dir / "stdout.txt", "wb") as out, open(run_dir / "stderr.txt", "wb") as err:
            proc = await asyncio.create_subprocess_exec(
                *capture.wrap(cmd), stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
                stdout=out, stderr=err, env=env, cwd=str(cwd), start_new_session=True)
        if stdin:
            proc.stdin.write(stdin.encode())
            await proc.stdin.drain()
            proc.stdin.close()
        timed_out = False
        if during is not None:
            await during(capture, proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
    finally:
        summary = await capture.stop()
    seconds = time.time() - started
    shutil.rmtree(room, ignore_errors=True)
    return Outcome(run_dir, summary, proc.returncode, timed_out, (run_dir / "stdout.txt").read_text(errors="replace"),
                   (run_dir / "stderr.txt").read_text(errors="replace"), seconds, capture.port)


def note_blocked(test: unittest.TestCase, outcome: "Outcome", label: str) -> None:
    """The sandbox refuses every such connection; the kernel's report of it is best-effort.

    macOS rate-limits sandbox reports across the whole machine, so a refused
    attempt can go unlisted. What must hold is that nothing got through, which
    the callers assert; the count is only printed.
    """
    summary = outcome.summary
    if summary["sandbox_log"] != "ok" or summary["blocked_attempts"] == 0:
        print(f"\n  note: {label}: refused, but the kernel's report did not arrive "
              f"(sandbox_log={summary['sandbox_log']})", file=sys.stderr)


def node(script: str, *args: str) -> list[str]:
    return [NODE, "--input-type=module", "-e", script, *args]


class Server:
    """A threaded HTTP server on 127.0.0.1 for one test class."""

    def __init__(self, handler):
        class Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass  # clients that the tests kill mid-stream reset their connections

        self.httpd = Threaded(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def chunk(self, data: bytes) -> None:
        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
        self.wfile.flush()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        self.route(body)

    def do_GET(self):
        self.route(b"")

    def route(self, body: bytes):
        if self.path.startswith("/sse"):
            # Five events 0.6 s apart, then a secret split across two chunks.
            count = int(self.path.split("n=")[1]) if "n=" in self.path else 5
            gap = 0.3 if count > 5 else 0.6
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            try:
                for i in range(count):
                    self.chunk(b"data: event %d\n\n" % i)
                    time.sleep(gap)
                self.chunk(b"data: " + FAKE_KEY[:12].encode())
                time.sleep(0.2)
                self.chunk(FAKE_KEY[12:].encode() + b"\n\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path.startswith("/echo"):
            # Echo everything back, gzipped, with the secret in a cookie and the body.
            payload = json.dumps({"path": self.path, "headers": dict(self.headers), "body_len": len(body),
                                  "secret": FAKE_KEY}).encode()
            data = gzip.compress(payload)
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-encoding", "gzip")
            self.send_header("set-cookie", f"session={FAKE_KEY}; Path=/")
            self.send_header("x-echo-secret", f"value-{ODD_SECRET}")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.send_header("content-length", "0")
            self.end_headers()


SSE_CLIENT = """
const t0 = Date.now();
const res = await fetch(process.argv[1], {method: "POST", body: JSON.stringify({q: "stream please"}),
  headers: {"content-type": "application/json", "authorization": "Bearer " + process.argv[2]}});
const reader = res.body.getReader(); const dec = new TextDecoder(); const arrivals = [];
const stopAfter = Number(process.argv[3] || 0);
while (true) {
  const {value, done} = await reader.read(); if (done) break;
  for (const line of dec.decode(value).split("\\n"))
    if (line.startsWith("data: event")) { arrivals.push((Date.now() - t0) / 1000);
      if (stopAfter && arrivals.length >= stopAfter) { console.log(JSON.stringify({arrivals})); process.exit(0); } }
}
console.log(JSON.stringify({status: res.status, arrivals}));
"""

ECHO_CLIENT = """
import zlib from "node:zlib";
const [url, key, odd] = process.argv.slice(1);
const headers = {"authorization": "Bearer " + key, "x-api-key": key, "x-goog-api-key": key,
  "cookie": "session=" + key, "x-custom": "prefix-" + key + "-suffix", "content-type": "application/json"};
const q = "?key=" + key + "&odd=" + encodeURIComponent(odd);
const r1 = await fetch(url + q, {method: "POST", headers, body: JSON.stringify({prompt: "hi", key, odd})});
await r1.text();
const r2 = await fetch(url + "?gz=1", {method: "POST", headers: {"content-encoding": "gzip", "content-type": "application/json"},
  body: zlib.gzipSync(JSON.stringify({compressed: key}))});
await r2.text();
const bin = Buffer.concat([Buffer.from([0xff, 0xfe, 0x00]), Buffer.from(key), Buffer.from([0x80, 0x81])]);
const r3 = await fetch(url + "?bin=1", {method: "POST", headers: {"content-type": "application/octet-stream"}, body: bin});
await r3.text();
console.log("ok", r1.status, r2.status, r3.status);
"""

WS_CLIENT = """
const ws = new WebSocket(process.argv[1]);
ws.onopen = () => { ws.send("hello " + process.argv[2]); ws.send(new Uint8Array([0, 255, 1, 2])); };
let n = 0;
ws.onmessage = () => { if (++n === 2) ws.close(1000, "done"); };
ws.onclose = () => console.log("closed");
ws.onerror = (e) => { console.log("error", e.message); process.exit(2); };
"""

DIRECT_CLIENT = """
import net from "node:net";
const s = net.connect(Number(process.argv[1]), "127.0.0.1");
s.on("connect", () => { console.log("connected"); process.exit(0); });
s.on("error", (e) => { console.log("error", e.code); process.exit(3); });
"""


def ws_server() -> tuple[socket.socket, int]:
    """A minimal WebSocket echo server: enough for one client."""
    import hashlib
    import struct

    def frame(payload: bytes, opcode: int) -> bytes:
        return bytes([0x80 | opcode, len(payload)]) + payload

    def recv_exact(conn, n):
        data = b""
        while len(data) < n:
            more = conn.recv(n - len(data))
            if not more:
                raise ConnectionError
            data += more
        return data

    def handle(conn):
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            key = [line.split(b":", 1)[1].strip() for line in request.split(b"\r\n")
                   if line.lower().startswith(b"sec-websocket-key")][0]
            accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            while True:
                b1, b2 = recv_exact(conn, 2)
                size = b2 & 0x7F
                if size == 126:
                    size = struct.unpack(">H", recv_exact(conn, 2))[0]
                mask = recv_exact(conn, 4)
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(recv_exact(conn, size)))
                if b1 & 0x0F == 8:
                    conn.sendall(frame(b"\x03\xe8", 8))
                    break
                conn.sendall(frame(b"echo:" + data, b1 & 0x0F))
        except (ConnectionError, OSError, IndexError):
            pass
        finally:
            conn.close()

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def accept_loop():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return server, server.getsockname()[1]


# ---- tests ------------------------------------------------------------------


def addon_call(expression: str, *args: str, secrets: list[str] = SECRETS) -> object:
    """Evaluate an expression against netlog_addon.py in the capture's own Python, which has mitmproxy.

    `addon` is the module and `log` its NetLog instance. The result comes back as JSON.
    """
    import subprocess

    folder = Path(tempfile.mkdtemp(prefix="netlog-test-addon-"))
    try:
        code = (
            "import importlib.util, json, os, sys\n"
            f"os.environ['NETLOG_FILE'] = {str(folder / 'log.jsonl')!r}\n"
            f"os.environ['NETLOG_SECRETS'] = {chr(10).join(secrets)!r}\n"
            "spec = importlib.util.spec_from_file_location('netlog_addon', sys.argv[1])\n"
            "addon = importlib.util.module_from_spec(spec); spec.loader.exec_module(addon)\n"
            "log = addon.addons[0]\n"
            "from mitmproxy.http import Headers\n"
            "args = sys.argv[2:]\n"
            f"print(json.dumps({expression}))\n"
        )
        out = subprocess.run([str(netlog.VENV_PYTHON), "-I", "-c", code, str(netlog.ADDON), *args],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(folder, ignore_errors=True)


class Pure(unittest.TestCase):
    def test_short_and_empty_secrets_are_ignored(self):
        self.assertEqual(netlog.clean_secrets(["", "  ", "short", FAKE_KEY, FAKE_KEY]), [FAKE_KEY])

    def test_redaction_covers_escaped_forms(self):
        data = f"a {ODD_SECRET} b sk-test%2Fabc%2Bdef%3Dghi-0123456789 c sk-test\\/abc+def=ghi-0123456789".encode()
        out, hits = netlog.redact_bytes(data, [ODD_SECRET])
        self.assertEqual(hits, 3)
        self.assertNotIn(b"abc", out)

    def test_redaction_covers_base64_and_partial_url_encoding(self):
        for secret in SECRETS:
            for prefix in ("", "u", "us", "user:"):  # every base64 alignment
                for encode in (base64.b64encode, base64.urlsafe_b64encode):
                    data = b"Basic " + encode((prefix + secret + ":x").encode())
                    out, hits = netlog.redact_bytes(data, [secret])
                    self.assertEqual(hits, 1, (secret, prefix, encode))
                    self.assertIn(b"<redacted>", out)
        for form in ("sk-test/abc%2Bdef%3Dghi-0123456789", "sk-test%2fabc%2bdef%3dghi-0123456789"):
            self.assertEqual(netlog.redact_bytes(form.encode(), [ODD_SECRET])[1], 1, form)
        # Ordinary text is left alone.
        self.assertEqual(netlog.redact_bytes(b"Basic dXNlcjpwYXNz hello sk-or-v1-", [FAKE_KEY])[1], 0)

    def test_netlog_and_the_addon_know_the_same_secret_forms(self):
        for secret in SECRETS:
            ours = sorted(netlog.secret_variants(secret))
            self.assertEqual(addon_call("sorted(addon.secret_variants(args[0]))", secret), ours)

    def test_addon_redacts_header_names_and_search_key_headers(self):
        headers = addon_call(
            "log.headers(Headers([(args[0].encode(), b'v'), (b'x-subscription-token', b'brave-key-not-listed'),"
            " (b'api-key', b'azure-key-not-listed'), (b'x-basic', ('Basic ' + __import__('base64')"
            ".b64encode(('me:' + args[0]).encode()).decode()).encode())]))", FAKE_KEY)
        self.assertEqual(headers[0][0], "<redacted>")
        self.assertEqual(headers[1][1], "<redacted>")
        self.assertEqual(headers[2][1], "<redacted>")
        self.assertIn("<redacted>", headers[3][1])

    def test_cut_off_compressed_bodies_are_decoded_and_redacted(self):
        # A stream cut off mid-body cannot be decoded whole, but its compressed bytes
        # still hold the secret for anyone who decompresses them piece by piece.
        result = addon_call(
            "[(name, log.body(data[: len(data) * 4 // 5], Headers(content_encoding=name))) for name, data in ("
            "('br', __import__('brotli').compress(payload, quality=5)), ('deflate', __import__('zlib').compress(payload)),"
            " ('gzip', __import__('gzip').compress(payload)))] if (payload := ("
            "__import__('random').Random(1).randbytes(60000).hex() + ' key=' + args[0] + ' '"
            " + __import__('random').Random(2).randbytes(60000).hex()).encode()) else None", FAKE_KEY)
        for name, out in result:
            with self.subTest(name):
                self.assertFalse(out["body_base64"], out.get("body_decode_error"))
                self.assertIn(" key=<redacted> ", out["body"])
                self.assertNotIn(FAKE_KEY, out["body"])

    def test_secret_split_across_stream_messages_is_redacted(self):
        pieces = ["hello " + FAKE_KEY[:5], FAKE_KEY[5:15], FAKE_KEY[15:] + " bye"]
        records = addon_call("[log.message('f', True, p.encode()) for p in args]", *pieces)
        self.assertEqual("".join(r["body"] for r in records), "hello <redacted> bye")
        self.assertEqual([r["size"] for r in records], [len(p) for p in pieces])
        tail = addon_call("[log.message('f', True, args[0].encode()), log.flush_carry('f', 'tcp_message'),"
                          " open(os.environ['NETLOG_FILE']).read()][2]", "end " + FAKE_KEY[:20])
        self.assertIn("<redacted>", tail)
        self.assertNotIn(FAKE_KEY[:20], tail)

    def test_message_ending_in_a_whole_key_is_redacted_for_every_last_character(self):
        # The base64 forms of every OpenRouter key start with "c2st" (base64 of "sk-"), so a
        # key ending in "c" ends with the start of one of its own forms.
        keys = ["sk-or-v1-" + "5" * 63 + last for last in "0123456789abcdef"]
        joined = addon_call(
            "[(setattr(log, 'redact', addon.Redactor([k])), log.carry.clear(), ''.join("
            "log.message('f', True, m)['body'] for m in (('hello ' + k).encode(), b' more')))[2] for k in args]", *keys)
        self.assertEqual(joined, ["hello <redacted> more"] * len(keys))

    def test_problems_report_every_gap(self):
        summary = {"sandbox_log": "ok", "proxy_stopped_cleanly": True, "byte_counter": False, "incomplete_flows": 2,
                   "tcp_flows": 1, "proxy_log_errors": 1, "capture_error": "finishing the record failed: OSError",
                   "dns": "allowed, not recorded", "blocked_by_sandbox": [
                       {"process": "node", "operation": "network-outbound", "target": netlog.MDNS_SOCKET, "attempts": 3},
                       {"process": "node", "operation": "file-write-create", "target": "/x/network.jsonl", "attempts": 1}]}
        text = "\n".join(netlog.problems(summary))
        for words in ("3 DNS lookups", "writes to the capture", "count socket bytes", "2 requests were still open",
                      "raw TCP", "mitmproxy reported 1 errors", "finishing the record failed", "block_dns=False"):
            self.assertIn(words, text)

    def test_mitmproxy_config_file_stops_the_capture(self):
        folder = Path(tempfile.mkdtemp(prefix="netlog-test-conf-"))
        saved = netlog.MITMPROXY_CONFIGS
        try:
            netlog.MITMPROXY_CONFIGS = (folder / "config.yaml",)
            netlog.check_install()
            (folder / "config.yaml").write_text("ignore_hosts: ['.*']\n")
            with self.assertRaises(netlog.NetlogError):
                netlog.check_install()
        finally:
            netlog.MITMPROXY_CONFIGS = saved
            shutil.rmtree(folder, ignore_errors=True)

    def test_proxy_output_with_a_huge_line_is_kept_and_redacted(self):
        # A line over asyncio's 64 KiB limit used to end the reader; mitmdump would then
        # block on a full pipe and stall the run, and stop() would fail.
        folder = Path(tempfile.mkdtemp(prefix="netlog-test-pump-"))

        async def pump():
            capture = netlog.NetworkCapture(folder, secrets=SECRETS)
            script = f"import sys; sys.stdout.write('x' * 200000 + ' {FAKE_KEY} ' + 'y' * 3000000 + '\\nend\\n')"
            capture.proc = await asyncio.create_subprocess_exec(sys.executable, "-c", script,
                                                                stdout=asyncio.subprocess.PIPE)
            await asyncio.wait_for(capture._pump_proxy_log(), 20)
            await capture.proc.wait()

        try:
            asyncio.run(pump())
            text = (folder / netlog.PROXY_LOG_NAME).read_text()
            self.assertEqual(len(text), 200000 + len(" <redacted> ") + 3000000 + len("\nend\n"))
            self.assertNotIn(FAKE_KEY, text)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_retry_keeps_the_earlier_capture(self):
        folder = Path(tempfile.mkdtemp(prefix="netlog-test-"))
        try:
            (folder / "network.jsonl.gz").write_text("first")
            netlog.archive_previous(folder)
            (folder / "network.jsonl.gz").write_text("second")
            netlog.archive_previous(folder)
            self.assertEqual(sorted(p.name for p in folder.iterdir()),
                             ["network.failed-1.jsonl.gz", "network.failed-2.jsonl.gz"])
        finally:
            shutil.rmtree(folder)

    def test_problems_name_what_was_missed(self):
        warnings = netlog.problems({
            "blocked_attempts": 2, "sandbox_log": "ok", "proxy_stopped_cleanly": True,
            "blocked_by_sandbox": [{"process": "codex", "operation": "network-outbound", "target": "remote:*:443", "attempts": 2}],
            "not_intercepted": [{"host": "github.com", "port": 443}],
        })
        self.assertEqual(len(warnings), 2)
        self.assertIn("codex", warnings[0])
        self.assertIn("github.com:443", warnings[1])
        self.assertEqual(netlog.problems({"sandbox_log": "ok", "proxy_stopped_cleanly": True}), [])


class LocalCapture(unittest.TestCase):
    """The proxy against servers on 127.0.0.1. No internet needed."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="netlog-test-local-"))
        cls.server = Server(Handler)
        cls.ws, cls.ws_port = ws_server()
        url = f"http://127.0.0.1:{cls.server.port}"

        async def stop_mid_stream(capture, proc):
            await asyncio.sleep(1.5)  # a few events in, the client still reading
            await capture.stop()

        async def everything():
            return await asyncio.gather(
                run_captured(cls.base, "sse", node(SSE_CLIENT, f"{url}/sse", FAKE_KEY)),
                run_captured(cls.base, "echo", node(ECHO_CLIENT, f"{url}/echo", FAKE_KEY, ODD_SECRET)),
                run_captured(cls.base, "ws", node(WS_CLIENT, f"ws://127.0.0.1:{cls.ws_port}/ws", FAKE_KEY)),
                run_captured(cls.base, "killed", node(SSE_CLIENT, f"{url}/sse?n=20", FAKE_KEY, "3")),
                run_captured(cls.base, "open-at-stop", node(SSE_CLIENT, f"{url}/sse?n=40", FAKE_KEY),
                             during=stop_mid_stream, timeout=5),
                run_captured(cls.base, "direct", node(DIRECT_CLIENT, str(cls.server.port))),
            )

        (cls.sse, cls.echo, cls.wsrun, cls.killed, cls.open_at_stop, cls.direct) = asyncio.run(everything())

    @classmethod
    def tearDownClass(cls):
        cls.server.close()
        cls.ws.close()
        shutil.rmtree(cls.base, ignore_errors=True)

    def assert_no_secret(self, outcome: Outcome):
        text = outcome.all_written_text()
        for fragment in KEY_FRAGMENTS:
            self.assertNotIn(fragment, text)
        self.assertEqual(outcome.summary["secrets_redacted_at_stop"], 0)

    def test_stream_is_passed_on_chunk_by_chunk(self):
        result = json.loads(self.sse.stdout)
        arrivals = result["arrivals"]
        self.assertEqual(len(arrivals), 5)
        # The server sends an event every 0.6 s. Through a buffering proxy all five
        # would arrive together after 2.4 s; streamed, they arrive as sent.
        self.assertLess(arrivals[0], 1.0)
        self.assertGreater(arrivals[-1] - arrivals[0], 2.0)
        gaps = [b - a for a, b in zip(arrivals, arrivals[1:])]
        self.assertTrue(all(g > 0.3 for g in gaps), gaps)
        (flow,) = self.sse.http()
        times = [t for t, _ in flow["response"]["chunk_times"]]
        self.assertGreater(times[-1] - times[0], 2.0)
        self.assertIn("data: event 4", flow["response"]["body"])

    def test_secret_split_across_chunks_is_redacted(self):
        (flow,) = self.sse.http()
        self.assertGreaterEqual(flow["response"]["chunks"], 7)
        self.assertIn("data: <redacted>", flow["response"]["body"])
        self.assert_no_secret(self.sse)

    def test_request_headers_and_body_are_recorded(self):
        (flow,) = self.sse.http()
        headers = dict((k.lower(), v) for k, v in flow["request"]["headers"])
        self.assertEqual(headers["authorization"], "<redacted>")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(json.loads(flow["request"]["body"]), {"q": "stream please"})
        self.assertEqual(flow["response"]["status"], 200)

    def test_secrets_are_redacted_everywhere(self):
        self.assertIn("ok 200 200 200", self.echo.stdout)
        flows = self.echo.http()
        self.assertEqual(len(flows), 3)
        first, gz, binary = sorted(flows, key=lambda f: f["start"])
        self.assertIn("key=<redacted>", first["request"]["url"])
        self.assertIn("odd=<redacted>", first["request"]["url"])
        headers = {k.lower(): v for k, v in first["request"]["headers"]}
        for name in ("authorization", "x-api-key", "x-goog-api-key", "cookie"):
            self.assertEqual(headers[name], "<redacted>")
        self.assertEqual(headers["x-custom"], "prefix-<redacted>-suffix")
        self.assertEqual(json.loads(first["request"]["body"])["key"], "<redacted>")
        response_headers = {k.lower(): v for k, v in first["response"]["headers"]}
        self.assertEqual(response_headers["set-cookie"], "<redacted>")
        self.assertEqual(response_headers["x-echo-secret"], "value-<redacted>")
        # Compressed bodies are decoded, so they are readable and redactable.
        self.assertEqual(first["response"]["body_decoded_from"], "gzip")
        self.assertEqual(json.loads(first["response"]["body"])["secret"], "<redacted>")
        self.assertEqual(gz["request"]["body_decoded_from"], "gzip")
        self.assertEqual(json.loads(gz["request"]["body"]), {"compressed": "<redacted>"})
        # Binary bodies are base64, flagged, and redacted before encoding.
        self.assertTrue(binary["request"]["body_base64"])
        raw = base64.b64decode(binary["request"]["body"])
        self.assertIn(b"<redacted>", raw)
        self.assertTrue(raw.startswith(b"\xff\xfe\x00"))
        self.assert_no_secret(self.echo)

    def test_websocket_messages_are_recorded(self):
        self.assertIn("closed", self.wsrun.stdout)
        messages = [r for r in self.wsrun.records if r["type"] == "websocket_message"]
        self.assertEqual(len(messages), 4)
        sent_text = next(m for m in messages if m["from_client"] and not m["body_base64"])
        self.assertEqual(sent_text["body"], "hello <redacted>")
        sent_binary = next(m for m in messages if m["from_client"] and m["body_base64"])
        self.assertEqual(base64.b64decode(sent_binary["body"]), b"\x00\xff\x01\x02")
        self.assertTrue(any(r["type"] == "websocket_end" and r["close_code"] == 1000 for r in self.wsrun.records))
        self.assert_no_secret(self.wsrun)

    def test_client_killed_mid_stream_keeps_partial_body(self):
        self.assertEqual(len(json.loads(self.killed.stdout)["arrivals"]), 3)
        (flow,) = self.killed.http()
        self.assertTrue(flow["error"])
        self.assertIn("data: event 2", flow["response"]["body"])

    def test_flow_open_at_stop_is_written_not_dropped(self):
        (flow,) = self.open_at_stop.http()
        self.assertTrue(flow.get("incomplete") or flow["error"], flow)
        self.assertIn("data: event 0", flow["response"]["body"])
        self.assertTrue(self.open_at_stop.summary["proxy_stopped_cleanly"])

    def test_sandbox_refuses_other_localhost_ports(self):
        # The test server is up on this port; only the proxy's port is allowed.
        self.assertIn("error EPERM", self.direct.stdout)
        self.assertEqual(self.direct.summary["requests"], 0)
        note_blocked(self, self.direct, "direct connection to a localhost port")

    def test_summary_is_complete(self):
        for outcome in (self.sse, self.echo, self.wsrun):
            s = outcome.summary
            self.assertEqual(s["not_intercepted"], [])
            self.assertEqual(s["blocked_attempts"], 0)
            self.assertEqual(s["addon_errors"], 0)
            self.assertTrue(s["proxy_stopped_cleanly"])
            self.assertTrue(s["byte_counter"])
            self.assertEqual(netlog.problems(s), [])
            self.assertTrue((outcome.run_dir / netlog.SUMMARY_NAME).exists())
            self.assertFalse((outcome.run_dir / netlog.LOG_NAME).exists())
        self.assertEqual(self.echo.summary["requests_per_host"], {"127.0.0.1": 3})


PY = sys.executable

# Every way out of the sandbox that is not the proxy, tried from inside it.
ESCAPES = """
import os, socket, sys
run_dir, confdir, relay = sys.argv[1:4]
def attempt(name, fn):
    try:
        fn()
        print(name, "ALLOWED")
    except OSError as e:
        print(name, "refused", type(e).__name__, getattr(e, "errno", ""))
def udp(fam, host):
    socket.socket(fam, socket.SOCK_DGRAM).sendto(b"x", (host, 53))
attempt("udp4", lambda: udp(socket.AF_INET, "1.1.1.1"))
attempt("udp6", lambda: udp(socket.AF_INET6, "2606:4700:4700::1111"))
attempt("udp_localhost", lambda: udp(socket.AF_INET, "127.0.0.1"))
attempt("icmp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP).sendto(
    bytes([8, 0, 0xF7, 0xFF, 0, 0, 0, 0]), ("1.1.1.1", 0)))
attempt("tcp6", lambda: socket.create_connection(("2606:4700:4700::1111", 443), 3))
attempt("dns", lambda: socket.getaddrinfo("example.com", 443))
os.chdir(relay)  # unix socket paths are limited to 104 bytes, so these are relative
attempt("unix_docker", lambda: socket.socket(socket.AF_UNIX).connect("docker.sock"))
attempt("unix_plain", lambda: socket.socket(socket.AF_UNIX).connect("plain.sock"))
attempt("write_run_dir", lambda: open(os.path.join(run_dir, "planted.txt"), "w").write("x"))
attempt("write_confdir", lambda: open(os.path.join(confdir, "netlog-write-test.txt"), "w").write("x"))
attempt("write_other_folder", lambda: open("../other-file.txt", "w").write("x"))
"""

# Raw TCP through a CONNECT tunnel, with the key split across two messages.
RAW_TCP = """
import socket, sys, time
proxy, target, key = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
s = socket.create_connection(("127.0.0.1", proxy))
s.sendall(b"CONNECT 127.0.0.1:%d HTTP/1.1\\r\\nHost: 127.0.0.1:%d\\r\\n\\r\\n" % (target, target))
assert b" 200 " in s.recv(4096)
s.sendall(b"\\x00\\x01RAW " + key[:10].encode()); time.sleep(0.4)
s.sendall(key[10:].encode() + b" BYE\\n")
got = b""
while not got.endswith(b"BYE\\n"):
    got += s.recv(4096)
print("echoed", len(got))
"""

# Reads a stream through curl over HTTP/2 and notes when each event arrives.
H2_CLIENT = """
import json, subprocess, sys, time
t0 = time.time()
p = subprocess.Popen(["/usr/bin/curl", "-sS", "-N", "--http2", sys.argv[1]], stdout=subprocess.PIPE)
arrivals = [round(time.time() - t0, 3) for line in p.stdout if line.startswith(b"data: event")]
print(json.dumps({"rc": p.wait(), "arrivals": arrivals}))
"""

# A local HTTPS server that speaks only HTTP/2 and streams events slowly, run by the
# capture's own Python (it has h2 and cryptography). It prints {"port", "ca"}.
H2_SERVER = r'''
import datetime, ipaddress, json, os, socket, ssl, sys, tempfile, threading, time
import h2.config, h2.connection, h2.events
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
folder, secret = sys.argv[1], sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc)
def builder(name, key):
    return (x509.CertificateBuilder().subject_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2)))
ca_key, key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "netlog test CA")])
ca = (builder(ca_name, ca_key).issuer_name(ca_name)
      .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
      .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
      .sign(ca_key, hashes.SHA256()))
cert = (builder(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]), key).issuer_name(ca_name)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                    x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
paths = {n: os.path.join(folder, n) for n in ("ca.pem", "cert.pem", "key.pem")}
open(paths["ca.pem"], "wb").write(ca.public_bytes(serialization.Encoding.PEM))
open(paths["cert.pem"], "wb").write(cert.public_bytes(serialization.Encoding.PEM))
open(paths["key.pem"], "wb").write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(paths["cert.pem"], paths["key.pem"])
context.set_alpn_protocols(["h2"])
def serve(sock):
    try:
        tls = context.wrap_socket(sock, server_side=True)
        conn = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
        conn.initiate_connection(); tls.sendall(conn.data_to_send())
        lock = threading.Lock()
        def stream(sid):
            with lock:
                conn.send_headers(sid, [(":status", "200"), ("content-type", "text/event-stream")])
                tls.sendall(conn.data_to_send())
            for piece in [b"data: event %d\n\n" % i for i in range(5)] + [b"data: " + secret[:12].encode(),
                                                                          secret[12:].encode() + b"\n\n"]:
                with lock:
                    conn.send_data(sid, piece); tls.sendall(conn.data_to_send())
                time.sleep(0.6)
            with lock:
                conn.end_stream(sid); tls.sendall(conn.data_to_send())
        while data := tls.recv(65535):
            for event in conn.receive_data(data):
                if isinstance(event, h2.events.RequestReceived):
                    threading.Thread(target=stream, args=(event.stream_id,), daemon=True).start()
                elif isinstance(event, h2.events.DataReceived):
                    conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            with lock:
                if out := conn.data_to_send():
                    tls.sendall(out)
    except Exception:
        pass
server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen()
def accept():
    while True:
        try:
            s, _ = server.accept()
        except OSError:
            return
        threading.Thread(target=serve, args=(s,), daemon=True).start()
threading.Thread(target=accept, daemon=True).start()
print(json.dumps({"port": server.getsockname()[1], "ca": paths["ca.pem"]}), flush=True)
sys.stdin.read()
'''


class TruncatingHandler(http.server.BaseHTTPRequestHandler):
    """Sends a deflate body with the key in it, and hangs up after 80% of it."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        import random
        import zlib

        payload = (random.Random(1).randbytes(40000).hex() + f" key={FAKE_KEY} "
                   + random.Random(2).randbytes(40000).hex()).encode()
        data = zlib.compress(payload)
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-encoding", "deflate")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data[: len(data) * 4 // 5])
        self.wfile.flush()
        self.connection.shutdown(socket.SHUT_RDWR)


def tcp_echo_server() -> tuple[socket.socket, int]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def handle(conn):
        with conn:
            while data := conn.recv(4096):
                conn.sendall(data)

    def accept_loop():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return server, server.getsockname()[1]


class Hardening(unittest.TestCase):
    """Ways around the record, and ways a secret could reach it, that the first version missed. No internet needed."""

    @classmethod
    def setUpClass(cls):
        import subprocess

        cls.base = Path(tempfile.mkdtemp(prefix="netlog-test-hard-"))
        cls.relay = cls.base / "relay"
        cls.relay.mkdir()
        # Unix sockets outside the sandbox: one named like a container engine's, one neutral.
        cls.unix = subprocess.Popen(
            [PY, "-c", "import socket, sys\nsocks = []\nfor n in ('docker.sock', 'plain.sock'):\n"
                       "    s = socket.socket(socket.AF_UNIX); s.bind(n); s.listen(); socks.append(s)\n"
                       "print('ready', flush=True); sys.stdin.read()"],
            cwd=cls.relay, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        cls.unix.stdout.readline()
        cls.truncating = Server(TruncatingHandler)
        cls.echo_server, cls.echo_port = tcp_echo_server()
        cls.h2 = subprocess.Popen([str(netlog.VENV_PYTHON), "-I", "-c", H2_SERVER, str(cls.base), FAKE_KEY],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        h2_info = json.loads(cls.h2.stdout.readline())

        async def everything():
            escapes = run_captured(cls.base, "escapes", [PY, "-I", "-c", ESCAPES, "{run_dir}", str(netlog.CONFDIR),
                                                         str(cls.relay)])
            return await asyncio.gather(
                escapes,
                run_captured(cls.base, "dns-node", node(DNS_LOOKUP, "example.com")),
                run_captured(cls.base, "truncated", node(FETCH, f"http://127.0.0.1:{cls.truncating.port}/")),
                run_captured(cls.base, "raw-tcp", [PY, "-I", "-c", RAW_TCP, "{proxy_port}", str(cls.echo_port), FAKE_KEY]),
                run_captured(cls.base, "h2", [PY, "-I", "-c", H2_CLIENT, f"https://127.0.0.1:{h2_info['port']}/sse"],
                             capture_kwargs={"upstream_ca": h2_info["ca"]}),
            )

        (cls.escapes, cls.dns, cls.truncated, cls.raw_tcp, cls.h2run) = asyncio.run(everything())

    @classmethod
    def tearDownClass(cls):
        for proc in (cls.unix, cls.h2):
            proc.stdin.close()
            proc.wait()
            proc.stdout.close()
        cls.truncating.close()
        cls.echo_server.close()
        (netlog.CONFDIR / "netlog-write-test.txt").unlink(missing_ok=True)
        shutil.rmtree(cls.base, ignore_errors=True)

    def lines(self) -> dict:
        return dict(line.split(" ", 1) for line in self.escapes.stdout.splitlines() if " " in line)

    def test_udp_icmp_and_ipv6_are_refused(self):
        lines = self.lines()
        for name in ("udp4", "udp6", "udp_localhost", "icmp", "tcp6"):
            self.assertTrue(lines[name].startswith("refused"), (name, lines[name]))

    def test_dns_is_refused_by_default(self):
        # A lookup would send the hostname, which can carry data, past the proxy.
        self.assertTrue(self.lines()["dns"].startswith("refused"), self.lines()["dns"])
        self.assertIn("error ENOTFOUND", self.dns.stdout)
        self.assertEqual(self.dns.summary["dns"], "blocked")
        note_blocked(self, self.dns, "DNS lookup")

    def test_local_relay_sockets_are_refused(self):
        lines = self.lines()
        self.assertTrue(lines["unix_docker"].startswith("refused"), lines["unix_docker"])
        self.assertEqual(lines["unix_plain"], "ALLOWED")

    def test_the_run_cannot_write_to_its_record_or_the_capture(self):
        lines = self.lines()
        self.assertTrue(lines["write_run_dir"].startswith("refused"), lines["write_run_dir"])
        self.assertTrue(lines["write_confdir"].startswith("refused"), lines["write_confdir"])
        self.assertEqual(lines["write_other_folder"], "ALLOWED")
        self.assertFalse((self.escapes.run_dir / "planted.txt").exists())
        self.assertFalse((netlog.CONFDIR / "netlog-write-test.txt").exists())

    def test_cut_off_compressed_response_is_decoded_and_redacted(self):
        (flow,) = self.truncated.http()
        response = flow["response"]
        self.assertTrue(response["body_decode_partial"], response.get("body_decode_error"))
        self.assertFalse(response["body_base64"])
        self.assertIn(" key=<redacted> ", response["body"])
        text = self.truncated.all_written_text()
        for fragment in KEY_FRAGMENTS:
            self.assertNotIn(fragment, text)

    def test_raw_tcp_with_a_split_key_is_recorded_and_redacted(self):
        self.assertIn("echoed", self.raw_tcp.stdout, self.raw_tcp.stderr)
        messages = [r for r in self.raw_tcp.records if r["type"] == "tcp_message"]
        sent = "".join(m["body"] for m in messages if m["from_client"] and not m["body_base64"])
        back = "".join(m["body"] for m in messages if not m["from_client"] and not m["body_base64"])
        self.assertIn("RAW <redacted> BYE", sent)
        self.assertIn("RAW <redacted> BYE", back)
        self.assertEqual(sum(m["size"] for m in messages if m["from_client"]), 2 + 4 + len(FAKE_KEY) + 5)
        self.assertNotIn("fake-key", self.raw_tcp.all_written_text())
        self.assertTrue(any("raw TCP" in w for w in netlog.problems(self.raw_tcp.summary)))

    def test_http2_stream_is_passed_on_chunk_by_chunk(self):
        # Codex and Grok Build talk HTTP/2 to OpenRouter, so their model streams take this path.
        result = json.loads(self.h2run.stdout)
        self.assertEqual(result["rc"], 0, self.h2run.stderr)
        arrivals = result["arrivals"]
        self.assertEqual(len(arrivals), 5)
        self.assertLess(arrivals[0], 1.0)
        self.assertGreater(arrivals[-1] - arrivals[0], 2.0)
        self.assertTrue(all(b - a > 0.3 for a, b in zip(arrivals, arrivals[1:])), arrivals)
        (flow,) = self.h2run.http()
        self.assertEqual((flow["request"]["http_version"], flow["response"]["http_version"]), ("HTTP/2.0", "HTTP/2.0"))
        self.assertEqual(flow["server"]["alpn"], "h2")
        self.assertIn("data: event 4", flow["response"]["body"])
        self.assertIn("data: <redacted>", flow["response"]["body"])  # split across two DATA frames
        self.assertNotIn("fake-key", self.h2run.all_written_text())
        self.assertEqual(netlog.problems(self.h2run.summary), [])

    def test_stop_never_raises_and_keeps_the_raw_record(self):
        folder = self.base / "finish-fails"

        async def go():
            capture = netlog.NetworkCapture(folder, secrets=SECRETS)
            await capture.start()
            saved = netlog.finish

            def broken(*args, **kwargs):
                raise OSError(f"disk full while writing {FAKE_KEY}")

            netlog.finish = broken
            try:
                return await capture.stop()
            finally:
                netlog.finish = saved

        summary = asyncio.run(go())
        self.assertIn("finishing the record failed", summary["capture_error"])
        self.assertNotIn(FAKE_KEY, summary["capture_error"])
        self.assertTrue(any("finishing the record failed" in w for w in netlog.problems(summary)))
        self.assertTrue((folder / netlog.LOG_NAME).exists())


DNS_LOOKUP = """
import dns from "node:dns";
dns.lookup(process.argv[1], (e, a) => console.log(e ? "error " + e.code : "ok " + a));
"""

FETCH = """
fetch(process.argv[1]).then(async r => console.log("status", r.status, (await r.text()).length))
  .catch(e => { console.log("error", e.cause && e.cause.code, e.message); process.exit(3); });
"""


@unittest.skipIf(SKIP_NETWORK, "NETLOG_SKIP_NETWORK=1")
class Internet(unittest.TestCase):
    """Plain clients against a real HTTPS site."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="netlog-test-net-"))

        async def everything():
            return await asyncio.gather(
                run_captured(cls.base, "fetch", node(FETCH, "https://example.com/")),
                run_captured(cls.base, "no-proxy", node(FETCH, "https://example.com/"), proxy_env=False),
                run_captured(cls.base, "no-ca", node(FETCH, "https://example.com/"), drop_env=CA_VARIABLES),
                run_captured(cls.base, "dns-allowed", node(DNS_LOOKUP, "example.com"),
                             capture_kwargs={"block_dns": False}),
            )

        cls.fetch, cls.no_proxy, cls.no_ca, cls.dns_allowed = asyncio.run(everything())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_node_global_fetch_is_captured(self):
        # Pi's web tools use Node's global fetch.
        self.assertIn("status 200", self.fetch.stdout)
        (flow,) = self.fetch.http("example.com")
        self.assertEqual(flow["response"]["status"], 200)
        self.assertIn("<html", flow["response"]["body"].lower())
        self.assertEqual(flow["server"]["sni"], "example.com")
        self.assertTrue(flow["server"]["tls"])

    def test_without_proxy_env_nothing_gets_out(self):
        # With DNS refused the lookup fails first (ENOTFOUND); the connection itself is refused too (EPERM).
        self.assertTrue("error ENOTFOUND" in self.no_proxy.stdout or "error EPERM" in self.no_proxy.stdout,
                        self.no_proxy.stdout)
        self.assertEqual(self.no_proxy.summary["requests"], 0)
        note_blocked(self, self.no_proxy, "node fetch without proxy settings")
        if self.no_proxy.summary["blocked_attempts"]:
            self.assertTrue(netlog.problems(self.no_proxy.summary))

    def test_dns_works_only_when_allowed_and_is_then_reported(self):
        # The same lookup that the default capture refuses (Hardening) resolves with block_dns=False,
        # and the record says that DNS went unrecorded.
        self.assertIn("ok ", self.dns_allowed.stdout)
        self.assertEqual(self.dns_allowed.summary["dns"], "allowed, not recorded")
        self.assertTrue(any("DNS lookups were allowed" in w for w in netlog.problems(self.dns_allowed.summary)))

    def test_client_that_rejects_the_ca_is_recorded(self):
        # Without any of the CA variables, Node trusts only public roots and refuses the proxy.
        self.assertIn("error", self.no_ca.stdout)
        (missed,) = self.no_ca.summary["not_intercepted"]
        self.assertEqual((missed["host"], missed["port"], missed["sni"]), ("example.com", 443, "example.com"))
        self.assertGreater(missed["bytes_up"], 0)
        self.assertGreater(missed["bytes_down"], 0)
        self.assertIn("does not trust", missed["reason"])
        self.assertTrue(any("not readable" in w for w in netlog.problems(self.no_ca.summary)))


MARKER = "NETLOG-MARKER"


def cli_commands() -> dict[str, dict]:
    """The four harnesses as the task describes them, pointed at OpenRouter with a fake key."""
    codex_config = [
        "-c", 'model_provider="openrouter"',
        "-c", 'model_providers.openrouter.name="OpenRouter"',
        "-c", 'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"',
        "-c", 'model_providers.openrouter.env_key="OPENROUTER_API_KEY"',
        "-c", 'model_providers.openrouter.wire_api="responses"',
    ]
    catalog = os.environ.get("NETLOG_CODEX_CATALOG")
    if catalog:
        codex_config += ["-c", f'model_catalog_json="{catalog}"']
    return {
        "claude_code": {
            "cmd": [str(BIN / "claude"), "-p", "--model", "anthropic/claude-haiku-5.5", "--tools", "WebSearch,WebFetch",
                    "--output-format", "stream-json", "--verbose", "--no-session-persistence"],
            "stdin": f"Say hi in one word. {MARKER}-CLAUDE",
            "env": {"ANTHROPIC_BASE_URL": "https://openrouter.ai/api", "ANTHROPIC_AUTH_TOKEN": FAKE_KEY,
                    "ANTHROPIC_API_KEY": "", "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anthropic/claude-haiku-5.5",
                    "ANTHROPIC_SMALL_FAST_MODEL": "anthropic/claude-haiku-5.5",
                    "CLAUDE_CONFIG_DIR": "{home}/.claude"},
            # It retries a 401 for minutes; the first attempts are all the test needs.
            "timeout": 25, "timeout_blocked": 20,
        },
        "codex": {
            "cmd": ["/bin/sh", "-c", 'mkdir -p "$CODEX_HOME" && exec "$0" "$@"', str(BIN / "codex"), "exec", "--json",
                    "--skip-git-repo-check", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                    "--sandbox", "read-only", "-m", "openai/gpt-6-luna", *codex_config, "-"],
            "stdin": f"Say hi in one word. {MARKER}-CODEX",
            "env": {"OPENROUTER_API_KEY": FAKE_KEY, "CODEX_HOME": "{home}/.codex"},
            "timeout": 60, "timeout_blocked": 25,
        },
        "grok_build": {
            "cmd": [str(BIN / "grok"), "-p", f"hi {MARKER}-GROK", "--output-format", "streaming-messages-json",
                    "-m", "x-ai/grok-4.7"],
            "stdin": None,
            "env": {"XAI_API_KEY": FAKE_KEY, "GROK_MODELS_BASE_URL": "https://openrouter.ai/api/v1",
                    "GROK_XAI_API_BASE_URL": "https://openrouter.ai/api/v1"},
            "timeout": 60, "timeout_blocked": 30,
        },
        "pi": {
            "cmd": [str(BIN / "pi"), "-p", "--mode", "json", "--no-session", "--provider", "openrouter",
                    "--model", "anthropic/claude-haiku-5.5", "--no-builtin-tools", "--no-extensions", "--",
                    f"hi {MARKER}-PI"],
            "stdin": None,
            "env": {"OPENROUTER_API_KEY": FAKE_KEY, "PI_CODING_AGENT_DIR": "{home}/.pi/agent", "PI_OFFLINE": "1",
                    "PI_TELEMETRY": "0"},
            "timeout": 60, "timeout_blocked": 30,
        },
    }


@unittest.skipIf(SKIP_CLIS, "NETLOG_SKIP_CLIS=1 or NETLOG_SKIP_NETWORK=1")
class RealClis(unittest.TestCase):
    """Each harness through the capture, and in the sandbox without the proxy settings."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp(prefix="netlog-test-clis-"))
        commands = cli_commands()

        async def everything():
            jobs = []
            for name, c in commands.items():
                jobs.append(run_captured(cls.base, f"{name}-proxied", c["cmd"], extra_env=c["env"], stdin=c["stdin"],
                                         timeout=c["timeout"]))
                jobs.append(run_captured(cls.base, f"{name}-blocked", c["cmd"], extra_env=c["env"], stdin=c["stdin"],
                                         timeout=c["timeout_blocked"], proxy_env=False))
            return await asyncio.gather(*jobs)

        outcomes = asyncio.run(everything())
        cls.proxied = {name: outcomes[2 * i] for i, name in enumerate(commands)}
        cls.blocked = {name: outcomes[2 * i + 1] for i, name in enumerate(commands)}
        report = {name: {"hosts": o.summary.get("requests_per_host"),
                         "requests": [f"{r['request']['method']} {r['request']['url'].split('?')[0]} -> "
                                      f"{(r['response'] or {}).get('status')}" for r in o.http()],
                         "blocked_without_proxy": cls.blocked[name].summary.get("blocked_by_sandbox")}
                  for name, o in cls.proxied.items()}
        (cls.base / "netlog_hosts.json").write_text(json.dumps(report, indent=2))
        for name, entry in report.items():
            print(f"\n{name}: {entry['hosts']}", file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        for outcome in list(cls.proxied.values()) + list(cls.blocked.values()):
            shutil.rmtree(outcome.run_dir.parent, ignore_errors=True)

    def model_request(self, name: str) -> dict:
        outcome = self.proxied[name]
        posts = [r for r in outcome.http("openrouter.ai")
                 if r["request"]["method"] == "POST" and f"{MARKER}-" in r["request"]["body"]]
        self.assertTrue(posts, f"{name}: no model request with the prompt reached the proxy: "
                               f"{outcome.summary.get('requests_per_host')} {outcome.stderr[-500:]}")
        return posts[0]

    def test_model_request_recorded_with_headers_and_body(self):
        for name in self.proxied:
            with self.subTest(name):
                flow = self.model_request(name)
                headers = {k.lower(): v for k, v in flow["request"]["headers"]}
                auth = headers.get("authorization") or headers.get("x-api-key")
                self.assertEqual(auth, "<redacted>")
                self.assertIn("json", headers.get("content-type", ""))
                self.assertGreater(flow["request"]["body_size"], 100)
                json.loads(flow["request"]["body"])  # the whole body, intact

    def test_response_body_recorded(self):
        for name in self.proxied:
            with self.subTest(name):
                flow = self.model_request(name)
                self.assertEqual(flow["response"]["status"], 401)
                self.assertIn("error", json.loads(flow["response"]["body"]))

    def test_every_connection_was_intercepted(self):
        for name, outcome in self.proxied.items():
            with self.subTest(name):
                s = outcome.summary
                self.assertEqual(s["not_intercepted"], [], s["not_intercepted"])
                self.assertEqual(s["blocked_attempts"], 0, s["blocked_by_sandbox"])
                self.assertEqual(s["addon_errors"], 0, s["error_details"])
                self.assertTrue(s["proxy_stopped_cleanly"])
                self.assertEqual(netlog.problems(s), [])

    def test_fake_key_is_written_nowhere(self):
        for name, outcome in list(self.proxied.items()) + [(f"{n}-blocked", o) for n, o in self.blocked.items()]:
            with self.subTest(name):
                text = outcome.all_written_text()
                for fragment in (FAKE_KEY, "fake-key-for-capture-test"):
                    self.assertNotIn(fragment, text)
                self.assertEqual(outcome.summary["secrets_redacted_at_stop"], 0)

    def test_without_proxy_env_nothing_reaches_the_network(self):
        for name, outcome in self.blocked.items():
            with self.subTest(name):
                self.assertEqual(outcome.summary["requests"], 0)
                self.assertEqual(outcome.summary["not_intercepted"], [])
                # OpenRouter's answer to the fake key never arrived.
                self.assertNotIn("User not found", outcome.stdout + outcome.stderr)
                self.assertNotIn('"status":401', outcome.stdout.replace(" ", ""))
                note_blocked(self, outcome, f"{name} without proxy settings")

    def test_codex_git_traffic_is_captured(self):
        # Codex shells out to git for its plugin repo; git needs GIT_SSL_CAINFO.
        git = [r for r in self.proxied["codex"].http("github.com")
               if any(k.lower() == "user-agent" and v.startswith("git/") for k, v in r["request"]["headers"])]
        if not git:
            self.skipTest("Codex did not sync its plugin repo in this run")
        self.assertTrue(all(r["response"] and r["response"]["status"] == 200 for r in git))


@unittest.skipIf(SKIP_CLIS, "NETLOG_SKIP_CLIS=1 or NETLOG_SKIP_NETWORK=1")
class WebToolsThroughCapture(unittest.TestCase):
    """run.py's real attempt(), with the capture on, against the local fake model server.

    The fake server scripts a search and a page read (https://example.com), so each
    harness runs its web tools for real inside the sandbox. This checks that the
    capture leaves web search and fetch working, and that those requests and the
    harness's telemetry are in the record. A fake key; nothing is spent.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ballot import runner as run
        import test_pipeline as tp
        from fake_provider import FakeProvider
        from ballot.harnesses import ClaudeCode, CodexOpenRouter, GeminiCli, GrokBuild, Pi

        cls.base = Path(tempfile.mkdtemp(prefix="netlog-test-web-"))
        cls.keys = tp.KEYS
        saved = run.CAPTURE_NETWORK
        run.CAPTURE_NETWORK = True
        cls.results = {}
        try:
            # Codex on its own key can only show its web tool to OpenAI itself, so it's checked
            # through the capture in test_pipeline.py; here Codex runs the OpenRouter way.
            for name in ("claude_code", "codex_openrouter", "gemini_cli", "grok_build", "pi"):
                fake = FakeProvider()
                try:
                    if name == "claude_code":
                        spec = tp.make_spec("anthropic/claude-opus-5.5", "anthropic", "native", name, effort="max")
                        harness = tp.ViaFake(ClaudeCode(), env={"ANTHROPIC_BASE_URL": fake.url})
                    elif name == "codex_openrouter":
                        spec = tp.make_spec("openai/gpt-6-astra", "openai", "native", name, effort="max")
                        harness = tp.ViaFake(CodexOpenRouter(), extra_args=[
                            "-c", f'model_providers.openrouter.base_url="{fake.url}/v1"'])
                    elif name == "gemini_cli":
                        spec = tp.make_spec("gemini-3.8-flash", "google-ai-studio", "native", name, effort="high")
                        harness = tp.ViaFake(GeminiCli(), env={"GOOGLE_GEMINI_BASE_URL": fake.url})
                    elif name == "grok_build":
                        spec = tp.make_spec("x-ai/grok-4.7", "xai", "native", name, effort="xhigh")
                        harness = tp.ViaFake(GrokBuild(), env={"GROK_MODELS_BASE_URL": f"{fake.url}/v1",
                                                               "GROK_XAI_API_BASE_URL": f"{fake.url}/v1"})
                    else:
                        model = tp.CFG["models"][0]
                        spec = tp.make_spec(model["model"], model["pin"], "common", "pi", effort=model["pi_thinking"])
                        harness = tp.ViaFake(Pi(tp.SEARCH, cls.base / "web-cache"),
                                             env={"OPENROUTER_CHAT_URL": f"{fake.url}/api/v1/chat/completions"},
                                             pi_base_url=f"{fake.url}/api/v1")
                    run_dir = cls.base / name
                    run_dir.mkdir()
                    result = asyncio.run(run.attempt(spec, harness, cls.keys, run_dir, timeout=150))
                    cls.results[name] = (result, run_dir, len(fake.requests) + len(fake.gets))
                finally:
                    fake.stop()
        finally:
            run.CAPTURE_NETWORK = saved
        for name, (result, run_dir, _) in cls.results.items():
            print(f"\n{name}: {result['status']} {result['answer']}, searches {result['searches']}, "
                  f"fetches {result['fetches']}, hosts {result['network'].get('requests_per_host')}", file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_web_search_and_fetch_still_work_under_the_capture(self):
        for name, (result, _, fake_requests) in self.results.items():
            with self.subTest(name):
                self.assertEqual(result["status"], "answered", result["error"])
                self.assertEqual(result["answer"], "YES")
                self.assertGreaterEqual(len(result["searches"]), 1)
                self.assertEqual(result["search_errors"], 0)
                self.assertEqual(result["tool_errors"], 0)
                self.assertGreater(fake_requests, 0)

    def test_every_request_is_in_the_record(self):
        for name, (result, run_dir, fake_requests) in self.results.items():
            with self.subTest(name):
                network = result["network"]
                problems = netlog.problems(network)
                if name in ("grok_build", "gemini_cli"):
                    # Their page readers look up a site's address before fetching it through the
                    # proxy, so their runs allow lookups and say so. Their resolvers sometimes also
                    # try the network directly; the sandbox blocks that, so nothing gets around the record.
                    dns = "DNS lookups were allowed and are not in the record (block_dns=False)"
                    self.assertIn(dns, problems)
                    problems = [p for p in problems if p != dns and "ignored the proxy were blocked" not in p]
                self.assertEqual(problems, [])
                records = netlog.read_log(run_dir / netlog.GZ_NAME)
                # Every request the fake model server answered went through the proxy and is recorded.
                to_fake = [r for r in records if r["type"] == "http" and r["server"]["host"] == "127.0.0.1"]
                self.assertEqual(len(to_fake), fake_requests)
                self.assertTrue(all(r["response"] and r["response"]["status"] == 200 for r in to_fake))
                for url in result["fetches"]:
                    self.assertTrue(any(r["type"] == "http" and r["request"]["url"] == url for r in records),
                                    f"{name}: the page read of {url} is not in the record")

    def test_claude_code_page_reads_and_telemetry_are_recorded(self):
        result, run_dir, _ = self.results["claude_code"]
        urls = [r["request"]["url"] for r in netlog.read_log(run_dir / netlog.GZ_NAME) if r["type"] == "http"]
        self.assertIn("https://example.com/", urls)
        self.assertTrue(any(u.startswith("https://api.anthropic.com/api/web/domain_info") for u in urls), urls)
        self.assertTrue(any("event_logging" in u for u in urls), urls)

    def test_no_key_is_in_any_file_of_the_run(self):
        import tarfile

        for name, (_, run_dir, _) in self.results.items():
            with self.subTest(name):
                for path in run_dir.iterdir():
                    if path.name.endswith(".tar.gz"):
                        with tarfile.open(path) as tar:
                            for member in tar.getmembers():
                                if member.isfile():
                                    data = tar.extractfile(member).read()
                                    for key in self.keys.values():
                                        self.assertNotIn(key.encode(), data, member.name)
                        continue
                    data = path.read_bytes()
                    if path.suffix == ".gz":
                        data = gzip.decompress(data)
                    for key in self.keys.values():
                        self.assertNotIn(key.encode(), data, path.name)


if __name__ == "__main__":
    unittest.main()
