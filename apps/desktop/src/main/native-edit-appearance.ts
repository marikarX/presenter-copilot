import {
  isJsonObject,
  type CoreMethod,
  type JsonObject,
} from "../shared/protocol";
import { copyEditPlanSnapshot, withEditPlanReader } from "./edit-plan-snapshot";
import {
  renderNativeSnapshot,
  validateNativeAppearanceRequest,
  type NativeAppearanceDependencies,
} from "./native-appearance";

export async function renderNativeEditAppearance(
  value: unknown,
  dependencies: Omit<
    NativeAppearanceDependencies,
    "copyRevision" | "validateAfterRender"
  > & {
    request(method: CoreMethod, params: JsonObject): Promise<unknown>;
  },
) {
  if (
    !isJsonObject(value) ||
    typeof value.plan_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value.plan_id,
    )
  )
    throw new Error("The proposed slide target is invalid.");
  const { plan_id: planId, ...savedFields } = value;
  const request = validateNativeAppearanceRequest(savedFields);
  const target = { ...request, planId };
  return renderNativeSnapshot(
    request,
    {
      runtime: dependencies.runtime,
      runWorker: dependencies.runWorker,
      copyRevision: (params) =>
        copyEditPlanSnapshot(
          target,
          params.destination_path as string,
          dependencies.request,
        ),
      validateAfterRender: () =>
        withEditPlanReader(target, dependencies.request, async () => undefined),
    },
    planId,
  );
}
