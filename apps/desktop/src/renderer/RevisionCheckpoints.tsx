import { useEffect, useRef, useState } from "react";
import { isCoreError, unwrapInvokeResult } from "../shared/protocol";

type Checkpoint = {
  revision_id: string;
  revision_number: number;
  record_token: string;
  name: string;
  note: string;
  sha256: string;
};
type Catalog = {
  current_revision_id: string;
  current_record_token: string | null;
  items: Checkpoint[];
};
export function RevisionCheckpoints({
  projectId,
  documentId,
  revisionId,
  disabled,
  onRestore,
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  disabled: boolean;
  onRestore: (id: string) => Promise<void>;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const owner = useRef({ live: true, generation: 0 });
  const scope = { project_id: projectId, document_id: documentId };
  const locked = busy || disabled;
  function failed(e: unknown) {
    setError(
      isCoreError(e)
        ? e.message
        : e instanceof Error
          ? e.message
          : "Checkpoints are unavailable.",
    );
  }
  async function reload(prefill = false) {
    const generation = ++owner.current.generation;
    setBusy(true);
    setError("");
    try {
      const value = unwrapInvokeResult<Catalog>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.list_checkpoints",
          scope,
        ),
      );
      if (!owner.current.live || owner.current.generation !== generation)
        return;
      if (
        value.current_revision_id !== revisionId ||
        !Array.isArray(value.items)
      )
        throw new Error(
          "The presentation changed. Reload the presentation before editing checkpoints.",
        );
      setCatalog(value);
      if (prefill) {
        const current = value.items.find(
          (item) => item.revision_id === revisionId,
        );
        setName(current?.name ?? "");
        setNote(current?.note ?? "");
      }
    } catch (e) {
      if (owner.current.live && owner.current.generation === generation)
        failed(e);
    } finally {
      if (owner.current.live && owner.current.generation === generation)
        setBusy(false);
    }
  }
  useEffect(() => {
    const current = owner.current;
    current.live = true;
    void reload(true);
    return () => {
      current.live = false;
      current.generation++;
    };
  }, [projectId, documentId, revisionId]);
  async function save() {
    if (locked || !catalog || !name.trim()) return;
    const generation = ++owner.current.generation;
    setBusy(true);
    setError("");
    try {
      const value = unwrapInvokeResult<Catalog>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.save_checkpoint",
          {
            ...scope,
            expected_revision_id: revisionId,
            expected_token: catalog.current_record_token,
            name,
            note,
          },
        ),
      );
      if (!owner.current.live || owner.current.generation !== generation)
        return;
      if (value.current_revision_id !== revisionId)
        throw new Error("The presentation changed. Reload the presentation.");
      setCatalog(value);
    } catch (e) {
      if (owner.current.live && owner.current.generation === generation)
        failed(e);
    } finally {
      if (owner.current.live && owner.current.generation === generation)
        setBusy(false);
    }
  }
  async function remove(item: Checkpoint) {
    if (locked) return;
    const generation = ++owner.current.generation;
    setBusy(true);
    setError("");
    try {
      const value = unwrapInvokeResult<Catalog>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.clear_checkpoint",
          {
            ...scope,
            revision_id: item.revision_id,
            expected_token: item.record_token,
          },
        ),
      );
      if (!owner.current.live || owner.current.generation !== generation)
        return;
      if (value.current_revision_id !== revisionId)
        throw new Error("The presentation changed. Reload the presentation.");
      setCatalog(value);
    } catch (e) {
      if (owner.current.live && owner.current.generation === generation)
        failed(e);
    } finally {
      if (owner.current.live && owner.current.generation === generation)
        setBusy(false);
    }
  }
  return (
    <section
      className="pw-revision-checkpoints"
      aria-label="Named revision checkpoints"
    >
      <h3>Revision checkpoints</h3>
      <p>
        Name the current revision so you can find it later. Labels and notes
        stay in this project. Removing a label keeps its revision and deck file.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label>
          Checkpoint name
          <input
            aria-label="Checkpoint name"
            value={name}
            maxLength={80}
            disabled={locked}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Checkpoint note
          <textarea
            aria-label="Checkpoint note"
            value={note}
            maxLength={500}
            rows={2}
            disabled={locked}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="button-row">
          <button
            type="submit"
            className="secondary-button"
            disabled={locked || !catalog || !name.trim()}
          >
            Save current checkpoint
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={locked}
            onClick={() => void reload()}
          >
            Reload checkpoints
          </button>
        </div>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      {!busy && catalog && !catalog.items.length ? (
        <p>No named checkpoints yet.</p>
      ) : null}
      {catalog?.items.map((item) => (
        <article key={item.revision_id}>
          <h4>
            {item.name}{" "}
            <span>
              Revision {item.revision_number}
              {item.revision_id === revisionId ? " (current)" : ""}
            </span>
          </h4>
          {item.note ? (
            <p style={{ whiteSpace: "pre-wrap" }}>{item.note}</p>
          ) : null}
          <div className="button-row">
            <button
              type="button"
              className="secondary-button"
              disabled={locked || item.revision_id === revisionId}
              onClick={() => void onRestore(item.revision_id)}
            >
              Restore checkpoint {item.name}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={locked}
              onClick={() => void remove(item)}
            >
              Remove checkpoint label {item.name}
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
