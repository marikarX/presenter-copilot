import { useState } from "react";
import { Modal } from "./Modal";
import { WorkspaceIcon } from "./WorkspaceIcon";

const steps = [
  {
    icon: "spark",
    label: "Meet your copilot",
    title: "Your ideas. Your voice.\nA little more confidence.",
    copy: "A calm place to prepare your presentation, practice the difficult questions, and find your next thought when it matters.",
    detail: "Prepare → Teach → Rehearse → Present",
  },
  {
    icon: "folder",
    label: "Bring your context",
    title: "Start with what\nyou already know.",
    copy: "Create a project and add your deck, notes, or supporting documents. Every source stays connected to the facts it supports.",
    detail: "PPTX, PDF, Markdown, text, and authorized transcripts",
  },
  {
    icon: "shield",
    label: "Choose your boundaries",
    title: "Local first.\nCloud only by choice.",
    copy: "New projects start in Local Only. Optional cloud reasoning requires a configured provider, a project privacy choice, and acknowledgement. Audio stays local.",
    detail: "Model downloads happen only when you choose Prepare model.",
  },
  {
    icon: "message",
    label: "Make it sound like you",
    title: "Teach it your thinking.\nThen test your answers.",
    copy: "Use Teach to save your explanations. Add audience roles and use Challenge to rehearse their questions. You decide what becomes a preferred answer or part of your Speaker Profile.",
    detail: "You can build your Speaker Profile later.",
  },
  {
    icon: "wave",
    label: "Find your rhythm",
    title: "Rehearse in peace.\nPresent with support.",
    copy: "Prepare speech recognition in Setup, then select your microphone in Run. Try a short rehearsal and check the transcript. Live Assist adds a small cue window near your camera.",
    detail:
      "Live Assist capture protection is best effort. Review its status before presenting.",
  },
] as const;

export function Walkthrough({
  onClose,
  onSetup,
}: {
  onClose: () => void;
  onSetup: () => void;
}) {
  const [step, setStep] = useState(0);
  const current = steps[step] ?? steps[0];
  return (
    <Modal
      titleId="walkthrough-title"
      onClose={onClose}
      className="walkthrough"
    >
      <div className="tour-top">
        <span>
          GETTING STARTED · {step + 1} OF {steps.length}
        </span>
        <button
          className="icon-button"
          aria-label="Close walkthrough"
          onClick={onClose}
        >
          <WorkspaceIcon name="close" />
        </button>
      </div>
      <div className={`tour-art tour-art-${step}`} aria-hidden="true">
        <div className="tour-orbit">
          <WorkspaceIcon name={current.icon} size={48} />
        </div>
        <span className="tour-art-note">{current.label}</span>
      </div>
      <div className="tour-body" aria-live="polite" aria-atomic="true">
        <h2 id="walkthrough-title">{current.title}</h2>
        <p>{current.copy}</p>
        <div className="tour-detail">{current.detail}</div>
      </div>
      <div
        className="tour-progress"
        aria-label={`Step ${step + 1} of ${steps.length}`}
      >
        {steps.map((item, index) => (
          <button
            key={item.label}
            aria-label={`Go to step ${index + 1}: ${item.label}`}
            aria-current={index === step ? "step" : undefined}
            onClick={() => setStep(index)}
          />
        ))}
      </div>
      <div className="tour-footer">
        <button
          className="text-button"
          onClick={step ? () => setStep(step - 1) : onClose}
        >
          {step ? "Back" : "Explore on my own"}
        </button>
        <button
          className="primary-button"
          onClick={
            step === steps.length - 1 ? onSetup : () => setStep(step + 1)
          }
        >
          {step === steps.length - 1 ? "Open setup" : "Continue"}
          <WorkspaceIcon name="arrow" size={16} />
        </button>
      </div>
      <p className="tour-restart">
        Always available from “Restart walkthrough” in the sidebar.
      </p>
    </Modal>
  );
}
