/**
 * The web tools every model gets in the shared harness: same search backend, same
 * page reader, same output format, whichever model is calling. Results are cached on
 * disk for the whole experiment, so two models that run the same search or open the
 * same page read the same text.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { extractText, getDocumentProxy } from "unpdf";

const PAGE_CHARS = 20_000;
const MAX_RESULTS = 10;
const TIMEOUT_MS = 30_000;
const USER_AGENT = "ca-ballot-experiment/1.0";

type SearchResult = { title: string; url: string; snippet: string };

function withTimeout(signal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

async function cached<T>(kind: string, key: string, load: () => Promise<T>): Promise<T> {
  const dir = process.env.WEB_CACHE_DIR;
  if (!dir) return load();
  const hash = createHash("sha256").update(key).digest("hex");
  const file = join(dir, `${kind}-${hash}.json`);
  try {
    return JSON.parse(readFileSync(file, "utf8")) as T;
  } catch {
    // Not cached yet. Failures are never cached, so a later run can try again.
  }
  const value = await load();
  mkdirSync(dir, { recursive: true });
  const partial = `${file}.${process.pid}`;
  writeFileSync(partial, JSON.stringify(value));
  renameSync(partial, file);
  return value;
}

async function tavily(query: string, key: string, signal: AbortSignal): Promise<SearchResult[]> {
  const res = await fetch("https://api.tavily.com/search", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
    body: JSON.stringify({
      query,
      max_results: MAX_RESULTS,
      search_depth: "basic",
      include_answer: false,
      include_raw_content: false,
    }),
    signal,
  });
  if (!res.ok) throw new Error(`Search failed with HTTP ${res.status}.`);
  const data = (await res.json()) as { results?: { title: string; url: string; content: string }[] };
  return (data.results ?? []).map((r) => ({ title: r.title, url: r.url, snippet: r.content }));
}

async function brave(query: string, key: string, signal: AbortSignal): Promise<SearchResult[]> {
  const url = new URL("https://api.search.brave.com/res/v1/web/search");
  url.searchParams.set("q", query);
  url.searchParams.set("count", String(MAX_RESULTS));
  const res = await fetch(url, {
    headers: { accept: "application/json", "x-subscription-token": key },
    signal,
  });
  if (!res.ok) throw new Error(`Search failed with HTTP ${res.status}.`);
  const data = (await res.json()) as { web?: { results?: { title: string; url: string; description: string }[] } };
  return (data.web?.results ?? []).map((r) => ({ title: r.title, url: r.url, snippet: r.description }));
}


/**
 * One OpenRouter key, no model in the result path. The web plugin runs one search with a pinned
 * engine before the helper model answers, and every result comes back as a url_citation annotation.
 * The helper's text is thrown away. An empty list is a failure, so it is never cached as "No results."
 */
const OR_CHAT_URL = process.env.OPENROUTER_CHAT_URL ?? "https://openrouter.ai/api/v1/chat/completions";
const OR_ENGINE = process.env.SEARCH_ENGINE ?? "perplexity";
const OR_HELPER = process.env.SEARCH_HELPER_MODEL ?? "mistralai/mistral-nemo"; // not a vendor under test; its text is discarded
const SNIPPET_CHARS = 1_500;

async function openrouter(query: string, key: string, signal: AbortSignal, noteCost: (usd: number) => void): Promise<SearchResult[]> {
  const res = await fetch(OR_CHAT_URL, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model: OR_HELPER,
      messages: [{ role: "user", content: query }],
      plugins: [{ id: "web", engine: OR_ENGINE, max_results: MAX_RESULTS }],
      max_tokens: 16,
      stream: false,
    }),
    signal,
  });
  if (!res.ok) throw new Error(`Search failed with HTTP ${res.status}.`);
  const data = (await res.json()) as {
    usage?: { cost?: number };
    choices?: { message?: { annotations?: { type: string; url_citation?: { url: string; title?: string; content?: string } }[] } }[];
  };
  noteCost(data.usage?.cost ?? 0);
  const citations = (data.choices?.[0]?.message?.annotations ?? []).filter((a) => a.type === "url_citation" && a.url_citation);
  if (!citations.length) throw new Error("OpenRouter returned no search results.");
  return citations.map(({ url_citation: c }) => ({ title: c!.title ?? c!.url, url: c!.url, snippet: (c!.content ?? "").slice(0, SNIPPET_CHARS) }));
}

/** Fixed results for tests that run without a search key. run.py refuses this outside a smoke test. */
function stubResults(): SearchResult[] {
  return [
    {
      title: "Qualified Statewide Ballot Measures | California Secretary of State",
      url: "https://www.sos.ca.gov/elections/ballot-measures/qualified-ballot-measures",
      snippet: "Official list of measures on the California ballot.",
    },
    {
      title: "Ballot Analyses | Legislative Analyst's Office",
      url: "https://lao.ca.gov/BallotAnalysis/Propositions",
      snippet: "Nonpartisan analysis of California ballot propositions.",
    },
  ];
}

async function search(query: string, signal: AbortSignal, noteCost: (usd: number) => void): Promise<SearchResult[]> {
  const provider = process.env.SEARCH_PROVIDER ?? "";
  const key = process.env.SEARCH_API_KEY ?? "";
  if (provider === "stub") return stubResults();
  if (provider === "tavily") return tavily(query, key, signal);
  if (provider === "brave") return brave(query, key, signal);
  if (provider === "openrouter") return openrouter(query, key, signal, noteCost);
  throw new Error("No search backend is configured.");
}

function publicUrl(raw: string): URL {
  const url = new URL(raw);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Only http and https pages can be read.");
  }
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  const isPrivate =
    host === "localhost" ||
    host === "::1" ||
    host.endsWith(".localhost") ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    /^(0|10|127)\./.test(host) ||
    /^169\.254\./.test(host) ||
    /^192\.168\./.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    /^f[cd][0-9a-f]{2}:/.test(host) ||
    /^fe80:/.test(host);
  if (isPrivate) throw new Error("Private network addresses can't be read.");
  return url;
}

const ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  ndash: "-",
  mdash: "-",
  rsquo: "'",
  lsquo: "'",
  rdquo: '"',
  ldquo: '"',
};

function decodeEntities(text: string): string {
  return text.replace(/&(#\d+|#x[0-9a-f]+|[a-z]+);/gi, (match, code: string) => {
    if (code[0] !== "#") return ENTITIES[code.toLowerCase()] ?? match;
    const hex = code[1].toLowerCase() === "x";
    const value = Number.parseInt(code.slice(hex ? 2 : 1), hex ? 16 : 10);
    return value > 0 && value <= 0x10ffff ? String.fromCodePoint(value) : match;
  });
}

function htmlToText(html: string, baseUrl: string): string {
  const clean = html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style|noscript|svg|template)\b[\s\S]*?<\/\1>/gi, " ");
  const body = /<body\b[^>]*>([\s\S]*)<\/body>/i.exec(clean)?.[1] ?? clean;
  // Keep link targets, because following links is how research moves between sources.
  const withLinks = body.replace(
    /<a\b[^>]*href=["']([^"'#][^"']*)["'][^>]*>([\s\S]*?)<\/a>/gi,
    (_match, href: string, label: string) => {
      const text = label.replace(/<[^>]+>/g, " ").trim();
      if (!text) return " ";
      try {
        return `${text} (${new URL(href, baseUrl).href})`;
      } catch {
        return text;
      }
    },
  );
  const blocks = withLinks
    .replace(/<(br|hr)\b[^>]*>/gi, "\n")
    .replace(/<\/(p|div|section|article|li|tr|table|ul|ol|h[1-6]|header|footer|nav|main|aside|blockquote|pre)>/gi, "\n")
    .replace(/<[^>]+>/g, " ");
  return decodeEntities(blocks)
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
}

async function readPage(raw: string, signal: AbortSignal): Promise<string> {
  const url = publicUrl(raw);
  const res = await fetch(url, {
    headers: { "user-agent": USER_AGENT, accept: "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5" },
    redirect: "follow",
    signal,
  });
  if (!res.ok) throw new Error(`The page returned HTTP ${res.status}.`);
  const type = res.headers.get("content-type") ?? "";
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (type.includes("pdf") || url.pathname.toLowerCase().endsWith(".pdf")) {
    const { text } = await extractText(await getDocumentProxy(bytes), { mergePages: true });
    return text;
  }
  const body = new TextDecoder().decode(bytes);
  // A bot-protection page is reported as a failure, and the model has to use another source.
  if (body.length < 5_000 && /_Incapsula_Resource|cf-chl|Just a moment|captcha/i.test(body)) {
    throw new Error("The site blocked automated access to this page. Try a different source.");
  }
  return type.includes("html") ? htmlToText(body, res.url) : body;
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "web_search",
    label: "Web search",
    description: "Search the web. Returns titles, URLs and short snippets.",
    parameters: Type.Object({
      query: Type.String({ description: "The search query" }),
    }),
    async execute(_toolCallId, params, signal) {
      const query = params.query.trim();
      let searchCostUsd = 0;
      const results = await cached("search", query.toLowerCase(), () => search(query, withTimeout(signal), (usd) => (searchCostUsd = usd)));
      const text = results.length
        ? results.map((r, i) => `${i + 1}. ${r.title}\n${r.url}\n${r.snippet}`).join("\n\n")
        : "No results.";
      return { content: [{ type: "text", text }], details: { searchCostUsd } };
    },
  });

  pi.registerTool({
    name: "web_fetch",
    label: "Web fetch",
    description: `Read a web page or PDF as plain text. Returns up to ${PAGE_CHARS} characters at a time, so use offset to read further into long documents.`,
    parameters: Type.Object({
      url: Type.String({ description: "The page URL" }),
      offset: Type.Optional(Type.Number({ description: "Character position to start from. Default 0." })),
    }),
    async execute(_toolCallId, params, signal) {
      const offset = Math.max(0, Math.floor(params.offset ?? 0));
      const text = await cached("page", params.url, () => readPage(params.url, withTimeout(signal)));
      const page = text.slice(offset, offset + PAGE_CHARS);
      const end = offset + page.length;
      const more =
        end < text.length
          ? `\n\n[Showing characters ${offset} to ${end} of ${text.length}. Call web_fetch with offset ${end} to keep reading.]`
          : "";
      return { content: [{ type: "text", text: `${page}${more}` }], details: {} };
    },
  });
}
