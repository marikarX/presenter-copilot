export type AccessibilityIssue = {
  issue: "missing_alt_text" | "missing_slide_title";
  slide_id: string;
  slide_number: number;
  object_id: string | null;
  name: string | null;
  object_type: string | null;
};

export type AccessibilityResult = {
  revision_id: string;
  issues: AccessibilityIssue[];
  truncated: boolean;
  slide_count: number;
};

export function isAccessibilityResult(
  value: unknown,
): value is AccessibilityResult {
  if (!value || typeof value !== "object") return false;
  const result = value as Partial<AccessibilityResult>;
  return (
    typeof result.revision_id === "string" &&
    typeof result.truncated === "boolean" &&
    Number.isSafeInteger(result.slide_count) &&
    Array.isArray(result.issues) &&
    result.issues.every(
      (item) =>
        !!item &&
        (item.issue === "missing_alt_text" ||
          item.issue === "missing_slide_title") &&
        Number.isSafeInteger(item.slide_number) &&
        (item.object_id === null || typeof item.object_id === "string"),
    )
  );
}

/** PowerPoint-style accessibility errors with a jump to each object or slide. */
export function AccessibilityCheck({
  result,
  current,
  disabled,
  onCheck,
  onGo,
}: {
  result: AccessibilityResult | null;
  current: boolean;
  disabled: boolean;
  onCheck: () => void;
  onGo: (issue: AccessibilityIssue) => void;
}) {
  const missingAlt =
    result?.issues.filter((item) => item.issue === "missing_alt_text") ?? [];
  const missingTitles =
    result?.issues.filter((item) => item.issue === "missing_slide_title") ?? [];
  return (
    <fieldset className="pw-picture-crop">
      <legend>Accessibility</legend>
      <p className="muted">
        Finds pictures, charts, diagrams and groups without alt text, and slides
        without a title.
      </p>
      <button
        type="button"
        className="secondary-button"
        onClick={onCheck}
        disabled={disabled}
      >
        {result ? "Check again" : "Check accessibility"}
      </button>
      {result ? (
        <>
          <p role="status">
            {result.issues.length === 0
              ? `No issues found on ${result.slide_count} slides.`
              : `${missingAlt.length} missing alt text · ${missingTitles.length} slides without a title${result.truncated ? " (first 500 shown)" : ""}`}
            {current ? "" : " · results are from an earlier revision"}
          </p>
          {result.issues.length ? (
            <ul className="pw-accessibility-list">
              {result.issues.map((item) => (
                <li key={`${item.issue}-${item.slide_id}-${item.object_id}`}>
                  <span>
                    Slide {item.slide_number}:{" "}
                    {item.issue === "missing_alt_text"
                      ? `${item.name ?? "Object"} (${item.object_type ?? "object"}) has no alt text`
                      : "no slide title"}
                  </span>
                  <button
                    type="button"
                    className="secondary-button"
                    aria-label={
                      item.issue === "missing_alt_text"
                        ? `Go to ${item.name ?? "object"} on slide ${item.slide_number}`
                        : `Go to slide ${item.slide_number}`
                    }
                    onClick={() => onGo(item)}
                    disabled={disabled}
                  >
                    Go to
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </fieldset>
  );
}
