# Hermes native runtime

The skill bundles `scripts/cos-actions.exe` (Windows ARM64, static CRT). The Rust
source is in `native/`; build with `setup/native/build-native.ps1` from the repository
root. A Windows x64 teammate must build with `-Target x86_64-pc-windows-msvc`.
No Rust installation or Python runtime is required to run the installed skill.

Hermes calls Bash launchers: `run-actions.sh`, `daily_brief.sh`, and
`run-second-brain.sh`. Each sources `runtime.sh` in the same process, selects the
active profile via `HERMES_HOME` (or explicit `COS_STATE_DIR`), then runs the helper.
Initialization only reads paths; it does not rewrite config or launch Python.
`run-actions.sh --batch` initializes once and runs an `action ...` block sequentially.
`gmail threads ID...` uses Gmail HTTP batching internally, preserving result order.

The profile supplies Google credentials and `second-brain.json`. Existing SOUL,
model, memory, scheduler settings, and vault connection remain profile-owned.
The default Windows profile is `%LOCALAPPDATA%/hermes/profiles/chief-of-staff`.
Runtime snapshots are stored under the profile's `chief-of-staff` folder.

The installer archives old skills under `retired-skills`, outside skill discovery.
Python source under repository `compat/` supports development/parity and demo setup;
it is not copied into the installed skill. Google data is not changed by installation.
