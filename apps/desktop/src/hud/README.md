# Live Assist HUD

This module renders the Milestone 7 transparent, click-through HUD. It receives
only bounded status, cue, and provenance projections through the dedicated HUD
preload bridge. Audio, retrieval, provider calls, persistence, and shortcut
authority remain in the Python core or Electron main process.

Automatic question segmentation is intentionally not part of this milestone;
the presenter explicitly pushes to assist.
