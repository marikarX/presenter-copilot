import { useCallback, useEffect, useState } from "react";
import type { RendererCoreMethod } from "../shared/protocol";

export type PresentationComponent = {
  component_id: string;
  name: string;
  document_id: string;
  revision_id: string;
  slide_id: string;
  object_ids: string[];
  names: string[];
  created_at: string;
};

export type ComponentSelection = {
  document_id: string;
  revision_id: string;
  slide_id: string;
  object_ids: string[];
  names: string[];
};

function isComponent(value: unknown): value is PresentationComponent {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<PresentationComponent>;
  return (
    typeof item.component_id === "string" &&
    typeof item.name === "string" &&
    typeof item.document_id === "string" &&
    typeof item.revision_id === "string" &&
    typeof item.slide_id === "string" &&
    Array.isArray(item.object_ids) &&
    item.object_ids.every((id) => typeof id === "string") &&
    Array.isArray(item.names) &&
    item.names.every((name) => typeof name === "string")
  );
}

/** Named object selections saved once and inserted into any deck of the project. */
export function ComponentLibrary({
  projectId,
  selection,
  sourceNames,
  canInsert,
  disabled,
  request,
  onInsert,
}: {
  projectId: string;
  /** The current selection, or a reason it cannot be saved. */
  selection: ComponentSelection | string;
  sourceNames: Record<string, string>;
  canInsert: boolean;
  disabled: boolean;
  request: <T>(
    method: RendererCoreMethod,
    params: Record<string, unknown>,
  ) => Promise<T>;
  onInsert: (component: PresentationComponent) => void;
}) {
  const [components, setComponents] = useState<PresentationComponent[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const result = await request<{ components: unknown[] }>(
      "presentation.workspace.list_components",
      { project_id: projectId },
    );
    if (
      !Array.isArray(result.components) ||
      !result.components.every(isComponent)
    )
      throw new Error("The component library could not be verified.");
    setComponents(result.components);
  }, [projectId, request]);

  useEffect(() => {
    setComponents([]);
    setStatus(null);
    refresh().catch((caught) =>
      setStatus(
        caught instanceof Error ? caught.message : "Components could not load.",
      ),
    );
  }, [refresh]);

  const run = async (work: () => Promise<string>) => {
    setBusy(true);
    setStatus(null);
    try {
      setStatus(await work());
      await refresh();
    } catch (caught) {
      setStatus(
        caught instanceof Error
          ? caught.message
          : "The component action failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const trimmed = name.trim();
  const saveable = typeof selection !== "string";
  return (
    <fieldset className="pw-component-library">
      <legend>Components</legend>
      <p className="muted">
        Save objects once, then insert them on any slide of any deck in this
        project. Each component keeps the revision it was saved from.
      </p>
      <div className="pw-component-save">
        <input
          type="text"
          aria-label="Component name"
          placeholder="Component name"
          maxLength={120}
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={disabled || busy}
        />
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || busy || !saveable || !trimmed}
          title={typeof selection === "string" ? selection : undefined}
          onClick={() =>
            typeof selection !== "string" &&
            void run(async () => {
              await request("presentation.workspace.save_component", {
                project_id: projectId,
                document_id: selection.document_id,
                revision_id: selection.revision_id,
                slide_id: selection.slide_id,
                object_ids: selection.object_ids,
                name: trimmed,
              });
              setName("");
              return `Saved component “${trimmed}” with ${selection.object_ids.length} object${selection.object_ids.length === 1 ? "" : "s"}.`;
            })
          }
        >
          Save selection as component
        </button>
      </div>
      {typeof selection === "string" ? (
        <p className="muted">{selection}</p>
      ) : null}
      {components.length ? (
        <ul className="pw-component-list" aria-label="Saved components">
          {components.map((component) => (
            <li key={component.component_id}>
              <span>
                <strong>{component.name}</strong>
                <span className="muted">
                  {" "}
                  · {component.names.join(", ")} · from{" "}
                  {sourceNames[component.document_id] ?? "a deck"}
                </span>
              </span>
              <button
                type="button"
                className="secondary-button"
                aria-label={`Insert component ${component.name}`}
                disabled={disabled || busy || !canInsert}
                onClick={() => onInsert(component)}
              >
                Insert
              </button>
              <button
                type="button"
                className="secondary-button"
                aria-label={`Delete component ${component.name}`}
                disabled={disabled || busy}
                onClick={() =>
                  void run(async () => {
                    await request("presentation.workspace.delete_component", {
                      project_id: projectId,
                      component_id: component.component_id,
                    });
                    return `Deleted component “${component.name}”.`;
                  })
                }
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No saved components yet.</p>
      )}
      {status ? (
        <p className="muted" role="status">
          {status}
        </p>
      ) : null}
    </fieldset>
  );
}
