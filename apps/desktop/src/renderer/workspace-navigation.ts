export const projectViews = [
  {
    id: "overview",
    label: "Overview",
    icon: "grid",
    description: "A little preparation. A lot more confidence.",
  },
  {
    id: "sources",
    label: "Sources",
    icon: "folder",
    description:
      "Bring your presentation and its supporting evidence together.",
  },
  {
    id: "audience",
    label: "Audience",
    icon: "people",
    description: "Prepare for the people and questions in the room.",
  },
  {
    id: "teach",
    label: "Teach",
    icon: "spark",
    description: "Give your copilot the context only you know.",
  },
  {
    id: "challenge",
    label: "Challenge",
    icon: "message",
    description: "Practice the hard questions before they happen.",
  },
  {
    id: "run",
    label: "Run",
    icon: "play",
    description: "Rehearse at your own pace. Reflect when you finish.",
  },
  {
    id: "live",
    label: "Live Assist",
    icon: "wave",
    description: "Short, source-grounded cues when you need them.",
  },
  {
    id: "project-settings",
    label: "Project settings",
    icon: "settings",
    description: "Your presentation, your voice, your privacy choices.",
  },
] as const;

export type ProjectView = (typeof projectViews)[number]["id"];
export type WorkspaceView = ProjectView | "home" | "setup";

// Navigation is presentation state only. Recording ownership stays in core.
export function canNavigate(
  view: WorkspaceView,
  runActive: boolean,
  liveActive: boolean,
  teachVoiceActive = false,
): boolean {
  return (
    (!runActive && !liveActive && !teachVoiceActive) ||
    (runActive && view === "run") ||
    (liveActive && view === "live") ||
    (teachVoiceActive && view === "teach")
  );
}

export const walkthroughKey = "presenter-copilot.walkthrough.v1";
export function needsWalkthrough(storage: Pick<Storage, "getItem">): boolean {
  try {
    return storage.getItem(walkthroughKey) !== "seen";
  } catch {
    return true;
  }
}
export function rememberWalkthrough(
  storage: Pick<Storage, "setItem">,
): boolean {
  try {
    storage.setItem(walkthroughKey, "seen");
    return true;
  } catch {
    return false;
  }
}
