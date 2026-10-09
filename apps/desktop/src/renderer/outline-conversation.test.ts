import { describe, expect, it } from "vitest";
import {
  activeOutlineTurn,
  appendOutlineTurn,
  editOutlineTurn,
  emptyOutlineConversation,
  MAX_OUTLINE_TURNS,
  outlineChanges,
  selectOutlineTurn,
  type OutlineProposal,
  type OutlineRequest,
} from "./outline-conversation";
const request = (count = 1): OutlineRequest => ({
  objective: "Choose a pilot",
  audience: "Leadership",
  briefing: "Measured evidence",
  slide_count: count,
  instruction: "Keep the decision clear",
});
const proposal = (id = 1): OutlineProposal => ({
  title: `Draft ${id}`,
  rationale: "A measured decision",
  slides: [
    {
      title: "Decision",
      bullets: ["Choose a pilot"],
      notes: "Explain the tradeoff",
      evidence_ids: [`evidence-${id}`],
    },
  ],
  provider_run_id: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`,
  provider_id: "fixture",
  model_id: "fixture-model",
  requires_user_review: true,
  evidence: [
    {
      evidence_id: `evidence-${id}`,
      text: `Source excerpt ${id}`,
      source_type: "document",
      source_locator: { page: id },
    },
  ],
});
describe("outline conversation draft ownership", () => {
  it("snapshots request, original and editable content independently of caller mutation", () => {
    const input = request(),
      response = proposal();
    const state = appendOutlineTurn(
      emptyOutlineConversation(),
      response,
      input,
    );
    input.briefing = "Replaced briefing";
    response.slides[0]!.bullets.push("Injected after response");
    response.evidence[0]!.text = "Replaced source";
    const saved = activeOutlineTurn(state)!;
    expect(saved.request.briefing).toBe("Measured evidence");
    expect(saved.draft.slides[0]!.bullets).toEqual(["Choose a pilot"]);
    expect(saved.original.evidence[0]!.text).toBe("Source excerpt 1");
    expect(saved.original).not.toBe(saved.draft);
  });
  it("restores user-edited wording and exact original run/source provenance after refinement", () => {
    let state = appendOutlineTurn(
      emptyOutlineConversation(),
      proposal(),
      request(),
    );
    state = editOutlineTurn(state, {
      title: "Reviewed decision",
      slides: [
        {
          ...activeOutlineTurn(state)!.draft.slides[0]!,
          notes: "User explanation",
        },
      ],
    });
    state = appendOutlineTurn(state, proposal(2), {
      ...request(),
      audience: "New audience",
      instruction: "Shorten it",
    });
    state = selectOutlineTurn(state, proposal().provider_run_id);
    const restored = activeOutlineTurn(state)!;
    expect(restored.draft.title).toBe("Reviewed decision");
    expect(restored.draft.slides[0]!.notes).toBe("User explanation");
    expect(restored.draft.provider_run_id).toBe(proposal().provider_run_id);
    expect(restored.draft.evidence).toEqual(proposal().evidence);
    expect(restored.request.audience).toBe("Leadership");
    expect(restored.original.title).toBe("Draft 1");
  });
  it("branches from the selected edited draft rather than the last generated result", () => {
    let state = appendOutlineTurn(
      emptyOutlineConversation(),
      proposal(),
      request(),
    );
    state = appendOutlineTurn(state, proposal(2), request());
    state = selectOutlineTurn(state, proposal().provider_run_id);
    state = editOutlineTurn(state, { title: "Older branch edited" });
    state = appendOutlineTurn(state, proposal(3), request());
    const branch = activeOutlineTurn(state)!;
    expect(branch.parentRunId).toBe(proposal().provider_run_id);
    expect(branch.baseline!.title).toBe("Older branch edited");
    expect(state.turns[1]!.draft.title).toBe("Draft 2");
    expect(state.turns).toHaveLength(3);
  });
  it("keeps request baseline immutable when the ancestor is edited later", () => {
    let state = appendOutlineTurn(
      emptyOutlineConversation(),
      proposal(),
      request(),
    );
    state = appendOutlineTurn(state, proposal(2), request());
    state = selectOutlineTurn(state, proposal().provider_run_id);
    state = editOutlineTurn(state, { title: "Later ancestor edit" });
    state = selectOutlineTurn(state, proposal(2).provider_run_id);
    expect(activeOutlineTurn(state)!.baseline!.title).toBe("Draft 1");
  });
  it("edits only the selected draft without sharing supplied slide arrays", () => {
    let state = appendOutlineTurn(
      emptyOutlineConversation(),
      proposal(),
      request(),
    );
    const slides = structuredClone(proposal().slides);
    slides[0]!.notes = "Reviewed notes";
    state = editOutlineTurn(state, { slides });
    slides[0]!.notes = "Later mutation";
    expect(activeOutlineTurn(state)!.draft.slides[0]!.notes).toBe(
      "Reviewed notes",
    );
    expect(activeOutlineTurn(state)!.original.slides[0]!.notes).toBe(
      "Explain the tradeoff",
    );
  });
  it("refuses duplicate runs and unavailable selection without changing history", () => {
    const state = appendOutlineTurn(
      emptyOutlineConversation(),
      proposal(),
      request(),
    );
    expect(() => appendOutlineTurn(state, proposal(), request())).toThrow(
      "reused",
    );
    expect(() =>
      selectOutlineTurn(state, proposal(99).provider_run_id),
    ).toThrow("unavailable");
    expect(state.turns).toHaveLength(1);
    expect(() =>
      appendOutlineTurn(
        { ...state, activeRunId: "missing" },
        proposal(2),
        request(),
      ),
    ).toThrow("unavailable");
  });
  it("enforces a finite history without dropping earlier edited drafts", () => {
    let state = emptyOutlineConversation();
    for (let index = 1; index <= MAX_OUTLINE_TURNS; index++)
      state = appendOutlineTurn(state, proposal(index), request());
    expect(() => appendOutlineTurn(state, proposal(99), request())).toThrow(
      "limit",
    );
    expect(state.turns).toHaveLength(MAX_OUTLINE_TURNS);
    expect(
      activeOutlineTurn(selectOutlineTurn(state, proposal().provider_run_id))!
        .draft,
    ).toEqual(proposal());
  });
  it("compares content, notes, evidence and added/removed slides by position", () => {
    const before = proposal(),
      after = proposal(2);
    after.rationale = "New rationale";
    after.slides[0]!.title = "Updated decision";
    after.slides[0]!.bullets = ["Updated pilot"];
    after.slides[0]!.notes = "Updated explanation";
    after.slides.push({
      title: "Next step",
      bullets: [],
      notes: "",
      evidence_ids: [],
    });
    expect(outlineChanges(before, after).map((change) => change.label)).toEqual(
      [
        "Presentation title",
        "Planning rationale",
        "Slide 1 title",
        "Slide 1 points",
        "Slide 1 speaker notes",
        "Slide 1 evidence references",
        "Slide 2 added",
      ],
    );
    expect(outlineChanges(after, before).at(-1)!.label).toBe("Slide 2 removed");
  });
  it("distinguishes a line break inside a point from two points and ignores provider metadata", () => {
    const before = proposal(),
      after = proposal(2);
    after.title = before.title;
    after.slides = structuredClone(before.slides);
    expect(outlineChanges(before, after)).toEqual([]);
    before.slides[0]!.bullets = ["First\nSecond"];
    after.slides[0]!.bullets = ["First", "Second"];
    expect(outlineChanges(before, after)).toHaveLength(1);
    expect(outlineChanges(before, after)[0]!.before).not.toBe(
      outlineChanges(before, after)[0]!.after,
    );
  });
});
