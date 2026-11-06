"""A local stand-in for the model APIs.

It scripts a short research loop (search, read a page, answer), so the real harness
binaries can run end to end with no API key and no spend. It also records every
request, which shows exactly which tools each harness offers the model.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FINAL = "Yes"
SEARCH_ARGS = {"query": "California Proposition 1 2026"}
CODEX_SEARCH_JS = 'const r = await tools.web__run({search_query: [{q: "California Proposition 1 2026"}]}); text(JSON.stringify(r));'


def tool_step(names: list[str], done: int) -> tuple[str, dict] | None:
    """The next tool call, given the tools on offer and how many have finished."""
    search = next((n for n in names if n in ("web_search", "WebSearch", "google_web_search")), None)
    fetch = next((n for n in names if n in ("web_fetch", "WebFetch")), None)
    if search and done == 0:
        return search, SEARCH_ARGS
    if fetch and done == 1:
        return fetch, {"url": "https://example.com/", "prompt": "Summarize https://example.com/"}
    return None


def anthropic_events(body: dict) -> list[dict]:
    tools = body.get("tools") or []
    messages = body.get("messages") or []
    done = sum(
        1
        for m in messages
        if isinstance(m.get("content"), list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    )
    if any(str(t.get("type", "")).startswith("web_search") for t in tools):
        return anthropic_search_events(body)  # Claude Code's search subrequest
    else:
        step, text = tool_step([t.get("name", "") for t in tools], done), FINAL

    usage = {"input_tokens": 100, "output_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    message = {"id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model"), "content": [],
               "stop_reason": None, "stop_sequence": None, "usage": usage}
    events = [{"type": "message_start", "message": message}]
    if step:
        name, args = step
        events += [
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "tool_use", "id": f"toolu_{done}", "name": name, "input": {}}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)}},
        ]
    else:
        events += [
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        ]
    return events + [
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use" if step else "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 20}},
        {"type": "message_stop"},
    ]


def anthropic_search_events(body: dict) -> list[dict]:
    """A server-side web search, the way Anthropic's API returns it: a call, results with links, then text."""
    usage = {"input_tokens": 100, "output_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    message = {"id": "msg_search", "type": "message", "role": "assistant", "model": body.get("model"), "content": [],
               "stop_reason": None, "stop_sequence": None, "usage": usage}
    results = [{"type": "web_search_result", "title": f"Result {n}", "url": f"https://example.com/{n}",
                "encrypted_content": "abc", "page_age": None} for n in range(1, 4)]
    return [
        {"type": "message_start", "message": message},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(SEARCH_ARGS)}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": results}},
        {"type": "content_block_stop", "index": 1},
        {"type": "content_block_start", "index": 2, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 2, "delta": {"type": "text_delta", "text": "Found three results."}},
        {"type": "content_block_stop", "index": 2},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 20, "server_tool_use": {"web_search_requests": 1}}},
        {"type": "message_stop"},
    ]


def openai_tools(body: dict) -> list[dict]:
    """GPT-6 requests declare tools in additional_tools items instead of a tools field."""
    items = body.get("input") if isinstance(body.get("input"), list) else []
    tools = list(body.get("tools") or [])
    for item in items:
        if isinstance(item, dict) and item.get("type") == "additional_tools":
            tools += item.get("tools") or []
    return tools


def openai_events(body: dict) -> list[dict]:
    tools = openai_tools(body)
    functions = [t.get("name", "") for t in tools if t.get("type") == "function"]
    hosted_search = any(str(t.get("type", "")).startswith("web_search") for t in tools)
    items = body.get("input") if isinstance(body.get("input"), list) else []
    done = sum(1 for i in items if isinstance(i, dict) and i.get("type") == "function_call_output")
    step = tool_step(functions, done)

    output = []
    has_exec = any(c.get("name") == "exec" for t in tools for c in t.get("tools") or [])
    exec_done = sum(1 for i in items if isinstance(i, dict) and i.get("type") == "custom_tool_call_output")
    if has_exec and exec_done == 0:
        # GPT-6 models in Codex reach web search through a nested tool inside exec.
        output.append({"type": "custom_tool_call", "id": "ctc_1", "call_id": "call_exec", "namespace": "functions",
                       "name": "exec", "input": CODEX_SEARCH_JS, "status": "completed"})
    elif step:
        name, args = step
        output.append({"type": "function_call", "id": f"fc_{done}", "call_id": f"call_{done}", "name": name,
                       "arguments": json.dumps(args), "status": "completed"})
    else:
        if hosted_search:
            output.append({"type": "web_search_call", "id": "ws_1", "status": "completed",
                           "action": {"type": "search", "query": SEARCH_ARGS["query"],
                                      "sources": [{"type": "url", "url": "https://example.com/1"}]}})
        output.append({"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                       "content": [{"type": "output_text", "text": FINAL, "annotations": []}]})

    events = [{"type": "response.created", "response": {"id": "resp_fake", "status": "in_progress", "output": []}}]
    for index, item in enumerate(output):
        added = {**item, "content": []} if item["type"] == "message" else item
        events.append({"type": "response.output_item.added", "output_index": index, "item": added})
        if item["type"] == "message":
            part = {"item_id": item["id"], "output_index": index, "content_index": 0}
            events += [
                {"type": "response.content_part.added", **part, "part": {"type": "output_text", "text": ""}},
                {"type": "response.output_text.delta", **part, "delta": FINAL},
                {"type": "response.output_text.done", **part, "text": FINAL},
                {"type": "response.content_part.done", **part, "part": item["content"][0]},
            ]
        if item["type"] == "function_call":
            events.append({"type": "response.function_call_arguments.delta", "item_id": item["id"],
                           "output_index": index, "delta": item["arguments"]})
            events.append({"type": "response.function_call_arguments.done", "item_id": item["id"],
                           "output_index": index, "arguments": item["arguments"]})
        events.append({"type": "response.output_item.done", "output_index": index, "item": item})
    usage = {"input_tokens": 100, "input_tokens_details": {"cached_tokens": 40}, "output_tokens": 20,
             "output_tokens_details": {"reasoning_tokens": 5}, "total_tokens": 120}
    events.append({"type": "response.completed",
                   "response": {"id": "resp_fake", "object": "response", "created_at": 1, "model": body.get("model"),
                                "status": "completed", "output": output, "usage": usage}})
    return events


def chat_events(body: dict) -> list[dict]:
    """Chat completions, which is what Grok Build speaks."""
    names = [(t.get("function") or {}).get("name", "") for t in body.get("tools") or []]
    done = sum(1 for m in body.get("messages") or [] if m.get("role") == "tool")
    step = tool_step(names, done)

    def chunk(delta: dict, finish: str | None = None, **extra) -> dict:
        return {"id": "chat_fake", "object": "chat.completion.chunk", "created": 1, "model": body.get("model"),
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}], **extra}

    if step:
        call = {"index": 0, "id": f"call_{done}", "type": "function",
                "function": {"name": step[0], "arguments": json.dumps(step[1])}}
        delta, finish = {"role": "assistant", "tool_calls": [call]}, "tool_calls"
    else:
        delta, finish = {"role": "assistant", "content": FINAL}, "stop"
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    return [chunk(delta), chunk({}, finish, usage=usage)]


def search_helper_response() -> dict:
    citations = [{"type": "url_citation", "url_citation": {"url": f"https://example.com/{n}", "title": f"Result {n}",
                                                           "content": f"Snippet {n}"}} for n in range(1, 4)]
    return {"id": "gen-fake", "choices": [{"message": {"role": "assistant", "content": "ignored", "annotations": citations}}],
            "usage": {"cost": 0.005}}


def gemini_response(body: dict) -> dict:
    tools = body.get("tools") or []
    contents = body.get("contents") or []
    done = sum(1 for c in contents for p in c.get("parts", []) if "functionResponse" in p)
    if any("urlContext" in t for t in tools):
        # Gemini CLI's page reader asks Google to read the page. An empty answer makes it fall
        # back to reading the page itself, the path that has to work through the capture.
        parts = [{"text": ""}]
    elif any("googleSearch" in t for t in tools):
        parts = [{"text": "No useful results."}]  # Gemini CLI's search subrequest
    else:
        names = [d["name"] for t in tools for d in t.get("functionDeclarations", [])]
        step = tool_step(names, done)
        if step and step[0] == "web_fetch":
            step = ("web_fetch", {"prompt": step[1]["prompt"]})  # Gemini CLI's page reader takes only a prompt
        parts = [{"functionCall": {"name": step[0], "args": step[1]}}] if step else [{"text": FINAL}]
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP", "index": 0}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 10,
                          "totalTokenCount": 130, "cachedContentTokenCount": 40},
    }


def offered_tools(body: dict) -> list[str]:
    """Every tool the model can see, in any of the request formats.

    Deferred tools are left out because the model can't see them. Namespaces are
    flattened, and tools nested inside Codex's exec tool are read from its description.
    """
    names = []
    for tool in openai_tools(body):
        if tool.get("defer_loading"):
            continue
        if isinstance(tool.get("function"), dict):
            names.append(tool["function"]["name"])
            continue
        if "functionDeclarations" in tool:
            names += [d["name"] for d in tool["functionDeclarations"]]
        elif tool.get("type") == "namespace":
            for inner in tool.get("tools") or []:
                names.append(inner["name"])
                if inner["name"] == "exec":
                    names += re.findall(r"^### `(\w+)`", inner.get("description", ""), flags=re.M)
        elif tool.get("name"):
            names.append(tool["name"])
        elif tool.get("type"):
            names.append(tool["type"])
        else:
            names += list(tool)
    return names


class FakeProvider:
    def __init__(self):
        self.requests: list[dict] = []
        self.gets: list[str] = []
        provider = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def send_body(self, data: bytes, content_type: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True

            def do_GET(self):
                provider.gets.append(self.path)
                if "/api-key" in self.path:  # Grok checks the key here before it starts
                    body = {"api_key_id": "fake", "name": "fake", "team_id": "fake", "acls": ["api-key:model:*"],
                            "api_key_blocked": False, "api_key_disabled": False, "team_blocked": False}
                else:
                    ids = ("grok-4.7", "x-ai/grok-4.7", "x-ai/grok-4.6")
                    body = {"data": [{"id": i, "object": "model", "owned_by": "xai"} for i in ids], "models": []}
                self.send_body(json.dumps(body).encode(), "application/json")

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = {}
                provider.requests.append({"path": self.path, "body": body, "headers": {k.lower(): v for k, v in self.headers.items()}})
                if "/alpha/search" in self.path:  # Codex's nested web search
                    self.send_body(b'{"output": []}', "application/json")
                elif "/chat/completions" in self.path and body.get("plugins"):
                    # The shared harness's search helper: results come back as citations.
                    self.send_body(json.dumps(search_helper_response()).encode(), "application/json")
                elif "/chat/completions" in self.path:
                    lines = [f"data: {json.dumps(e)}\n\n" for e in chat_events(body)] + ["data: [DONE]\n\n"]
                    self.send_body("".join(lines).encode(), "text/event-stream")
                elif "/messages/count_tokens" in self.path:
                    self.send_body(b'{"input_tokens": 100}', "application/json")
                elif "/messages" in self.path:
                    lines = [f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in anthropic_events(body)]
                    self.send_body("".join(lines).encode(), "text/event-stream")
                elif "/responses" in self.path and not body.get("stream"):
                    self.send_body(json.dumps(openai_events(body)[-1]["response"]).encode(), "application/json")
                elif "/responses" in self.path:
                    lines = [f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in openai_events(body)]
                    self.send_body("".join(lines).encode(), "text/event-stream")
                elif ":countTokens" in self.path:
                    self.send_body(b'{"totalTokens": 100}', "application/json")
                elif ":streamGenerateContent" in self.path:
                    line = f"data: {json.dumps(gemini_response(body))}\n\n"
                    self.send_body(line.encode(), "text/event-stream")
                elif ":generateContent" in self.path:
                    self.send_body(json.dumps(gemini_response(body)).encode(), "application/json")
                else:
                    self.send_body(b"{}", "application/json")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tools_seen(self) -> set[str]:
        return {name for r in self.requests for name in offered_tools(r["body"])}

    def main_requests(self) -> list[dict]:
        """Requests that carry the user's question, leaving out harness subrequests."""
        return [r for r in self.requests if "vote" in json.dumps(r["body"]) and "alpha/search" not in r["path"]
                and not r["body"].get("plugins")]

    def reasoning_settings(self) -> set[str]:
        """The reasoning settings sent to the model, in each API's own format."""
        settings = set()
        for request in self.main_requests():
            body = request["body"]
            effort = (body.get("output_config") or {}).get("effort")
            effort = effort or (body.get("reasoning") or {}).get("effort") or body.get("reasoning_effort")
            thinking = (body.get("generationConfig") or {}).get("thinkingConfig")
            items = body.get("input") if isinstance(body.get("input"), list) else []
            for item in items:
                if isinstance(item, dict) and item.get("type") == "configuration_update":
                    effort = (item.get("reasoning") or {}).get("effort")
            # On Claude, Pi keeps a fixed top-level effort and sets the real one per message.
            for message in body.get("messages") or []:
                if message.get("role") == "system" and message.get("output_config"):
                    effort = message["output_config"].get("effort")
            settings.add(json.dumps(thinking) if thinking else str(effort))
        return settings

    def stop(self) -> None:
        self.server.shutdown()
