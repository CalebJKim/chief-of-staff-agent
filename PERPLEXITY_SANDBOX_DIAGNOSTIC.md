# Perplexity sandbox investigation (resolved)

Resolved on 2026-09-29 after signing in with the personal Max account. Settings > Permissions > Local file system access > Enable installed the sandbox successfully. `PerplexitySandboxSvc` is running, Desktop tools is enabled, and a local PowerShell command completed through Perplexity. No ACL or security-policy workaround was needed. The investigation below is historical.

Package: PerplexityAI.PerplexityApp_2026.9.35878.0_arm64__3jh4kjrg4dzr2
Source build: 2026.09.25.1790373502+e486383, Windows ARM64 MSIX

## Reproduction

The user completed sign-in. Settings > Local Inference reports that Local Mode is unavailable because the agent sandbox could not be established; Enable remains disabled. Windows app Repair and uninstall/reinstall did not resolve this, per the user.

Launching app/resources/native/bin/pplx-sandbox-setup.exe directly or using Run as administrator fails before the installer starts. The sandbox service PerplexitySandboxSvc is absent.

## Trace evidence

Process Monitor captured the manual administrator-launch attempt on 2026-09-28 at 21:17:02 local time:
- Process: svchost.exe, PID 13452, confirmed as Application Information (Appinfo).
- Operation: CreateFile on the packaged pplx-sandbox-setup.exe.
- Result: ACCESS DENIED.
- Desired access: Generic Read/Execute.
- Detail: Impersonating TESTPC/testuser.

The file ACL grants ordinary Users read access; its Users execute grant is conditional on WIN://SYSAPPID containing PerplexityAI.PerplexityApp_3jh4kjrg4dzr2. This is consistent with the direct launch failing outside the package identity. It does not, by itself, establish why the app's own sandbox provisioning path fails.

The package manifest declares both runFullTrust and allowElevation. No matching Perplexity denial event was found in the Code Integrity or AppLocker logs checked. Microsoft-signed Process Monitor launched successfully with elevation.

## Requested vendor guidance

Please confirm the supported sandbox provisioning entry point for this ARM64 MSIX. Does this build require a separate signed sandbox installer? Please provide a supported repair procedure or corrected build that provisions PerplexitySandboxSvc from the packaged app.

No package ACLs, Windows security policies, or sandbox requirements were changed. Native Chief of Staff skills are staged; all four in-app demo prompts remain unrun.

Filtered trace: .pplx-state/diagnostics/procmon/sandbox-installer-events.json
The full trace remains local and includes unrelated machine activity; use the filtered events for initial escalation.

## Additional supported path identified

The packaged settings UI exposes Settings > Permissions > Local file system access (description: Access files and run commands on this PC). Its Enable/Repair/Update control invokes the app's sandbox_provision flow. This path has not yet been tested.

Code inspection also shows the Local Inference sandbox Enable control is disabled when capability information is not ready or desktop_tools is blocked by enterprise policy. The Permissions page exposes a "Blocked by your organization" label / "Managed by your organization" tooltip and a "Could not refresh capabilities" error banner for these distinct conditions. These should be checked before treating the disabled button as proof of an installer packaging defect.
