import { describe, expect, it } from "vitest";
import type { TypedDecisionProviderStatus } from "../shared/protocol";
import {
  mergeDecisionSettingsDraft,
  type DecisionSettingsDraft,
} from "./decision-settings-draft";

const status: TypedDecisionProviderStatus = {
  selected_provider_id: "disabled",
  ollama_model_id: "tev1:4b",
  chatgpt_plan_model_id: "model-a",
  providers: [],
};
const models = [
  { model_id: "model-a", label: "A" },
  { model_id: "model-b", label: "B" },
];
const draft: DecisionSettingsDraft = {
  providerId: "openai_chatgpt_plan",
  ollamaModelId: "nimble:latest",
  chatgptModelId: "model-b",
  accountId: "account-a",
};

describe("decision settings refresh ownership", () => {
  it("hydrates saved settings including native Decisions once", () => {
    expect(
      mergeDecisionSettingsDraft(
        null,
        { ...status, selected_provider_id: "openai_decisions" },
        "account-a",
        models,
      ),
    ).toEqual({
      providerId: "openai_decisions",
      ollamaModelId: "tev1:4b",
      chatgptModelId: "model-a",
      accountId: "account-a",
    });
  });
  it("does not replace unsaved provider or either model on account status polling", () => {
    expect(
      mergeDecisionSettingsDraft(draft, status, "account-a", models),
    ).toEqual(draft);
  });
  it("preserves a model through catalog failure and resumes it when available", () => {
    const retained = mergeDecisionSettingsDraft(
      draft,
      status,
      "account-a",
      null,
    );
    expect(retained).toEqual(draft);
    expect(
      mergeDecisionSettingsDraft(retained, status, "account-a", models),
    ).toEqual(draft);
  });
  it("revalidates a removed model against a successful fresh catalog", () => {
    expect(
      mergeDecisionSettingsDraft(draft, status, "account-a", models.slice(0, 1))
        .chatgptModelId,
    ).toBe("model-a");
    expect(
      mergeDecisionSettingsDraft(draft, status, "account-a", []).chatgptModelId,
    ).toBe("");
  });
  it("does not carry the previous account's draft model to a different account", () => {
    const switched = mergeDecisionSettingsDraft(
      draft,
      status,
      "account-b",
      models,
    );
    expect(switched.chatgptModelId).toBe("model-a");
    expect(switched.providerId).toBe("openai_chatgpt_plan");
    expect(switched.accountId).toBe("account-b");
    expect(
      mergeDecisionSettingsDraft(draft, status, "account-b", null)
        .chatgptModelId,
    ).toBe("");
  });
  it("rejects an unknown persisted provider and unavailable saved model", () => {
    const hydrated = mergeDecisionSettingsDraft(
      null,
      {
        ...status,
        selected_provider_id: "unknown",
        chatgpt_plan_model_id: "missing",
      },
      null,
      models,
    );
    expect(hydrated.providerId).toBe("disabled");
    expect(hydrated.chatgptModelId).toBe("model-a");
  });
});
