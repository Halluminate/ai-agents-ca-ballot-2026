/**
 * Pins every request to one OpenRouter provider and warns when a run drifts from the
 * design. Pi ignores compat.openRouterRouting on Claude's anthropic-messages path, so the
 * pin is set here for all models. Lines starting with "warning:" reach run.py's report.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Letters and digits only: "Moonshot AI" and "moonshotai", "Z.AI" and "z-ai" name one provider.
const slug = (name: unknown) => String(name).toLowerCase().replace(/[^a-z0-9]/g, "");

export default function (pi: ExtensionAPI) {
  const only = (process.env.OPENROUTER_ONLY ?? "").split(",").filter(Boolean);
  const warned = new Set<string>();
  const warn = (message: string) => {
    if (warned.has(message)) return;
    warned.add(message);
    process.stderr.write(`warning: ${message}\n`);
  };

  pi.on("before_provider_request", (event) => {
    const payload = event.payload as Record<string, any>;
    if (only.length === 0) {
      warn("OPENROUTER_ONLY is not set, so this request is not pinned to a provider");
      return undefined;
    }
    const assistants = (payload.messages ?? []).filter((m: any) => m.role === "assistant");
    const carriesReasoning = (m: any) =>
      Array.isArray(m.reasoning_details) ||
      (Array.isArray(m.content) && m.content.some((b: any) => b.type === "thinking" || b.type === "redacted_thinking"));
    if (assistants.length > 0 && !assistants.every(carriesReasoning)) {
      warn("reasoning was not replayed on an assistant turn");
    }
    return { ...payload, provider: { only, allow_fallbacks: false } };
  });

  pi.on("provider_stream_event", (event) => {
    const data = event.data as Record<string, any>;
    const served = data?.provider ?? data?.message?.provider;
    if (served && only.length > 0 && !only.map(slug).includes(slug(served))) warn(`served by ${served}, not ${only.join(",")}`);
  });
}
