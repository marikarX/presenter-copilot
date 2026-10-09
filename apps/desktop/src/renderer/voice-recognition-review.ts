export type RecognitionReview = {
  version: 1;
  chunk_count: number;
  unavailable_count: number;
  truncated: boolean;
  chunks: { text: string; adapter_score: number | null }[];
};

export function parseRecognitionReview(
  value: unknown,
  transcript: string,
): RecognitionReview {
  const review = value as RecognitionReview | undefined;
  if (
    !review ||
    review.version !== 1 ||
    !Number.isInteger(review.chunk_count) ||
    review.chunk_count < 0 ||
    review.chunk_count > 16000 ||
    !Number.isInteger(review.unavailable_count) ||
    review.unavailable_count < 0 ||
    review.unavailable_count > review.chunk_count ||
    !Array.isArray(review.chunks) ||
    review.chunks.length !== Math.min(64, review.chunk_count) ||
    review.truncated !== review.chunk_count > 64 ||
    review.chunks.some(
      (chunk) =>
        !chunk ||
        typeof chunk.text !== "string" ||
        !chunk.text.trim() ||
        chunk.text !== chunk.text.trim() ||
        chunk.text.length > 16000 ||
        (chunk.adapter_score !== null &&
          (typeof chunk.adapter_score !== "number" ||
            !Number.isFinite(chunk.adapter_score) ||
            chunk.adapter_score < 0 ||
            chunk.adapter_score > 1)),
    )
  )
    throw new Error(
      "The original recognition review could not be verified. Dictate again or type your request.",
    );
  const original = review.chunks.map((chunk) => chunk.text).join(" ");
  const unknown = review.chunks.filter(
    (chunk) => chunk.adapter_score === null,
  ).length;
  if (
    (!review.truncated &&
      (original !== transcript || unknown !== review.unavailable_count)) ||
    (review.truncated &&
      (!transcript.startsWith(original + " ") ||
        unknown > review.unavailable_count ||
        review.unavailable_count - unknown >
          review.chunk_count - review.chunks.length))
  )
    throw new Error(
      "Recognition phrases no longer match the original transcript.",
    );
  return review;
}

export function clarifiedVoiceInstruction(
  transcript: string,
  clarification: string,
): string {
  const text = transcript.trim(),
    target = clarification.trim();
  return text && target ? `${text}\nTarget clarification: ${target}` : text;
}
