import { expect, it } from "vitest";
import { validOutlineEvidencePage } from "./OutlineEvidenceReview";

function page() {
  const id = "11111111-2222-4333-8444-555555555555";
  return {
    document_id: id,
    revision_id: id,
    offset: 0,
    limit: 20,
    has_receipt: true,
    has_more: false,
    total_points: 1,
    requires_user_review: true,
    citation_only_slides: [],
    items: [
      {
        original_slide_number: 1,
        point_number: 1,
        slide_id: id,
        slide_number: 3,
        object_id: id,
        quote: "Reviewed point",
        source_kind: "native_text" as const,
        span_status: "unchanged",
        reviewable: true,
        references: [
          {
            evidence_id: id,
            original_excerpt: "Originally supplied excerpt",
            original_excerpt_truncated: false,
            original_source_type: "markdown",
            excerpt_comparison: "excerpt_changed",
            source_status: "available",
            can_link: true,
            current_evidence: {
              chunk_id: id,
              text: "Current source excerpt",
              name: "Pilot.md",
              sha256: "a".repeat(64),
              relation: "context",
            },
          },
        ],
      },
    ],
  };
}

it("allows changed current evidence only as an unsaved context suggestion", () => {
  const packet = page();
  expect(validOutlineEvidencePage(packet)).toBe(true);
  packet.items[0]!.references[0]!.current_evidence.relation = "supports";
  expect(validOutlineEvidencePage(packet)).toBe(false);
});

it("rejects changed native points that incorrectly claim reviewability", () => {
  const packet = page();
  packet.items[0]!.span_status = "changed";
  expect(validOutlineEvidencePage(packet)).toBe(false);
  packet.items[0]!.reviewable = false;
  expect(validOutlineEvidencePage(packet)).toBe(true);
});

it("rejects duplicate reference identities, oversized text and unavailable link authority", () => {
  const duplicate = page();
  duplicate.items[0]!.references.push(duplicate.items[0]!.references[0]!);
  expect(validOutlineEvidencePage(duplicate)).toBe(false);
  const oversized = page();
  oversized.items[0]!.references[0]!.current_evidence.text = "x".repeat(8001);
  expect(validOutlineEvidencePage(oversized)).toBe(false);
  const missing = page();
  missing.items[0]!.references[0]!.source_status = "planning_record_missing";
  expect(validOutlineEvidencePage(missing)).toBe(false);
});
