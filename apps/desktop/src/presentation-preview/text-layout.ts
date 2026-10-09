/** Keep browser text breaking aligned with PowerPoint's word-level wrapping. */
export function applyPowerPointWordWrapping(root: ParentNode): void {
  const styledElements = root.querySelectorAll<HTMLElement>("[style]");
  for (const element of styledElements) {
    const text = element.textContent ?? "";
    if (element.style.overflowWrap === "anywhere") {
      element.style.overflowWrap = "normal";
    }
    if (
      element.style.lineBreak === "anywhere" &&
      element.style.wordBreak !== "keep-all" &&
      /[\p{L}\p{N}]\s+[\p{L}\p{N}]/u.test(text) &&
      !/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(
        text,
      )
    ) {
      element.style.lineBreak = "normal";
    }
  }
}
