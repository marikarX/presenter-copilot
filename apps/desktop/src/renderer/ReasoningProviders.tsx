import { useCallback, useEffect, useRef, useState } from "react";
import {
  mergeDecisionSettingsDraft,
  type DecisionSettingsDraft,
} from "./decision-settings-draft";
import {
  type ChatGPTPlanAuthStatus,
  type CodexAuthStatus,
  type DecisionCredentialStatus,
  type ProviderStatus,
  type TypedDecisionProviderId,
  type TypedDecisionModelOption,
  type TypedDecisionProviderStatus,
  unwrapInvokeResult,
} from "../shared/protocol";

export function ReasoningProviders({ disabled }: { disabled: boolean }) {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selection, setSelection] = useState("local_openai");
  const [model, setModel] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:11434/v1");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [auth, setAuth] = useState<CodexAuthStatus["state"]>("signed_out");
  const [decisionStatus, setDecisionStatus] =
    useState<TypedDecisionProviderStatus | null>(null);
  const [decisionSelection, setDecisionSelection] =
    useState<TypedDecisionProviderId>("disabled");
  const [decisionModel, setDecisionModel] = useState("tev1:4b");
  const [decisionCredential, setDecisionCredential] =
    useState<DecisionCredentialStatus | null>(null);
  const [chatgptPlanAuth, setChatgptPlanAuth] =
    useState<ChatGPTPlanAuthStatus | null>(null);
  const [chatgptPlanModels, setChatgptPlanModels] = useState<
    TypedDecisionModelOption[]
  >([]);
  const [chatgptPlanModel, setChatgptPlanModel] = useState("");
  const draftRef = useRef<DecisionSettingsDraft | null>(null);
  const statusOwner = useRef({
    epoch: 0,
    inFlight: null as number | null,
    action: false,
    live: true,
  });
  const showDraft = useCallback((draft: DecisionSettingsDraft) => {
    draftRef.current = draft;
    setDecisionSelection(draft.providerId);
    setDecisionModel(draft.ollamaModelId);
    setChatgptPlanModel(draft.chatgptModelId);
  }, []);
  function editDraft(change: Partial<DecisionSettingsDraft>) {
    if (draftRef.current) showDraft({ ...draftRef.current, ...change });
  }
  function beginDecisionAction() {
    if (statusOwner.current.action) return false;
    statusOwner.current.action = true;
    statusOwner.current.epoch += 1;
    setBusy(true);
    return true;
  }
  function finishDecisionAction() {
    statusOwner.current.action = false;
    setBusy(false);
  }
  useEffect(() => {
    statusOwner.current.live = true;
    return () => {
      statusOwner.current.live = false;
      statusOwner.current.epoch += 1;
    };
  }, []);
  async function codexAuth(action: "sign_in" | "status" | "sign_out") {
    setBusy(true);
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<CodexAuthStatus>(
          `provider.codex.${action}`,
        ),
      );
      setAuth(result.state);
      setNotice(
        result.state === "signing_in"
          ? "Complete ChatGPT sign-in in your browser, then refresh status."
          : "ChatGPT status updated.",
      );
      await load();
    } catch {
      setNotice(
        "Codex authentication is unavailable. Check the supported runtime and try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  const load = useCallback(async () => {
    const result = unwrapInvokeResult(
      await window.presenterCopilot.core.request<{
        providers: ProviderStatus[];
      }>("provider.list"),
    );
    setProviders(result.providers);
    return result.providers;
  }, []);
  const loadDecisionStatus = useCallback(async () => {
    const epoch = ++statusOwner.current.epoch;
    statusOwner.current.inFlight = epoch;
    try {
      const [status, credential, planAuthResult] = await Promise.all([
        window.presenterCopilot.core.request<TypedDecisionProviderStatus>(
          "provider.decision.status",
        ),
        window.presenterCopilot.core.request<DecisionCredentialStatus>(
          "provider.decision.credentials.status",
        ),
        window.presenterCopilot.core.request<ChatGPTPlanAuthStatus>(
          "provider.chatgpt_plan.status",
        ),
      ]);
      const resolvedStatus = unwrapInvokeResult(status);
      const resolvedCredential = unwrapInvokeResult(credential);
      const resolvedPlanAuth = unwrapInvokeResult(planAuthResult);
      if (!statusOwner.current.live || epoch !== statusOwner.current.epoch)
        return null;
      let planModels: TypedDecisionModelOption[] | null = null;
      if (resolvedPlanAuth.state === "signed_in") {
        try {
          const modelsResult = unwrapInvokeResult(
            await window.presenterCopilot.core.request<{
              models: TypedDecisionModelOption[];
            }>("provider.chatgpt_plan.models"),
          );
          planModels = modelsResult.models;
        } catch {
          planModels = null;
        }
      }
      if (!statusOwner.current.live || epoch !== statusOwner.current.epoch)
        return null;
      const draft = mergeDecisionSettingsDraft(
        draftRef.current,
        resolvedStatus,
        resolvedPlanAuth.active_account_id,
        planModels,
      );
      setDecisionStatus(resolvedStatus);
      setDecisionCredential(resolvedCredential);
      setChatgptPlanAuth(resolvedPlanAuth);
      setChatgptPlanModels(planModels ?? []);
      showDraft(draft);
      return resolvedStatus;
    } catch (error) {
      if (!statusOwner.current.live || epoch !== statusOwner.current.epoch)
        return null;
      throw error;
    } finally {
      if (statusOwner.current.inFlight === epoch)
        statusOwner.current.inFlight = null;
    }
  }, [showDraft]);
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
  useEffect(() => {
    void loadDecisionStatus().catch(() =>
      setNotice("Fast decision provider status unavailable."),
    );
  }, [loadDecisionStatus]);
  useEffect(() => {
    if (chatgptPlanAuth?.state !== "signing_in") return;
    const timer = window.setInterval(() => {
      if (statusOwner.current.action || statusOwner.current.inFlight !== null)
        return;
      void loadDecisionStatus().catch(() =>
        setNotice("ChatGPT plan sign-in status could not be refreshed."),
      );
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [chatgptPlanAuth?.state, loadDecisionStatus]);
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
  async function configureDecisionProvider() {
    if (!beginDecisionAction()) return;
    setNotice("");
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "provider.decision.configure",
          {
            provider_id: decisionSelection,
            ...(decisionSelection === "ollama_systemone"
              ? { model_id: decisionModel }
              : decisionSelection === "openai_chatgpt_plan"
                ? { model_id: chatgptPlanModel }
                : {}),
          },
        ),
      );
      setNotice("Fast decision provider selection saved.");
      await loadDecisionStatus();
    } catch (error) {
      const safe = error as { message?: string };
      setNotice(safe.message ?? "Fast decision provider could not be saved.");
    } finally {
      finishDecisionAction();
    }
  }
  async function saveOpenRouterCredential() {
    if (!beginDecisionAction()) return;
    setNotice("");
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<{
          saved: boolean;
          detected: boolean;
          secure_store_available?: boolean;
        }>("provider.decision.credentials.save_detected"),
      );
      setNotice(
        result.saved
          ? "OpenRouter key stored in Windows Credential Manager."
          : result.detected
            ? "A secure credential store is unavailable; the key was not stored."
            : "No OPENROUTER_API_KEY was detected in the Core environment.",
      );
      await loadDecisionStatus();
    } catch (error) {
      const safe = error as { message?: string };
      setNotice(safe.message ?? "The OpenRouter key could not be stored.");
    } finally {
      finishDecisionAction();
    }
  }
  async function removeOpenRouterCredential() {
    if (!beginDecisionAction()) return;
    setNotice("");
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "provider.decision.credentials.remove",
        ),
      );
      setNotice(
        "Stored OpenRouter key removed. Environment keys remain external.",
      );
      await loadDecisionStatus();
    } catch (error) {
      const safe = error as { message?: string };
      setNotice(safe.message ?? "The OpenRouter key could not be removed.");
    } finally {
      finishDecisionAction();
    }
  }
  async function chatgptPlanAuthAction(
    action: "sign_in" | "status" | "select" | "cancel" | "sign_out",
    params: Record<string, unknown> = {},
  ) {
    if (!beginDecisionAction()) return;
    setNotice("");
    try {
      const result = unwrapInvokeResult(
        await window.presenterCopilot.core.request<
          ChatGPTPlanAuthStatus & { remote_revocation_confirmed?: boolean }
        >(`provider.chatgpt_plan.${action}`, params),
      );
      setChatgptPlanAuth(result);
      if (
        action === "sign_out" &&
        result.remote_revocation_confirmed === false
      ) {
        setNotice(
          "Signed out locally. OpenAI could not confirm remote token revocation; you can disconnect Presenter Copilot in ChatGPT settings.",
        );
      } else if (action === "sign_in") {
        setNotice(
          "Continue sign-in in your browser. Presenter Copilot will refresh this status when it returns.",
        );
      } else if (action === "cancel") {
        setNotice("ChatGPT sign-in cancellation requested.");
      } else if (action === "select") {
        setNotice("The active ChatGPT account changed.");
      } else {
        setNotice("ChatGPT plan account status updated.");
      }
      await loadDecisionStatus();
    } catch (error) {
      const safe = error as { message?: string };
      setNotice(safe.message ?? "ChatGPT plan account action failed.");
    } finally {
      finishDecisionAction();
    }
  }
  async function openChatGPTUsageSettings() {
    try {
      const result =
        await window.presenterCopilot.chatgptPlan.openUsageSettings();
      setNotice(
        result.ok ? "Opened ChatGPT usage settings." : result.error.message,
      );
    } catch {
      setNotice("Could not open ChatGPT usage settings.");
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
              : provider.provider_id === "codex_chatgpt"
                ? "Codex — ChatGPT"
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
          <option value="codex_chatgpt">Codex — ChatGPT sign-in</option>
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
      {selection === "codex_chatgpt" ? (
        <div>
          <p>
            ChatGPT: {auth.replaceAll("_", " ")}. Sign-in lasts for this app
            session. Codex uses an isolated runtime and approved Selected
            Context only.
          </p>
          <button
            disabled={disabled || busy}
            onClick={() => void codexAuth("sign_in")}
          >
            Sign in with ChatGPT
          </button>
          <button
            disabled={disabled || busy}
            onClick={() => void codexAuth("status")}
          >
            Refresh ChatGPT status
          </button>
          <button
            disabled={disabled || busy}
            onClick={() => void codexAuth("sign_out")}
          >
            Sign out of ChatGPT
          </button>
        </div>
      ) : null}
      <label>
        Model
        <input
          value={model}
          maxLength={120}
          onChange={(event) => setModel(event.target.value)}
          disabled={disabled || busy || selection === "codex_chatgpt"}
        />
      </label>
      <p>
        {selection === "local_openai"
          ? "Optional credential: PRESENTER_LOCAL_API_KEY in the Core environment. Start your model server separately; this app does not download or launch it."
          : selection === "codex_chatgpt"
            ? "Requires official Codex 0.153.1 or 0.153.4. Uses ChatGPT-managed authentication; independent of API-key billing."
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
      <section className="decision-provider-panel" aria-label="Fast Decisions">
        <h3>Fast Decisions</h3>
        <p>
          Typed decisions return a bounded suggestion and never replace a
          reasoning provider. Remote choices send selected slide text off this
          machine only when project privacy allows it.
        </p>
        <label htmlFor="decision-provider-select">
          Decision provider
          <select
            id="decision-provider-select"
            value={decisionSelection}
            onChange={(event) =>
              editDraft({
                providerId: event.target.value as TypedDecisionProviderId,
              })
            }
            disabled={disabled || busy || !decisionStatus}
          >
            <option value="disabled">Disabled</option>
            <option value="local_choice">
              Local model · strict JSON Schema
            </option>
            <option value="openai_fast">OpenAI Responses · Fast mode</option>
            <option value="openai_ultrafast">
              OpenAI Responses · Ultrafast (GPT-6 Astra)
            </option>
            <option value="openai_decisions">
              OpenAI Decisions · Beta (GPT-6 Luna)
            </option>
            <option value="openrouter_jev">Jev · OpenRouter System One</option>
            <option value="ollama_systemone">
              Ollama · Jev-compatible System One
            </option>
            <option value="openai_chatgpt_plan">
              ChatGPT plan usage · Preview
            </option>
          </select>
        </label>
        {decisionStatus?.providers.map((item) => (
          <p key={item.provider_id}>
            <strong>{item.label}</strong>
            {": "}
            {item.configured ? item.model_id || "configured" : "not configured"}
            {item.leaves_machine
              ? " · sends content off this machine"
              : " · loopback"}
            {decisionStatus.selected_provider_id === item.provider_id
              ? " · selected"
              : ""}
          </p>
        ))}
        {decisionSelection === "local_choice" ? (
          <p>
            Uses the local endpoint and model configured above. Loopback stays
            local; private LAN requires project cloud permission.
          </p>
        ) : null}
        {decisionSelection === "openai_fast" ? (
          <p>
            Uses the existing OpenAI API credential and model. Fast mode may
            cost more per token. This uses Responses Structured Outputs.
          </p>
        ) : null}
        {decisionSelection === "openai_ultrafast" ? (
          <p>
            Uses GPT-6 Astra with OpenAI Responses Ultrafast. Availability is
            subject to account rate limits and higher service-tier cost. This is
            not the separately announced Decisions API.
          </p>
        ) : null}
        {decisionSelection === "openai_decisions" ? (
          <p>
            Uses GPT-6 Luna through the native OpenAI Decisions beta endpoint
            with your existing OpenAI API credential. Project cloud permission
            is required. Confidence is uncalibrated; review recommendations.
            ChatGPT sign-in does not configure this API credential.
          </p>
        ) : null}
        {decisionSelection === "openrouter_jev" ? (
          <div>
            <p>
              Uses the pinned Jev model through OpenRouter's documented System
              One API. Key status:{" "}
              {decisionCredential?.credential_source ?? "unknown"}. The key is
              never sent to the renderer.
            </p>
            <button
              className="secondary-button"
              disabled={
                disabled || busy || !decisionCredential?.environment_detected
              }
              onClick={() => void saveOpenRouterCredential()}
            >
              Save detected key to Windows Credential Manager
            </button>
            <button
              className="secondary-button"
              disabled={
                disabled ||
                busy ||
                decisionCredential?.credential_source !==
                  "windows_credential_manager"
              }
              onClick={() => void removeOpenRouterCredential()}
            >
              Remove stored OpenRouter key
            </button>
          </div>
        ) : null}
        {decisionSelection === "ollama_systemone" ? (
          <div>
            <label htmlFor="ollama-decision-model-select">
              Ollama decision model
              <select
                id="ollama-decision-model-select"
                value={decisionModel}
                onChange={(event) =>
                  editDraft({ ollamaModelId: event.target.value })
                }
                disabled={disabled || busy}
              >
                {(
                  decisionStatus?.providers.find(
                    (item) => item.provider_id === "ollama_systemone",
                  )?.model_options ?? []
                ).map((option) => (
                  <option key={option.model_id} value={option.model_id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <p>
              Requires Ollama 0.35 or later at localhost. Install the selected
              model first with <code>ollama pull {decisionModel}</code>. This
              app does not launch Ollama or download models. Tev1 is
              experimental; longer slide text may not fit its smaller context.
              Suggestions remain review-only.
            </p>
          </div>
        ) : null}
        {decisionSelection === "openai_chatgpt_plan" ? (
          <div>
            <p>
              ChatGPT plan account:{" "}
              {chatgptPlanAuth?.state.replaceAll("_", " ") ?? "loading"}. This
              is separate from Codex — ChatGPT sign-in and OpenAI API-key
              billing. Preview access and usage limits depend on your account.
            </p>
            {chatgptPlanAuth?.accounts.map((account) => (
              <p key={account.account_id}>
                <button
                  className="secondary-button"
                  disabled={disabled || busy || account.active}
                  onClick={() =>
                    void chatgptPlanAuthAction("select", {
                      account_id: account.account_id,
                    })
                  }
                >
                  {account.email ?? "ChatGPT account"}
                  {account.active ? " · selected" : " · select"}
                  {account.connected ? " · connected" : " · sign-in needed"}
                </button>
                {account.active && account.connected ? (
                  <button
                    className="secondary-button"
                    disabled={disabled || busy}
                    onClick={() => void chatgptPlanAuthAction("sign_out")}
                  >
                    Sign out of this account
                  </button>
                ) : null}
              </p>
            ))}
            {chatgptPlanAuth?.state === "signing_in" ? (
              <button
                className="secondary-button"
                disabled={disabled || busy}
                onClick={() => void chatgptPlanAuthAction("cancel")}
              >
                Cancel sign-in
              </button>
            ) : (
              <>
                <button
                  className="secondary-button"
                  disabled={
                    disabled ||
                    busy ||
                    !chatgptPlanAuth?.credential_store_available
                  }
                  onClick={() =>
                    void chatgptPlanAuthAction("sign_in", {
                      ...(chatgptPlanAuth?.active_account_id
                        ? { account_id: chatgptPlanAuth.active_account_id }
                        : {}),
                    })
                  }
                >
                  {chatgptPlanAuth?.accounts.length
                    ? "Continue with selected account"
                    : "Continue with ChatGPT"}
                </button>
                <button
                  className="secondary-button"
                  disabled={
                    disabled ||
                    busy ||
                    !chatgptPlanAuth?.credential_store_available
                  }
                  onClick={() => void chatgptPlanAuthAction("sign_in")}
                >
                  Add another ChatGPT account
                </button>
              </>
            )}
            <button
              className="secondary-button"
              disabled={disabled || busy}
              onClick={() => void chatgptPlanAuthAction("status")}
            >
              Refresh ChatGPT plan status
            </button>
            {chatgptPlanAuth?.state === "signed_in" &&
            chatgptPlanModels.length === 0 ? (
              <p role="status">
                The model catalog could not be loaded. Check the connection and
                retry the status refresh.
              </p>
            ) : null}
            <label htmlFor="chatgpt-plan-model-select">
              ChatGPT model
              <select
                id="chatgpt-plan-model-select"
                value={chatgptPlanModel}
                onChange={(event) =>
                  editDraft({ chatgptModelId: event.target.value })
                }
                disabled={disabled || busy || chatgptPlanModels.length === 0}
              >
                {chatgptPlanModels.map((option) => (
                  <option key={option.model_id} value={option.model_id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <p>
              Only the selected slide text is sent for a reviewed decision. Plan
              usage may share limits with other ChatGPT apps. Responses stream
              with storage disabled; this preview uses text choices only.
            </p>
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => void openChatGPTUsageSettings()}
            >
              Manage ChatGPT usage
            </button>
          </div>
        ) : null}
        <button
          className="secondary-button"
          disabled={
            disabled ||
            busy ||
            (decisionSelection !== "disabled" &&
              !decisionStatus?.providers.some(
                (item) =>
                  item.provider_id === decisionSelection && item.configured,
              )) ||
            (decisionSelection === "openai_chatgpt_plan" &&
              (!chatgptPlanModel ||
                !chatgptPlanModels.some(
                  (item) => item.model_id === chatgptPlanModel,
                )))
          }
          onClick={() => void configureDecisionProvider()}
        >
          Save decision provider
        </button>
      </section>
    </section>
  );
}
