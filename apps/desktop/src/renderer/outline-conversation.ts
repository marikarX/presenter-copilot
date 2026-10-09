export type PlannedSlide = {
  title: string;
  bullets: string[];
  notes: string;
  evidence_ids: string[];
};
export type OutlineProposal = {
  title: string;
  rationale: string;
  slides: PlannedSlide[];
  provider_run_id: string;
  provider_id: string;
  model_id: string;
  requires_user_review: true;
  evidence: Array<{
    evidence_id: string;
    text: string;
    source_type: string | null;
    source_locator: unknown;
  }>;
};
export type OutlineRequest = {
  objective: string;
  audience: string;
  briefing: string;
  slide_count: number;
  instruction: string;
};
export type OutlineTurn = {
  ordinal: number;
  request: OutlineRequest;
  parentRunId: string | null;
  baseline: OutlineProposal | null;
  original: OutlineProposal;
  draft: OutlineProposal;
};
export type OutlineConversation = {
  turns: OutlineTurn[];
  activeRunId: string | null;
};
export const MAX_OUTLINE_TURNS = 10;
export const emptyOutlineConversation = (): OutlineConversation => ({
  turns: [],
  activeRunId: null,
});
export function activeOutlineTurn(conversation: OutlineConversation) {
  return (
    conversation.turns.find(
      (turn) => turn.original.provider_run_id === conversation.activeRunId,
    ) ?? null
  );
}

/** A completed response appends a turn; it never erases an edited ancestor. */
export function appendOutlineTurn(
  conversation: OutlineConversation,
  response: OutlineProposal,
  request: OutlineRequest,
): OutlineConversation {
  if (conversation.turns.length >= MAX_OUTLINE_TURNS)
    throw new Error("This conversation has reached its draft limit.");
  if (
    conversation.turns.some(
      (turn) => turn.original.provider_run_id === response.provider_run_id,
    )
  )
    throw new Error("The outline response reused an earlier provider run.");
  const parent = activeOutlineTurn(conversation);
  if (conversation.activeRunId && !parent)
    throw new Error("The selected outline draft is unavailable.");
  const turn: OutlineTurn = {
    ordinal: conversation.turns.length + 1,
    request: structuredClone(request),
    parentRunId: parent?.original.provider_run_id ?? null,
    baseline: parent ? structuredClone(parent.draft) : null,
    original: structuredClone(response),
    draft: structuredClone(response),
  };
  return {
    turns: [...conversation.turns, turn],
    activeRunId: response.provider_run_id,
  };
}

export function selectOutlineTurn(
  conversation: OutlineConversation,
  runId: string,
): OutlineConversation {
  if (
    !conversation.turns.some((turn) => turn.original.provider_run_id === runId)
  )
    throw new Error("The selected outline draft is unavailable.");
  return { ...conversation, activeRunId: runId };
}

/** User-editable content changes without changing run/evidence provenance. */
export function editOutlineTurn(
  conversation: OutlineConversation,
  update: Partial<Pick<OutlineProposal, "title" | "slides">>,
): OutlineConversation {
  return {
    ...conversation,
    turns: conversation.turns.map((turn) =>
      turn.original.provider_run_id === conversation.activeRunId
        ? {
            ...turn,
            draft: {
              ...turn.draft,
              title: update.title ?? turn.draft.title,
              slides: update.slides
                ? structuredClone(update.slides)
                : turn.draft.slides,
            },
          }
        : turn,
    ),
  };
}

export type OutlineChange = {
  label: string;
  before: string;
  after: string;
};
const lines = (values: string[]) =>
  values.map((value, index) => `${index + 1}. ${value}`).join("\n");

/** Position-based comparison, without claiming stable planned-slide identities. */
export function outlineChanges(
  before: OutlineProposal,
  after: OutlineProposal,
): OutlineChange[] {
  const changes: OutlineChange[] = [];
  const add = (label: string, left: string, right: string) => {
    if (left !== right) changes.push({ label, before: left, after: right });
  };
  add("Presentation title", before.title, after.title);
  add("Planning rationale", before.rationale, after.rationale);
  for (
    let index = 0;
    index < Math.max(before.slides.length, after.slides.length);
    index++
  ) {
    const left = before.slides[index],
      right = after.slides[index];
    const label = `Slide ${index + 1}`;
    if (!left || !right) {
      const render = (slide: PlannedSlide | undefined) =>
        slide
          ? [
              slide.title,
              lines(slide.bullets),
              slide.notes,
              lines(slide.evidence_ids),
            ]
              .filter(Boolean)
              .join("\n\n")
          : "";
      changes.push({
        label: `${label} ${left ? "removed" : "added"}`,
        before: render(left),
        after: render(right),
      });
      continue;
    }
    add(`${label} title`, left.title, right.title);
    add(`${label} points`, lines(left.bullets), lines(right.bullets));
    add(`${label} speaker notes`, left.notes, right.notes);
    add(
      `${label} evidence references`,
      lines(left.evidence_ids),
      lines(right.evidence_ids),
    );
  }
  return changes;
}
