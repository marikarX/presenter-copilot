import type { NativeClaimSourceKind } from "./claim-source";

export type ClaimReviewEvidence = {
  chunk_id: string;
  text: string;
  name: string;
  sha256: string;
  ordinal?: number | null;
  relation?: string;
  status?: string;
};

export type ClaimReviewSelection = {
  object_id: string;
  quote: string;
  source_kind?: NativeClaimSourceKind;
  initial_evidence?: ClaimReviewEvidence[];
  selection_token?: number;
};
