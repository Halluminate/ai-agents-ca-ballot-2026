"""mitmproxy addon that writes every network flow to a JSON-lines file.

netlog.py loads it with `mitmdump -s netlog_addon.py`. It reads three variables:

  NETLOG_FILE     the file to append to, one JSON object per line (required)
  NETLOG_SECRETS  secrets to redact, one per line (optional)
  NETLOG_READY    a file to write once the proxy is listening (optional)

Record types, all with a "type" field:

  proxy_start, proxy_stop    the proxy's own start and stop
  client_connect             a client opened a connection to the proxy
  client_disconnect          that connection closed, with exact bytes each way
  http                       one request and its response, with full bodies
  websocket_message          one WebSocket message; websocket_end closes the stream
  tcp_start, tcp_message, tcp_end   raw TCP that was not HTTP
  tls_failed                 a TLS handshake that failed, on the client or server side
  not_intercepted            a connection that carried bytes but no readable flow
  addon_error                this addon failed on a hook; traffic still passed

Response and request bodies are streamed through unchanged. Each chunk is copied
on the way past and the joined body is written when the flow ends, so a slow
server-sent event stream reaches the client exactly as fast as it would directly.

Headers that carry credentials are replaced with "<redacted>", and every secret
from NETLOG_SECRETS is replaced wherever it appears: URLs, headers (names too),
bodies, WebSocket and TCP messages, error text. That includes its URL-encoded,
JSON-escaped and base64 forms, compressed bodies (decoded first, even when cut
off mid-stream), and a secret split across two stream chunks or two messages.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import os
import re
import time
import urllib.parse
import zlib
from collections import defaultdict

from mitmproxy import ctx, version
from mitmproxy.net import encoding

REDACTED = "<redacted>"
REDACT_HEADERS = frozenset({
    "authorization", "proxy-authorization", "x-api-key", "x-goog-api-key", "cookie", "set-cookie",
    "x-subscription-token",  # Brave Search's key header, used by pi_ext/web_tools.ts
    "api-key",  # Azure OpenAI style
})
MAX_CHUNK_TIMES = 20_000

logger = logging.getLogger("netlog")


def secret_variants(secret: str) -> set[str]:
    """Every form of a secret the log could hold. netlog.py keeps an identical copy for its final check."""
    variants = {secret, secret.replace("/", "\\/")}
    for safe in ("", "/"):
        for encoded in (urllib.parse.quote(secret, safe=safe), urllib.parse.quote_plus(secret, safe=safe)):
            variants.add(encoded)
            variants.add(re.sub("%[0-9A-F]{2}", lambda m: m.group(0).lower(), encoded))  # %2f is valid too
    # Base64 (standard and URL-safe) at each of the three byte alignments. Only the
    # characters that depend on the secret alone, so it matches inside longer data,
    # such as "Basic base64(user:key)" in a header that is not redacted by name.
    raw = secret.encode()
    for offset in range(3):
        encoded = base64.b64encode(b"\0" * offset + raw).decode()
        first = (8 * offset + 5) // 6  # first character with no bits from the padding before
        end = (8 * offset + 8 * len(raw)) // 6  # characters after this mix in the bytes that follow
        core = encoded[first:end]
        if len(core) >= 8:
            variants |= {core, core.replace("+", "-").replace("/", "_")}
    return {v for v in variants if v}


class Redactor:
    """Replaces every secret, in all the forms secret_variants() lists, with <redacted>."""

    # A cut-off secret at the very end of a stream is redacted from this length on.
    MIN_TAIL = 8

    def __init__(self, secrets: list[str]):
        variants: set[str] = set()
        for secret in secrets:
            secret = secret.strip()
            if secret:
                variants |= secret_variants(secret)
        # Longest first, so a secret that contains another is replaced whole.
        self.texts = sorted(variants, key=len, reverse=True)
        self.raw = [v.encode() for v in self.texts]
        self.longest = max((len(v) for v in self.raw), default=0)
        # Every proper prefix of every form: the start of a secret that the next piece may finish.
        self.prefixes = {v[:i] for v in self.raw for i in range(1, len(v))}

    def text(self, value: str | None) -> str | None:
        if not value:
            return value
        for secret in self.texts:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return value

    def bytes(self, data: bytes) -> bytes:
        for secret in self.raw:
            if secret in data:
                data = data.replace(secret, REDACTED.encode())
        return data

    def hold_back(self, data: bytes) -> int:
        """How much of one piece of a stream can be written now.

        data[cut:] is the longest ending of data that could be the start of a
        secret. It goes in front of the next piece of the same stream, so a secret
        split across two or more pieces is always redacted whole.
        """
        for start in range(max(0, len(data) - self.longest + 1), len(data)):
            if data[start:] in self.prefixes:
                return start
        return len(data)

    def tail(self, data: bytes) -> bytes:
        """Redact a secret cut off at the very end of a stream, from MIN_TAIL bytes on."""
        cut = self.hold_back(data)
        if len(data) - cut >= self.MIN_TAIL:
            return data[:cut] + REDACTED.encode()
        return data


def partial_decode(raw: bytes, name: str) -> bytes:
    """Decode as much of a cut-off or damaged compressed body as possible.

    A stream cut off mid-body cannot be decoded whole, and its compressed bytes
    could still hold a secret that anyone can decompress. Decoding the readable
    part means it can be redacted and stored as text instead.
    """
    out: list[bytes] = []
    piece = 4096
    try:
        if name in ("gzip", "x-gzip", "deflate", "deflateraw"):
            for wbits in ((47,) if "gzip" in name else (15, -15)):
                decoder, out = zlib.decompressobj(wbits), []
                try:
                    for i in range(0, len(raw), piece):
                        out.append(decoder.decompress(raw[i:i + piece]))
                except zlib.error:
                    pass
                if any(out):
                    break
        elif name == "br":
            import brotli

            decoder = brotli.Decompressor()
            for i in range(0, len(raw), piece):
                out.append(decoder.process(raw[i:i + piece]))
        elif name == "zstd":
            try:
                from compression import zstd
            except ImportError:
                from backports import zstd
            decoder = zstd.ZstdDecompressor()
            for i in range(0, len(raw), piece):
                out.append(decoder.decompress(raw[i:i + piece]))
                if decoder.eof:
                    break
    except Exception:  # noqa: BLE001 - keep what was decoded before the damage
        pass
    return b"".join(out)


def decode_body(raw: bytes, content_encoding: str) -> tuple[bytes, dict]:
    """Undo Content-Encoding, last applied first. Falls back to a partial decode."""
    names = [n.strip().lower() for n in content_encoding.split(",")]
    names = [n for n in names if n and n != "identity"]
    data, info = raw, {}
    for name in reversed(names):
        try:
            data = encoding.decode(data, "gzip" if name == "x-gzip" else name)
        except Exception as e:  # noqa: BLE001
            partial = partial_decode(data, name)
            info["body_decode_error"] = f"{type(e).__name__}: {e}"[:200]
            if not partial:
                return data, info  # stored as received; secrets in it are still redacted literally
            data = partial
            info["body_decode_partial"] = True
    if names:
        info["body_decoded_from"] = content_encoding
    return data, info


def safe_hook(func):
    """A bug in this addon must never break traffic, and must never go unnoticed."""

    @functools.wraps(func)
    def wrapper(self, *args):
        try:
            return func(self, *args)
        except Exception as e:  # noqa: BLE001
            self.write({"type": "addon_error", "time": time.time(), "hook": func.__name__,
                        "error": self.redact.text(f"{type(e).__name__}: {e}")})

    return wrapper


def address(addr) -> list | None:
    return [addr[0], addr[1]] if addr else None


class ConnState:
    __slots__ = ("id", "peer", "start", "flows", "connect", "sni", "alpn_offers",
                 "client_hello_bytes", "tls_error", "server")

    def __init__(self, client):
        self.id = client.id
        self.peer = address(client.peername)
        self.start = client.timestamp_start or time.time()
        self.flows = 0
        self.connect: dict | None = None
        self.sni: str | None = None
        self.alpn_offers: list[str] = []
        self.client_hello_bytes = 0
        self.tls_error: str | None = None
        self.server: list | None = None


class FlowState:
    __slots__ = ("flow", "request_chunks", "response_chunks", "chunk_times", "response_started")

    def __init__(self, flow):
        self.flow = flow
        self.request_chunks: list[bytes] = []
        self.response_chunks: list[bytes] = []
        self.chunk_times: list[list] = []
        self.response_started: float | None = None


def recorder(chunks: list[bytes], times: list[list] | None = None, started=None):
    """A stream function: copy each chunk and hand it on unchanged."""

    def record(data: bytes) -> bytes:
        if data:
            chunks.append(data)
            if times is not None and len(times) < MAX_CHUNK_TIMES:
                times.append([round(time.time() - (started() or time.time()), 4), len(data)])
        return data

    return record


class NetLog:
    def __init__(self):
        path = os.environ.get("NETLOG_FILE")
        if not path:
            raise RuntimeError("NETLOG_FILE is not set")
        self.redact = Redactor(os.environ.get("NETLOG_SECRETS", "").splitlines())
        self.out = open(path, "ab")
        self.conns: dict[str, ConnState] = {}
        self.flows: dict[str, FlowState] = {}
        self.websockets: dict[str, object] = {}
        self.tcp_flows: set[str] = set()
        # Per (flow, direction): bytes held back from the last message, see message().
        self.carry: dict[tuple[str, bool], bytes] = {}
        # Exact socket bytes per client connection, kept by install_byte_counter.
        self.socket_bytes: dict[str, dict[str, int]] = defaultdict(
            lambda: {"from_client": 0, "to_client": 0, "to_server": 0, "from_server": 0}
        )
        self.closed = False
        self.byte_counter = install_byte_counter(self)

    # ---- output -------------------------------------------------------------

    def write(self, record: dict) -> None:
        if self.closed:
            return
        # ensure_ascii keeps lone surrogates from undecodable headers writable.
        self.out.write(json.dumps(record, ensure_ascii=True).encode() + b"\n")
        self.out.flush()

    def headers(self, headers) -> list[list[str]]:
        if headers is None:
            return []
        return [
            [self.redact.text(name), REDACTED if name.lower() in REDACT_HEADERS else self.redact.text(value)]
            for name, value in headers.items(multi=True)
        ]

    def body(self, raw: bytes | None, headers) -> dict:
        """Text bodies as text, anything else as base64, both after secrets are redacted."""
        raw = raw or b""
        out: dict = {"body_size": len(raw)}
        data = raw
        content_encoding = (headers.get("content-encoding", "") if headers is not None else "").strip().lower()
        if raw and content_encoding and content_encoding != "identity":
            data, info = decode_body(raw, content_encoding)
            if "body_decode_error" in info:
                info["body_decode_error"] = self.redact.text(info["body_decode_error"])
            out.update(info)
        data = self.redact.tail(self.redact.bytes(data))
        return out | self.encode(data)

    @staticmethod
    def encode(data: bytes) -> dict:
        try:
            return {"body": data.decode("utf-8"), "body_base64": False}
        except UnicodeDecodeError:
            return {"body": base64.b64encode(data).decode("ascii"), "body_base64": True}

    def message(self, flow_id: str, from_client: bool, content: bytes) -> dict:
        """One WebSocket or TCP message, redacted as part of its whole stream.

        A secret split across messages is redacted whole: the end of a message that
        could be the start of a secret is moved to the front of the next message of
        the same stream ("held_back" says how many bytes moved on).
        """
        key = (flow_id, from_client)
        # Redact whole secrets first: holding back first could split off the last
        # character of a secret that this message completes, and leak the rest.
        data = self.redact.bytes(self.carry.pop(key, b"") + (content or b""))
        cut = self.redact.hold_back(data)
        if cut < len(data):
            self.carry[key] = data[cut:]
        record = {"size": len(content or b""), **self.encode(data[:cut])}
        if cut < len(data):
            record["held_back"] = len(data) - cut
        return record

    def flush_carry(self, flow_id: str, kind: str) -> None:
        """Write what a stream held back when it ends, so nothing it carried is lost."""
        for key in [k for k in self.carry if k[0] == flow_id]:
            data = self.carry.pop(key)
            self.write({"type": kind, "time": time.time(), "flow": flow_id, "from_client": key[1],
                        "size": 0, "held_back_tail": True, **self.encode(self.redact.tail(self.redact.bytes(data)))})

    def conn(self, client) -> ConnState:
        state = self.conns.get(client.id)
        if state is None:
            state = self.conns[client.id] = ConnState(client)
        return state

    # ---- lifecycle ----------------------------------------------------------

    @safe_hook
    def running(self):
        addrs = [address(a) for a in ctx.master.addons.get("proxyserver").listen_addrs()]
        self.write({"type": "proxy_start", "time": time.time(), "pid": os.getpid(), "listen": addrs,
                    "mitmproxy": version.VERSION, "byte_counter": self.byte_counter,
                    "secrets": len(self.redact.texts)})
        ready = os.environ.get("NETLOG_READY")
        if ready:
            tmp = f"{ready}.tmp"
            with open(tmp, "w") as f:
                json.dump({"listen": addrs, "pid": os.getpid()}, f)
            os.replace(tmp, ready)

    def done(self):
        """Shutdown. Whatever is still in flight is written as incomplete, never dropped."""
        try:
            for state in list(self.flows.values()):
                try:
                    self.write_http_safely(state.flow, state, incomplete=True)
                except Exception:  # noqa: BLE001 - the fallback record is already written
                    pass
            self.flows.clear()
            for flow_id in list(self.websockets):
                self.flush_carry(flow_id, "websocket_message")
                self.write({"type": "websocket_end", "time": time.time(), "flow": flow_id, "incomplete": True})
            self.websockets.clear()
            for flow_id in list(self.tcp_flows):
                self.flush_carry(flow_id, "tcp_message")
                self.write({"type": "tcp_end", "time": time.time(), "flow": flow_id, "incomplete": True})
            self.tcp_flows.clear()
            for flow_id in {k[0] for k in self.carry}:
                self.flush_carry(flow_id, "stream_tail")
            for state in list(self.conns.values()):
                self.write_connection(state, end=time.time(), open_at_shutdown=True)
            self.conns.clear()
            self.write({"type": "proxy_stop", "time": time.time()})
        finally:
            self.closed = True
            self.out.close()

    # ---- connections --------------------------------------------------------

    @safe_hook
    def client_connected(self, client):
        state = self.conn(client)
        self.write({"type": "client_connect", "time": state.start, "conn": client.id, "peer": state.peer})

    @safe_hook
    def client_disconnected(self, client):
        state = self.conns.pop(client.id, None) or ConnState(client)
        self.write_connection(state, end=client.timestamp_end or time.time(), error=client.error)

    def write_connection(self, state: ConnState, end: float, error: str | None = None, open_at_shutdown: bool = False):
        counts = self.socket_bytes.pop(state.id, None) if self.byte_counter else None
        counts = dict(counts) if counts else ({"from_client": 0, "to_client": 0, "to_server": 0, "from_server": 0}
                                              if self.byte_counter else None)
        record = {
            "type": "client_disconnect", "time": end, "conn": state.id, "peer": state.peer,
            "start": state.start, "duration": round(end - state.start, 4),
            "connect": state.connect, "sni": state.sni, "alpn_offers": state.alpn_offers,
            "flows": state.flows, "bytes": counts,
            "tls_error": self.redact.text(state.tls_error), "error": self.redact.text(error),
        }
        if open_at_shutdown:
            record["open_at_shutdown"] = True
        self.write(record)
        bytes_up = counts["from_client"] if counts else state.client_hello_bytes
        if state.flows == 0 and (bytes_up > 0 or state.tls_error):
            # Bytes moved but no request, message or TCP stream was recorded.
            host, port = (state.connect or {}).get("host"), (state.connect or {}).get("port")
            if state.server:
                host, port = state.server
            self.write({
                "type": "not_intercepted", "time": end, "conn": state.id,
                "host": host, "port": port, "sni": state.sni,
                "start": state.start, "end": end, "duration": round(end - state.start, 4),
                "bytes_up": bytes_up,
                "bytes_down": counts["to_client"] if counts else None,
                "bytes_to_server": counts["to_server"] if counts else None,
                "bytes_from_server": counts["from_server"] if counts else None,
                "client_hello_bytes": state.client_hello_bytes,
                "reason": self.redact.text(state.tls_error or error or "no request was read on this connection"),
            })

    @safe_hook
    def http_connect(self, flow):
        state = self.conn(flow.client_conn)
        state.connect = {
            "time": flow.request.timestamp_start, "host": flow.request.host, "port": flow.request.port,
            "headers": self.headers(flow.request.headers),
        }

    @safe_hook
    def http_connect_error(self, flow):
        self.write({"type": "connect_error", "time": time.time(), "conn": flow.client_conn.id,
                    "host": flow.request.host, "port": flow.request.port,
                    "error": self.redact.text(flow.error.msg if flow.error else None),
                    "status": flow.response.status_code if flow.response else None})

    @safe_hook
    def tls_clienthello(self, data):
        state = self.conn(data.context.client)
        state.sni = data.client_hello.sni
        state.alpn_offers = [a.decode("ascii", "replace") for a in data.client_hello.alpn_protocols]
        state.client_hello_bytes = len(data.client_hello.raw_bytes())
        state.server = address(data.context.server.address)

    @safe_hook
    def tls_failed_client(self, data):
        state = self.conn(data.context.client)
        state.tls_error = data.conn.error or "client TLS handshake failed"
        self.write({"type": "tls_failed", "side": "client", "time": time.time(), "conn": state.id,
                    "server": address(data.context.server.address), "sni": data.conn.sni,
                    "error": self.redact.text(state.tls_error)})

    @safe_hook
    def tls_failed_server(self, data):
        self.write({"type": "tls_failed", "side": "server", "time": time.time(), "conn": data.context.client.id,
                    "server": address(data.conn.address), "sni": data.conn.sni,
                    "error": self.redact.text(data.conn.error)})

    # ---- HTTP ---------------------------------------------------------------

    @safe_hook
    def requestheaders(self, flow):
        state = self.flows[flow.id] = FlowState(flow)
        self.conn(flow.client_conn).flows += 1
        flow.request.stream = recorder(state.request_chunks)

    @safe_hook
    def responseheaders(self, flow):
        state = self.flows.get(flow.id)
        if state is None:
            state = self.flows[flow.id] = FlowState(flow)
        state.response_started = time.time()
        flow.response.stream = recorder(state.response_chunks, state.chunk_times, lambda: state.response_started)

    @safe_hook
    def response(self, flow):
        state = self.flows.pop(flow.id, None)
        self.write_http_safely(flow, state)

    @safe_hook
    def error(self, flow):
        state = self.flows.pop(flow.id, None)
        self.write_http_safely(flow, state)

    def write_http_safely(self, flow, state: FlowState | None, incomplete: bool = False):
        try:
            self.write_http(flow, state, incomplete)
        except Exception as e:
            # Keep at least the request line and the status: a flow is never missing.
            self.write({
                "type": "http", "id": flow.id, "partial_record": True,
                "server": {"host": flow.request.host, "port": flow.request.port},
                "request": {"method": flow.request.method, "url": self.redact.text(flow.request.url)},
                "response": {"status": flow.response.status_code} if flow.response else None,
                "error": self.redact.text(flow.error.msg) if flow.error else None,
                "addon_error": self.redact.text(f"{type(e).__name__}: {e}"),
            })
            raise  # safe_hook adds an addon_error record, which problems() reports

    def write_http(self, flow, state: FlowState | None, incomplete: bool = False):
        request, response = flow.request, flow.response
        if state is not None and state.request_chunks:
            request_raw = b"".join(state.request_chunks)
        else:
            request_raw = request.raw_content or b""
        record = {
            "type": "http", "id": flow.id, "conn": flow.client_conn.id,
            "start": request.timestamp_start,
            "end": (response.timestamp_end if response and response.timestamp_end else None) or time.time(),
            "server": {
                "host": request.host, "port": request.port,
                "sni": flow.server_conn.sni or flow.client_conn.sni,
                "client_sni": flow.client_conn.sni,
                "address": address(flow.server_conn.address), "ip": address(flow.server_conn.peername),
                "tls": flow.server_conn.tls_established,
                "tls_version": flow.server_conn.tls_version,
                "alpn": flow.server_conn.alpn.decode("ascii", "replace") if flow.server_conn.alpn else None,
            },
            "request": {
                "method": request.method,
                "url": self.redact.text(request.url),
                "http_version": request.http_version,
                "headers": self.headers(request.headers),
                "trailers": self.headers(request.trailers) if request.trailers else None,
                "timestamp_end": request.timestamp_end,
                **self.body(request_raw, request.headers),
            },
            "response": None,
            "error": self.redact.text(flow.error.msg) if flow.error else None,
            "websocket": flow.websocket is not None,
        }
        if response is not None:
            if state is not None and state.response_chunks:
                response_raw = b"".join(state.response_chunks)
            else:
                response_raw = response.raw_content or b""
            record["response"] = {
                "status": response.status_code,
                "reason": response.reason,
                "http_version": response.http_version,
                "headers": self.headers(response.headers),
                "trailers": self.headers(response.trailers) if response.trailers else None,
                "timestamp_start": response.timestamp_start,
                "timestamp_end": response.timestamp_end,
                "chunks": len(state.response_chunks) if state else None,
                "chunk_times": state.chunk_times if state else None,
                **self.body(response_raw, response.headers),
            }
        if incomplete:
            record["incomplete"] = True
        self.write(record)

    # ---- WebSocket ----------------------------------------------------------

    @safe_hook
    def websocket_start(self, flow):
        self.websockets[flow.id] = flow
        self.write({"type": "websocket_start", "time": time.time(), "flow": flow.id,
                    "url": self.redact.text(flow.request.url)})

    @safe_hook
    def websocket_message(self, flow):
        message = flow.websocket.messages[-1]
        self.write({"type": "websocket_message", "time": message.timestamp, "flow": flow.id,
                    "from_client": message.from_client, "opcode": message.type.name,
                    **self.message(flow.id, message.from_client, message.content)})

    @safe_hook
    def websocket_end(self, flow):
        self.websockets.pop(flow.id, None)
        self.flush_carry(flow.id, "websocket_message")
        ws = flow.websocket
        self.write({"type": "websocket_end", "time": ws.timestamp_end or time.time(), "flow": flow.id,
                    "close_code": ws.close_code, "close_reason": self.redact.text(ws.close_reason),
                    "closed_by_client": ws.closed_by_client, "messages": len(ws.messages),
                    "error": self.redact.text(flow.error.msg) if flow.error else None})

    # ---- raw TCP ------------------------------------------------------------

    @safe_hook
    def tcp_start(self, flow):
        self.conn(flow.client_conn).flows += 1
        self.tcp_flows.add(flow.id)
        self.write({"type": "tcp_start", "time": time.time(), "flow": flow.id, "conn": flow.client_conn.id,
                    "server": address(flow.server_conn.address), "sni": flow.client_conn.sni})

    @safe_hook
    def tcp_message(self, flow):
        message = flow.messages[-1]
        self.write({"type": "tcp_message", "time": message.timestamp, "flow": flow.id,
                    "from_client": message.from_client, **self.message(flow.id, message.from_client, message.content)})

    @safe_hook
    def tcp_end(self, flow):
        self.tcp_flows.discard(flow.id)
        self.flush_carry(flow.id, "tcp_message")
        self.write({"type": "tcp_end", "time": time.time(), "flow": flow.id, "messages": len(flow.messages)})

    @safe_hook
    def tcp_error(self, flow):
        self.tcp_flows.discard(flow.id)
        self.flush_carry(flow.id, "tcp_message")
        self.write({"type": "tcp_end", "time": time.time(), "flow": flow.id, "messages": len(flow.messages),
                    "error": self.redact.text(flow.error.msg) if flow.error else None})


def install_byte_counter(netlog: NetLog) -> bool:
    """Count the exact bytes read from and written to every socket.

    mitmproxy has no hook for raw socket bytes. Every socket read passes through
    ConnectionHandler.server_event as a DataReceived event, and every socket write
    goes through the asyncio writer that the handler keeps per connection, so this
    counts reads there and wraps each writer the first time it is seen. It is what
    gives a connection that was never intercepted its byte counts. If mitmproxy's
    internals ever change shape, counting switches off, the log says
    "byte_counter": false, and traffic is never affected.
    """
    try:
        from mitmproxy.connection import Client
        from mitmproxy.proxy import events, server

        original = server.ConnectionHandler.server_event
        if getattr(original, "_netlog", False):
            return True
    except Exception:  # noqa: BLE001
        return False

    def counter(handler, connection, direction: str):
        counts = netlog.socket_bytes[handler.client.id]
        if isinstance(connection, Client):
            return counts, "from_client" if direction == "in" else "to_client"
        return counts, "from_server" if direction == "in" else "to_server"

    def wrap_writer(handler, connection, writer) -> None:
        write = writer.write

        def counting_write(data, _write=write):
            try:
                counts, key = counter(handler, connection, "out")
                counts[key] += len(data)
            except Exception:  # noqa: BLE001
                pass
            return _write(data)

        writer.write = counting_write
        writer._netlog = True

    async def server_event(self, event):
        try:
            if isinstance(event, events.DataReceived):
                counts, key = counter(self, event.connection, "in")
                counts[key] += len(event.data)
            for connection, io in list(self.transports.items()):
                if io.writer is not None and not getattr(io.writer, "_netlog", False):
                    wrap_writer(self, connection, io.writer)
        except Exception:  # noqa: BLE001
            pass
        return await original(self, event)

    server_event._netlog = True
    server.ConnectionHandler.server_event = server_event
    return True


addons = [NetLog()]
