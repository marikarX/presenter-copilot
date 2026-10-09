import { PptxEditorSession, type SourceHandle } from "pptx-glimpse";

const MAX_SLIDE_SVG_CHARS = 8 * 1024 * 1024;
const MAX_TEXT_TARGET_CHARS = 2_000;

type Request =
  | { id: number; type: "open"; buffer: ArrayBuffer }
  | { id: number; type: "render"; slideNumber: number }
  | {
      id: number;
      type: "mock-text";
      slideNumber: number;
      handle: SourceHandle;
      text: string;
    };

type TextTarget = {
  key: string;
  shapeNodeId: string;
  handle?: SourceHandle;
  label: string;
  text: string;
};

type Response =
  | { id: number; ok: true; type: "opened"; slideCount: number }
  | {
      id: number;
      ok: true;
      type: "slide";
      slideNumber: number;
      svg: string;
      textTargets: TextTarget[];
    }
  | {
      id: number;
      ok: true;
      type: "mock-text";
      slideNumber: number;
      svg: string;
    }
  | { id: number; ok: false; message: string };

let sourceBytes: Uint8Array | null = null;
let session: PptxEditorSession | null = null;
let queue = Promise.resolve();

function response(message: Response): void {
  self.postMessage(message);
}

function findSlideSvg(editor: PptxEditorSession, slideNumber: number): string {
  const slide = editor.slides.find((item) => item.slideNumber === slideNumber);
  if (!slide || slide.svg.length > MAX_SLIDE_SVG_CHARS) {
    throw new Error("Preview slide is unavailable.");
  }
  return slide.svg;
}

function textTargetsForSlide(
  editor: PptxEditorSession,
  slideNumber: number,
): TextTarget[] {
  const targets = editor.shapes(slideNumber).flatMap((shape) => {
    const paragraphs = shape.textBody?.paragraphs ?? [];
    if (paragraphs.length < 1 || paragraphs.length > 128) return [];
    const text = paragraphs
      .map((paragraph) => paragraph.runs.map((run) => run.text).join(""))
      .join("\n");
    const singleRun =
      paragraphs.length === 1 && paragraphs[0]?.runs.length === 1
        ? paragraphs[0].runs[0]
        : undefined;
    const shapeNodeId = shape.handle?.nodeId;
    if (
      !shapeNodeId ||
      (singleRun !== undefined && !singleRun.handle) ||
      text.length > MAX_TEXT_TARGET_CHARS ||
      !text.trim()
    ) {
      return [];
    }
    const description = shape.name?.trim() || "Text box";
    const excerpt = text.replace(/\s+/g, " ").trim().slice(0, 90);
    return [
      {
        key: singleRun?.handle
          ? JSON.stringify(singleRun.handle)
          : String(shapeNodeId),
        shapeNodeId: String(shapeNodeId),
        ...(singleRun?.handle ? { handle: singleRun.handle } : {}),
        label: `${description}: ${excerpt}`,
        text,
      },
    ];
  });
  return targets.slice(0, 100);
}

async function handle(message: Request): Promise<void> {
  try {
    if (message.type === "open") {
      sourceBytes = new Uint8Array(message.buffer);
      session = await PptxEditorSession.create(sourceBytes, {
        textOutput: "path",
        logLevel: "off",
      });
      response({
        id: message.id,
        ok: true,
        type: "opened",
        slideCount: session.slides.length,
      });
      return;
    }

    if (!session || !sourceBytes) {
      throw new Error("Preview is closed.");
    }
    if (
      !Number.isSafeInteger(message.slideNumber) ||
      message.slideNumber < 1 ||
      message.slideNumber > session.slides.length
    ) {
      throw new Error("Slide is unavailable.");
    }

    if (message.type === "render") {
      response({
        id: message.id,
        ok: true,
        type: "slide",
        slideNumber: message.slideNumber,
        svg: findSlideSvg(session, message.slideNumber),
        textTargets: textTargetsForSlide(session, message.slideNumber),
      });
      return;
    }

    if (message.text.length > 2_000) {
      throw new Error(
        "Replacement text must be no longer than 2,000 characters.",
      );
    }
    const mockSession = await PptxEditorSession.create(sourceBytes.slice(), {
      textOutput: "path",
      logLevel: "off",
    });
    const result = await mockSession.apply({
      kind: "replaceTextRunPlainText",
      handle: message.handle,
      text: message.text,
    });
    const slide = result.slides.find(
      (item) => item.slideNumber === message.slideNumber,
    );
    if (!slide || slide.svg.length > MAX_SLIDE_SVG_CHARS) {
      throw new Error("Mock preview is unavailable.");
    }
    response({
      id: message.id,
      ok: true,
      type: "mock-text",
      slideNumber: message.slideNumber,
      svg: slide.svg,
    });
  } catch {
    response({
      id: message.id,
      ok: false,
      message:
        "This slide could not be rendered in the preview. The imported PPTX remains unchanged.",
    });
  }
}

self.addEventListener("message", (event: MessageEvent<Request>) => {
  queue = queue.then(() => handle(event.data));
});
