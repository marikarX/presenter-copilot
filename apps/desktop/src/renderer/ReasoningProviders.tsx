import { useCallback, useEffect, useState } from "react";
import { type ProviderStatus, unwrapInvokeResult } from "../shared/protocol";

export function ReasoningProviders({ disabled }: { disabled: boolean }) {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selection, setSelection] = useState("local_openai");
  const [model, setModel] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:11434/v1");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    const result = unwrapInvokeResult(
      await window.presenterCopilot.core.request<{
        providers: ProviderStatus[];
      }>("provider.list"),
    );
    setProviders(result.providers);
    return result.providers;
  }, []);
  useEffect(() => {
    void load()
      .then((items) => {
        const active =
          items.find((item) => item.enabled) ??
          items.find((item) => item.provider_id === "local_openai");
        if (!active) return;
        setSelection(active.provider_id);
        setModel(active.model_id);
        if (
          typeof active.safe_config.endpoint === "string" &&
          active.safe_config.endpoint
        ) {
          setEndpoint(active.safe_config.endpoint);
        }
      })
      .catch(() => setNotice("Provider status unavailable."));
  }, [load]);
  function choose(id: string) {
    setSelection(id);
    const provider = providers.find((item) => item.provider_id === id);
    setModel(provider?.model_id ?? "");
    const configured = provider?.safe_config.endpoint;
    if (typeof configured === "string" && configured) setEndpoint(configured);
  }
  async function act(test: boolean) {
    setBusy(true);
    setNotice("");
    try {
      if (test) {
        unwrapInvokeResult(
          await window.presenterCopilot.core.request("provider.test", {
            provider_id: selection,
          }),
        );
        setNotice(
          "Reachable: synthetic structured response validated. No project content was sent.",
        );
      } else {
        unwrapInvokeResult(
          await window.presenterCopilot.core.request("provider.configure", {
            provider_id: selection,
            model_id: model,
            enabled: true,
            ...(selection === "local_openai" ? { endpoint } : {}),
          }),
        );
        setNotice(
          "Provider selected. Project privacy still controls every content request.",
        );
      }
    } catch (error) {
      const safe = error as { message?: string };
      setNotice(safe.message ?? "Provider request failed.");
    } finally {
      await load().catch(() => undefined);
      setBusy(false);
    }
  }
  return (
    <section className="provider-panel" aria-label="Reasoning Providers">
      <h3>Reasoning Providers</h3>
      {providers.map((provider) => (
        <p key={provider.provider_id}>
          <strong>
            {provider.provider_id === "local_openai"
              ? "Local model"
              : "OpenAI API"}
          </strong>
          {": "}
          {provider.health.status === "ready"
            ? provider.provider_id === "local_openai"
              ? "reachable (last request)"
              : "ready"
            : provider.health.configured
              ? `configured / ${provider.health.status}`
              : "not configured"}
          {provider.enabled ? " · selected" : ""}
        </p>
      ))}
      <p>
        Local Only permits loopback inference. Private LAN endpoints send
        content off this machine and require project cloud permission. Failure
        keeps retrieval-only fallback.
      </p>
      <label>
        Provider
        <select
          value={selection}
          onChange={(event) => choose(event.target.value)}
          disabled={disabled || busy}
        >
          <option value="local_openai">Local model — OpenAI-compatible</option>
          <option value="openai">OpenAI API — API-key billing</option>
        </select>
      </label>
      {selection === "local_openai" ? (
        <label>
          Base URL
          <input
            value={endpoint}
            maxLength={512}
            onChange={(event) => setEndpoint(event.target.value)}
            disabled={disabled || busy}
          />
        </label>
      ) : null}
      <label>
        Model
        <input
          value={model}
          maxLength={120}
          onChange={(event) => setModel(event.target.value)}
          disabled={disabled || busy}
        />
      </label>
      <p>
        {selection === "local_openai"
          ? "Optional credential: PRESENTER_LOCAL_API_KEY in the Core environment. Start your model server separately; this app does not download or launch it."
          : "Uses the existing OS-stored OpenAI API credential or OPENAI_API_KEY."}
      </p>
      <div className="retrieval-actions">
        <button
          className="primary-button"
          disabled={disabled || busy || !model.trim()}
          onClick={() => void act(false)}
        >
          Save and select
        </button>
        <button
          className="secondary-button"
          disabled={
            disabled ||
            busy ||
            !providers.some((p) => p.provider_id === selection && p.enabled)
          }
          onClick={() => void act(true)}
        >
          Test selected provider (synthetic)
        </button>
        <button
          className="secondary-button"
          disabled={disabled || busy}
          onClick={() =>
            void load().catch(() => setNotice("Provider status unavailable."))
          }
        >
          Refresh status
        </button>
      </div>
      {notice ? <p role="status">{notice}</p> : null}
    </section>
  );
}
