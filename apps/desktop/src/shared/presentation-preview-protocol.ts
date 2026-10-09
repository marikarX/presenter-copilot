export type PresentationPreviewHostRequest =
  | { id: string; type: "open"; buffer: ArrayBuffer }
  | {
      id: string;
      type: "render";
      slide_number: number;
      mock_text?: { shape_node_id: string; text: string };
    }
  | { id: string; type: "release-frame" };

export interface PresentationPreviewHostTextCandidate {
  shape_node_id: string;
  name: string;
  text: string;
}

export type PresentationPreviewHostResponse =
  | {
      id: string;
      ok: true;
      type: "opened";
      slide_count: number;
      slide_width: number;
      slide_height: number;
      font_substitutions: string[];
      unresolved_font_families: string[];
      font_check_limited: boolean;
    }
  | {
      id: string;
      ok: true;
      type: "slide";
      slide_number: number;
      text_candidates: PresentationPreviewHostTextCandidate[];
      mock_text_overflows_shape?: boolean | null;
    }
  | { id: string; ok: true; type: "released" }
  | { id: string; ok: false };

export interface PresentationPreviewHostApi {
  ready(): void;
  onRequest(
    listener: (request: PresentationPreviewHostRequest) => void,
  ): () => void;
  respond(response: PresentationPreviewHostResponse): void;
}

declare global {
  interface Window {
    presentationPreviewHost: PresentationPreviewHostApi;
  }
}
