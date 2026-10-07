# Perplexity native runtime

The documented PowerShell launchers execute the bundled `scripts/cos-actions.exe`.
No Python interpreter, Python packages, or Rust installation is needed at runtime.
The distributed executable targets Windows ARM64. Other architectures require a
matching build; native document previews use Windows PDF and imaging APIs.

`run-actions.ps1` provides the existing Google Workspace command interface and
`-Batch { action ... }`. `run-second-brain.ps1` searches or reads local notes.
`daily_brief.ps1` collects evidence and builds the packet in one native process;
`-Fixture` runs offline. Command names, documented flags, JSON fields, confirmation
requirements, and recipient checks retain the Python backend's contracts.

Pass `-WorkspaceRoot` with the absolute selected workspace, which must directly
contain `CoS_SecondBrain`. Each launcher initializes and executes in the same call.
`runtime.ps1` sets `COS_STATE_DIR` to `<workspace>/.chief-of-staff-state`, creates
`second-brain.json` for that vault, and copies credentials from the installed
`runtime/state` only when the workspace copy is absent. Token refresh, snapshots,
packets, and previews use the writable workspace; no vault or evidence is bundled.
An explicit workspace takes precedence over the legacy `COS_WORKSPACE_ROOT` override.

The installed skill is read-only. Perplexity still controls access and execution;
the native runtime does not bypass permission denials. OAuth uses silent refresh,
and errors do not trigger automatic reconnects or script restarts.

Developers can rebuild with `setup/perplexity/build-native.ps1` in the source repo.
Source is in `native/`; the installer ships the executable rather than build tools
or source. The retired Python implementation is retained in the repository's
`compat/python-runtime`, outside the skill, for parity tests and the demo reset's
credential helper. Setup and reset utilities remain Python; the skill does not.

`runtime/` contains private credentials and must never be shared. Source changes
must be installed explicitly; they do not automatically update an installed skill.
