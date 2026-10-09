import {
  unwrapInvokeResult,
  type PresentationPreviewRenderResult,
} from "../shared/protocol";

export type PreviewSlide = { slide_id: string; ordinal: number };
export type EditPlanIdentity = {
  plan_id: string;
  sha256: string;
  byte_size: number;
};
type Scope = { project_id: string; document_id: string };

export async function openEditPlanPreview(
  scope: Scope,
  plan: EditPlanIdentity,
): Promise<PreviewSlide[]> {
  let sessionId: string | null = null;
  try {
    const reader = unwrapInvokeResult<{
      session_id: string;
      sha256: string;
      byte_size: number;
      chunk_bytes: number;
      plan_id: string;
      is_edit_plan_preview: boolean;
      fidelity_report: { slides: PreviewSlide[] };
    }>(
      await window.presenterCopilot.core.request(
        "presentation.workspace.open_edit_plan_preview",
        { ...scope, plan_id: plan.plan_id },
      ),
    );
    sessionId = reader.session_id;
    if (
      reader.plan_id !== plan.plan_id ||
      reader.is_edit_plan_preview !== true ||
      reader.sha256 !== plan.sha256 ||
      reader.byte_size !== plan.byte_size ||
      !Number.isSafeInteger(reader.byte_size) ||
      reader.byte_size < 1 ||
      reader.byte_size > 50 * 1024 * 1024 ||
      !Number.isSafeInteger(reader.chunk_bytes) ||
      reader.chunk_bytes < 1 ||
      reader.chunk_bytes > 512 * 1024
    )
      throw new Error("The proposed package could not be verified.");
    const bytes = new Uint8Array(reader.byte_size);
    let offset = 0;
    while (offset < bytes.length) {
      const chunk = unwrapInvokeResult<{
        offset: number;
        bytes_b64: string;
        complete: boolean;
      }>(
        await window.presenterCopilot.core.request(
          "presentation.workspace.read_source",
          {
            ...scope,
            session_id: sessionId,
            offset,
            max_bytes: reader.chunk_bytes,
          },
        ),
      );
      const decoded = Uint8Array.from(atob(chunk.bytes_b64), (character) =>
        character.charCodeAt(0),
      );
      if (
        chunk.offset !== offset ||
        !decoded.length ||
        offset + decoded.length > bytes.length ||
        chunk.complete !== (offset + decoded.length === bytes.length)
      )
        throw new Error("The proposed preview stream changed.");
      bytes.set(decoded, offset);
      offset += decoded.length;
    }
    sessionId = null;
    const digest = await crypto.subtle.digest("SHA-256", bytes.buffer);
    if (
      Array.from(new Uint8Array(digest), (value) =>
        value.toString(16).padStart(2, "0"),
      ).join("") !== plan.sha256
    )
      throw new Error("The proposed package changed during preview.");
    const opened = unwrapInvokeResult<{ slide_count: number }>(
      await window.presenterCopilot.presentationPreview.open(bytes.buffer),
    );
    const slides = reader.fidelity_report?.slides;
    if (
      !Array.isArray(slides) ||
      !slides.length ||
      opened.slide_count !== slides.length ||
      slides.some(
        (slide, index) =>
          typeof slide.slide_id !== "string" ||
          slide.slide_id.length !== 36 ||
          slide.ordinal !== index + 1,
      )
    )
      throw new Error("The proposed slide order could not be verified.");
    return slides;
  } finally {
    if (sessionId)
      await window.presenterCopilot.core
        .request("presentation.workspace.close_source", {
          ...scope,
          session_id: sessionId,
        })
        .catch(() => undefined);
  }
}

export async function renderEditPlanSlide(
  slideNumber: number,
): Promise<Uint8Array> {
  const result = unwrapInvokeResult<PresentationPreviewRenderResult>(
    await window.presenterCopilot.presentationPreview.render(slideNumber),
  );
  const signature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (
    result.slide_number !== slideNumber ||
    !Number.isSafeInteger(result.width) ||
    !Number.isSafeInteger(result.height) ||
    result.width < 1 ||
    result.height < 1 ||
    result.width > 4096 ||
    result.height > 4096 ||
    !(result.image instanceof Uint8Array) ||
    result.image.byteLength < 8 ||
    result.image.byteLength > 32 * 1024 * 1024 ||
    signature.some((value, index) => result.image[index] !== value)
  )
    throw new Error("The proposed slide could not be rendered.");
  return result.image;
}
