import { useEffect, useState } from "react";
import { unwrapInvokeResult } from "../shared/protocol";

export type BackgroundReplacement =
  | { replacement_gradient: { start: string; end: string; angle: number } }
  | { replacement_picture_asset_id: string };

type ProjectPicture = { asset_id: string; name: string };

/** Gradient and picture backgrounds; solid colors stay in the color control. */
export function BackgroundFills({
  projectId,
  gradient,
  disabled,
  onApply,
}: {
  projectId: string;
  gradient: { start: string; end: string; angle: number } | null;
  disabled: boolean;
  onApply: (replacement: BackgroundReplacement) => void;
}) {
  const [start, setStart] = useState(gradient?.start ?? "#0B1F33");
  const [end, setEnd] = useState(gradient?.end ?? "#3A7BD5");
  const [angle, setAngle] = useState(String(gradient?.angle ?? 90));
  const [pictures, setPictures] = useState<ProjectPicture[]>([]);
  const [picture, setPicture] = useState("");
  useEffect(() => {
    setStart(gradient?.start ?? "#0B1F33");
    setEnd(gradient?.end ?? "#3A7BD5");
    setAngle(String(gradient?.angle ?? 90));
  }, [gradient?.start, gradient?.end, gradient?.angle]);
  useEffect(() => {
    let cancelled = false;
    window.presenterCopilot.core
      .request<{ assets: ProjectPicture[] }>(
        "presentation.workspace.list_project_pictures",
        {
          project_id: projectId,
          cursor: 0,
        },
      )
      .then((reply) => {
        const result = unwrapInvokeResult(reply);
        if (!cancelled && Array.isArray(result.assets))
          setPictures(
            result.assets.filter(
              (asset) =>
                /^[a-f0-9]{64}$/.test(asset.asset_id) &&
                typeof asset.name === "string",
            ),
          );
      })
      .catch(() => {
        if (!cancelled) setPictures([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);
  const degrees = Number(angle);
  const validAngle = Number.isInteger(degrees) && degrees >= 0 && degrees < 360;
  const same =
    gradient !== null &&
    gradient.start === start.toUpperCase() &&
    gradient.end === end.toUpperCase() &&
    gradient.angle === degrees;
  return (
    <>
      <div className="pw-shape-color-control">
        <label>
          Gradient from
          <input
            type="color"
            aria-label="Background gradient start color"
            value={start}
            onChange={(event) => setStart(event.target.value.toUpperCase())}
            disabled={disabled}
          />
        </label>
        <label>
          to
          <input
            type="color"
            aria-label="Background gradient end color"
            value={end}
            onChange={(event) => setEnd(event.target.value.toUpperCase())}
            disabled={disabled}
          />
        </label>
        <label>
          Angle
          <input
            type="number"
            min={0}
            max={359}
            aria-label="Background gradient angle"
            value={angle}
            onChange={(event) => setAngle(event.target.value)}
            disabled={disabled}
          />
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || !validAngle || same}
          onClick={() =>
            onApply({
              replacement_gradient: {
                start: start.toUpperCase(),
                end: end.toUpperCase(),
                angle: degrees,
              },
            })
          }
        >
          Apply gradient
        </button>
      </div>
      <div className="pw-shape-color-control">
        <label>
          Picture
          <select
            aria-label="Background picture"
            value={picture}
            onChange={(event) => setPicture(event.target.value)}
            disabled={disabled || !pictures.length}
          >
            <option value="">
              {pictures.length
                ? "Choose a project picture…"
                : "Add pictures to the project library first"}
            </option>
            {pictures.map((item) => (
              <option key={item.asset_id} value={item.asset_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={disabled || !picture}
          onClick={() => onApply({ replacement_picture_asset_id: picture })}
        >
          Apply picture
        </button>
      </div>
    </>
  );
}
