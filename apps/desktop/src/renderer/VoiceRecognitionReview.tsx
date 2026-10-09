import type { RecognitionReview } from "./voice-recognition-review";

export function VoiceRecognitionReview({
  review,
}: {
  review: RecognitionReview | null;
}) {
  if (!review) return null;
  return (
    <div
      className="pw-voice-recognition-review"
      aria-label="Recognition uncertainty review"
    >
      {review.chunk_count === 0 ? (
        <p>
          No final speech was recognized. Type your intended instruction or
          dictate again.
        </p>
      ) : (
        <>
          <p>
            Recognition confidence unavailable for {review.unavailable_count} of{" "}
            {review.chunk_count} phrases. Check names, numbers, negations and
            intended targets. Adapter scores are not calibrated probabilities.
          </p>
          <details>
            <summary>Review original recognized phrases</summary>
            <ol>
              {review.chunks.map((chunk, index) => (
                <li key={index}>
                  <blockquote>{chunk.text}</blockquote>
                  <span>
                    {chunk.adapter_score === null
                      ? "Confidence unavailable"
                      : `Adapter score: ${chunk.adapter_score.toFixed(2)}`}
                  </span>
                </li>
              ))}
            </ol>
          </details>
          {review.truncated ? (
            <p>
              Showing the first 64 phrases. The editable transcript contains the
              complete request; review the rest there.
            </p>
          ) : null}
          <p className="muted">
            These are the original recognized phrases. Corrections belong in the
            editable transcript.
          </p>
        </>
      )}
    </div>
  );
}
