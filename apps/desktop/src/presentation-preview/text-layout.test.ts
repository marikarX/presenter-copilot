import { describe, expect, it } from "vitest";
import { applyPowerPointWordWrapping } from "./text-layout";

describe("PowerPoint word wrapping", () => {
  it("prevents the renderer from splitting a word at the text-box edge", () => {
    const paragraph = {
      textContent: "A title with its last word near the text-box edge",
      style: { overflowWrap: "anywhere", lineBreak: "anywhere", wordBreak: "" },
    };
    const unchanged = {
      style: { overflowWrap: "normal", lineBreak: "normal", wordBreak: "" },
    };
    const root = {
      querySelectorAll: (selector: string) => {
        expect(selector).toBe("[style]");
        return [paragraph, unchanged];
      },
    };

    applyPowerPointWordWrapping(root as unknown as ParentNode);

    expect(paragraph.style.overflowWrap).toBe("normal");
    expect(paragraph.style.lineBreak).toBe("normal");
    expect(unchanged.style).toEqual({
      overflowWrap: "normal",
      lineBreak: "normal",
      wordBreak: "",
    });
  });

  it("leaves vertical-text word-break behavior unchanged", () => {
    const paragraph = {
      style: {
        overflowWrap: "anywhere",
        lineBreak: "anywhere",
        wordBreak: "keep-all",
      },
    };
    const root = {
      querySelectorAll: () => [paragraph],
    };

    applyPowerPointWordWrapping(root as unknown as ParentNode);

    expect(paragraph.style).toEqual({
      overflowWrap: "normal",
      lineBreak: "anywhere",
      wordBreak: "keep-all",
    });
  });

  it("keeps unrestricted breaks for East Asian text", () => {
    const paragraph = {
      textContent: "タイトルの折り返し",
      style: { overflowWrap: "anywhere", lineBreak: "anywhere", wordBreak: "" },
    };
    const root = { querySelectorAll: () => [paragraph] };

    applyPowerPointWordWrapping(root as unknown as ParentNode);

    expect(paragraph.style).toEqual({
      overflowWrap: "normal",
      lineBreak: "anywhere",
      wordBreak: "",
    });
  });
});
