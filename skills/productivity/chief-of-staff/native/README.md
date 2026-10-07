# Native Chief of Staff runtime

This is the complete Rust replacement for the seven formerly bundled Python
modules. The installed skill contains the release executable and PowerShell
launchers; this source and the retired Python reference are development assets.

| Previous module | Native implementation |
|---|---|
| actions.py | main.rs, cli.rs, drafts.rs, mutations.rs |
| workspace_formatting.py | formatting.rs, preview.rs |
| ingest.py | ingest.rs |
| brief.py | brief.rs |
| daily_brief.py | workflows.rs: daily-brief |
| second_brain.py | brain.rs |
| verify.py | workflows.rs: verify |

The CLI preserves the existing Google Workspace command names, flags, aliases,
JSON fields, and write guards. Standalone workflow commands are now subcommands
of the executable. User-facing instructions continue to call the same PowerShell
launchers. Error/help wording and MIME transport headers can differ; email body,
recipient validation, threading headers, and draft-only behavior are preserved.
There is no Python fallback. `commands.json` records the original argument schema;
`instructions.json` preserves the packet's original instruction strings.

Build from the repository root using `setup/perplexity/build-native.ps1`. This
requires Rust and MSVC build tools with LLVM/Clang and the Windows SDK. The default
target is Windows ARM64; a matching compiler/toolchain can build Windows x64 using
`-Target x86_64-pc-windows-msvc`. The CRT is linked statically. End users need no
compiler or interpreter. PDF previews use Windows PDF/imaging APIs and do not
require PyMuPDF; other operating systems need a renderer before distribution.

Verification:

- `cargo test --manifest-path skills/productivity/chief-of-staff/native/Cargo.toml`
  exercises mocked Google writes, draft guards, formatting and native PDF rendering.
- `tests/native_parity.py` compares packets, ingestion fixtures, and Second Brain
  results against `compat/python-runtime/scripts`. Set `COS_TEST_EXE` to the binary.
- `tests/generate_native_formatting_fixtures.py` regenerates the Python contract
  fixtures for tabs, nested tables/shapes, Unicode ranges, lists, and hyperlinks.
- `setup/perplexity/test_runtime.py` checks the real PowerShell 5.1 launchers,
  workspace state, batching, Unicode, stdin, and operation without Python.
- `setup/perplexity/test_workspace_install.py` checks deployment and retirement
  of legacy Python code while preserving credentials and evidence boundaries.

Writes in these tests use mocks. They neither send mail nor change live Google
documents. A passing native test does not guarantee Perplexity sandbox permission
for a particular operation; denials must still be reported and respected.
