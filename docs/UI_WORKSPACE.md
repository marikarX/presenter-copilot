# Desktop workspace redesign

The interface follows the supplied desktop reference: a soft sidebar, quiet
chrome, white workspace, restrained color, and a focused view for each task.
Home introduces the workflow and opens existing projects. Project creation
asks only for a name before moving directly to source import.

## Interaction and dependency boundaries

- View navigation changes presentation state, not core session ownership.
  Hidden panels retain drafts and subscriptions. The existing Run/Live Assist
  mutual exclusion and project-switch restrictions remain in force.
- Returning to audio views refreshes devices and ASR readiness; it does not
  reset session or HUD state. Setup refreshes model and credential metadata.
- The walkthrough records only a versioned dismissal marker. It cannot grant
  transcript consent, change project privacy, prepare models, or start capture.
- Transcript disclosure still precedes the native main-process picker. Its
  dialog now provides native keyboard focus containment and Escape dismissal.
- Core methods, preload authority, provider routing, persisted project schemas,
  and the separate HUD renderer are unchanged. Main-process changes are limited
  to initial window dimensions and background color.
- Cloud setup uses the existing detected-environment/Windows Credential Manager
  path. There is no renderer secret-entry form or new provider integration.

## Validation

Run `pnpm check`, `pnpm build`, and `pnpm test:ui` on Windows. The UI test uses
the pinned Playwright driver with the repository's Electron binary and real
Python core. It creates disposable core and Electron profiles, does not use
the user's projects, and makes no microphone recording or model download.

The UI scenarios cover fresh-profile walkthrough, dismissal/restart, native
dialog interaction, real project creation, transcript-consent cancellation,
synthetic Markdown import/preview (only native picker selection is substituted),
mode navigation, draft retention, minimum-window layout, sidebar collapse,
and full Electron restart. The test explicitly selects the main window because
the separate hidden HUD can register with the driver first.

Screenshots and the scenario report are generated under the gitignored
`.local/ui-validation/` directory. Physical microphone quality, global hotkey
use, and independent capture protection are not proved by these UI tests.
The release baseline's physical HUD retest remains applicable after this
redesign.
