import {
  isActiveTypedDecisionProviderId,
  type TypedDecisionProviderId,
  type TypedDecisionProviderStatus,
  type TypedDecisionModelOption,
} from "../shared/protocol";

export interface DecisionSettingsDraft {
  providerId: TypedDecisionProviderId;
  ollamaModelId: string;
  chatgptModelId: string;
  accountId: string | null;
}

/** Hydrate once; refresh availability without overwriting the user's edits. */
export function mergeDecisionSettingsDraft(
  current: DecisionSettingsDraft | null,
  status: TypedDecisionProviderStatus,
  accountId: string | null,
  models: TypedDecisionModelOption[] | null,
): DecisionSettingsDraft {
  const savedProvider = isActiveTypedDecisionProviderId(
    status.selected_provider_id,
  )
    ? status.selected_provider_id
    : "disabled";
  const hasModel = (id: string | undefined) =>
    !!id && !!models?.some((model) => model.model_id === id);
  const sameAccount = current !== null && current.accountId === accountId;
  const savedModel = hasModel(status.chatgpt_plan_model_id)
    ? status.chatgpt_plan_model_id!
    : (models?.[0]?.model_id ?? "");
  return {
    providerId: current?.providerId ?? savedProvider,
    ollamaModelId:
      current?.ollamaModelId ?? status.ollama_model_id ?? "tev1:4b",
    chatgptModelId:
      sameAccount && (models === null || hasModel(current.chatgptModelId))
        ? current.chatgptModelId
        : savedModel,
    accountId,
  };
}
