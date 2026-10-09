import { useEffect, useRef, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";

export type Asset = {
  asset_id: string;
  name: string;
  mime_type: string;
  byte_size: number;
  sha256: string;
  width: number;
  height: number;
  thumbnail_base64: string;
};
export function DeckPictureAssets({
  projectId,
  documentId,
  revisionId,
  disabled,
  onUse,
  onAttach,
  onBusyChange,
  source = "deck",
}: {
  projectId: string;
  documentId: string;
  revisionId: string;
  disabled: boolean;
  onUse?: (file: File) => Promise<void>;
  onAttach?: (asset: Asset) => void;
  onBusyChange: (busy: boolean) => void;
  source?: "deck" | "project";
}) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [cursor, setCursor] = useState<number | null>(0);
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  const [removeId, setRemoveId] = useState("");
  const projectMode = source === "project";
  const scope = projectMode
    ? { project_id: projectId }
    : {
        project_id: projectId,
        document_id: documentId,
        expected_revision_id: revisionId,
      };
  async function load(next = 0) {
    setBusy(true);
    setError(null);
    try {
      const result = unwrapInvokeResult<{
        revision_id: string;
        project_id: string;
        assets: Asset[];
        skipped: number;
        has_more: boolean;
        next_cursor: number | null;
      }>(
        await window.presenterCopilot.core.request(
          projectMode
            ? "presentation.workspace.list_project_pictures"
            : "presentation.workspace.list_picture_assets",
          { ...scope, cursor: next },
        ),
      );
      if (
        (projectMode
          ? result.project_id !== projectId
          : result.revision_id !== revisionId) ||
        !Array.isArray(result.assets) ||
        result.assets.length > 20 ||
        !Number.isSafeInteger(result.skipped) ||
        result.skipped < 0 ||
        typeof result.has_more !== "boolean" ||
        (result.has_more &&
          (!Number.isSafeInteger(result.next_cursor) ||
            result.next_cursor! <= next)) ||
        result.assets.some(
          (asset) =>
            !/^[a-f0-9]{64}$/.test(asset.asset_id) ||
            !/^[a-f0-9]{64}$/.test(asset.sha256) ||
            !["image/png", "image/jpeg"].includes(asset.mime_type) ||
            typeof asset.name !== "string" ||
            typeof asset.thumbnail_base64 !== "string" ||
            asset.thumbnail_base64.length > 128 * 1024 ||
            !Number.isSafeInteger(asset.byte_size) ||
            asset.byte_size < 1 ||
            asset.byte_size > 4 * 1024 * 1024,
        )
      )
        throw new Error("The deck picture inventory could not be verified.");
      if (!alive.current) return;
      setAssets(result.assets);
      setCursor(result.has_more ? result.next_cursor : null);
      setSkipped(result.skipped);
      setOpened(true);
    } catch (caught) {
      if (alive.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "Deck pictures could not be loaded.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function use(asset: Asset) {
    if (onAttach) {
      onAttach(asset);
      return;
    }
    if (!onUse) return;
    setBusy(true);
    setError(null);
    try {
      const result = unwrapInvokeResult<
        Asset & {
          revision_id: string;
          project_id: string;
          image_base64: string;
        }
      >(
        await window.presenterCopilot.core.request(
          projectMode
            ? "presentation.workspace.read_project_picture"
            : "presentation.workspace.read_picture_asset",
          { ...scope, asset_id: asset.asset_id },
        ),
      );
      if (
        (projectMode
          ? result.project_id !== projectId
          : result.revision_id !== revisionId) ||
        result.asset_id !== asset.asset_id ||
        result.sha256 !== asset.sha256 ||
        result.byte_size !== asset.byte_size ||
        result.mime_type !== asset.mime_type ||
        typeof result.image_base64 !== "string" ||
        result.image_base64.length > 6 * 1024 * 1024
      )
        throw new Error("The selected picture changed. Reload deck pictures.");
      const bytes = Uint8Array.from(atob(result.image_base64), (c) =>
        c.charCodeAt(0),
      );
      const hash = await crypto.subtle.digest("SHA-256", bytes.buffer);
      if (
        bytes.length !== asset.byte_size ||
        Array.from(new Uint8Array(hash), (v) =>
          v.toString(16).padStart(2, "0"),
        ).join("") !== asset.sha256
      )
        throw new Error("The selected picture bytes could not be verified.");
      if (!alive.current) return;
      await onUse(
        new File([bytes.buffer], asset.name, { type: asset.mime_type }),
      );
    } catch (caught) {
      if (alive.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "The picture could not be selected.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      if (
        !file.size ||
        file.size > 4 * 1024 * 1024 ||
        !["image/png", "image/jpeg"].includes(file.type)
      )
        throw new Error("Choose a PNG or JPEG no larger than 4 MiB.");
      const encoded = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () =>
          typeof reader.result === "string"
            ? resolve(reader.result.split(",")[1] ?? "")
            : reject(new Error("The picture could not be read."));
        reader.onerror = () =>
          reject(new Error("The picture could not be read."));
        reader.readAsDataURL(file);
      });
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.import_project_picture",
          {
            project_id: projectId,
            name: file.name.slice(0, 120),
            image_base64: encoded,
          },
        ),
      );
      if (alive.current) await load();
    } catch (caught) {
      if (alive.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "The picture could not be imported.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function remove(asset: Asset) {
    setBusy(true);
    setError(null);
    try {
      unwrapInvokeResult(
        await window.presenterCopilot.core.request(
          "presentation.workspace.delete_project_picture",
          {
            project_id: projectId,
            asset_id: asset.asset_id,
            expected_sha256: asset.sha256,
            confirm: true,
          },
        ),
      );
      if (alive.current) {
        setRemoveId("");
        await load();
      }
    } catch (caught) {
      if (alive.current)
        setError(
          caught instanceof Error
            ? caught.message
            : "The picture could not be removed.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <fieldset className="pw-deck-assets">
      <legend>
        {projectMode ? "Project pictures" : "Reuse a deck picture"}
      </legend>
      <p className="muted">
        {projectMode
          ? "Reusable uploads belong to this project and stay available across decks and revisions. Removing a library item leaves existing decks unchanged."
          : "Browse embedded PNG and JPEG images in this revision, including master/layout assets."}{" "}
        {onAttach
          ? "Attach pictures to the edit request. The provider receives names and dimensions; image bytes stay in Core."
          : "Choosing one fills Add a picture; insertion is a separate action."}
      </p>
      {projectMode ? (
        <label>
          Upload project picture
          <input
            type="file"
            accept="image/png,image/jpeg"
            aria-label="Upload project picture"
            disabled={disabled || busy}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file) void upload(file);
            }}
          />
        </label>
      ) : null}
      <button
        type="button"
        className="secondary-button"
        disabled={disabled || busy}
        onClick={() => void load()}
      >
        {busy
          ? "Reading pictures…"
          : projectMode
            ? "Browse project pictures"
            : "Browse deck pictures"}
      </button>
      {opened ? (
        <>
          {!assets.length ? (
            <p>No reusable PNG or JPEG pictures on this page.</p>
          ) : (
            <div className="pw-deck-asset-grid">
              {assets.map((asset) => (
                <article key={asset.asset_id}>
                  <img
                    src={`data:image/png;base64,${asset.thumbnail_base64}`}
                    alt={`Deck picture ${asset.name}`}
                  />
                  <span>
                    {asset.name} · {asset.width} × {asset.height}
                  </span>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={disabled || busy}
                    onClick={() => void use(asset)}
                  >
                    {onAttach ? "Attach" : "Use"} {asset.name}
                  </button>
                  {projectMode ? (
                    <div>
                      {removeId === asset.asset_id ? (
                        <>
                          <p>
                            Remove {asset.name} from this project library? Saved
                            decks and staged previews keep their copies.
                          </p>
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={disabled || busy}
                            onClick={() => void remove(asset)}
                          >
                            Confirm remove {asset.name}
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={busy}
                            onClick={() => setRemoveId("")}
                          >
                            Keep picture
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={disabled || busy}
                          onClick={() => setRemoveId(asset.asset_id)}
                        >
                          Remove library item {asset.name}
                        </button>
                      )}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          )}
          {skipped ? (
            <p className="muted">
              Skipped {skipped} unsupported, invalid or oversized media entries
              on this page.
            </p>
          ) : null}
          {cursor !== null ? (
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || busy}
              onClick={() => void load(cursor)}
            >
              Next pictures
            </button>
          ) : null}
        </>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </fieldset>
  );
}
